import csv
import io
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch
from django.contrib.auth.models import User, Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from .models import Campaign, Recipient, Video, AnalyticsEvent
from .services import normalize_video, parse_csv

@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class WorkflowTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('staff', password='a-long-test-password', is_staff=True)
        self.staff.groups.add(Group.objects.get(name='Coordinator'))
        self.campaign = Campaign.objects.create(name='Test Nursing Campaign', cta_text='Learn More', cta_url='https://example.edu/accept', created_by=self.staff)
        self.recipient = Recipient.objects.create(campaign=self.campaign, first_name='Jane')
        self.client.force_login(self.staff)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(VIDEO_ROOT=Path(self.directory.name))
        self.override.enable()
        self.addCleanup(self.override.disable)

    def ready_video(self):
        path = Path(self.directory.name) / 'sample.mp4'
        path.write_bytes(b'0123456789')
        return Video.objects.create(campaign=self.campaign, recipient=self.recipient, stored_filename='sample.mp4', status='ready')

    def test_staff_gate_and_csrf(self):
        self.client.logout()
        for url in ['/', reverse('record', args=[self.campaign.pk]), reverse('upload', args=[self.recipient.pk])]:
            self.assertEqual(self.client.get(url).status_code, 302)
        ordinary = User.objects.create_user('ordinary', password='testing123')
        self.client.force_login(ordinary)
        self.assertEqual(self.client.get('/').status_code, 403)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.staff)
        self.assertEqual(strict.post(reverse('campaign_new'), {}).status_code, 403)
        self.assertEqual(strict.post('/api/event', '{}', content_type='application/json').status_code, 403)

    def test_all_staff_pages_render(self):
        for name in ['campaign', 'campaign_settings', 'campaign_delete', 'recipients', 'import', 'record', 'distribution', 'analytics']:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=[self.campaign.pk])).status_code, 200)
        for name in ['recipient_edit', 'recipient_delete']:
            self.assertEqual(self.client.get(reverse(name, args=[self.recipient.pk])).status_code, 200)
        for url in ['/', '/campaign/new/', '/login/', '/template.csv']:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_csv_preview_validation_and_confirmation(self):
        upload = SimpleUploadedFile('test.csv', b'first_name,email\nAlex,alex@example.ca\n,invalid\nSam,\n')
        url = reverse('import', args=[self.campaign.pk])
        response = self.client.post(url, {'csv': upload})
        self.assertContains(response, '2 valid recipients')
        self.assertContains(response, 'Row 3')
        self.assertEqual(self.campaign.recipients.count(), 1)
        self.client.post(url, {'confirm': '1'})
        self.assertEqual(self.campaign.recipients.count(), 3)
        self.client.post(url, {'confirm': '1'})
        self.assertEqual(self.campaign.recipients.count(), 3)
        tokens = list(self.campaign.recipients.values_list('public_token', flat=True))
        self.assertEqual(len(set(tokens)), 3)
        self.assertTrue(all(len(t) >= 32 for t in tokens))

    def test_csv_malformed_and_minimal(self):
        for content in [b'email\nx@y.ca', b'first_name,first_name\na,b', b'first_name\n"unterminated', b'first_name\n\xff']:
            with self.assertRaises(ValueError):
                parse_csv(SimpleUploadedFile('x.csv', content))
        rows, errors = parse_csv(SimpleUploadedFile('x.csv', b'first_name\nJane\n'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(errors, [])

    def test_token_playback_ranges_and_archive(self):
        self.ready_video()
        self.client.logout()
        url = reverse('media', args=[self.recipient.public_token])
        response = self.client.get(url, HTTP_RANGE='bytes=2-5')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(b''.join(response.streaming_content), b'2345')
        self.assertEqual(response['Content-Range'], 'bytes 2-5/10')
        self.assertEqual(b''.join(self.client.get(url, HTTP_RANGE='bytes=-3').streaming_content), b'789')
        self.assertEqual(self.client.get(url, HTTP_RANGE='bytes=20-30').status_code, 416)
        self.assertEqual(self.client.head(url)['Content-Length'], '10')
        self.assertContains(self.client.get(reverse('public', args=[self.recipient.public_token])), 'Hi Jane,')
        self.assertEqual(self.client.get('/v/invalid').status_code, 404)
        self.assertEqual(self.client.get('/videos/sample.mp4').status_code, 404)
        self.campaign.status = 'archived'; self.campaign.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_analytics_deduplicate_and_aggregate(self):
        self.ready_video()
        browser = Client(enforce_csrf_checks=True)
        browser.get(reverse('public', args=[self.recipient.public_token]))
        csrf = browser.cookies['csrftoken'].value
        session = str(uuid.uuid4())
        for kind, _ in AnalyticsEvent.TYPES:
            for _ in range(2):
                response = browser.post('/api/event', json.dumps({'token': self.recipient.public_token, 'event': kind, 'session': session}), content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
                self.assertEqual(response.status_code, 200)
        self.assertEqual(AnalyticsEvent.objects.count(), 7)
        response = self.client.get(reverse('analytics', args=[self.campaign.pk]))
        self.assertContains(response, '100%')
        self.assertEqual(response.context['rows'][0]['cta'], True)
        self.assertEqual(dict(response.context['metrics'])['Completed'], 1)
        for payload in [{'event': 'nonsense', 'session': session}, {'event':'page_view', 'session':'invalid'}, []]:
            self.assertEqual(self.client.post('/api/event', json.dumps(payload), content_type='application/json').status_code, 400)

    def test_export_ready_only_and_formula_protection(self):
        self.ready_video()
        Recipient.objects.create(campaign=self.campaign, first_name='Missing')
        self.recipient.first_name = '=HYPERLINK("bad")'; self.recipient.save()
        self.campaign.status='ready'; self.campaign.save()
        response = self.client.get(reverse('distribution', args=[self.campaign.pk]) + '?download=1')
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[1][1].startswith("'="))
        self.assertEqual(rows[1][-1], self.recipient.public_url)

    def test_upload_next_replacement_and_failure(self):
        self.ready_video()
        next_r = Recipient.objects.create(campaign=self.campaign, first_name='Alex')
        replacement = Path(self.directory.name) / 'replacement.mp4'
        replacement.write_bytes(b'new')
        with patch('messaging.views.normalize_video', return_value=('replacement.mp4', 2.5)):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse('upload', args=[self.recipient.pk]), {'video': SimpleUploadedFile('recording.webm', b'test')})
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'?recipient={next_r.pk}', response.json()['next_url'])
        self.assertFalse((Path(self.directory.name) / 'sample.mp4').exists())
        self.assertEqual(Video.objects.get(recipient=self.recipient).status, 'ready')
        with patch('messaging.views.normalize_video', side_effect=ValueError):
            response = self.client.post(reverse('upload', args=[self.recipient.pk]), {'video': SimpleUploadedFile('recording.webm', b'test')})
        self.assertEqual(response.status_code, 422)
        self.assertTrue(replacement.exists())
        self.assertEqual(Video.objects.get(recipient=self.recipient).stored_filename, 'replacement.mp4')
        self.assertFalse(list(Path(self.directory.name).glob('*.upload')))

    def test_campaign_deletion_removes_everything(self):
        video = self.ready_video()
        AnalyticsEvent.objects.create(campaign=self.campaign, recipient=self.recipient, video=video, event_type='page_view', session_id=uuid.uuid4())
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('campaign_delete', args=[self.campaign.pk]))
        for model in [Campaign, Recipient, Video, AnalyticsEvent]:
            self.assertEqual(model.objects.count(), 0)
        self.assertFalse((Path(self.directory.name) / 'sample.mp4').exists())

    @skipUnless(shutil.which('ffmpeg'), 'FFmpeg installed in Docker')
    def test_real_ffmpeg_normalization_and_public_playback(self):
        source = Path(self.directory.name) / 'fixture.webm'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=15', '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '1', '-c:v', 'libvpx', '-c:a', 'libopus', str(source)], check=True)
        with source.open('rb') as file:
            response = self.client.post(reverse('upload', args=[self.recipient.pk]), {'video': file})
        self.assertEqual(response.status_code, 200)
        video = Video.objects.get(recipient=self.recipient)
        self.assertEqual(video.status, 'ready')
        path = Path(self.directory.name) / video.stored_filename
        probe = subprocess.run(['ffprobe','-v','error','-show_streams','-of','json',str(path)], capture_output=True, check=True)
        self.assertEqual({s['codec_name'] for s in json.loads(probe.stdout)['streams']}, {'h264','aac'})
        data = path.read_bytes()
        self.assertLess(data.index(b'moov'), data.index(b'mdat'))
        self.client.logout()
        response = self.client.get(reverse('media', args=[self.recipient.public_token]))
        self.assertEqual(b''.join(response.streaming_content), data)

    def test_campaign_script_is_staff_only_and_persists(self):
        url = reverse('save_script', args=[self.campaign.pk])
        script = 'Hello, this is a private staff recording script.\nCongratulations!'
        self.assertEqual(self.client.post(url, {'script': script}).status_code, 200)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.script_text, script)
        self.assertContains(self.client.get(reverse('record', args=[self.campaign.pk])), 'private staff recording script')
        self.assertNotContains(self.client.get(reverse('public', args=[self.recipient.public_token])), 'private staff recording script')
        self.assertEqual(self.client.post(url, {'script': 'x' * 20001}).status_code, 400)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.script_text, script)
        self.assertEqual(self.client.get(url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.staff)
        self.assertEqual(strict.post(url, {'script': 'overwrite'}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(url, {'script': 'overwrite'}).status_code, 302)
        ordinary = User.objects.create_user('script-nonstaff')
        self.client.force_login(ordinary)
        self.assertEqual(self.client.post(url, {'script': 'overwrite'}).status_code, 403)

    def make_recorder(self, username='recorder'):
        user = User.objects.create_user(username, password='recorder-test-password')
        user.groups.add(Group.objects.get(name='Recorder'))
        return user

    def test_recorder_sees_only_assigned_recipients(self):
        recorder = self.make_recorder()
        self.recipient.assigned_to = recorder
        self.recipient.save()
        hidden = Recipient.objects.create(campaign=self.campaign, first_name='HiddenContact')
        self.campaign.script_text = 'Shared campaign reading script'
        self.campaign.save()
        self.client.force_login(recorder)
        response = self.client.get('/')
        self.assertContains(response, 'Jane')
        self.assertNotContains(response, 'HiddenContact')
        response = self.client.get(reverse('record', args=[self.campaign.pk]))
        self.assertContains(response, 'Recipient 1 of 1')
        self.assertContains(response, 'Shared campaign reading script')
        self.assertNotContains(response, 'Edit campaign script')
        self.assertNotContains(response, 'Distribution')
        self.assertNotContains(response, hidden.public_token)
        self.assertEqual(self.client.get(reverse('record', args=[self.campaign.pk]) + f'?recipient={hidden.pk}').status_code, 404)
        self.campaign.status = 'archived'; self.campaign.save()
        self.assertNotContains(self.client.get('/'), 'Jane')
        self.assertEqual(self.client.get(reverse('record', args=[self.campaign.pk])).status_code, 404)

    def test_recorder_cannot_use_management_routes_or_admin(self):
        recorder = self.make_recorder()
        self.client.force_login(recorder)
        for name in ['campaign', 'campaign_settings', 'campaign_delete', 'recipients', 'import', 'distribution', 'analytics', 'save_script', 'assign_recipients']:
            for method in ['get', 'post']:
                with self.subTest(route=name, method=method):
                    self.assertEqual(getattr(self.client, method)(reverse(name, args=[self.campaign.pk])).status_code, 403)
        for name in ['recipient_edit', 'recipient_delete']:
            self.assertEqual(self.client.post(reverse(name, args=[self.recipient.pk])).status_code, 403)
        for name in ['campaign_new', 'csv_template']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        other_campaign = Campaign.objects.create(name='Other', cta_url='https://example.edu', created_by=self.staff)
        self.assertEqual(self.client.get(reverse('record', args=[other_campaign.pk])).status_code, 404)

    def test_assign_reassign_and_unassign_with_campaign_validation(self):
        recorder = self.make_recorder()
        other = self.make_recorder('second-recorder')
        url = reverse('assign_recipients', args=[self.campaign.pk])
        response = self.client.post(url, {'assigned_to': recorder.pk, 'recipients': [self.recipient.pk]})
        self.assertEqual(response.status_code, 302)
        self.recipient.refresh_from_db()
        self.assertEqual(self.recipient.assigned_to, recorder)
        self.client.force_login(recorder)
        self.assertEqual(self.client.get(reverse('record', args=[self.campaign.pk])).status_code, 200)
        self.client.force_login(self.staff)
        self.client.post(url, {'assigned_to': other.pk, 'recipients': [self.recipient.pk]})
        self.client.force_login(recorder)
        self.assertEqual(self.client.get(reverse('record', args=[self.campaign.pk])).status_code, 404)
        with patch('messaging.views.normalize_video') as converter:
            self.assertEqual(self.client.post(reverse('upload', args=[self.recipient.pk]), {'video': SimpleUploadedFile('recording.webm', b'test')}).status_code, 404)
            converter.assert_not_called()
        self.client.force_login(self.staff)
        foreign_campaign = Campaign.objects.create(name='Other', cta_url='https://example.edu', created_by=self.staff)
        foreign = Recipient.objects.create(campaign=foreign_campaign, first_name='Foreign')
        self.assertEqual(self.client.post(url, {'assigned_to': recorder.pk, 'recipients': [self.recipient.pk, foreign.pk]}).status_code, 400)
        self.recipient.refresh_from_db()
        self.assertEqual(self.recipient.assigned_to, other)
        self.assertEqual(self.client.post(url, {'assigned_to': self.staff.pk, 'recipients': [self.recipient.pk]}).status_code, 404)
        self.client.post(url, {'assigned_to': '', 'recipients': [self.recipient.pk]})
        self.recipient.refresh_from_db()
        self.assertIsNone(self.recipient.assigned_to)

    def test_recorder_upload_next_stays_in_assigned_queue(self):
        recorder = self.make_recorder()
        self.recipient.assigned_to = recorder; self.recipient.save()
        hidden = Recipient.objects.create(campaign=self.campaign, first_name='OtherRecorder')
        assigned = Recipient.objects.create(campaign=self.campaign, first_name='Assigned', assigned_to=recorder)
        self.client.force_login(recorder)
        def convert(*args):
            path = Path(self.directory.name) / f'{uuid.uuid4().hex}.mp4'
            path.write_bytes(b'video')
            return path.name, 1
        with patch('messaging.views.normalize_video', side_effect=convert):
            response = self.client.post(reverse('upload', args=[self.recipient.pk]), {'video': SimpleUploadedFile('recording.webm', b'test')})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['next_url'], reverse('record', args=[self.campaign.pk]) + f'?recipient={assigned.pk}')
            response = self.client.post(reverse('upload', args=[assigned.pk]), {'video': SimpleUploadedFile('recording.webm', b'test')})
            self.assertEqual(response.json()['next_url'], '/')
        self.assertFalse(Video.objects.filter(recipient=hidden).exists())

    def test_coordinator_cannot_admin_and_unroled_staff_has_no_access(self):
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        self.assertNotContains(self.client.get('/'), 'href="/admin/"')
        self.staff.groups.clear()
        self.assertEqual(self.client.get('/').status_code, 403)
        self.staff.is_superuser = True; self.staff.save()
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/admin/').status_code, 200)

    def test_admin_creates_and_changes_roles(self):
        self.staff.is_superuser = True; self.staff.save()
        response = self.client.post('/admin/auth/user/add/', {'username': 'new-recorder', 'role': 'recorder', 'usable_password': 'true', 'password1': 'Test-role-password-72!', 'password2': 'Test-role-password-72!'})
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='new-recorder')
        from .access import role_for
        self.assertEqual(role_for(user), 'recorder')
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        response = self.client.post(f'/admin/auth/user/{user.pk}/change/', {'username': user.username, 'role': 'coordinator', 'is_active': 'on', 'date_joined_0': '2026-09-18', 'date_joined_1': '00:00:00'})
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(role_for(user), 'coordinator')
        self.assertFalse(user.groups.filter(name='Recorder').exists())
