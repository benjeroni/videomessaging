import csv
import io
import json
import subprocess
import uuid
from pathlib import Path
from django.conf import settings
from .forms import RecipientForm

COLUMNS = ['external_id', 'first_name', 'last_name', 'email', 'phone', 'program', 'notes']

def parse_csv(upload):
    if upload.size > 1024 * 1024:
        raise ValueError('CSV must be no larger than 1 MB.')
    try:
        reader = csv.DictReader(io.StringIO(upload.read().decode('utf-8-sig')), strict=True)
        if not reader.fieldnames or 'first_name' not in reader.fieldnames:
            raise ValueError('Include a first_name column. Other columns are optional.')
        if len(set(reader.fieldnames)) != len(reader.fieldnames) or any(c not in COLUMNS for c in reader.fieldnames):
            raise ValueError('Headers must be unique and use the template column names.')
        valid, errors = [], []
        for index, row in enumerate(reader, 2):
            if index > 1001:
                raise ValueError('Import at most 1,000 rows at a time.')
            if None in row or any(v is None for v in row.values()):
                errors.append(f'Row {index}: incorrect number of columns.')
                continue
            form = RecipientForm({k: v.strip() for k, v in row.items()})
            if form.is_valid():
                valid.append(form.cleaned_data)
            else:
                errors.append(f'Row {index}: ' + '; '.join(f'{k}: {", ".join(v)}' for k, v in form.errors.items()))
        return valid, errors
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError('Malformed CSV. Save as UTF-8 CSV and try again.') from exc

def normalize_video(source, campaign_id):
    directory = settings.VIDEO_ROOT / str(campaign_id)
    directory.mkdir(parents=True, exist_ok=True)
    relative = f'{campaign_id}/{uuid.uuid4().hex}.mp4'
    output = settings.VIDEO_ROOT / relative
    try:
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(source)], capture_output=True, timeout=20, check=True)
        info = json.loads(probe.stdout)
        if not any(s['codec_type'] == 'video' for s in info['streams']):
            raise ValueError('No video track found.')
        # Browser WebM may omit duration; output is capped and checked below.
        duration = float(info.get('format', {}).get('duration', 0))
        if duration > settings.MAX_VIDEO_SECONDS + 1:
            raise ValueError('Recording exceeds the duration limit.')
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-threads', '2', '-i', str(source), '-t', str(settings.MAX_VIDEO_SECONDS + 1), '-map', '0:v:0', '-map', '0:a:0?', '-vf', "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2", '-c:v', 'libx264', '-threads', '2', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-y', str(output)], capture_output=True, timeout=300, check=True)
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(output)], capture_output=True, timeout=20, check=True)
        duration = float(result.stdout)
        if duration > settings.MAX_VIDEO_SECONDS + 0.5:
            raise ValueError('Recording exceeds the duration limit.')
        return relative, duration
    except Exception:
        output.unlink(missing_ok=True)
        raise

def csv_safe(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')) else value
