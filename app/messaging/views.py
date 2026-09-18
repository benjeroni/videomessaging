import csv
import json
import logging
import re
import tempfile
import uuid
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST, require_safe
from .forms import CampaignForm, RecipientForm
from .models import Campaign, Recipient, Video, AnalyticsEvent
from .services import COLUMNS, csv_safe, normalize_video, parse_csv
from .access import manager, workspace_user, can_manage, recordable_recipients, available_recorders
log = logging.getLogger('operations')

@workspace_user
def dashboard(request):
    if not can_manage(request.user):
        assigned = recordable_recipients(request.user).exclude(campaign__status='archived').select_related('campaign', 'video')
        return render(request, 'assignments.html', {'assignments': assigned})
    campaigns = Campaign.objects.annotate(total=Count('recipients'), recorded=Count('recipients', filter=Q(recipients__video__status='ready'))).order_by('-created_at')
    return render(request, 'dashboard.html', {'campaigns': campaigns})

@manager
def campaign_form(request, pk=None):
    campaign = get_object_or_404(Campaign, pk=pk) if pk else None
    form = CampaignForm(request.POST or None, instance=campaign)
    if request.method == 'POST' and form.is_valid():
        campaign = form.save(commit=False)
        if not campaign.pk:
            campaign.created_by = request.user
        campaign.save()
        log.info('campaign_saved campaign_id=%s user_id=%s', campaign.pk, request.user.pk)
        return redirect('campaign', pk=campaign.pk)
    return render(request, 'form.html', {'form': form, 'campaign': campaign, 'title': 'Campaign settings' if pk else 'New campaign'})

@manager
def campaign_detail(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    return render(request, 'campaign.html', {'campaign': campaign, 'total': campaign.recipients.count(), 'recorded': campaign.recipients.filter(video__status='ready').count()})

@manager
def campaign_delete(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    if request.method == 'POST':
        campaign.delete()
        messages.success(request, 'Campaign, recipients, videos and analytics deleted.')
        return redirect('dashboard')
    return render(request, 'delete.html', {'title': f'Delete {campaign.name}?', 'detail': 'This permanently removes all recipients, video files and analytics.'})

@manager
def recipients(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    rows = campaign.recipients.select_related('video', 'assigned_to').prefetch_related('events')
    query = request.GET.get('q', '')
    if query:
        rows = rows.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(program__icontains=query) | Q(email__icontains=query) | Q(external_id__icontains=query))
    return render(request, 'recipients.html', {'campaign': campaign, 'rows': recipient_stats(rows), 'query': query, 'recorders': available_recorders()})

def recipient_stats(rows):
    result = []
    for recipient in rows:
        events = {e.event_type for e in recipient.events.all()}
        watched = max([n for event, n in [('video_25', 25), ('video_50', 50), ('video_75', 75), ('video_complete', 100)] if event in events], default=0)
        result.append({'recipient': recipient, 'viewed': 'page_view' in events, 'started': 'video_play' in events, 'cta': 'cta_click' in events, 'watched': watched})
    return result

@manager
def recipient_edit(request, pk):
    recipient = get_object_or_404(Recipient, pk=pk)
    form = RecipientForm(request.POST or None, instance=recipient)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('recipients', pk=recipient.campaign_id)
    return render(request, 'form.html', {'form': form, 'title': 'Edit recipient', 'campaign': recipient.campaign})

@manager
def recipient_delete(request, pk):
    recipient = get_object_or_404(Recipient, pk=pk)
    if request.method == 'POST':
        campaign_id = recipient.campaign_id
        recipient.delete()
        return redirect('recipients', pk=campaign_id)
    return render(request, 'delete.html', {'title': f'Delete {recipient}?', 'detail': 'Their video, link and analytics will be permanently removed.'})

@manager
def csv_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="recipient-template.csv"'
    csv.writer(response).writerow(COLUMNS)
    return response

@manager
def import_csv(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    key = f'import_{pk}'
    preview, errors = [], []
    if request.method == 'POST':
        if request.POST.get('confirm'):
            # Pop from server-side session; repeated confirmation cannot reimport.
            preview = request.session.pop(key, [])
            with transaction.atomic():
                for row in preview:
                    Recipient.objects.create(campaign=campaign, **row)
            log.info('csv_import campaign_id=%s count=%s', pk, len(preview))
            messages.success(request, f'Imported {len(preview)} recipients.')
            return redirect('recipients', pk=pk)
        request.session.pop(key, None)
        try:
            if 'csv' not in request.FILES:
                raise ValueError('Choose a CSV file.')
            preview, errors = parse_csv(request.FILES['csv'])
            request.session[key] = preview
        except ValueError as exc:
            errors = [str(exc)]
    return render(request, 'import.html', {'campaign': campaign, 'preview': preview, 'errors': errors})

@workspace_user
def record(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    rows = list(recordable_recipients(request.user).filter(campaign=campaign).select_related('video'))
    if not can_manage(request.user) and (not rows or campaign.status == 'archived'):
        raise Http404
    selected = request.GET.get('recipient')
    index = next((i for i, r in enumerate(rows) if str(r.pk) == selected), None)
    if selected and index is None:
        raise Http404
    if index is None:
        index = next((i for i, r in enumerate(rows) if not hasattr(r, 'video') or r.video.status != 'ready'), 0)
    recipient = rows[index] if rows else None
    unrecorded = next((r for r in rows[index + 1:] + rows[:index] if not hasattr(r, 'video') or r.video.status != 'ready'), None)
    return render(request, 'record.html', {'campaign': campaign, 'recipient': recipient, 'position': index + 1, 'total': len(rows), 'previous': rows[index - 1] if index else None, 'following': rows[index + 1] if index + 1 < len(rows) else None, 'unrecorded': unrecorded, 'max_seconds': settings.MAX_VIDEO_SECONDS})

@workspace_user
@require_POST
def upload(request, pk):
    recipient = get_object_or_404(recordable_recipients(request.user), pk=pk)
    if recipient.campaign.status == 'archived':
        return JsonResponse({'error': 'Unarchive this campaign before recording.'}, status=400)
    recording = request.FILES.get('video')
    if not recording or recording.size > settings.MAX_UPLOAD_BYTES or recording.size == 0:
        return JsonResponse({'error': f'Choose a nonempty recording under {settings.MAX_UPLOAD_BYTES // 1048576} MB.'}, status=400)
    output = None
    try:
        # Synchronous processing is deliberate for this small prototype. Lock the
        # recipient so replacement/deletion cannot orphan files during processing.
        with transaction.atomic():
            recipient = get_object_or_404(recordable_recipients(request.user).select_for_update(), pk=pk)
            if recipient.campaign.status == 'archived':
                raise PermissionDenied
            video, _ = Video.objects.get_or_create(recipient=recipient, defaults={'campaign': recipient.campaign})
            old_file = video.stored_filename
            video.status = 'processing'
            video.save()
            settings.VIDEO_ROOT.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=settings.VIDEO_ROOT, suffix='.upload') as source:
                for chunk in recording.chunks():
                    source.write(chunk)
                source.flush()
                output, duration = normalize_video(source.name, recipient.campaign_id)
            video.stored_filename = output
            video.original_filename = 'browser-recording'  # no user-supplied PII
            video.duration_seconds = duration
            video.recorded_at = timezone.now()
            video.status = 'ready'
            video.save()
            if old_file:
                transaction.on_commit(lambda: (settings.VIDEO_ROOT / old_file).unlink(missing_ok=True))
            Campaign.objects.filter(pk=recipient.campaign_id, status='draft').update(status='recording')
        log.info('video_saved recipient_id=%s', pk)
        remaining = recordable_recipients(request.user).filter(campaign_id=recipient.campaign_id).exclude(video__status='ready')
        next_recipient = remaining.filter(pk__gt=pk).first() or remaining.first()
        finish_url = reverse('campaign', args=[recipient.campaign_id]) if can_manage(request.user) else reverse('dashboard')
        url = reverse('record', args=[recipient.campaign_id]) + f'?recipient={next_recipient.pk}' if next_recipient else finish_url
        return JsonResponse({'next_url': url})
    except (Http404, PermissionDenied):
        raise
    except Exception:
        if output:
            (settings.VIDEO_ROOT / output).unlink(missing_ok=True)
        Video.objects.get_or_create(recipient=recipient, defaults={'campaign': recipient.campaign, 'status': 'failed'})
        log.error('video_processing_failed recipient_id=%s', pk)
        return JsonResponse({'error': 'Video processing failed. Your previous saved video is preserved. Retry or re-record a shorter video.'}, status=422)

@manager
def distribution(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    ready = campaign.recipients.filter(video__status='ready')
    if request.GET.get('download') == '1':
        if campaign.status != 'ready':
            messages.error(request, 'Set campaign status to Ready before exporting.')
            return redirect('distribution', pk=pk)
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="distribution.csv"'
        writer = csv.writer(response)
        writer.writerow(['external_id', 'first_name', 'last_name', 'email', 'phone', 'video_url'])
        for r in ready:
            writer.writerow([csv_safe(getattr(r, name)) for name in ['external_id', 'first_name', 'last_name', 'email', 'phone', 'public_url']])
        return response
    return render(request, 'distribution.html', {'campaign': campaign, 'ready': ready.count(), 'missing': campaign.recipients.count() - ready.count()})

@manager
def analytics(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    totals = dict(AnalyticsEvent.objects.filter(campaign=campaign).values('event_type').annotate(total=Count('recipient', distinct=True)).values_list('event_type', 'total'))
    labels = ['Landing pages viewed', 'Videos started', '25% watched', '50% watched', '75% watched', 'Completed', 'CTA clicks']
    metrics = [('Recipients', campaign.recipients.count()), ('Videos recorded', campaign.recipients.filter(video__status='ready').count())] + [(label, totals.get(event, 0)) for (event, _), label in zip(AnalyticsEvent.TYPES, labels)]
    return render(request, 'analytics.html', {'campaign': campaign, 'metrics': metrics, 'rows': recipient_stats(campaign.recipients.select_related('video').prefetch_related('events'))})

def public_recipient(token):
    return get_object_or_404(Recipient.objects.select_related('campaign', 'video').exclude(campaign__status='archived'), public_token=token)

@require_safe
@ensure_csrf_cookie
def public(request, token):
    recipient = public_recipient(token)
    return render(request, 'public.html', {'recipient': recipient, 'campaign': recipient.campaign, 'public_page': True})

@require_safe
def media(request, token):
    recipient = public_recipient(token)
    if not hasattr(recipient, 'video') or recipient.video.status != 'ready':
        raise Http404('Video unavailable')
    path = settings.VIDEO_ROOT / recipient.video.stored_filename
    if not path.is_file():
        raise Http404('Video unavailable')
    size = path.stat().st_size
    start, end, status = 0, size - 1, 200
    header = request.headers.get('Range')
    if header:
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
        if not match or not any(match.groups()):
            return HttpResponse(status=416, headers={'Content-Range': f'bytes */{size}'})
        a, b = match.groups()
        if a:
            start, end = int(a), min(int(b), end) if b else end
        else:
            start = max(0, size - int(b))
        if start > end or start >= size:
            return HttpResponse(status=416, headers={'Content-Range': f'bytes */{size}'})
        status = 206
    def chunks():
        with path.open('rb') as file:
            file.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = file.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
    response = StreamingHttpResponse(chunks() if request.method != 'HEAD' else [], status=status, content_type='video/mp4')
    response['Accept-Ranges'] = 'bytes'
    response['Content-Length'] = end - start + 1
    if status == 206:
        response['Content-Range'] = f'bytes {start}-{end}/{size}'
    return response

@require_POST
def event(request):
    try:
        body = json.loads(request.body)
        event_type = body['event']
        session_id = uuid.UUID(body['session'])
        if event_type not in dict(AnalyticsEvent.TYPES):
            raise ValueError
        recipient = public_recipient(body['token'])
    except (ValueError, KeyError, TypeError, AttributeError):
        return JsonResponse({'error': 'Invalid event.'}, status=400)
    video = getattr(recipient, 'video', None)
    if event_type.startswith('video_') and (not video or video.status != 'ready'):
        return JsonResponse({'error': 'Video unavailable.'}, status=400)
    AnalyticsEvent.objects.get_or_create(recipient=recipient, event_type=event_type, session_id=session_id, defaults={'campaign': recipient.campaign, 'video': video})
    return JsonResponse({'ok': True})


@manager
@require_POST
def save_script(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    script = request.POST.get('script', '')
    if len(script) > 20000:
        return JsonResponse({'error': 'Keep your script under 20,000 characters.'}, status=400)
    campaign.script_text = script
    campaign.save(update_fields=['script_text', 'updated_at'])
    return JsonResponse({'ok': True})


@manager
@require_POST
def assign_recipients(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    recorder_id = request.POST.get('assigned_to', '')
    recorder = get_object_or_404(available_recorders(), pk=recorder_id) if recorder_id.isdecimal() else None
    if recorder_id and recorder is None:
        return HttpResponse('Invalid recorder.', status=400)
    try:
        selected = {int(value) for value in request.POST.getlist('recipients')}
    except ValueError:
        return HttpResponse('Invalid recipient selection.', status=400)
    if not selected:
        messages.error(request, 'Select at least one recipient to assign.')
        return redirect('recipients', pk=pk)
    with transaction.atomic():
        rows = campaign.recipients.select_for_update().filter(pk__in=selected)
        if len(list(rows)) != len(selected):
            return HttpResponse('Recipients must belong to this campaign.', status=400)
        count = campaign.recipients.filter(pk__in=selected).update(assigned_to=recorder)
    log.info('recipients_assigned campaign_id=%s count=%s user_id=%s', pk, count, request.user.pk)
    messages.success(request, f'Updated assignments for {count} recipients.')
    return redirect('recipients', pk=pk)
