# Personalized Video Messaging — prototype

A self-hosted Django application for importing an audience, recording one personal video per recipient, exporting private links, and viewing basic engagement. Uses Django templates, local CSS/JavaScript, PostgreSQL 17, Gunicorn and FFmpeg. No external frontend assets, analytics, messaging integrations, or cloud storage.

**Use fabricated test data only.** This is a workflow prototype, not an institutional production system. MFA, SSO, automatic captions, retention automation and production security review are deferred.

## Start with Docker

Requires Docker Engine and the Compose plugin. Clone this repository and enter its directory:

```bash
git clone <your-repository-url> video-messaging
cd video-messaging
cp .env.example .env
```

Edit `.env`: generate separate random values for `POSTGRES_PASSWORD` and `DJANGO_SECRET_KEY` (for example, run `openssl rand -hex 32` twice). Never commit `.env`. Set permissions with `chmod 600 .env`.

Set `VIDEO_STORAGE_PATH` to an existing persistent directory, for example `/data/video-messaging/videos`. Prepare that directory for the container's unprivileged UID/GID 10001:

```bash
sudo mkdir -p /data/video-messaging/videos
sudo chown 10001:10001 /data/video-messaging/videos
sudo chmod 750 /data/video-messaging/videos
```

For the default `./data/videos`, apply the same ownership and permissions to that path instead. Then:

```bash
docker compose build
docker compose up -d
docker compose exec app python manage.py migrate
docker compose exec app python manage.py createsuperuser
```

The entrypoint also runs migrations and collects static assets automatically, so the explicit migration command is safe to repeat. Open http://localhost:8000 and sign in with the username you created. Email may be used as the username when creating accounts. Django Admin manages additional users; choose their **Role** and keep the account **Active**. See User roles and recording assignments below.

The database lives in the `postgres-data` named volume; videos live in the host bind mount. No persistent application data is stored only in the app container. `.env` is generated locally during initial agent setup if absent; it is excluded from version control.

## Hostname, reverse proxy and HTTPS

For `https://video.example.ca`, set:

```dotenv
DJANGO_ALLOWED_HOSTS=video.example.ca,localhost,127.0.0.1
BASE_URL=https://video.example.ca
CSRF_TRUSTED_ORIGINS=https://video.example.ca
COOKIE_SECURE=true
TRUST_PROXY=true
DJANGO_DEBUG=false
```

Recreate the app with `docker compose up -d`. `BASE_URL` determines exported links. `APP_BIND=127.0.0.1` and `APP_PORT=8000` bind only to the host loopback interface by default. Use an SSH tunnel for remote localhost testing (`ssh -L 8000:127.0.0.1:8000 user@server`), or configure your existing HTTPS reverse proxy. Camera/microphone access requires HTTPS, except on localhost.

An example location block for a host Nginx proxy is in `docker/nginx.conf.example`. Configure your hostname and TLS certificate in your existing Nginx/Caddy/Traefik installation. A containerized proxy should share a Docker network with `app` and forward to `app:8000`; do not use its own loopback address. Only enable `TRUST_PROXY` when direct access is restricted and the proxy overwrites `X-Forwarded-Proto`. Do not publish PostgreSQL or the video directory. Disable proxy access logs (including upstream platform logs) for this app: request paths contain bearer tokens. Limit uploads to 160 MB at the proxy and allow at least 360 seconds for processing.

Branding: `ORGANIZATION_NAME`, `BRAND_HEADING`, `BRAND_FOOTER`, and optional `BRAND_LOGO_URL`. Prefer a same-origin logo served by your proxy, e.g. `/brand/logo.svg`. The campaign's heading overrides the default heading. No page designer is included.

## Test the workflow

1. Create **Test Nursing Campaign**, with CTA **Learn More** and an HTTP(S) destination.
2. Import `examples/recipients.csv` (10 fabricated recipients). Review errors and the valid-row preview, then confirm. Only `first_name` is required. Imports append; they never deduplicate or overwrite recipients.
3. Choose **Continue recording**. Enable camera/microphone, record, stop, preview with the player's Play control, then **Save & Next**. Repeat ten times. Previous, Skip, and Next unrecorded are available. Unsaved recordings trigger a browser navigation warning.
4. Set campaign status to **Ready** in Settings. Export Distribution CSV. Only recipients with ready videos are included; spreadsheet formula-like values are escaped with an apostrophe.
5. Open a generated URL in a private browser. Verify the first name, play through to the end, and click the CTA.
6. Open Analytics: the recipient should show Viewed, Started, 100%, and CTA clicked. Counts are unique recipients, not raw event totals.
7. Archive the campaign to disable all public links. Delete a test campaign to permanently delete recipients, video files, and analytics.

Public links work while draft/recording/ready so staff can preview them. A recipient without a video sees an availability message. Archived campaigns return 404. Each URL has a random 192-bit bearer token; anyone holding the link can view or share it. Public URLs never use database IDs. All video requests, including byte-range requests for mobile playback and seeking, validate the token. No direct video filesystem URL is served.

## Recording and processing

Desktop Chrome and Edge are the intended recording browsers. Device selectors appear after permission is granted. Recordings are limited to 300 seconds and 150 MB by default (`MAX_VIDEO_SECONDS`, `MAX_UPLOAD_MB`). FFmpeg produces H.264/AAC MP4, up to 1280×720, with fast-start metadata. Files use random internal names. Temporary uploads are deleted on success and handled failure; replacing a recording deletes the previous file only after the database update commits. Failed replacement preserves the previous saved video.

Conversion runs synchronously with a 300-second FFmpeg timeout. This keeps the prototype small; simultaneous recordings consume Gunicorn workers and CPU. It is intended for a small staff pilot, not high throughput. An interrupted container can leave temporary/orphan files; after confirming no uploads are active, remove stale `*.upload` files from the video root and reconcile random MP4 files against `Video.stored_filename` using a database-aware maintenance procedure. Conversion must finish before Save & Next advances.

Analytics POSTs retain CSRF protection. Events are deduplicated in the database by recipient, event type, and random browser session UUID. `sessionStorage` survives reloads in the same tab. A new browser tab/session can generate new raw events; campaign totals remain unique-recipient counts. Watched means highest playback position milestone reported, not proof of attention; seeking, ad blockers, disabled JavaScript, and forged events affect accuracy. CTA opens in a new tab and uses a keepalive event POST. No IP address field, external analytics, or contact details are recorded in operational logs. Gunicorn access logs are disabled; errors log only generic operational identifiers.

## Automated verification

Run the suite against real PostgreSQL and FFmpeg inside Docker:

```bash
docker compose exec app python manage.py check
docker compose exec app python manage.py test messaging -v 2
docker compose exec app python manage.py makemigrations --check --dry-run
```

Tests use a separate temporary database (the configured database user must have permission to create it) and temporary video storage. They cover staff/CSRF gates, CSV validation and preview, exports, token playback/ranges, analytics deduplication, replacement failure, physical deletion, and actual FFmpeg conversion including codecs and fast-start layout. Physical webcam permissions and ten human recordings still require the manual acceptance test above.

Optional local development:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export DJANGO_SECRET_KEY="$(openssl rand -hex 32)"
export USE_SQLITE=1
export DJANGO_DEBUG=true
.venv/bin/python app/manage.py migrate
.venv/bin/python app/manage.py createsuperuser
.venv/bin/python app/manage.py runserver
```

SQLite is an explicit development/test convenience only. Install FFmpeg locally for recording uploads; Compose always uses PostgreSQL. `.env` is loaded by Compose, not automatically by manage.py.

## Backup, restore and upgrade

Back up the **database, videos, and `.env` together**. Stop app writes for a consistent snapshot; PostgreSQL remains running. Protect backups because they contain recipient information, private tokens, and secrets.

```bash
mkdir -p backups
chmod 700 backups
docker compose stop app
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/database.dump
# Replace the source with your VIDEO_STORAGE_PATH:
sudo tar -C /data/video-messaging/videos -czf backups/videos.tar.gz .
cp .env backups/config.env
chmod 600 backups/config.env backups/database.dump
docker compose start app
```

Copy backups to a separate protected location. Also preserve the application revision and Compose configuration. Test restoration periodically.

To restore on an empty deployment, restore `.env` as mode 600, restore videos into `VIDEO_STORAGE_PATH`, and set ownership to 10001:10001. Start only PostgreSQL and wait for its healthcheck, then restore:

```bash
docker compose up -d postgres
docker compose ps
cat backups/database.dump | docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error'
docker compose up -d --build app
```

Restore into an empty database; do not overwrite a running installation without a separate backup and deliberate database reset. Extract the videos with `sudo tar -C /data/video-messaging/videos -xzf backups/videos.tar.gz` before starting the app. Existing public links require the same hostname and preserved database tokens.

For upgrades: take a consistent backup, pull the desired application revision, run `docker compose build --pull`, then `docker compose up -d`. Review migration output and run checks/tests. Pin and review dependency updates in `requirements.txt`; PostgreSQL major-version upgrades require a separate dump/restore or upgrade plan. Rollback may require restoring both the matching database and video backup. **Do not use `docker compose down -v` on data you want to keep.**

## Prototype limits

No email/SMS sending, recipient authentication, MFA, captions/transcription, background workers, external services, or advanced reporting. Before real institutional data: review security, dependencies, identity/MFA, host/network hardening, privacy, accessibility (including captions), retention, monitoring, backups, incident response and penetration testing. The UI consistently labels the app as a prototype.

Framework reference: [Django 5.2 LTS release notes](https://docs.djangoproject.com/en/5.2/releases/5.2/).

If this host's Docker build bridge cannot resolve package servers, build with `docker build --network host -t videomessaging-app .` and then start with `docker compose up -d --no-build`. This is a host-specific build workaround; the application and database still use their private Compose network at runtime.

For the already-initialized local workspace, the generated staff login is stored in `.local-admin.json` (mode 600, ignored by Git and Docker builds). Sign in and change the password in Django Admin; delete the bootstrap credential file when no longer needed. Fresh clones should use `createsuperuser` as described above.

`tests/browser_smoke.py` is an optional Playwright acceptance test using simulated camera/microphone input. It creates ten recordings, exports links, checks mobile-size public playback and CTA analytics, then deletes its campaign. Install Playwright and Chromium with system dependencies in a disposable test environment, set `SMOKE_CREDENTIALS` to a JSON file containing `username` and `password`, and optionally set `SMOKE_BASE_URL`. Run `python tests/browser_smoke.py`. It deliberately creates and deletes test data; use a test deployment.

### Verification completed in this workspace

On 2026-09-18, the 10 Django integration tests passed against PostgreSQL 17 with real FFmpeg. The Chromium browser smoke test also passed all ten simulated camera/audio recordings through Save & Next, distribution CSV download, a separate mobile-sized recipient browser context, complete playback and CTA analytics, and campaign deletion. Browser testing found and verified a fix for same-origin form CSRF compatibility. Actual hardware permissions, desktop Edge, and physical mobile devices still need manual pilot testing. Both Compose services were healthy after validation.

## User roles and recording assignments

Admins manage users in **Admin → Users**. Each account has a single Role selector:

| Role | Access |
| --- | --- |
| Admin | All workflows, plus user creation, roles, passwords, and account activation. |
| Coordinator | All campaigns, CSV import/export, campaign scripts, recipient edits/deletion, analytics, recording, and recipient assignment. No user administration. |
| Recorder | Only their assigned recipients in non-archived campaigns, including recording/re-recording and reading the campaign script. No campaign management, script edits, imports, exports, analytics, or assignments. |

On **Campaign → Recipients**, select individual contacts or all displayed contacts, choose an active recorder, and click **Apply assignment**. Choose Unassigned to remove assignments. Each recipient has at most one assigned recorder. Reassignment immediately changes access, including upload authorization from an already-open page. The recording queue, Previous, Skip, and Save & Next stay within the recorder's assignments. Existing recordings are preserved on reassignment. Assignments to deleted accounts become unassigned; inactive recorders cannot sign in.

Recorders land on **My recordings** after login. Coordinators share campaign access with other coordinators. Admin uses Django superuser status; Coordinator and Recorder use built-in Django groups, managed through the Role selector. Merely setting `is_staff` does not grant workflow access. The role migration preserves existing non-superuser staff campaign access by assigning Coordinator. Accounts without a role cannot enter the workspace. Recipient bearer-link access is unchanged.

## Recording scripts and teleprompter

Admins/coordinators can type or paste a script on the recording screen, load a plain `.txt` file, or edit Script text in Campaign Settings. Scripts autosave to the campaign (20,000 characters maximum); check for **Script saved**. Save & Next waits for pending script changes to save. The same script appears for each recipient; it is not automatically personalized.

The script appears beside the camera preview. Adjust scroll speed (5–100 pixels/second) and text size (18–56 pixels), start/pause scrolling, or choose Back to top. By default, starting a recording resets and starts the script; stopping the recording pauses it. Uncheck the auto-start option for manual control. Scrolling can also be rehearsed without recording. Speed, size, and auto-start preferences are remembered in that browser; scripts are stored in PostgreSQL. Recorders can change reading controls but cannot edit the campaign script. Scripts are staff-only and are never included in the recorded video or public landing page.

The script/role update was verified with 17 PostgreSQL/FFmpeg integration tests and two Chromium acceptance tests. The tests covered script persistence, size/speed controls, scrolling/pause/reset, automatic scrolling during ten recordings, role creation, coordinator assignment, recorder-only queues/uploads, and access removal after unassignment. `tests/browser_roles.py` exercises the separate-role workflow. When pointed at a LAN HTTP address, the browser tests create a temporary localhost TCP forwarder for camera access, matching the documented SSH-tunnel workflow. Real users still need HTTPS or an SSH tunnel for camera access. Recipient analytics also support LAN HTTP testing.
