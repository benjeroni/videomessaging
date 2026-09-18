"""Optional full workflow smoke test. Uses fake camera/audio and fabricated data.
Requires playwright and its Chromium browser; run against a disposable local app.
Reads .local-admin.json by default (or SMOKE_CREDENTIALS); never prints credentials.
"""
import csv
import io
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from browser_support import browser_base

root = Path(__file__).resolve().parent.parent
credentials = json.loads(Path(os.getenv('SMOKE_CREDENTIALS', str(root / '.local-admin.json'))).read_text())
base = browser_base()
with sync_playwright() as p:
    browser = p.chromium.launch(args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--no-sandbox'])
    context = browser.new_context(permissions=['camera', 'microphone'], viewport={'width':1280,'height':900})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(base + '/login/')
    page.get_by_label('Username:').fill(credentials['username'])
    page.get_by_label('Password:').fill(credentials['password'])
    page.get_by_role('button', name='Sign in').click()
    if '/login/' in page.url:
        raise AssertionError('Login did not complete: ' + page.locator('body').inner_text())
    page.get_by_role('link', name='New campaign').click()
    page.get_by_label('Name:', exact=True).fill('Browser acceptance — fabricated nursing campaign')
    page.get_by_label('Cta text:').fill('Learn More')
    page.get_by_label('Cta url:').fill('https://example.edu/accept')
    page.get_by_label('Landing page message:').fill('We recorded a personal message for you.')
    page.get_by_role('button', name='Save changes').click()
    campaign_url = page.url
    page.get_by_role('link', name='Import recipients').click()
    page.get_by_label('Recipient CSV').set_input_files(root / 'examples/recipients.csv')
    page.get_by_role('button', name='Validate & preview').click()
    page.get_by_role('button', name='Import 10 valid recipients').click()
    page.get_by_role('link', name='Record', exact=True).first.click()
    script = '\n\n'.join(['Congratulations on your nursing offer. We look forward to welcoming you.'] * 20)
    page.get_by_label('Script text', exact=True).fill(script)
    page.get_by_role('button', name='Save script', exact=True).click()
    expect(page.locator('#script-save-status')).to_have_text('Script saved')
    page.locator('#script-speed').fill('60')
    page.locator('#script-size').fill('36')
    expect(page.locator('#script-content')).to_have_css('font-size', '36px')
    page.get_by_role('button', name='Start scrolling', exact=True).click()
    page.wait_for_timeout(400)
    assert page.locator('#script-display').evaluate('(e) => e.scrollTop') > 0
    page.get_by_role('button', name='Pause scrolling', exact=True).click()
    paused_position = page.locator('#script-display').evaluate('(e) => e.scrollTop')
    page.wait_for_timeout(250)
    assert page.locator('#script-display').evaluate('(e) => e.scrollTop') == paused_position
    page.get_by_role('button', name='Back to top', exact=True).click()
    assert page.locator('#script-display').evaluate('(e) => e.scrollTop') == 0
    for index in range(10):
        expect(page.get_by_text(f'Recipient {index+1} of 10', exact=True)).to_be_visible()
        page.get_by_role('button', name='Enable camera & microphone').click()
        try:
            expect(page.get_by_role('button', name='Start recording')).to_be_enabled()
        except AssertionError:
            raise AssertionError(page.locator('#record-status').inner_text())
        page.get_by_role('button', name='Start recording').click()
        page.wait_for_timeout(1400)
        assert page.locator('#script-display').evaluate('(e) => e.scrollTop') > 0
        expect(page.locator('#script-text')).to_have_value(script)
        expect(page.locator('#script-content')).to_have_css('font-size', '36px')
        page.get_by_role('button', name='Stop recording').click()
        expect(page.get_by_role('button', name='Save & Next')).to_be_visible()
        expect(page.get_by_role('button', name='Start scrolling', exact=True)).to_be_visible()
        page.locator('#preview').evaluate('(v) => v.play()')
        page.get_by_role('button', name='Save & Next').click()
        if index < 9:
            expect(page.get_by_text(f'Recipient {index+2} of 10', exact=True)).to_be_visible(timeout=60000)
        else:
            expect(page.get_by_role('link', name='Continue recording')).to_be_visible(timeout=60000)
    page.get_by_role('link', name='Settings', exact=True).click()
    page.get_by_label('Status:').select_option('ready')
    page.get_by_role('button', name='Save changes').click()
    page.get_by_role('link', name='Export distribution').click()
    with page.expect_download() as download:
        page.get_by_role('link', name='Export distribution CSV').click()
    rows = list(csv.DictReader(io.StringIO(Path(download.value.path()).read_text())))
    assert len(rows) == 10
    public_context = browser.new_context(viewport={'width':390,'height':844})
    recipient_page = public_context.new_page()
    recipient_page.on('pageerror', lambda error: errors.append(str(error)))
    recipient_page.goto(rows[0]['video_url'])
    expect(recipient_page.get_by_role('heading', name='Hi Jane,')).to_be_visible()
    recipient_page.locator('video').evaluate('(v) => v.play()')
    recipient_page.wait_for_function('document.querySelector("video").ended')
    with recipient_page.expect_popup() as popup:
        recipient_page.get_by_role('link', name='Learn More').click()
    assert popup.value.url.startswith('https://example.edu/accept')
    recipient_page.screenshot(path='/tmp/video-messaging-public.png', full_page=True)
    page.goto(campaign_url + 'analytics/')
    expect(page.get_by_role('cell', name='100%', exact=True)).to_be_visible()
    jane = page.get_by_role('row').filter(has_text='Jane Smith')
    assert jane.locator('td').all_text_contents() == ['Jane Smith','Yes','Yes','Yes','100%','Yes']
    page.screenshot(path='/tmp/video-messaging-analytics.png', full_page=True)
    page.goto(campaign_url)
    page.get_by_role('link', name='Delete test campaign').click()
    page.get_by_role('button', name='Permanently delete').click()
    assert recipient_page.goto(rows[0]['video_url']).status == 404
    assert errors == [], errors
    browser.close()
print('PASS: saved script, scroll/pause/reset, size and speed persistence, auto-scroll during 10 camera recordings, Save & Next, CSV export, private mobile playback, CTA, 100% analytics, and campaign deletion.')
