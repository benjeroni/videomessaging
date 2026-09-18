"""Role/assignment browser acceptance test against a disposable prototype.
Uses the same SMOKE_CREDENTIALS/SMOKE_BASE_URL settings as browser_smoke.py.
"""
import json
import os
import re
import secrets
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from browser_support import browser_base

root = Path(__file__).resolve().parent.parent
credentials = json.loads(Path(os.getenv('SMOKE_CREDENTIALS', str(root / '.local-admin.json'))).read_text())
base = browser_base()
password = secrets.token_urlsafe(24)
suffix = secrets.token_hex(4)
with sync_playwright() as p:
    browser = p.chromium.launch(args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--no-sandbox'])
    errors = []
    def sign_in(username, password):
        context = browser.new_context(permissions=['camera','microphone'])
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base + '/login/')
        page.locator('#id_username').fill(username)
        page.locator('#id_password').fill(password)
        page.get_by_role('button', name='Sign in', exact=True).click()
        expect(page).to_have_url(base + '/')
        return page
    admin = sign_in(credentials['username'], credentials['password'])
    user_ids = []
    for role in ['coordinator', 'recorder']:
        admin.goto(base + '/admin/auth/user/add/')
        admin.locator('#id_username').fill(f'{role}-{suffix}')
        admin.locator('#id_role').select_option(role)
        admin.locator('#id_password1').fill(password)
        admin.locator('#id_password2').fill(password)
        admin.get_by_role('button', name='Save', exact=True).click()
        expect(admin).to_have_url(re.compile(r'/admin/auth/user/\d+/change/'))
        user_ids.append(re.search(r'/user/(\d+)/', admin.url).group(1))
    coordinator = sign_in(f'coordinator-{suffix}', password)
    expect(coordinator.get_by_role('link', name='Admin', exact=True)).to_have_count(0)
    coordinator.get_by_role('link', name='New campaign').click()
    coordinator.get_by_label('Name:', exact=True).fill(f'Role acceptance {suffix}')
    coordinator.get_by_label('Cta url:').fill('https://example.edu')
    coordinator.get_by_label('Script text:').fill('Congratulations!\n\n' * 40)
    coordinator.get_by_role('button', name='Save changes').click()
    campaign_url = coordinator.url
    coordinator.get_by_role('link', name='Import recipients').click()
    coordinator.get_by_label('Recipient CSV').set_input_files({'name':'test.csv','mimeType':'text/csv','buffer':b'first_name\nAssignedPerson\nHiddenPerson\n'})
    coordinator.get_by_role('button', name='Validate & preview').click()
    coordinator.get_by_role('button', name='Import 2 valid recipients').click()
    coordinator.get_by_label('Select AssignedPerson', exact=True).check()
    coordinator.get_by_label('Assigned recorder', exact=True).select_option(user_ids[1])
    coordinator.get_by_role('button', name='Apply assignment').click()
    recorder = sign_in(f'recorder-{suffix}', password)
    expect(recorder.get_by_role('heading', name='My recordings')).to_be_visible()
    expect(recorder.get_by_text('AssignedPerson', exact=True)).to_be_visible()
    expect(recorder.get_by_text('HiddenPerson', exact=True)).to_have_count(0)
    recorder.get_by_role('link', name='Record', exact=True).click()
    queue_url = recorder.url
    expect(recorder.get_by_text('Recipient 1 of 1', exact=True)).to_be_visible()
    expect(recorder.get_by_text('Edit campaign script', exact=True)).to_have_count(0)
    recorder.get_by_role('button', name='Enable camera & microphone').click()
    recorder.get_by_role('button', name='Start recording', exact=True).click()
    recorder.wait_for_timeout(1500)
    assert recorder.locator('#script-display').evaluate('(e) => e.scrollTop') > 0
    recorder.get_by_role('button', name='Stop recording', exact=True).click()
    recorder.get_by_role('button', name='Save & Next', exact=True).click()
    expect(recorder.get_by_role('heading', name='My recordings')).to_be_visible(timeout=60000)
    expect(recorder.get_by_role('cell', name='Recorded', exact=True)).to_be_visible()
    assert recorder.goto(campaign_url + 'settings/').status == 403
    coordinator.goto(campaign_url + 'recipients/')
    coordinator.get_by_label('Select AssignedPerson', exact=True).check()
    coordinator.get_by_label('Assigned recorder', exact=True).select_option('')
    coordinator.get_by_role('button', name='Apply assignment').click()
    assert recorder.goto(queue_url).status == 404
    recorder.goto(base + '/')
    expect(recorder.get_by_text('No recipients are currently assigned to you.', exact=False)).to_be_visible()
    coordinator.goto(campaign_url)
    coordinator.get_by_role('link', name='Delete test campaign').click()
    coordinator.get_by_role('button', name='Permanently delete').click()
    for user_id in user_ids:
        admin.goto(base + f'/admin/auth/user/{user_id}/delete/')
        admin.locator('input[type=submit]').click()
    assert not errors, errors
    browser.close()
print('PASS: admin role creation, coordinator campaign/script/import/assignment, recorder-only queue and upload, unassignment revocation, and cleanup.')
