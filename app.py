"""Archiver: dependency-free local FFmpeg library and encoding queue."""
import argparse
import collections
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import webbrowser

ROOT = Path(__file__).resolve().parent
VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
VIDEO_EXT = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v', '.mpeg', '.mpg', '.mts', '.m2ts', '.ts', '.wmv', '.flv', '.vob', '.ogv'}
ENCODERS = {'h264': ['libx264', 'h264_nvenc', 'h264_qsv', 'h264_amf'], 'hevc': ['libx265', 'hevc_nvenc', 'hevc_qsv', 'hevc_amf'], 'av1': ['libsvtav1', 'libaom-av1', 'av1_nvenc', 'av1_qsv', 'av1_amf'], 'vp9': ['libvpx-vp9']}
TOKEN = secrets.token_urlsafe(32)
STATE = {'files': {}, 'jobs': [], 'ffmpeg': shutil.which('ffmpeg') or '', 'ffprobe': shutil.which('ffprobe') or '', 'encoders': [], 'scan': {'running': False, 'done': 0, 'total': 0, 'errors': []}}
LOCK = threading.RLock()
WAKE = threading.Event()
SCAN_STOP = threading.Event()
BROWSE_LOCK = threading.Lock()
PROCESS = None
CACHE = tempfile.TemporaryDirectory(prefix='archiver-')


def run(command, timeout=30):
    return subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def browse_directory(initial=''):
    """Run Tk on a separate process's main thread, independent of HTTP threads."""
    if not BROWSE_LOCK.acquire(blocking=False):
        raise ValueError('A folder picker is already open. Choose a folder or cancel it first.')
    try:
        initial_path = Path(initial).expanduser() if initial else Path.home()
        if not initial_path.is_dir():
            initial_path = Path.home()
        result = subprocess.run(
            [sys.executable, str(ROOT / 'folder_picker.py'), str(initial_path)],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('Could not open the folder picker. Ensure Python includes tkinter, or paste the folder path manually.')
        directory = json.loads(result.stdout)['directory']
        if directory and not Path(directory).is_dir():
            raise ValueError('The selected directory is no longer available')
        return directory
    finally:
        BROWSE_LOCK.release()


def configure(ffmpeg, ffprobe):
    # Only executable paths are accepted; arguments never pass through a shell.
    verified = {}
    for name, value in [('ffmpeg', ffmpeg), ('ffprobe', ffprobe)]:
        resolved = shutil.which(value) if value else None
        if not resolved or not Path(resolved).is_file():
            raise ValueError(f'{name} executable was not found. Enter its full path.')
        result = run([resolved, '-version'])
        if result.returncode or not result.stdout.lower().startswith(name + ' version'):
            raise ValueError(f'The selected executable is not {name}.')
        verified[name] = resolved
    result = run([verified['ffmpeg'], '-hide_banner', '-encoders'])
    available = set(re.findall(r'^\s*V\S*\s+(\S+)', result.stdout, re.M))
    STATE.update(verified)
    STATE['encoders'] = [e for group in ENCODERS.values() for e in group if e in available]


def probe(path, cancel=None):
    command = [STATE['ffprobe'], '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]
    if cancel is None:
        result = run(command, 90)
    else:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 90
        try:
            while True:
                if cancel.is_set():
                    raise InterruptedError('Scan stopped')
                if time.monotonic() >= deadline:
                    raise TimeoutError('FFprobe exceeded 90 seconds')
                try:
                    stdout, stderr = process.communicate(timeout=.2)
                    result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    if result.returncode:
        raise ValueError(result.stderr.strip() or 'FFprobe could not read this file')
    data = json.loads(result.stdout)
    video = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')), None)
    if not video:
        raise ValueError('No video stream found')
    fmt = data.get('format', {})
    ratio = video.get('avg_frame_rate', '0/1').split('/')
    fps = float(ratio[0]) / float(ratio[1]) if len(ratio) == 2 and float(ratio[1]) else 0
    tags = {str(k).lower(): str(v) for k, v in {**fmt.get('tags', {}), **video.get('tags', {})}.items()}
    rate_text = ' '.join(tags.get(key, '') for key in ['encoding_settings', 'encoder_settings', 'settings', 'rate_control_mode', 'rc_mode'])
    mode_match = re.search(r'\brc[= :]+(crf|cqp|cbr|vbr)\b', rate_text, re.I)
    rate_mode = mode_match.group(1).lower() if mode_match else ''
    if not rate_mode and rate_text.strip().lower() in ['cbr', 'vbr', 'cqp', 'crf']:
        rate_mode = rate_text.strip().lower()
    quality_match = re.search(r'\b(crf|qp)[= :]+([0-9]+(?:\.[0-9]+)?)', rate_text, re.I)
    source_quality = float(quality_match.group(2)) if quality_match else None
    if quality_match and not rate_mode:
        rate_mode = 'crf' if quality_match.group(1).lower() == 'crf' else 'cqp'
    tagged_bitrate = tags.get('bps', tags.get('bps-eng', '0'))
    stream_bitrate = int(video.get('bit_rate') or (tagged_bitrate if tagged_bitrate.isdigit() else 0))
    return {'id': secrets.token_hex(12), 'path': str(path), 'name': path.name, 'size': path.stat().st_size, 'codec': video.get('codec_name', '?'), 'width': video.get('width', 0), 'height': video.get('height', 0), 'fps': fps, 'video_bitrate': stream_bitrate, 'rate_mode': rate_mode, 'source_quality': source_quality, 'pixel_format': video.get('pix_fmt', ''), 'color_transfer': video.get('color_transfer', ''), 'bitrate': int(fmt.get('bit_rate') or 0), 'duration': float(fmt.get('duration') or video.get('duration') or 0), 'audio': ', '.join(dict.fromkeys(s.get('codec_name', '?') for s in data.get('streams', []) if s.get('codec_type') == 'audio')), 'container': fmt.get('format_name', '?')}


def scan(directory, recursive):
    started = time.time()
    with LOCK:
        STATE['scan'].update(phase='discovering', started=started, finished=None,
                             current='', entries=0, folders=0, recent=[], file_started=None)
        STATE['files'] = {}
    def recent(message):
        STATE['scan']['recent'] = (STATE['scan']['recent'] + [message])[-8:]
    try:
        root = Path(directory).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError('Choose an existing directory')
        paths = []
        def discovery_error(error):
            with LOCK:
                STATE['scan']['errors'].append(str(error))
                recent(f'Skipped folder: {error.filename}')
        for folder, dirs, files in os.walk(root, onerror=discovery_error, followlinks=False):
            if not recursive:
                dirs[:] = []
            with LOCK:
                STATE['scan']['current'] = str(folder)
                STATE['scan']['folders'] += 1
            if SCAN_STOP.is_set():
                raise InterruptedError('Scan stopped')
            for name in files:
                if SCAN_STOP.is_set():
                    raise InterruptedError('Scan stopped')
                path = Path(folder) / name
                with LOCK:
                    STATE['scan']['entries'] += 1
                    if path.suffix.lower() in VIDEO_EXT:
                        paths.append(path)
                        STATE['scan']['total'] = len(paths)
        with LOCK:
            STATE['scan'].update(phase='probing', current='', file_started=None)
            recent(f'Discovered {len(paths)} video files')
        for path in sorted(paths):
            if SCAN_STOP.is_set():
                raise InterruptedError('Scan stopped')
            with LOCK:
                STATE['scan'].update(current=str(path), file_started=time.time())
            try:
                item = probe(path, cancel=SCAN_STOP)
                with LOCK:
                    STATE['files'][item['id']] = item
                    recent(f'Read: {path.name}')
            except InterruptedError:
                raise
            except Exception as exc:
                with LOCK:
                    STATE['scan']['errors'].append(f'{path.name}: {exc}')
                    recent(f'Skipped: {path.name} — {exc}')
            with LOCK:
                STATE['scan']['done'] += 1
    except InterruptedError:
        with LOCK:
            recent('Scan stopped by user; loaded videos retained')
    except Exception as exc:
        with LOCK:
            STATE['scan']['errors'].append(str(exc))
    finally:
        with LOCK:
            STATE['scan'].update(running=False, phase='stopped' if SCAN_STOP.is_set() else 'complete', finished=time.time(), current='', file_started=None)


def command_for(source, output, settings):
    encoder = settings.get('encoder')
    codec = settings.get('codec')
    if encoder not in ENCODERS.get(codec, []) or encoder not in STATE['encoders']:
        raise ValueError('Choose an available encoder for this codec')
    cmd = [STATE['ffmpeg'], '-hide_banner', '-nostdin', '-y', '-i', str(source), '-map', '0:v:0', '-map', '0:a?', '-map_metadata', '0', '-c:v', encoder]
    resolution = settings.get('resolution', 'original')
    heights = {'2160': 2160, '1440': 1440, '1080': 1080, '720': 720, '480': 480}
    filters = []
    if resolution != 'original':
        if resolution not in heights:
            raise ValueError('Invalid resolution')
        # Fits either portrait or landscape inside the chosen landscape bounding box; never upscales.
        height = heights[resolution]
        width = round(height * 16 / 9 / 2) * 2
        filters.append(f"scale=w='min({width},iw)':h='min({height},ih)':force_original_aspect_ratio=decrease:force_divisible_by=2")
    else:
        filters.append('scale=trunc(iw/2)*2:trunc(ih/2)*2')
    cmd += ['-vf', ','.join(filters), '-pix_fmt', 'yuv420p']
    fps = settings.get('fps', 'original')
    if fps != 'original':
        if fps not in ['23.976', '24', '25', '29.97', '30', '50', '59.94', '60']:
            raise ValueError('Invalid frame rate')
        cmd += ['-r', fps]
    bitrate = settings.get('bitrate', 'auto')
    if bitrate in ['crf', 'cqp']:
        try:
            value = int(settings.get('qualityValue', ''))
        except (ValueError, TypeError):
            raise ValueError('Enter a whole-number quality value')
        hardware = encoder.endswith(('_nvenc', '_qsv', '_amf'))
        maximum = 51 if hardware or codec in ['h264', 'hevc'] else 63
        if not 0 <= value <= maximum:
            raise ValueError(f'Quality must be between 0 and {maximum}')
        quality = str(value)
        if bitrate == 'crf':
            if hardware:
                raise ValueError('CRF requires a software encoder. Use CQP for hardware encoders.')
            cmd += ['-crf', quality]
            if codec in ['av1', 'vp9']:
                cmd += ['-b:v', '0']
        elif not hardware:
            raise ValueError('CQP mode requires a hardware encoder. Use CRF for software encoders.')
        elif encoder.endswith('_nvenc'):
            cmd += ['-rc', 'constqp', '-qp', quality]
        elif encoder.endswith('_qsv'):
            cmd += ['-flags:v', '+qscale', '-global_quality', quality]
        else:
            cmd += ['-rc', 'cqp', '-qp_i', quality, '-qp_p', quality]
    elif bitrate == 'custom':
        try:
            value = float(settings.get('customBitrate', ''))
        except (ValueError, TypeError):
            raise ValueError('Enter a custom bitrate in Mbps')
        if not 0.1 <= value <= 1000:
            raise ValueError('Custom bitrate must be between 0.1 and 1000 Mbps')
        cmd += ['-b:v', f'{round(value * 1000)}k']
    elif bitrate == 'auto':
        metadata = settings.get('sourceMetadata') or probe(source)
        rate_mode = metadata.get('rate_mode', '')
        source_quality = metadata.get('source_quality')
        hardware = encoder.endswith(('_nvenc', '_qsv', '_amf'))
        same_codec = metadata.get('codec') == codec
        # Never infer CRF/QP or CBR from average bitrate alone.
        if same_codec and rate_mode in ['crf', 'cqp'] and source_quality is not None and float(source_quality).is_integer() and ((rate_mode == 'crf' and not hardware) or (rate_mode == 'cqp' and hardware)):
            return command_for(source, output, {**settings, 'bitrate': rate_mode, 'qualityValue': int(source_quality)})
        source_bitrate = metadata.get('video_bitrate', 0)
        if not source_bitrate or source_bitrate <= 0:
            raise ValueError('Automatic cannot find video-stream bitrate or reusable quality metadata. Choose CRF, CQP, or a custom bitrate.')
        target = str(int(source_bitrate))
        cmd += ['-b:v', target]
        if rate_mode == 'cbr':
            cmd += ['-minrate', target, '-maxrate', target, '-bufsize', str(int(source_bitrate) * 2)]
            if encoder.endswith(('_nvenc', '_amf')):
                cmd += ['-rc', 'cbr']
        elif encoder.endswith('_nvenc'):
            cmd += ['-rc', 'vbr']
        elif encoder.endswith('_amf'):
            cmd += ['-rc', 'vbr_peak']
    else:
        if not re.fullmatch(r'[1-9][0-9]{1,5}k', bitrate):
            raise ValueError('Invalid bitrate')
        cmd += ['-b:v', bitrate]
    audio = settings.get('audio', 'aac')
    audio_encoders = {'aac': 'aac', 'mp3': 'libmp3lame', 'opus': 'libopus', 'flac': 'flac', 'copy': 'copy'}
    if audio not in [*audio_encoders, 'none']:
        raise ValueError('Invalid audio mode')
    if output.suffix.lower() == '.webm' and audio not in ['opus', 'none']:
        raise ValueError('WebM audio must use Opus or Remove audio')
    if output.suffix.lower() == '.mp4' and audio in ['opus', 'flac']:
        raise ValueError('Use MKV for Opus or FLAC audio, or select AAC/MP3 for MP4')
    cmd += ['-an'] if audio == 'none' else ['-c:a', audio_encoders[audio]]
    if audio in ['aac', 'mp3', 'opus']:
        audio_bitrate = settings.get('audioBitrate', '192k')
        if audio_bitrate not in ['64k', '96k', '128k', '160k', '192k', '256k', '320k']:
            raise ValueError('Invalid audio bitrate')
        cmd += ['-b:a', audio_bitrate]
        if audio == 'mp3':
            cmd += ['-ac', '2']
    if output.suffix.lower() == '.mp4':
        cmd += ['-movflags', '+faststart']
    return cmd + ['-progress', 'pipe:1', '-stats_period', '0.5', '-stats', str(output)]


def recommend_quality(items, settings):
    encoder = settings.get('encoder', '')
    codec = settings.get('codec')
    if encoder not in ENCODERS.get(codec, []):
        raise ValueError('Select a codec and encoder first')
    if not items:
        raise ValueError('Select source videos first; rescan older libraries to read video-stream metadata')
    base = {'h264': 20, 'hevc': 22, 'av1': 26, 'vp9': 26}[codec]
    values, warnings = [], []
    for item in items:
        bitrate = item.get('video_bitrate', 0)
        pixels = item.get('width', 0) * item.get('height', 0) * item.get('fps', 0)
        value = base
        if bitrate and pixels:
            # Heuristic normalized source bit density, not a perceptual measurement.
            efficiency = {'h264': 1, 'hevc': 1.4, 'av1': 1.7, 'vp9': 1.4}.get(item.get('codec'), 1)
            density = bitrate / pixels * efficiency
            value += -2 if density > .16 else 2 if density < .045 else 0
        else:
            warnings.append('Video-stream bitrate unavailable; using a codec baseline for some files.')
        if item.get('color_transfer') in ['smpte2084', 'arib-std-b67'] or any(x in item.get('pixel_format', '') for x in ['10', '12']):
            warnings.append('Some sources are HDR or high bit depth; current 8-bit output may change their appearance.')
        values.append(value)
    mode = 'cqp' if encoder.endswith(('_nvenc', '_qsv', '_amf')) else 'crf'
    return {'mode': mode, 'value': min(values), 'note': 'Source-based estimate using codec and video bits per pixel per frame. Uses the most conservative value across selected files. Not the original CRF/QP or a measured quality match. Resolution and frame-rate changes can lose detail regardless of this value.', 'warnings': list(dict.fromkeys(warnings))}


def output_name(item, settings, index=1):
    source = Path(item['path'])
    action = settings.get('mode', 'preserve')
    if action == 'overwrite':
        return source.name
    naming = settings.get('naming', 'default')
    extension = source.suffix if action in ['copy', 'move'] else '.' + settings.get('container', 'mp4')
    def safe(value):
        value = value.strip()
        if not value or len(value) > 100 or re.search(r'[<>:"/\\|?*\x00-\x1f]', value) or value.endswith(('.', ' ')):
            raise ValueError('Names must be 1–100 characters without path separators or reserved filename characters')
        return value
    if naming == 'batch':
        base = safe(settings.get('batchName', ''))
        if base.split('.')[0].upper() in ['CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(1, 10)], *[f'LPT{i}' for i in range(1, 10)]]:
            raise ValueError('Choose a batch name that is not a reserved device name')
        return f'{base}_{index:03d}{extension}'
    if naming == 'default':
        suffix = ''
    elif naming == 'custom':
        suffix = '_' + safe(settings.get('nameSuffix', ''))
    elif naming in ['resolution', 'framerate', 'quality', 'settings']:
        width, height = item['width'], item['height']
        resolution = settings.get('resolution', 'original') if action not in ['copy', 'move'] else 'original'
        if resolution != 'original':
            if resolution not in ['2160', '1440', '1080', '720', '480']:
                raise ValueError('Invalid resolution')
            limit = int(resolution)
            ratio = min(1, (round(limit * 16 / 9 / 2) * 2) / width, limit / height)
            width, height = int(width * ratio) // 2 * 2, int(height * ratio) // 2 * 2
        elif action not in ['copy', 'move']:
            width, height = width // 2 * 2, height // 2 * 2
        fps = settings.get('fps', 'original') if action not in ['copy', 'move'] else 'original'
        fps = f"{item['fps']:.3f}".rstrip('0').rstrip('.') if fps == 'original' else fps
        quality = settings.get('bitrate', 'auto')
        if quality in ['crf', 'cqp']:
            quality += '-' + str(settings.get('qualityValue', ''))
        elif quality == 'custom':
            quality = str(settings.get('customBitrate', '')) + 'Mbps'
        quality = 'original' if action in ['copy', 'move'] else {'auto': 'source-bitrate'}.get(quality, quality)
        tags = {'resolution': f'{width}x{height}', 'framerate': f'{fps}fps', 'quality': quality}
        suffix = '_' + safe('_'.join(tags.values()) if naming == 'settings' else tags[naming])
    else:
        raise ValueError('Invalid output naming option')
    return source.stem + suffix + extension


def enqueue(ids, settings, auto_start=False):
    if not ids:
        raise ValueError('Select at least one video')
    mode = settings.get('mode', 'preserve')
    if mode not in ['preserve', 'overwrite', 'directory', 'copy', 'move']:
        raise ValueError('Invalid file action')
    if mode == 'overwrite' and settings.get('deleteOriginal') is True and settings.get('confirmDelete') is not True:
        raise ValueError('Confirm that you understand the original files will be permanently deleted')
    container = settings.get('container', 'mp4')
    if container not in ['mp4', 'mkv', 'webm']:
        raise ValueError('Invalid container')
    if container == 'webm' and mode not in ['copy', 'move'] and settings.get('codec') not in ['av1', 'vp9']:
        raise ValueError('WebM requires AV1 or VP9 video')
    destination = None
    if mode in ['directory', 'copy', 'move']:
        if not settings.get('destination', '').strip():
            raise ValueError('Enter a destination directory')
        destination = Path(settings['destination']).expanduser().resolve()
        if not destination.is_dir():
            raise ValueError('Destination directory must already exist')
    new_jobs = []
    with LOCK:
        busy_sources = {j['source'] for j in STATE['jobs'] if j['status'] in ['queued', 'running']}
        reserved = {os.path.normcase(j['output']) for j in STATE['jobs'] if j['status'] in ['queued', 'running']}
        for index, fid in enumerate(dict.fromkeys(ids), 1):
            item = STATE['files'].get(fid)
            if not item:
                raise ValueError('A selected file is no longer in the library. Scan again.')
            source = Path(item['path'])
            if str(source) in busy_sources:
                raise ValueError(f'{source.name} is already queued')
            if mode in ['copy', 'move']:
                output = destination / output_name(item, settings, index)
            elif mode == 'overwrite':
                if source.suffix.lower() != '.' + container:
                    raise ValueError('Replacing originals requires the output container to match every selected file extension. Use a new output directory instead.')
                output = source
            else:
                output = (destination or source.parent) / output_name(item, settings, index)
            if mode != 'overwrite' and (output.exists() or os.path.normcase(str(output)) in reserved):
                raise ValueError(f'Output already exists or is queued: {output}')
            if output == source and mode != 'overwrite':
                raise ValueError('Source and destination must differ')
            job_settings = {**settings, 'sourceMetadata': {key: item.get(key) for key in ['codec', 'video_bitrate', 'rate_mode', 'source_quality']}}
            if mode not in ['copy', 'move']:
                command_for(source, output, job_settings)
            reserved.add(os.path.normcase(str(output)))
            new_jobs.append({'id': secrets.token_hex(10), 'name': source.name, 'source': str(source), 'output': str(output), 'settings': job_settings, 'duration': item['duration'], 'status': 'queued', 'percent': 0, 'speed': '', 'fps': '', 'eta': None, 'log': collections.deque(maxlen=1500), 'cancel': False, 'error': ''})
        STATE['jobs'].extend(new_jobs)
        if auto_start:
            WAKE.set()


def recycle_file(path):
    """Use Windows IFileOperation with recycle-only deletion and fail on errors."""
    if sys.platform != 'win32':
        raise ValueError('Recycle Bin replacement currently requires Windows; the original backup has been retained')
    import ctypes as ct
    from ctypes import wintypes as wt
    class GUID(ct.Structure):
        _fields_ = [('data', ct.c_ubyte * 16)]
    import uuid
    def guid(value):
        return GUID((ct.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))
    ole = ct.OleDLL('ole32')
    shell = ct.OleDLL('shell32')
    def check(hr):
        if hr < 0:
            raise OSError(f'Windows Recycle Bin operation failed (0x{hr & 0xffffffff:08x})')
    def invoke(ptr, slot, *types):
        address = ct.cast(ptr, ct.POINTER(ct.POINTER(ct.c_void_p))).contents[slot]
        return ct.WINFUNCTYPE(ct.c_long, ct.c_void_p, *types)(address)
    check(ole.CoInitializeEx(None, 2))
    operation, item = ct.c_void_p(), ct.c_void_p()
    try:
        clsid = guid('3ad05575-8857-4850-9277-11b85bdb8e09')
        iid = guid('947aab5f-0a5c-4c13-b4d6-4bf7836fc9f8')
        check(ole.CoCreateInstance(ct.byref(clsid), None, 1, ct.byref(iid), ct.byref(operation)))
        shell.SHCreateItemFromParsingName.argtypes = [wt.LPCWSTR, ct.c_void_p, ct.POINTER(GUID), ct.POINTER(ct.c_void_p)]
        item_iid = guid('43826d1e-e718-42ee-bc55-a1e261c37bfe')
        check(shell.SHCreateItemFromParsingName(str(path.resolve()), None, ct.byref(item_iid), ct.byref(item)))
        check(invoke(operation, 5, wt.DWORD)(operation, 0x80000 | 0x100000 | 0x40 | 0x10 | 0x400 | 4))
        check(invoke(operation, 18, ct.c_void_p, ct.c_void_p)(operation, item, None))
        check(invoke(operation, 21)(operation))
        aborted = wt.BOOL()
        check(invoke(operation, 22, ct.POINTER(wt.BOOL))(operation, ct.byref(aborted)))
        if aborted.value or path.exists():
            raise OSError('Windows did not recycle the original file')
    finally:
        if item:
            invoke(item, 2)(item)
        if operation:
            invoke(operation, 2)(operation)
        ole.CoUninitialize()


def replace_original(temp, output, permanently_delete=False):
    # Keep a recoverable on-disk original until the replacement has been published.
    backup_dir = Path(tempfile.mkdtemp(prefix='.archiver-original-', dir=output.parent))
    backup = backup_dir / output.name
    try:
        output.rename(backup)
        try:
            os.replace(temp, output)
        except Exception:
            backup.rename(output)
            raise
        try:
            if permanently_delete:
                backup.unlink()
            else:
                recycle_file(backup)
        except Exception as exc:
            raise OSError(f'Transcode saved to {output}. Original retained at {backup}: {exc}') from exc
    finally:
        if not backup.exists():
            backup_dir.rmdir()


def start_queue():
    with LOCK:
        if not any(j['status'] == 'queued' for j in STATE['jobs']):
            raise ValueError('Add files to the queue first')
        WAKE.set()


def copy_job(job, temp):
    total = Path(job['source']).stat().st_size
    done = 0
    with open(job['source'], 'rb') as src, open(temp, 'wb') as dst:
        while chunk := src.read(4 * 1024 * 1024):
            if job['cancel']:
                return
            dst.write(chunk)
            done += len(chunk)
            with LOCK:
                job['percent'] = done / max(total, 1) * 100
        dst.flush()
        os.fsync(dst.fileno())
    shutil.copystat(job['source'], temp)


def worker():
    global PROCESS
    while True:
        WAKE.wait()
        with LOCK:
            job = next((j for j in STATE['jobs'] if j['status'] == 'queued'), None)
            if not job:
                WAKE.clear()
                continue
            job['status'] = 'running'
        output = Path(job['output'])
        temp = None
        try:
            mode = job['settings']['mode']
            fd, tmp = tempfile.mkstemp(prefix='.archiver-', suffix=output.suffix, dir=output.parent)
            os.close(fd)
            temp = Path(tmp)
            if mode in ['copy', 'move']:
                copy_job(job, temp)
            else:
                cmd = command_for(Path(job['source']), temp, job['settings'])
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                with LOCK:
                    PROCESS = process
                    if job['cancel']:
                        process.terminate()
                def logs():
                    # FFmpeg terminal stats use carriage returns. Universal newline translation handles both.
                    for line in process.stderr:
                        with LOCK:
                            job['log'].append(line.rstrip())
                reader = threading.Thread(target=logs, daemon=True)
                reader.start()
                for line in process.stdout:
                    key, _, value = line.strip().partition('=')
                    with LOCK:
                        if key in ['speed', 'fps']:
                            job[key] = value
                        elif key == 'out_time_us':
                            try:
                                seconds = int(value) / 1_000_000
                                job['percent'] = min(99.9, seconds / max(job['duration'], .001) * 100)
                                speed = float(job['speed'].rstrip('x'))
                                job['eta'] = max(0, (job['duration'] - seconds) / speed) if speed > 0 else None
                            except ValueError:
                                pass
                code = process.wait()
                reader.join()
                process.stdout.close()
                process.stderr.close()
                with LOCK:
                    PROCESS = None
                if code and not job['cancel']:
                    raise ValueError('FFmpeg failed. See verbose output for details. Hardware encoders also require compatible hardware and drivers.')
            with LOCK:
                if job['cancel']:
                    job['status'] = 'cancelled'
                else:
                    if not temp.stat().st_size:
                        raise ValueError('The output file is empty')
                    if mode == 'overwrite':
                        verified = probe(temp)
                        if verified['duration'] <= 0:
                            raise ValueError('Output validation failed: no video duration')
                        replace_original(temp, output, job['settings'].get('deleteOriginal') is True)
                    else:
                        # Exclusive creation prevents overwriting a file created after this job was queued.
                        try:
                            os.link(temp, output)
                        except OSError:
                            with open(temp, 'rb') as src, open(output, 'xb') as dst:
                                try:
                                    shutil.copyfileobj(src, dst)
                                except BaseException:
                                    dst.close()
                                    output.unlink(missing_ok=True)
                                    raise
                        if mode == 'move':
                            Path(job['source']).unlink()
                    job.update(status='completed', percent=100, eta=0)
        except Exception as exc:
            with LOCK:
                job.update(status='cancelled' if job['cancel'] else 'failed', error=str(exc))
        finally:
            if temp:
                temp.unlink(missing_ok=True)
            with LOCK:
                PROCESS = None


class Handler(BaseHTTPRequestHandler):
    def valid_host(self):
        return self.headers.get('Host') in [f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}']

    def log_message(self, *_):
        pass

    def send(self, data, status=200, content_type='application/json'):
        body = json.dumps(data).encode() if content_type == 'application/json' else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.valid_host():
            return self.send({'error': 'Invalid host'}, 403)
        url = urlparse(self.path)
        if url.path == '/':
            html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN)
            return self.send(html.encode(), content_type='text/html; charset=utf-8')
        if url.path in ['/app.js', '/style.css']:
            file = ROOT / 'web' / url.path[1:]
            return self.send(file.read_bytes(), content_type='text/javascript' if file.suffix == '.js' else 'text/css')
        if self.headers.get('X-Token') != TOKEN and parse_qs(url.query).get('token', [''])[0] != TOKEN:
            return self.send({'error': 'Unauthorized'}, 403)
        if url.path == '/api/state':
            with LOCK:
                return self.send({'files': list(STATE['files'].values()), 'scan': STATE['scan'], 'jobs': [{**j, 'log': list(j['log'])} for j in STATE['jobs']], 'queue_running': WAKE.is_set(), 'ffmpeg': STATE['ffmpeg'], 'ffprobe': STATE['ffprobe'], 'encoders': STATE['encoders']})
        if url.path in ['/api/thumbnail', '/api/media']:
            query = parse_qs(url.query)
            item = STATE['files'].get(query.get('id', [''])[0])
            if not item:
                return self.send({'error': 'File not found'}, 404)
            path = Path(item['path'])
            if url.path == '/api/thumbnail':
                try:
                    second = max(0, min(float(query.get('t', ['0'])[0]), max(0, item['duration'] - .1)))
                    target = Path(CACHE.name) / f"{item['id']}-{int(second)}.jpg"
                    if not target.exists():
                        result = run([STATE['ffmpeg'], '-v', 'error', '-ss', str(second), '-i', str(path), '-frames:v', '1', '-vf', 'scale=480:-2', '-y', str(target)], 20)
                        if result.returncode or not target.exists():
                            return self.send({'error': 'Preview unavailable'}, 422)
                    return self.send(target.read_bytes(), content_type='image/jpeg')
                except Exception:
                    return self.send({'error': 'Preview unavailable'}, 422)
            return self.send({'error': 'Use thumbnail scrubbing'}, 404)
        self.send({'error': 'Not found'}, 404)

    def do_POST(self):
        if not self.valid_host() or self.headers.get('X-Token') != TOKEN:
            return self.send({'error': 'Unauthorized'}, 403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length < 1_000_000:
                raise ValueError('Invalid request size')
            body = json.loads(self.rfile.read(length))
            path = urlparse(self.path).path
            if path == '/api/config':
                with LOCK:
                    if any(j['status'] in ['running', 'queued'] for j in STATE['jobs']) or STATE['scan']['running']:
                        raise ValueError('Wait for scans and the queue to finish before changing tools')
                    configure(body['ffmpeg'], body['ffprobe'])
            elif path == '/api/browse':
                return self.send({'directory': browse_directory(body.get('initial', ''))})
            elif path == '/api/stop-scan':
                with LOCK:
                    if STATE['scan']['running']:
                        SCAN_STOP.set()
                        STATE['scan']['stopping'] = True
            elif path == '/api/scan':
                with LOCK:
                    if STATE['scan']['running']:
                        raise ValueError('A scan is already running')
                    if not STATE['encoders']:
                        raise ValueError('Configure FFmpeg and FFprobe first')
                    SCAN_STOP.clear()
                    STATE['scan'] = {'running': True, 'done': 0, 'total': 0, 'errors': []}
                threading.Thread(target=scan, args=(body['directory'], bool(body.get('recursive'))), daemon=True).start()
            elif path == '/api/queue':
                enqueue(body['ids'], body['settings'], body.get('auto_start') is True)
            elif path == '/api/recommend-quality':
                with LOCK:
                    items = [STATE['files'][fid] for fid in body.get('ids', []) if fid in STATE['files']]
                    return self.send(recommend_quality(items, body['settings']))
            elif path == '/api/naming-preview':
                with LOCK:
                    items = [STATE['files'][fid] for fid in dict.fromkeys(body.get('ids', [])) if fid in STATE['files']]
                    if not items:
                        items = [{'path': 'Video.mp4', 'width': 1920, 'height': 1080, 'fps': 30}]
                    names = [output_name(item, body['settings'], index) for index, item in enumerate(items[:3], 1)]
                return self.send({'names': names, 'example': not bool(body.get('ids'))})
            elif path == '/api/start':
                start_queue()
            elif path == '/api/cancel':
                with LOCK:
                    job = next(j for j in STATE['jobs'] if j['id'] == body['id'])
                    if job['status'] in ['queued', 'running']:
                        job['cancel'] = True
                        if job['status'] == 'queued':
                            job['status'] = 'cancelled'
                        elif PROCESS:
                            PROCESS.terminate()
            elif path == '/api/clear':
                with LOCK:
                    STATE['jobs'] = [j for j in STATE['jobs'] if j['status'] in ['queued', 'running']]
            else:
                raise ValueError('Unknown action')
            self.send({'ok': True})
        except Exception as exc:
            self.send({'error': str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser(description='Archiver local video utility')
    parser.add_argument('--version', action='version', version=f'Archiver {VERSION}')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        configure(STATE['ffmpeg'], STATE['ffprobe'])
    except Exception:
        pass
    threading.Thread(target=worker, daemon=True).start()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Archiver is running at http://127.0.0.1:{args.port} — Ctrl+C to quit.')
    if not args.no_browser:
        webbrowser.open(f'http://127.0.0.1:{args.port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        with LOCK:
            if PROCESS:
                PROCESS.terminate()
        server.server_close()


if __name__ == '__main__':
    main()
