"""Archiver: dependency-free local FFmpeg library and encoding queue."""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import math
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
sys.path.insert(0, str(ROOT / '.dependencies'))
from quality import Analyzer, POLICIES, CODEC_ESTIMATES, candidates, fingerprint, preset_args, validate_source
import ab_av1
import prores
import proxy_media
import tool_config
import dependency_setup
import folder_history
import exclusion_preferences
import output_presets
import notification_history
import import_filters
import output_names
import metadata_cache
import import_metadata
import import_admission
import sample_preview
import hardware_queue
import workflow_store
import preservation
import output_verification
import encode_reports
import replacement_stage
import storage_checks
import comparison
import watch_folders
from preview_work import PreviewWork
import motion
import motion_selection
import test_levels
import test_folders
import adaptive_testing
VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
VIDEO_EXT = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v', '.mpeg', '.mpg', '.mts', '.m2ts', '.ts', '.wmv', '.flv', '.vob', '.ogv'}
ENCODERS = {'h264': ['libx264', 'h264_nvenc', 'h264_qsv', 'h264_amf'], 'hevc': ['libx265', 'hevc_nvenc', 'hevc_qsv', 'hevc_amf'], 'av1': ['libsvtav1', 'libaom-av1', 'av1_nvenc', 'av1_qsv', 'av1_amf']}
TOKEN = secrets.token_urlsafe(32)
STATE = {'files': {}, 'jobs': [], 'queue_paused': False, 'ffmpeg': shutil.which('ffmpeg') or '', 'ffprobe': shutil.which('ffprobe') or '', 'encoders': [], 'scan': {'running': False, 'done': 0, 'total': 0, 'errors': []}}
LOCK = threading.RLock()
WAKE = threading.Event()
SCAN_STOP = threading.Event()
BROWSE_LOCK = threading.Lock()
PREVIEW_WORK = PreviewWork()
PROCESS = None
PROCESSES = {}
QUEUE_ADMISSION = hardware_queue.Admission()
STATE['parallel_hardware'] = True
CACHE = tempfile.TemporaryDirectory(prefix='archiver-')
MEDIA_LOCK = threading.Lock()
VERIFY_LOCK = threading.Lock()
TEST_JOBS = []
TEST_FILES = {}
TEST_SCAN = {'running': False, 'done': 0, 'errors': []}
TEST_SCAN_STOP = threading.Event()
TEST_WAKE = threading.Event()
TEST_PAUSED = False
QUALITY_CACHE = {}
AUTO_REPORTS = {}
SHUTTING_DOWN = threading.Event()
WORKFLOW_OPTIONS=dict(workflow_store.DEFAULTS)
RECOVERY={'jobs':[],'tests':[],'error':''}
STORAGE={'locations':[],'blocked':False,'warning':False}
WATCH_STATE={'rules':[]}
WORKFLOW_ERROR=''
WORKFLOW_LOAD_WARNING=''
WORKFLOW_READY=False
PROFILE_STATUS={}
CHECKPOINT_LOCK=threading.Lock()


def checkpoint():
    with CHECKPOINT_LOCK:
        if SHUTTING_DOWN.is_set() or not WORKFLOW_READY or RECOVERY['jobs'] or RECOVERY['tests'] or RECOVERY.get('error'):return
        with LOCK:
            jobs=workflow_store.clean(STATE['jobs']);tests=workflow_store.clean([{**j,'recoverySource':j.get('recoverySource') or next((f for f in STATE['files'].values() if f['path']==j['source']),None)} for j in TEST_JOBS])
        workflow_store.save(VERSION,jobs if WORKFLOW_OPTIONS['recovery'] else [],tests if WORKFLOW_OPTIONS['recovery'] else [])


def restore_queues(discard=False):
    global TEST_PAUSED
    with LOCK:
        if RECOVERY.get('loading'):raise ValueError('Queue restoration is already running')
        if RECOVERY.get('error') and not discard:raise ValueError(RECOVERY['error'])
        if STATE['jobs'] or TEST_JOBS:raise ValueError('Restore or dismiss the saved queue before adding new jobs')
        saved_jobs=list(RECOVERY['jobs']);saved_tests=list(RECOVERY['tests'])
        RECOVERY.update(loading=True,done=0,total=len(saved_jobs)+len(saved_tests));STATE['queue_paused']=True;WAKE.clear();TEST_PAUSED=True;TEST_WAKE.clear()
    try:
        if RECOVERY.get('error') and discard:
            journal=workflow_store.journal(VERSION)
            if journal.exists():journal.rename(journal.with_suffix('.unreadable-'+str(int(time.time()))+'.json'))
        restored=[];tests=[];files={}
        if not discard:
            for saved in saved_jobs:
                if SHUTTING_DOWN.is_set():raise InterruptedError('Queue restoration interrupted; saved records were retained')
                job=workflow_store.restored_job(saved,VERSION);restored.append(job)
                item=job.get('settings',{}).get('sourceMetadata')
                if item:files[item['id']]=item
                with LOCK:RECOVERY['done']+=1
            for saved in saved_tests:
                job=dict(saved)
                if job['status'] in ('queued','waiting','running'):
                    job.update(status='queued',cancel=False,phase='Restored · Waiting to restart',percent=0,result=None,progress={},activity=[],error='')
                    job['outputDirectory']=str(test_folders.planned(job['directory']))
                tests.append(job)
                if job.get('recoverySource'):files[job['recoverySource']['id']]=job['recoverySource']
                with LOCK:RECOVERY['done']+=1
        with LOCK:
            STATE['jobs'].extend(restored);TEST_JOBS.extend(tests);STATE['files'].update(files)
            RECOVERY.update(jobs=[],tests=[],error='',loading=False)
        for job in restored:
            if job['status']=='failed':notify_queue_result(job,'encoding')
        checkpoint()
    finally:
        with LOCK:RECOVERY['loading']=False


def watch_dispatch(file,rule,stamp):
    if SHUTTING_DOWN.is_set():raise ValueError('Archiver is shutting down. Retry this file after restarting.')
    if RECOVERY['jobs'] or RECOVERY['tests']:raise ValueError('Restore or dismiss the saved queue before watching new files')
    require_video_tools()
    with LOCK:
        if any(j['source']==str(file) and j.get('watchStamp')==stamp for j in [*STATE['jobs'],*TEST_JOBS]):return
    item=probe(file)
    if [file.stat().st_size,file.stat().st_mtime_ns]!=stamp:raise ValueError('File is still changing. Retry when copying or recording finishes.')
    if SHUTTING_DOWN.is_set():raise ValueError('Archiver is shutting down. Retry this file after restarting.')
    preset=next((p for p in output_presets.load()['presets'] if p['id']==rule['presetId']),None)
    if not preset:raise ValueError('The saved preset was deleted. Edit this watch rule and choose another preset.')
    config={**preset['settings'],'mode':'directory','deleteOriginal':False,'confirmDelete':False}
    if config.get('qualityMode')=='proxy':config.update(proxyScale='2' if config.get('outputPreset')=='proxy-half' else '4',proxyCodec=config.get('proxyCodec',config.get('outputCodec','prores')))
    destination=Path(rule['destination'])/file.parent.relative_to(Path(rule['source']));destination.mkdir(parents=True,exist_ok=True);config['destination']=str(destination)
    if config.get('qualityMode')=='proxy':config['proxyLocation']='custom'
    with LOCK:STATE['files'][item['id']]=item
    if config.get('qualityMode')=='auto':
        config.update(autoEngine='ab-av1',abTarget='perceptual',abCodec=config['outputCodec'])
        enqueue_tests([item['id']],config,encode_settings=config,encode_auto_start=rule['autoStart'],auto_start=rule['autoStart'])
        with LOCK:TEST_JOBS[-1]['watchStamp']=stamp
    else:
        enqueue([item['id']],config,auto_start=rule['autoStart'])
        with LOCK:STATE['jobs'][-1]['watchStamp']=stamp
    checkpoint()


def watch_worker():
    global WATCH_STATE
    engine=watch_folders.Engine(VIDEO_EXT,watch_dispatch,lambda msg,level:notification_history.add('Watch folders',msg,level))
    while not SHUTTING_DOWN.is_set():
        try:
            if not STATE['scan']['running'] and not RECOVERY['jobs'] and not RECOVERY['tests'] and dependency_status()['ready']:engine.tick()
            with watch_folders.LOCK:WATCH_STATE=watch_folders.public()
        except Exception as exc:WATCH_STATE={**WATCH_STATE,'error':str(exc)}
        SHUTTING_DOWN.wait(5)


def workflow_worker():
    global STORAGE,WORKFLOW_ERROR
    while not SHUTTING_DOWN.is_set():
        try:
            with LOCK:jobs=list(STATE['jobs'])
            STORAGE=storage_checks.snapshot(jobs)
            if WORKFLOW_OPTIONS['storage']:
                for job in jobs:
                    if job['status']=='running' and not job.get('committing'):
                        try:storage_checks.guard(job)
                        except (OSError,ValueError) as exc:
                            with LOCK:
                                job['storagePaused']=str(exc);STATE['queue_paused']=True;WAKE.clear();process=PROCESSES.get(job['id'])
                            if process:
                                try:process.terminate()
                                except OSError:pass
            checkpoint()
            WORKFLOW_ERROR=''
        except Exception as exc:WORKFLOW_ERROR=str(exc)
        SHUTTING_DOWN.wait(2)


def profile_worker():
    # Network source validation must never delay storage monitoring/checkpoints.
    while not SHUTTING_DOWN.is_set():
        with LOCK:reports=workflow_store.clean(auto_reports())
        for report in reports:
            if SHUTTING_DOWN.is_set():return
            try:PROFILE_STATUS[report['id']]=usable_profiles(report)
            except (OSError,ValueError,TypeError,KeyError):PROFILE_STATUS[report['id']]=[]
        SHUTTING_DOWN.wait(2)


def auto_reports():
    reports = {**AUTO_REPORTS, **{j['id']: j for j in TEST_JOBS if (j.get('result') or {}).get('profiles')}}
    return list(reports.values())


def usable_profiles(job, settings=None):
    if job.get('status') != 'completed' or not (job.get('result') or {}).get('profiles'):
        return []
    if settings and any(job['settings'].get(k) != settings.get(k) for k in ['encodingMode', 'hardwareBackend', 'container', 'autoEngine', 'abTarget', 'abCodec']):
        return []
    if settings and job['settings'].get('autoEngine') == 'ab-av1' and ab_av1.target_for(job['settings']) != ab_av1.target_for(settings):
        return []
    valid = []
    for name, key in job['result'].get('profileKeys', {}).items():
        try:
            current = fingerprint({'path': job['source']}, {**job['settings'], 'qualityMode': name}, STATE['ffmpeg'], STATE['ffprobe'])
            if key == current and name in job['result']['profiles']:
                winner=job['result']['profiles'][name].get('winner',{})
                if winner.get('encoder','').endswith('_qsv') and not 1<=winner.get('qualityValue',0)<=51:continue
                valid.append(name)
        except OSError:
            pass
    return valid


class EstimateError(ValueError):
    def __init__(self,code,message):
        super().__init__(message);self.code=code


def validate_estimate_source(item):
    if item.get('color_transfer') in ('smpte2084','arib-std-b67') or item.get('pixel_format') not in ('yuv420p','yuvj420p'):
        raise EstimateError('source_format',f"{item['name']}: Automated (Estimate) supports 8-bit SDR YUV 4:2:0 sources, including full range. Use Manual for this source format.")
    if any(not isinstance(item.get(k),(int,float)) or not math.isfinite(item[k]) or item[k]<=0 for k in ('width','height','fps','duration')) or item['width']%2 or item['height']%2:
        raise EstimateError('source_timing',f"{item['name']}: duration, frame rate and even video dimensions are required for Automated (Estimate).")


def source_preset(item, settings):
    """Documentation-guided codec/bitrate estimates; not measured equivalence."""
    settings=match_container(item,settings)
    name = settings.get('sourcePreset', '100')
    if name not in ['100', '75', '50', 'optimized']:
        raise ValueError('Choose an Estimated bitrate level')
    validate_estimate_source(item)
    rate = item.get('video_bitrate', 0)
    if not rate or rate <= 0:
        raise EstimateError('missing_video_bitrate',f"{item['name']}: reported video bitrate is unavailable. Automated (Estimate) needs this value; choose Manual or run a quality test.")
    source_codec = item['codec']
    if source_codec not in CODEC_ESTIMATES['relativeBitrate']:
        raise EstimateError('unsupported_codec',f"{item['name']}: this source codec has no bitrate conversion model. Choose Manual or run a quality test.")
    method = settings.get('encodingMode')
    if method not in ['software', 'hardware']:
        raise ValueError('Choose software or hardware encoding')
    backend = settings.get('hardwareBackend', 'nvenc')
    if backend not in ['nvenc', 'qsv', 'amf']:
        raise ValueError('Choose a hardware backend')
    def encoder_for(codec):
        choices = ENCODERS.get(codec, [])
        choices = [e for e in choices if not e.endswith(('_nvenc', '_qsv', '_amf'))] if method == 'software' else [e for e in choices if e.endswith('_' + backend)]
        return next((e for e in choices if e in STATE['encoders']), None)
    codec = settings.get('sourceCodec', 'source')
    if codec == 'source':
        codec = source_codec
    if name == 'optimized':
        allowed = [c for c in CODEC_ESTIMATES['relativeBitrate'] if encoder_for(c) and (settings.get('container') != 'webm' or c in ['av1', 'vp9'])]
        if not allowed:
            raise ValueError('No encoder available for optimized source presets. Choose another method or Manual.')
        codec = min(allowed, key=lambda c: CODEC_ESTIMATES['relativeBitrate'][c])
        if CODEC_ESTIMATES['relativeBitrate'][codec] > CODEC_ESTIMATES['relativeBitrate'][source_codec]:
            raise ValueError('Optimized has no available codec at least as efficient as the source. Choose an explicit output codec or Manual.')
    if codec not in ENCODERS:
        raise ValueError('Choose a supported output codec for source presets')
    encoder = encoder_for(codec)
    if not encoder:
        raise EstimateError('encoder_unavailable',f"No {codec.upper()} encoder is available for the selected method. Choose another method or Manual.")
    if settings.get('container', 'mp4') == 'webm' and codec not in ['av1', 'vp9']:
        raise ValueError('This source-codec preset requires MP4/MKV. WebM requires AV1 or VP9.')
    quality_budget = {'100': 1., '75': .75, '50': .5, 'optimized': 1.}[name]
    codec_factor = CODEC_ESTIMATES['relativeBitrate'][codec] / CODEC_ESTIMATES['relativeBitrate'][source_codec]
    resolution = settings.get('resolution', 'original')
    width, height = item['width'], item['height']
    if resolution != 'original':
        if resolution not in ['2160','1440','1080','720','480']:
            raise ValueError('Invalid resolution')
        limit = int(resolution)
        scale = min(1., (round(limit * 16 / 9 / 2) * 2) / width, limit / height)
        output_width, output_height = math.floor(width * scale + .5) // 2 * 2, math.floor(height * scale + .5) // 2 * 2
    else:
        output_width, output_height = width // 2 * 2, height // 2 * 2
    if output_width < 2 or output_height < 2:
        raise ValueError('Source dimensions are too small for the selected output')
    pixel_factor = output_width * output_height / (width * height)
    fps = settings.get('fps', 'original')
    fps_factor = 1.
    if fps != 'original':
        if fps not in ['23.976','24','25','29.97','30','50','59.94','60']:
            raise ValueError('Invalid frame rate')
        if not item.get('fps') or not math.isfinite(item['fps']) or item['fps'] <= 0:
            raise ValueError('Reported source frame rate is unavailable. Keep original frame rate or use Manual.')
        fps_factor = float(fps) / item['fps']
    bitrate_ratio = codec_factor * quality_budget * pixel_factor * fps_factor
    target = rate * bitrate_ratio / 1_000_000
    if not .1 <= target <= 1000:
        raise EstimateError('bitrate_range',f"{item['name']}: estimated video bitrate ({target:g} Mbps) is outside the supported 0.1–1000 Mbps range. Use Manual.")
    return {**settings, 'qualityMode': 'custom', 'requestedQualityMode': 'source', 'sourcePreset': name,
            'codec': codec, 'encoder': encoder, 'bitrate': 'custom', 'customBitrate': target,
            'sourceEstimate': {'version': CODEC_ESTIMATES['version'], 'inputCodec': source_codec,
                               'outputCodec': codec, 'codecFactor': codec_factor, 'qualityBudget': quality_budget,
                               'bitrateRatio': bitrate_ratio, 'pixelFactor': pixel_factor, 'fpsFactor': fps_factor,
                               'outputWidth': output_width, 'outputHeight': output_height, 'outputFps': item.get('fps') if fps == 'original' else float(fps), 'measured': False},
            'resolution': resolution, 'fps': fps, 'encoderPriority': 'balanced'}


def quality_analysis(item, settings, cancelled, progress, work_directory=None, telemetry=None, previews=None):
    settings = {**settings, 'priority': 'balanced', 'testLevel':settings.get('testLevel') or 'balanced'}
    test_levels.policy(settings['testLevel'])
    if settings.get('qualityMode') not in POLICIES:
        raise ValueError('Choose an automatic quality target')
    validate_source(item)
    if cancelled():
        raise InterruptedError('Quality test cancelled')
    key = fingerprint(item, settings, STATE['ffmpeg'], STATE['ffprobe'])
    # A newly scouted job must validate its own random windows, not a prior job's.
    if key not in QUALITY_CACHE or item.get('_motionSelection'):
        if settings.get('autoEngine') == 'ab-av1' and work_directory is None:
            work_directory = test_folders.create(Path(item['path']).parent)
        if settings.get('autoEngine')!='ab-av1':raise ValueError('Auto quality testing uses ab-av1 with XPSNR only')
        if item.get('_motionSelection'):
            analyzer=Analyzer(STATE['ffmpeg'],STATE['ffprobe'],command_for,cancelled,progress,work_directory=work_directory,telemetry=telemetry)
            result=adaptive_testing.analyze(item,settings,STATE['encoders'],STATE['ffmpeg'],STATE['ffprobe'],work_directory,cancelled,progress,telemetry,analyzer,previews)
        else:
            result=ab_av1.analyze(item,settings,STATE['encoders'],STATE['ffmpeg'],STATE['ffprobe'],work_directory,cancelled,progress,telemetry)
        if key != fingerprint(item, settings, STATE['ffmpeg'], STATE['ffprobe']):
            raise ValueError('Source changed during analysis; scan and analyze again')
        if len(QUALITY_CACHE) >= 30:
            QUALITY_CACHE.pop(next(iter(QUALITY_CACHE)))
        QUALITY_CACHE[key] = result
    else:
        progress('Reusing validated results for this source and quality target')
        if telemetry:
            telemetry({'stage': 'cached', 'encodersCompleted': len(QUALITY_CACHE[key]['alternatives']),
                       'encoderTotal': len(QUALITY_CACHE[key]['alternatives']), 'operationPercent': None,
                       **QUALITY_CACHE[key].get('sampling', {})})
            if settings.get('autoEngine') == 'ab-av1':
                telemetry({'engine': 'ab-av1', 'sampleWindows': QUALITY_CACHE[key].get('sampleWindows', ab_av1.windows(item['duration'])), 'sourceDuration': item['duration'],
                           'encoder': QUALITY_CACHE[key]['winner']['encoder'], 'trialsCompleted': 0, 'fromCache': True})
    return QUALITY_CACHE[key]


def scan_test_sources(directory, recursive):
    """Independent source selection for tests; preserves the current media library."""
    try:
        root = Path(directory).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError('Choose an existing source directory')
        for folder, directories, names in os.walk(root, followlinks=False):
            directories[:] = [name for name in directories if not import_filters.is_test_folder(name)]
            if not recursive:
                directories[:] = []
            for name in sorted(names):
                if TEST_SCAN_STOP.is_set():
                    raise InterruptedError('Test source scan stopped')
                path = Path(folder) / name
                if path.suffix.lower() not in VIDEO_EXT:
                    continue
                with LOCK:
                    TEST_SCAN['current'] = str(path)
                try:
                    item = probe(path, cancel=TEST_SCAN_STOP)
                    with LOCK:
                        TEST_FILES[item['id']] = item
                except InterruptedError:
                    raise
                except Exception as exc:
                    with LOCK:
                        TEST_SCAN['errors'].append(f'{name}: {exc}')
                with LOCK:
                    TEST_SCAN['done'] += 1
    except Exception as exc:
        with LOCK:
            TEST_SCAN['errors'].append(str(exc))
    finally:
        with LOCK:
            TEST_SCAN.update(running=False, current='')


def enqueue_tests(ids, settings, directory='', encode_settings=None, encode_auto_start=False, auto_start=False):
    global TEST_PAUSED
    settings = {**settings, 'priority': 'balanced', 'testLevel':settings.get('testLevel') or 'balanced'}
    test_levels.policy(settings['testLevel'])
    if settings.get('qualityMode') == 'auto':
        settings = {**settings, 'autoEngine': 'ab-av1', 'abTarget': 'perceptual'}
    if settings.get('autoEngine') != 'ab-av1':
        raise ValueError('Choose a supported test engine')
    if settings.get('autoEngine') == 'ab-av1':
        settings = {**settings, 'xpsnrTarget': ab_av1.target_for(settings)}
        ab_av1.encoder_for(settings, STATE['encoders'])
        if not ab_av1.binary():
            raise ValueError('ab-av1 executable is missing from the tools folder')
        if settings.get('abTarget') not in [*POLICIES, 'suite']:
            raise ValueError('Choose an ab-av1 quality target')
    metric = 'xpsnr'
    if not STATE.get(metric):
        raise ValueError('Quality tests need FFmpeg with ' + 'XPSNR')
    if settings.get('qualityMode') not in [*POLICIES, 'auto']:
        raise ValueError('Choose Auto to generate measured presets')
    if settings.get('container') not in ['mp4', 'mkv', 'webm', 'mov', 'source']:
        raise ValueError('Choose an output container')
    candidates(STATE['encoders'], settings.get('encodingMode'), settings.get('priority'), settings['container'], settings.get('hardwareBackend', 'nvenc'))
    pool_directory=STATE.get('scan',{}).get('directory')
    if not (directory and directory.strip()) and pool_directory:
        pool_root=Path(pool_directory).resolve()
        if pool_root.is_dir() and all(fid in STATE['files'] and Path(STATE['files'][fid]['path']).resolve().is_relative_to(pool_root) for fid in ids):
            directory=str(pool_root)
    destination = Path(directory).expanduser().resolve(strict=True) if directory and directory.strip() else None
    if destination is not None and not destination.is_dir():
        raise ValueError('Choose an existing test output directory')
    if not ids:
        raise ValueError('Choose at least one test video')
    if encode_settings is not None:
        if not isinstance(encode_settings,dict):raise ValueError('Invalid output settings')
        if settings.get('autoEngine')!='ab-av1':raise ValueError('Per-file testing requires ab-av1')
        if any(fid not in STATE['files'] for fid in ids):raise ValueError('Select files in the Media Pool for per-file testing')
        if encode_settings.get('mode','preserve') not in ['preserve','directory','overwrite']:
            raise ValueError('Choose a transcode output action for per-file testing')
        encoder=ab_av1.encoder_for(settings,STATE['encoders'])
        preflight={**encode_settings,**settings,'qualityMode':'custom','requestedQualityMode':'auto','autoPreset':'perceptual',
                   'codec':settings['abCodec'],'encoder':encoder,'testedEncoder':encoder,'encoderPriority':'balanced',
                   'qualityValue':22,'bitrate':'cq' if encoder.endswith('_nvenc') else 'icq' if encoder.endswith('_qsv') else 'crf',
                   'resolution':'original','fps':'original'}
        enqueue(ids,preflight,dry_run=True)
    preferences = {key: settings.get(key) for key in ['qualityMode', 'encodingMode', 'hardwareBackend', 'priority', 'container', 'autoEngine', 'abTarget', 'abCodec', 'xpsnrTarget', 'testLevel']}
    jobs = []
    with LOCK:
        for fid in dict.fromkeys(ids):
            item = TEST_FILES.get(fid) or STATE['files'].get(fid)
            if not item:
                raise ValueError('Test source is no longer available. Load the directory again.')
            require_metadata(item)
            match_container(item, settings)
            validate_source(item)
            test_directory = destination or Path(item['path']).resolve(strict=True).parent
            if any(j['source'] == item['path'] and j['settings'] == preferences and j['status'] in ['queued', 'waiting', 'running'] for j in TEST_JOBS):
                raise ValueError(f"{item['name']} already has a matching test queued")
            job_id = secrets.token_hex(10)
            jobs.append({'id': job_id, 'source': item['path'], 'name': item['name'], 'settings': dict(preferences),
                         'directory': str(test_directory), 'outputDirectory': str(test_folders.planned(test_directory)),
                         'status': 'queued', 'phase': 'Waiting to test', 'cancel': False, 'result': None,
                         'encodeSettings': ({**encode_settings,'_batchSequence':len(jobs)+1} if encode_settings is not None else None),
                         'encodeAutoStart':encode_auto_start is True,
                         'error': '', 'created': time.time(), 'started': None, 'finished': None,
                         'progress': {}, 'activity': [], 'percent': 0,'recoverySource':dict(item)})
        TEST_JOBS.extend(jobs)
        if auto_start is True and not TEST_PAUSED:
            TEST_WAKE.set()
    checkpoint()
    return [j['id'] for j in jobs]


def prepare_test_previews(job, item, plan=None):
    """Fill the same caches served by the UI before expensive analysis starts."""
    directory=Path(job['outputDirectory'])/'thumbnails'
    directory.mkdir(exist_ok=True)
    cancelled=lambda:job['cancel'] or SHUTTING_DOWN.is_set()
    seconds=sorted(set(int(min(item['duration']-.1,item['duration']*i/18)) for i in range(18))) if plan is None else sorted(set(int(w['start']+w['duration']/2) for w in plan))
    def still(second):
        analyzer=Analyzer(STATE['ffmpeg'],STATE['ffprobe'],command_for,cancelled,lambda _:None)
        target=directory/f'{second}.jpg'
        with PREVIEW_WORK.generation('thumbnail',target):
            if target.exists():return
            temporary=directory/f'{second}.preparing.jpg'
            try:
                analyzer.run([STATE['ffmpeg'],'-v','error','-nostdin','-y','-threads','1','-ss',str(second),'-i',item['path'],'-frames:v','1','-filter_threads','1','-vf','scale=320:-2','-threads','1',str(temporary)])
                os.replace(temporary,target)
            finally:temporary.unlink(missing_ok=True)
    def safely(second):
        if cancelled():raise InterruptedError('Preview cancelled')
        try:still(second)
        except (ValueError,OSError):pass
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(safely,seconds))
    # Animated previews use source media directly. Proxies are generated only
    # when a browser requests the fallback endpoint, never on the critical path.


def run_test_job(job):
    started=job.get('started')
    if started is None:started=time.time()
    directory=test_folders.create(job.get('directory') or Path(job['outputDirectory']).parent,started)
    with LOCK:job.update(outputDirectory=str(directory),started=started)
    def progress(message):
        with LOCK:
            job['phase'] = message
            job['activity'] = (job['activity'] + [message])[-100:]
    def telemetry(details):
        with LOCK:
            job['progress'].update(details)
            data = job['progress']
            profile_count = data.get('profileTotal', 1)
            job['percent'] = min(99, ((data.get('profileIndex', 1) - 1) + data.get('searchPercent', data.get('encodersCompleted', 0) / max(1, data.get('encoderTotal', 1)) * 100) / 100) / profile_count * 100)
    item = probe(Path(job['source']), cancel=lambda: job['cancel'], timeout=None)
    plan = ab_av1.windows(item['duration'])
    selection_stamp = (Path(item['path']).stat().st_size, Path(item['path']).stat().st_mtime_ns)
    telemetry({'sourceDuration':item['duration'],'stage':'previews','motionAvailable':bool(STATE.get('vmafmotion')),'nativePreview':{'mime':sample_preview.native_mime(item),'fps':item.get('fps',30)}})
    progress('Preparing timeline thumbnails')
    prepare_test_previews(job,item)
    if job['settings'].get('autoEngine') == 'ab-av1':
        selector = Analyzer(STATE['ffmpeg'], STATE['ffprobe'], command_for, lambda: job['cancel'], progress)
        selection = motion_selection.prepare(selector, item, directory, progress, telemetry, previews=lambda selected: prepare_test_previews(job,item,selected), probe_factory=lambda: Analyzer(STATE['ffmpeg'], STATE['ffprobe'], command_for, lambda: job['cancel'], progress),use_motion=bool(STATE.get('vmafmotion')),level=job['settings'].get('testLevel') or 'balanced')
        if selection_stamp != (Path(item['path']).stat().st_size, Path(item['path']).stat().st_mtime_ns):
            raise ValueError('Source changed while selecting footage; run the test again.')
        item['_motionSelection'] = selection
        plan = selection['windows']
    telemetry({'sampleWindows': plan, 'sourceDuration': item['duration']})
    if not item.get('_motionSelection'):
        prepare_test_previews(job,item,plan)
    sample_motion=[]
    motion_stamp=(Path(item['path']).stat().st_size,Path(item['path']).stat().st_mtime_ns)
    if item.get('_motionSelection',{}).get('sampleMotion'):
        sample_motion=item['_motionSelection']['sampleMotion']
        telemetry({'sampleMotion':sample_motion,'activeSampleIndices':[]})
    elif STATE.get('vmafmotion'):
        telemetry({'stage':'motion','searchEtaText':'','terminalProgress':''})
        motion_analyzer=Analyzer(STATE['ffmpeg'], STATE['ffprobe'], command_for, lambda: job['cancel'], progress)
        for index, window in enumerate(plan):
            progress(f'Measuring source motion · Sample {index+1}/{len(plan)}')
            telemetry({'sampleIndex':index+1,'sampleTotal':len(plan),'activeSampleIndices':[index]})
            try:
                summary=motion.measure(motion_analyzer,item['path'],window,directory,index)
                progress(f"Sample {index+1} vmafmotion · Mean {summary['mean']:.3f} · Peak {summary['peak']:.3f}")
            except InterruptedError:raise
            except (ValueError,OSError) as exc:
                summary={'error':str(exc),'start':window['start'],'duration':window['duration']}
                progress(f'Sample {index+1} motion unavailable: {exc}')
            sample_motion.append(summary)
            telemetry({'sampleMotion':list(sample_motion)})
    else:
        progress('vmafmotion filter unavailable in configured FFmpeg; quality search remains valid.')
        sample_motion=[{'error':'FFmpeg vmafmotion filter unavailable'} for _ in plan]
        telemetry({'sampleMotion':sample_motion})
    if motion_stamp!=(Path(item['path']).stat().st_size,Path(item['path']).stat().st_mtime_ns):
        raise ValueError('Source changed during motion analysis; run the test again.')
    telemetry({'activeSampleIndices':[]})
    sample_motion=motion.rank_samples(sample_motion)
    telemetry({'sampleMotion':sample_motion})
    (directory/'motion-summary.json').write_text(json.dumps({'samples':sample_motion,'method':'Native-resolution source-timed requested windows','relativeLabels':'Within this test only'},indent=2),encoding='utf-8')
    profiles = None
    profile_failures = {}
    profile_keys = {}
    suite_trials = 0
    if job['settings'].get('autoEngine') == 'ab-av1':
        source_key = fingerprint(item, job['settings'], STATE['ffmpeg'], STATE['ffprobe'])
        targets = ['perceptual']
        profiles = {}
        for index, target in enumerate(targets, 1):
            telemetry({'profile': target, 'profileIndex': index, 'profileTotal': len(targets), 'encodersCompleted': 0, 'searchPercent': 0, 'searchEtaText': '', 'terminalProgress': '', 'sampleIndex': None})
            progress(f'Finding settings for {target} ({index}/{len(targets)})')
            try:
                result = quality_analysis(item, {**job['settings'], 'qualityMode': target}, lambda: job['cancel'], progress,
                                          work_directory=directory, telemetry=telemetry,previews=lambda selected: prepare_test_previews(job,item,selected))
                profiles[target] = result
                telemetry({'searchPercent': 100})
                suite_trials += result['trials']
                profile_keys[target] = fingerprint(item, {**job['settings'], 'qualityMode': target}, STATE['ffmpeg'], STATE['ffprobe'])
            except ValueError as exc:
                profile_failures[target] = str(exc)
        if not profiles:
            raise ValueError('No encode met the requested quality target. Original retained. ' + ' | '.join(profile_failures.values()))
        if source_key != fingerprint(item, job['settings'], STATE['ffmpeg'], STATE['ffprobe']):
            raise ValueError('Source changed during testing. Run the test again.')
        result = profiles.get('perceptual') or next(iter(profiles.values()))
    else:
        raise ValueError('Auto quality testing uses ab-av1 with XPSNR only')
    if job['cancel']:
        raise InterruptedError('Quality test cancelled')
    result['sampleMotion']=result.get('sampleMotion') or sample_motion
    result={**result,'preview':False}
    if profiles is not None:
        result = {**result, 'profiles': profiles, 'profileFailures': profile_failures, 'profileKeys': profile_keys, 'trials': suite_trials}
    report = {'source': item['path'], 'settings': job['settings'], 'result': result}
    (directory / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    with LOCK:
        job.update(status='completed', result=result, percent=100, phase='Test complete')
        if profiles:
            if len(AUTO_REPORTS) >= 30:
                AUTO_REPORTS.pop(next(iter(AUTO_REPORTS)))
            AUTO_REPORTS[job['id']] = job

    if job.get('encodeSettings') is not None and not job['cancel']:
        try:
            queue_test_result(job)
        except (ValueError,OSError) as exc:
            with LOCK:job['queueError']='Test completed, but could not add to the encoding queue: '+str(exc)


def queue_test_result(job):
    config={**job['encodeSettings'],**job['settings'],'qualityMode':'auto','autoPreset':'perceptual',
            'autoTestId':job['id'],'resolution':'original','fps':'original'}
    if 'perceptual' not in usable_profiles(job,config):raise ValueError('Test result no longer matches the source or settings')
    source=job.get('recoverySource') or probe(Path(job['source']))
    enqueue([source['id']],config,auto_start=job.get('encodeAutoStart',False),source_items={source['id']:source})
    with LOCK:job['queuedForEncoding']=True
    checkpoint()


def notify_queue_result(job,category):
    try:notification_history.queue_result(job,category)
    except (OSError,ValueError):pass  # History storage cannot turn completed media work into a failure.
    if job.get('reportError'):
        try:notification_history.add('Report not saved',job['reportError'],'error')
        except (OSError,ValueError):pass


def runnable_test_work():
    """A manually held test queue must not reserve encoder capacity."""
    return TEST_WAKE.is_set() and not TEST_PAUSED and any(j['status'] in ('queued','waiting') for j in TEST_JOBS)


def test_worker():
    while True:
        TEST_WAKE.wait()
        with LOCK:
            job = next((j for j in TEST_JOBS if j['status'] == 'queued'), None)
            if TEST_PAUSED or not job:
                TEST_WAKE.clear()
                continue
            job.update(status='waiting', phase='Waiting for the active encode or test to finish')
        acquired = False
        try:
            while not acquired:
                if job['cancel']:
                    raise InterruptedError('Quality test cancelled')
                acquired = MEDIA_LOCK.acquire(timeout=.25)
            with LOCK:
                job.update(status='running', started=time.time(), phase='Inspecting source')
            require_video_tools()
            run_test_job(job)
        except Exception as exc:
            with LOCK:
                job.update(status='cancelled' if job['cancel'] else 'failed', error=str(exc), phase='Test stopped')
        finally:
            if job['status'] != 'completed':
                for name in ['quality-source.mp4', 'quality-candidate.mp4']:
                    (Path(job['outputDirectory']) / name).unlink(missing_ok=True)
            with LOCK:
                job['finished'] = time.time()
            notify_queue_result(job,'test')
            if acquired:
                MEDIA_LOCK.release()



def run(command, timeout=30):
    return subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def browse_directory(initial='',kind=None,fallback=''):
    """Run Tk on a separate process's main thread, independent of HTTP threads."""
    if not BROWSE_LOCK.acquire(blocking=False):
        raise ValueError('A folder picker is already open. Choose a folder or cancel it first.')
    try:
        initial_path=folder_history.initial_folder(initial,kind,fallback)
        report=None
        try:
            if getattr(sys,'frozen',False):
                fd,filename=tempfile.mkstemp(prefix='folder-picker-',suffix='.json',dir=CACHE.name)
                os.close(fd);report=Path(filename)
                command=[sys.executable,'--pick-folder',str(initial_path),str(report)]
            else:
                command=[sys.executable,str(ROOT/'folder_picker.py'),str(initial_path)]
            result = subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',errors='replace',
                                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode:raise ValueError('Could not open the folder picker; paste the folder path or check the application log.')
            directory=json.loads(report.read_text(encoding='utf-8') if report else result.stdout)['directory']
        finally:
            if report:report.unlink(missing_ok=True)
        if directory and not Path(directory).is_dir():
            raise ValueError('The selected directory is no longer available')
        if directory:folder_history.remember(directory,kind)
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
        verified[name+'Version']=result.stdout.splitlines()[0]
    result = run([verified['ffmpeg'], '-hide_banner', '-encoders'])
    available = set(re.findall(r'^\s*V\S*\s+(\S+)', result.stdout, re.M))
    filters = run([verified['ffmpeg'], '-hide_banner', '-filters'])
    if result.returncode or filters.returncode:raise ValueError('FFmpeg could not list its encoders and filters')
    STATE.update({**verified,'tools_verified':True,'ffv1':'ffv1' in available,'framePreview':'mjpeg' in available,
                  'encoders':[e for group in ENCODERS.values() for e in group if e in available],
                  'archive_encoders':[e for e in ['prores_ks'] if e in available],
                  'xpsnr':bool(re.search(r'\bxpsnr\s',filters.stdout)),
                  'vmafmotion':bool(re.search(r'\bvmafmotion\s',filters.stdout))})


TOOL_SETUP={'running':False,'status':'idle','message':'','revision':0}

def tools_busy():
    return TEST_SCAN['running'] or STATE['scan']['running'] or any(j['status'] in ('waiting','running') for j in TEST_JOBS) or any(j['status']=='running' for j in STATE['jobs'])

def start_tool_setup():
    global TEST_PAUSED
    with LOCK:
        if TOOL_SETUP['running']:raise ValueError('Video tools setup is already running')
        if tools_busy():raise ValueError('Wait for scans and the queue to finish before installing tools')
        if os.name!='nt':raise ValueError('Automatic downloads currently support Windows. Select installed tools using their executable paths.')
        STATE['queue_paused']=True;WAKE.clear();TEST_PAUSED=True;TEST_WAKE.clear()
        TOOL_SETUP.update(running=True,status='running',message='Checking installed tools…',revision=TOOL_SETUP['revision']+1)
    threading.Thread(target=install_video_tools,daemon=True).start()

def install_video_tools():
    def progress(message):
        with LOCK:TOOL_SETUP['message']=message
    try:
        base=tool_config.app_directory()
        ff_ready=STATE.get('tools_verified') and all(STATE.get(k) for k in ('xpsnr','vmafmotion','ffv1','encoders')) and all(Path(STATE.get(k) or '').is_file() for k in ('ffmpeg','ffprobe'))
        paths={k:STATE[k] for k in ('ffmpeg','ffprobe')} if ff_ready else dependency_setup.setup(base,VERSION,progress)
        if not ab_av1.installation(recheck=True)['available']:dependency_setup.restore_ab_av1(ab_av1.BINARY,progress)
        progress('Verifying video tools and saving paths…')
        configure(paths['ffmpeg'],paths['ffprobe']);tool_config.save_paths(base,paths)
        if not ab_av1.installation(recheck=True)['available']:raise ValueError('ab-av1 could not be verified')
        with LOCK:TOOL_SETUP.update(running=False,status='success',message='Video tools are ready. Paths saved for future launches.')
    except Exception as exc:
        with LOCK:TOOL_SETUP.update(running=False,status='error',message=str(exc))

def dependency_status():
    missing=[]
    for name in ('ffmpeg','ffprobe'):
        if not STATE.get('tools_verified') or not STATE.get(name) or not Path(STATE[name]).is_file():missing.append('FFmpeg' if name=='ffmpeg' else 'FFprobe')
    if STATE.get('tools_verified'):
        for key,label in [('xpsnr','FFmpeg XPSNR filter'),('vmafmotion','FFmpeg motion filter'),('ffv1','FFmpeg FFV1 encoder')]:
            if not STATE.get(key):missing.append(label)
        if not STATE.get('encoders'):missing.append('A supported FFmpeg video encoder')
    ab=ab_av1.installation()
    if not ab['available']:missing.append('ab-av1')
    if TOOL_SETUP['running']:missing.append('Video tools installation in progress')
    return {'ready':not missing,'missing':missing,'ab_av1':ab,'setup':dict(TOOL_SETUP)}

def require_video_tools():
    status=dependency_status()
    if not status['ready']:raise ValueError('Video tools setup required: '+', '.join(status['missing'])+'. Open Video tools to finish setup.')


def probe(path, cancel=None, timeout=90, light=False):
    command = [STATE['ffprobe'], '-v', 'error', *(['-probesize','1048576','-analyzeduration','1000000'] if light else []), '-show_format', '-show_streams', '-show_chapters', '-of', 'json', str(path)]
    if cancel is None:
        result = run(command, timeout)
    else:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + timeout if timeout is not None else None
        try:
            while True:
                cancelled = cancel() if callable(cancel) else cancel.is_set()
                if cancelled:
                    raise InterruptedError('Media inspection cancelled')
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError(f'FFprobe exceeded {timeout} seconds')
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
    if video.get('pix_fmt') in (None,'','unknown','unspecified'):
        raise ValueError('FFprobe found a video track but could not read its pixel format. Its video index may be incomplete or damaged. Check the source file or try another copy; changing encoding settings will not repair an unreadable index.')

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
    audio_streams=[{'channel_layout':stream.get('channel_layout',''),'bitrate':int(stream.get('bit_rate') or 0),'sample_rate':int(stream.get('sample_rate') or 0),'channels':int(stream.get('channels') or 0)} for stream in data.get('streams',[]) if stream.get('codec_type')=='audio']
    def stream_duration(stream):
        try:
            value=stream.get('duration')
            if value is not None:return float(value)
            text=next((v for k,v in stream.get('tags',{}).items() if k.upper()=='DURATION'),'')
            h,m,sec=text.split(':');return int(h)*3600+int(m)*60+float(sec)
        except (ValueError,TypeError):return 0.
    streams=[{'index':s.get('index',0),'type':s.get('codec_type',''),'codec':s.get('codec_name','?'),'title':s.get('tags',{}).get('title',''),'language':s.get('tags',{}).get('language',''),'disposition':s.get('disposition',{}),'channels':s.get('channels',0),'sampleRate':s.get('sample_rate',''),'duration':stream_duration(s)} for s in data.get('streams',[]) if s.get('codec_type') in ('video','audio','subtitle')]
    return {'videoDuration':stream_duration(video),'videoIndex':video.get('index',0),'streams':streams,'chapters':data.get('chapters',[]),'metadataTags':fmt.get('tags',{}),'sourceMtimeNs':path.stat().st_mtime_ns,'color_primaries':video.get('color_primaries',''),'color_range':video.get('color_range',''),'sample_aspect_ratio':video.get('sample_aspect_ratio','1:1'),'timecode':tags.get('timecode',''),'rotation':next((x.get('rotation',0) for x in video.get('side_data_list',[]) if 'rotation' in x),0),'field_order':video.get('field_order','unknown'),'frame_rate':video.get('avg_frame_rate','0/1'),'audio_streams':audio_streams,'id': secrets.token_hex(12), 'path': str(path), 'name': path.name, 'size': path.stat().st_size, 'codec': video.get('codec_name', '?'), 'width': video.get('width', 0), 'height': video.get('height', 0), 'fps': fps, 'video_bitrate': stream_bitrate, 'rate_mode': rate_mode, 'source_quality': source_quality, 'profile':video.get('profile',''),'color_space':video.get('color_space',''),'pixel_format': video.get('pix_fmt', ''), 'color_transfer': video.get('color_transfer', ''), 'bitrate': int(fmt.get('bit_rate') or 0), 'duration': float(fmt.get('duration') or video.get('duration') or 0), 'audio': ', '.join(dict.fromkeys(s.get('codec_name', '?') for s in data.get('streams', []) if s.get('codec_type') == 'audio')), 'container': fmt.get('format_name', '?')}


def import_workers(options):
    if options.get('parallel') is False:return 1
    workers=options.get('workers',16)
    if workers=='auto':return 16
    if type(workers) is not int or workers not in (4,8,16):
        raise ValueError('Choose Auto, 4, 8, or 16 files at a time')
    return workers


def file_listing(path):
    stat=path.stat()
    return dict(id=secrets.token_hex(12),path=str(path),name=path.name,size=stat.st_size,
                sourceMtimeNs=stat.st_mtime_ns,metadataPending=True,codec='Unknown',width=0,height=0,
                fps=0,duration=0,bitrate=0,video_bitrate=0,audio='',container=path.suffix.lstrip('.'))


def analyze_pool(ids):
    try:
        cache=metadata_cache.Cache();tool=metadata_cache.tool_signature(STATE['ffprobe'])
        for fid in ids:
            if SCAN_STOP.is_set():break
            with LOCK:item=STATE['files'].get(fid)
            if not item:continue
            try:
                with LOCK:STATE['scan'].update(current=item['path'])
                full=import_metadata.read(Path(item['path']),probe,cache,tool,SCAN_STOP)
                with LOCK:STATE['files'][fid]={**full,'id':fid,'metadataPending':False}
            except InterruptedError:break
            except Exception as exc:
                with LOCK:STATE['scan']['errors'].append(f"{item['name']}: {exc}")
            finally:
                with LOCK:STATE['scan']['done']+=1
    finally:
        with LOCK:STATE['scan'].update(running=False,phase='stopped' if SCAN_STOP.is_set() else 'complete',finished=time.time(),current='')
        notification_history.add('Media analysis complete',f"{STATE['scan']['done']} files processed",'error' if STATE['scan']['errors'] else 'success','import')


def require_metadata(item):
    if 'pixel_format' in item and item['pixel_format'] in (None,'','unknown','unspecified'):
        raise ValueError('Video pixel format is unreadable. The video index may be incomplete or damaged; check the source file or try another copy.')
    if item.get('metadataPending'):
        raise ValueError('Select the files in the Media Pool and choose Analyze selected before encoding or testing.')


def scan(directory, recursive, workers=1, excluded_folders=None, skip_parent_copies=False, exclude_test_folders=True, adaptive=False, files_only=False):
    # skip_parent_copies is accepted only for older callers and intentionally ignored.
    excluded=import_filters.folder_names(excluded_folders)
    started = time.time()
    cache=metadata_cache.Cache() if not files_only else None;tool=metadata_cache.tool_signature(STATE['ffprobe']) if not files_only else None
    admission=import_admission.Admission(workers,time.monotonic()) if adaptive and workers>1 else None
    with LOCK:
        STATE['scan'].update(phase='discovering', started=started, finished=None,
                             workers=workers, workerLimit=admission.limit if admission else workers, adaptive=bool(admission), cached=0, inspected=0, fast=0, fallbacks=0, timeouts=0, cachePath=str(cache.path) if cache else '', cacheWarning='', excludedFolders=0, active={}, current='', entries=0, folders=0, recent=[], file_started=None)
        STATE['files'] = {}
    def recent(message):
        STATE['scan']['recent'] = (STATE['scan']['recent'] + [message])[-8:]
    try:
        root = Path(directory).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError('Choose an existing directory')
        with LOCK:STATE['scan']['directory']=str(root)
        paths = []
        def discovery_error(error):
            with LOCK:
                STATE['scan']['errors'].append(str(error))
                recent(f'Skipped folder: {error.filename}')
        for folder, dirs, files in os.walk(root, onerror=discovery_error, followlinks=False):
            if recursive:
                removed=[name for name in dirs if import_filters.is_system_folder(name) or name.casefold() in excluded or (exclude_test_folders and import_filters.is_test_folder(name))]
                dirs[:]=[name for name in dirs if name not in removed]
                with LOCK:
                    STATE['scan']['excludedFolders']+=len(removed)
                    for name in removed:recent(f'Excluded folder: {Path(folder)/name}')
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
        if admission:admission=import_admission.Admission(workers,time.monotonic())
        with LOCK:
            STATE['scan'].update(phase='listing' if files_only else 'probing', current='', file_started=None)
            recent(f'Discovered {len(paths)} video files')
        def inspect(path):
            fresh=False;failed=False
            def notify(event):
                kind,value=event
                with LOCK:
                    scan_state=STATE['scan']
                    if kind=='cached':scan_state['cached']+=1
                    elif kind=='inspected':
                        scan_state['inspected']+=1
                        if value=='fast':scan_state['fast']+=1
                    elif kind=='fallback':scan_state['fallbacks']+=1;recent(f'Reading more metadata: {path.name}')
                    elif kind=='cache-warning' and scan_state['cacheWarning']!=value:scan_state['cacheWarning']=value;recent(value)
            if SCAN_STOP.is_set():
                return
            with LOCK:
                STATE['scan']['active'][str(path)] = time.time()
                STATE['scan'].update(current=' | '.join(STATE['scan']['active']), file_started=min(STATE['scan']['active'].values()))
            try:
                item = file_listing(path) if files_only else import_metadata.read(path,probe,cache,tool,SCAN_STOP,notify)
                fresh=item.get('metadataSource')!='cache'
                with LOCK:
                    STATE['files'][item['id']] = item
                    recent(f"{'Cached' if item.get('metadataSource')=='cache' else 'Inspected'}: {path.name}")
            except InterruptedError:
                return
            except Exception as exc:
                with LOCK:
                    failed=isinstance(exc,TimeoutError)
                    if isinstance(exc,TimeoutError):STATE['scan']['timeouts']+=1
                    STATE['scan']['errors'].append(f'{path.name}: {exc}')
                    recent(f'Skipped: {path.name} — {exc}')
            finally:
                with LOCK:
                    STATE['scan']['active'].pop(str(path), None)
                    STATE['scan']['current'] = ' | '.join(STATE['scan']['active'])
            with LOCK:
                STATE['scan']['done'] += 1
            return fresh,failed
        if workers == 1:
            for path in sorted(paths):
                if SCAN_STOP.is_set():
                    break
                inspect(path)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                remaining=iter(sorted(paths));pending=set();exhausted=False
                while pending or not exhausted:
                    limit=admission.stalled(time.monotonic()) if admission else workers
                    with LOCK:STATE['scan']['workerLimit']=limit
                    while not exhausted and not SCAN_STOP.is_set() and len(pending)<limit:
                        try:path=next(remaining)
                        except StopIteration:exhausted=True;break
                        pending.add(executor.submit(inspect,path))
                    if SCAN_STOP.is_set():exhausted=True
                    if not pending:break
                    completed,pending=wait(pending,timeout=.2,return_when=FIRST_COMPLETED)
                    for future in completed:
                        outcome=future.result()
                        if admission and outcome:admission.observe(time.monotonic(),*outcome)
        if SCAN_STOP.is_set():
            raise InterruptedError('Scan stopped')

    except InterruptedError:
        with LOCK:
            recent('Scan stopped by user; loaded videos retained')
    except Exception as exc:
        with LOCK:
            STATE['scan']['errors'].append(str(exc))
    finally:
        with LOCK:
            STATE['scan'].update(running=False, phase='stopped' if SCAN_STOP.is_set() else 'complete', finished=time.time(), current='', file_started=None)
            scan_summary=dict(STATE['scan'])
        try:
            errors=scan_summary.get('errors',[])
            notification_history.add('Media import stopped' if scan_summary['phase']=='stopped' else 'Media import complete'+(' · Some files failed' if errors else ''),f"{scan_summary.get('done',0)} / {scan_summary.get('total',0)} files processed · {len(errors)} errors",'error' if errors else 'success','import',key='import:'+str(scan_summary.get('started')))
        except (OSError,ValueError):pass


def match_container(item, settings):
    """Resolve the source option per file, never from FFprobe's ambiguous format list."""
    if settings.get('container') != 'source':
        return settings
    container = Path(item['path']).suffix.lower().lstrip('.')
    if container not in ('mp4', 'mkv', 'webm', 'mov'):
        raise ValueError(f"Cannot match the container of {Path(item['path']).name}. Choose MP4, MKV, MOV or WebM explicitly.")
    if container == 'webm' and settings.get('codec', settings.get('abCodec')) not in ('av1', None):
        raise ValueError('Matching a WebM source requires AV1 video. Choose AV1 or another output container.')
    return {**settings, 'container': container}


def command_for(source, output, settings):
    settings=match_container({"path":str(source)},settings)
    if settings.get('container')=='webm' and settings.get('audio','aac') not in ('opus','copy'):
        raise ValueError('WebM requires Opus or Copy original audio. Change the audio codec or output container.')
    command=_base_command_for(source,output,settings)
    return preservation.command(command,settings.get('sourceMetadata') or {},settings)


def _base_command_for(source, output, settings):
    if settings.get('qualityMode') == 'proxy':
        item=settings.get('sourceMetadata') or probe(Path(source))
        encoder=proxy_media.encoder_for(settings,[*STATE.get('archive_encoders',[]),*STATE.get('encoders',[])],item)
        return proxy_media.command(STATE['ffmpeg'],source,output,item,settings,encoder)
    if settings.get('qualityMode') == 'archive':
        return archive_command(source, output, settings)
    encoder = settings.get('encoder')
    codec = settings.get('codec')
    if encoder not in ENCODERS.get(codec, []) or encoder not in STATE['encoders']:
        raise ValueError('No encoder is available for this codec and encoding method. Choose another method or configure FFmpeg.')
    if codec in ['mpeg2', 'mpeg4', 'mjpeg']:
        if settings.get('container', 'mkv') != 'mkv':
            raise ValueError('Extended codecs use MKV in this preview')
        if settings.get('bitrate') in ['crf', 'cqp']:
            raise ValueError('Extended codecs require a bitrate setting; CRF/CQP is supported only for recommended delivery codecs')
    cmd = [STATE['ffmpeg'], '-hide_banner', '-nostdin', '-y', '-i', str(source), '-map', '0:v:0', '-map', '0:a?', '-map_metadata', '0', '-c:v', encoder]
    if settings.get('encoderPriority'):
        cmd += preset_args(encoder, settings['encoderPriority'])
    cmd += ['-fps_mode', 'passthrough'] if settings.get('fps', 'original') == 'original' else []
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
    if settings.get('requestedQualityMode')=='source' and settings.get('sourceMetadata',{}).get('pixel_format')=='yuvj420p':
        filters[-1]+=':in_range=pc:out_range=tv'
        cmd+=['-color_range','tv']
    cmd += ['-vf', ','.join(filters), '-pix_fmt', 'yuvj420p' if codec == 'mjpeg' else 'yuv420p']
    fps = settings.get('fps', 'original')
    if fps != 'original':
        if fps not in ['23.976', '24', '25', '29.97', '30', '50', '59.94', '60']:
            raise ValueError('Invalid frame rate')
        cmd += ['-r', fps]
    bitrate = settings.get('bitrate', 'auto')
    if (settings.get('autoEngine') == 'ab-av1' and settings.get('qualityMode') in POLICIES) or (settings.get('qualityMode') == 'custom' and settings.get('testedEncoder') == encoder and bitrate in ['crf', 'cq', 'icq']):
        try:value = int(settings['qualityValue'])
        except (TypeError,ValueError):raise ValueError('Enter a whole-number quality value') from None
        if encoder != ab_av1.encoder_for(settings, STATE['encoders']):raise ValueError('The encoder does not match the test result. Apply a matching test result first.')
        minimum=1 if encoder.endswith('_qsv') else 0
        maximum=51 if encoder.endswith(('_nvenc','_qsv')) else 63 if codec=='av1' else 51
        if not minimum<=value<=maximum:
            label='ICQ' if encoder.endswith('_qsv') else 'CQ' if encoder.endswith('_nvenc') else 'CRF'
            raise ValueError(f'{label} must be between {minimum} and {maximum}')
        metadata = settings.get('sourceMetadata') or probe(source)
        cmd += ['-g', str(int(metadata['fps'] * 10 + .5)), '-enc_time_base', 'demux']
        if encoder == 'libsvtav1':
            cmd += ['-crf', str(value), '-svtav1-params', f'scd=0:crf={value}']
        elif encoder.endswith('_nvenc'):
            cmd += ['-cq', str(value)]
        elif encoder.endswith('_qsv'):
            cmd += ['-global_quality', str(value), '-look_ahead', '1', '-extbrc', '1', '-look_ahead_depth', '40']
        else:
            cmd += ['-crf', str(value)]
    elif bitrate in ['cq', 'icq']:
        raise ValueError('Apply a tested setting to use CQ / ICQ tuning')
    elif bitrate in ['crf', 'cqp']:
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
            raise ValueError('Enter a target video bitrate in Mbps')
        if not 0.1 <= value <= 1000:
            raise ValueError('Target video bitrate must be between 0.1 and 1000 Mbps')
        cmd += ['-b:v', f'{round(value * 1000)}k']
    elif bitrate in ['auto', 'average']:
        metadata = settings.get('sourceMetadata') or probe(source)
        rate_mode = metadata.get('rate_mode', '')
        source_quality = metadata.get('source_quality')
        hardware = encoder.endswith(('_nvenc', '_qsv', '_amf'))
        same_codec = metadata.get('codec') == codec
        # Never infer CRF/QP or CBR from average bitrate alone.
        if bitrate == 'auto' and same_codec and rate_mode in ['crf', 'cqp'] and source_quality is not None and float(source_quality).is_integer() and ((rate_mode == 'crf' and not hardware) or (rate_mode == 'cqp' and hardware)):
            return command_for(source, output, {**settings, 'bitrate': rate_mode, 'qualityValue': int(source_quality)})
        source_bitrate = metadata.get('video_bitrate', 0)
        if not source_bitrate or source_bitrate <= 0:
            raise ValueError('No reported average video bitrate was found. Choose a quality setting or Target bitrate.' if bitrate == 'average' else 'No reusable quality value or reported video bitrate was found. Choose CRF, CQP, or Target bitrate.')
        target = str(int(source_bitrate))
        cmd += ['-b:v', target]
        if bitrate == 'auto' and rate_mode == 'cbr':
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
    if output.suffix.lower() == '.webm':
        if audio not in ['opus','copy','none']:raise ValueError('WebM requires Opus or copied Opus/Vorbis audio. Choose MKV to preserve other audio codecs.')
        if audio=='copy' and settings.get('sourceMetadata'):
            source_audio={value.strip() for value in settings['sourceMetadata'].get('audio','').split(',') if value.strip()}
            if not source_audio.issubset({'opus','vorbis'}):raise ValueError('The original audio codec cannot be copied into WebM. Choose MKV to preserve it, or encode audio as Opus.')
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


def output_size_estimate(items, settings, reports=()):
    """Budget/sample-derived total; never infer size from an arbitrary CRF."""
    total=0.;unavailable=[];issues=[]
    for item in items:
        try:
            duration=float(item['duration'])
            if not math.isfinite(duration) or duration<=0:raise EstimateError('source_timing','Duration unavailable')
            if settings.get('mode') in ('copy','move'):
                total+=item['size'];continue
            resolved=source_preset(item,settings) if settings.get('qualityMode')=='source' else match_container(item,settings)
            if resolved.get('qualityMode')=='proxy':
                proxy_item={**item,'audio_streams':preservation.audio_metadata(item,resolved)}
                if not proxy_item['audio_streams']:proxy_item['audio']=''
                total+=proxy_media.resolve(proxy_item,resolved)['estimatedBytes'];continue
            if resolved.get('qualityMode')=='archive':
                video=prores.resolve(item,resolved)['estimatedVideoBytes']
                streams=preservation.audio_metadata(item,resolved)
                if item.get('audio') and (not item.get('audio_streams') or any(not s.get('sample_rate') or not s.get('channels') for s in streams)):raise EstimateError('missing_audio_metadata','Audio metadata unavailable')
                audio=sum(s['sample_rate']*s['channels']*24 for s in streams)*duration/8
            else:
                bitrate=resolved.get('bitrate','auto');rate=None
                if resolved.get('qualityMode')=='auto' or bitrate in ('crf','cqp','cq','icq'):
                    if resolved.get('resolution','original')!='original' or resolved.get('fps','original')!='original':raise EstimateError('test_required','A matching test is needed for quality-controlled output at this resolution or frame rate')
                    for report in reversed(list(reports)):
                        if report.get('source')!=item['path'] or report.get('status')!='completed':continue
                        result=report.get('result') or {};result=result.get('profiles',{}).get('perceptual',result);winner=result.get('winner') or {}
                        if resolved.get('qualityMode')=='auto':
                            if resolved.get('autoTestId') and resolved['autoTestId']!=report['id']:continue
                            if not usable_profiles(report,resolved):continue
                        elif resolved.get('testedEncoder')!=winner.get('encoder') or resolved.get('encoder')!=winner.get('encoder') or str(resolved.get('qualityValue'))!=str(winner.get('qualityValue')):continue
                        rate=winner.get('bytesPerSecond',0)*8;break
                    if not rate:raise EstimateError('test_required','Size requires a matching test for each selected file')
                elif bitrate=='custom':rate=float(resolved.get('customBitrate',0))*1000000
                elif bitrate in ('auto','average'):
                    hardware=resolved.get('encoder','').endswith(('_nvenc','_qsv','_amf'))
                    if bitrate=='auto' and item.get('codec')==resolved.get('codec') and item.get('source_quality') is not None and ((item.get('rate_mode')=='crf' and not hardware) or (item.get('rate_mode')=='cqp' and hardware)):raise EstimateError('test_required','Recorded quality needs a test to estimate size')
                    rate=item.get('video_bitrate',0)
                elif re.fullmatch(r'[1-9][0-9]*k',bitrate):rate=int(bitrate[:-1])*1000
                if not rate or not math.isfinite(rate) or rate<=0:raise EstimateError('missing_video_bitrate','Video bitrate unavailable')
                video=rate*duration/8
                audio_mode=resolved.get('audio','aac');streams=preservation.audio_metadata(item,resolved) if item.get('audio_streams') is not None else None
                count=len(streams) if streams is not None else (1 if item.get('audio') else 0)
                if audio_mode=='none' or not count:audio=0
                elif audio_mode=='copy':
                    if streams is not None and all(s.get('bitrate',0)>0 for s in streams):audio=sum(s['bitrate'] for s in streams)*duration/8
                    elif item.get('video_bitrate',0)>0:audio=max(0,item['size']-item['video_bitrate']*duration/8)
                    else:raise EstimateError('missing_audio_metadata','Copied audio size unavailable')
                elif audio_mode in ('aac','mp3','opus'):audio=int(resolved.get('audioBitrate','192k')[:-1])*1000*duration/8*count
                else:raise EstimateError('audio_size_unavailable','Lossless audio size is unavailable; choose a bitrate-based audio codec to estimate it')
            total+=video+audio
        except (ValueError,KeyError,TypeError,OverflowError) as exc:
            unavailable.append(str(exc));issues.append({'id':item.get('id'),'name':item.get('name',Path(item.get('path','Video')).name),'code':getattr(exc,'code','estimate_unavailable'),'message':str(exc)})
    source=sum(item.get('size',0) for item in items)
    return {'count':len(items),'estimatedCount':len(items)-len(unavailable),'bytes':round(total) if items and not unavailable else None,'sourceBytes':source,'reduction':(1-total/source) if source and not unavailable else None,'reason':unavailable[0] if unavailable else '', 'reasonCode':issues[0]['code'] if issues else '', 'issues':issues, 'partialBytes':round(total) if unavailable and len(unavailable)<len(items) else None, 'note':'Estimate includes audio; container overhead and content-dependent bitrate may vary.'}


def encoding_details(items, settings):
    """Explain the exact resolved parameters without probing or executing media."""
    rows=[]
    for item in items:
        try:
            mode=settings.get('qualityMode','custom')
            if mode=='auto':
                rows.append({'name':item['name'],'pending':True,'note':'Apply a completed test result to review its settings.'});continue
            resolved=source_preset(item,settings) if mode=='source' else dict(match_container(item,settings))
            resolved['sourceMetadata']=item
            output=Path('OUTPUT.'+(proxy_media.container_for(resolved) if mode=='proxy' else 'mov' if mode=='archive' else resolved.get('container','mp4')))
            command=command_for(Path(item['path']),output,resolved)
            def arg(*keys):
                for key in keys:
                    if key in command:
                        return command[command.index(key)+1]
                return None
            encoder=arg('-c:v','-c:v:0')
            preset=arg('-preset','-quality','-cpu-used')
            control,value='Target bitrate',arg('-b:v')
            if arg('-crf') is not None:control,value='CRF',arg('-crf')
            elif arg('-cq') is not None:control,value='CQ',arg('-cq')
            elif arg('-qp','-qp_i') is not None:control,value='CQP',arg('-qp','-qp_i')
            elif arg('-global_quality') is not None:
                control,value=('CQP' if arg('-flags:v')=='+qscale' else 'ICQ'),arg('-global_quality')
            elif mode=='proxy' and settings.get('proxyCodec','prores')=='prores':control,value='ProRes profile','422 Proxy · '+str(proxy_media.resolve(item,settings)['width'])+' × '+str(proxy_media.resolve(item,settings)['height'])
            elif mode=='archive':control,value='ProRes profile',prores.resolve(item,resolved)['label']
            if control=='Target bitrate' and value:
                rate=float(value[:-1])*1000 if value.endswith('k') else float(value)
                value=f'{rate/1000000:g} Mbps'
            provenance='Selected manually'
            if mode=='proxy':provenance='Proxy preset · profile-controlled VBR' if settings.get('proxyCodec','prores')=='prores' else 'Proxy preset · short GOP, no B-frames'
            elif mode=='source':provenance='Adjusted bitrate estimate'
            elif settings.get('bitrate')=='auto':
                provenance='Recorded '+control if control in ('CRF','CQP') else 'Reported average video bitrate'
                if arg('-minrate') and arg('-maxrate'):provenance='Reported video bitrate and CBR mode'
            elif settings.get('testedEncoder')==encoder:provenance='Applied test result'
            rows.append({'name':item['name'],'encoder':encoder,'preset':preset or 'Encoder default','presetFlag':'-cpu-used' if '-cpu-used' in command else '-quality' if '-quality' in command else '-preset' if '-preset' in command else '',
                         'conversions':preservation.conversion_notes(item,resolved),'control':control,'value':value,'provenance':provenance,'lookahead':arg('-look_ahead')=='1','command':command})
        except (ValueError,TypeError,KeyError) as exc:rows.append({'name':item.get('name','Video'),'error':str(exc)})
    return {'files':rows,'count':len(items)}


def prores_recommendations(ids,settings):
    results=[]
    for fid in ids:
        item=STATE['files'].get(fid)
        if not item:results.append({'id':fid,'name':'Unknown file','error':'File no longer available'});continue
        try:results.append({'id':fid,'name':item['name'],**prores.resolve(item,settings)})
        except ValueError as exc:results.append({'id':fid,'name':item['name'],'error':str(exc)})
    return results


def archive_command(source, output, settings):
    profile = settings.get('archiveProfile', 'ffv1')
    if profile != 'prores':
        raise ValueError('Only ProRes output is supported')
    encoder = 'prores_ks'
    if encoder not in STATE.get('archive_encoders', []):
        raise ValueError(f'Configured FFmpeg does not provide {encoder}')
    metadata = settings.get('sourceMetadata') or probe(Path(source))
    pixel = metadata.get('pixel_format', '')
    if not pixel or not re.fullmatch(r'[a-zA-Z0-9_]+', pixel):
        raise ValueError('Unknown source pixel format; keep this source unchanged')
    resolved=prores.resolve(metadata,settings)
    # Map all streams: fail rather than silently discarding unsupported streams.
    cmd = [STATE['ffmpeg'], '-hide_banner', '-nostdin', '-y', '-xerror', '-i', str(source), '-map', '0',
           '-map_metadata', '0', '-map_chapters', '0', '-c', 'copy', '-c:v:0', encoder, '-fps_mode:v:0', 'passthrough']
    if output.suffix.lower() != '.mov':
        raise ValueError('ProRes output requires MOV')
    cmd += ['-profile:v:0',str(resolved['profileNumber']),'-pix_fmt:v:0',resolved['pixelFormat'],'-c:a','pcm_s24le','-enc_time_base:v:0','demux']
    if resolved['rgb']:
        matrix='bt709' if metadata['height']>=720 else 'bt601'
        cmd += ['-vf',f'scale=in_range=full:out_range=tv:out_color_matrix={matrix}', '-color_range','tv','-colorspace','bt709' if matrix=='bt709' else 'smpte170m']
    if resolved['profileNumber']>=4:cmd+=['-alpha_bits','16' if resolved['alpha'] else '0']
    return cmd + ['-progress', 'pipe:1', '-stats_period', '0.5', '-stats', str(output)]


def verify_archive(job, output):
    source = job['settings']['sourceMetadata']
    result = probe(output)
    if (result['width'], result['height']) != output_verification.dimensions(source,job['settings']) or abs(result['duration'] - output_verification.expected_duration(source,job['settings'])) > max(.15, 2 / max(source['fps'], 1)):
        raise ValueError('Archival output dimensions or duration changed; original retained')
    resolved=prores.resolve(source,job['settings'])
    aliases=[('proxy',),('lt',),('standard',),('hq',),('4444',),('xq','4444xq')]
    if result.get('profile','').lower().replace(' ','') not in aliases[resolved['profileNumber']]:
        raise ValueError('ProRes output profile did not match the selected profile; original retained')
    if result['codec']!='prores' or ('444' in result['pixel_format'])!=(resolved['profileNumber']>=4) or (resolved['alpha'] and not result['pixel_format'].startswith('yuva')):
        raise ValueError('ProRes chroma or alpha verification failed; original retained')
    analyzer = Analyzer(STATE['ffmpeg'], STATE['ffprobe'], command_for, lambda: job['cancel'], lambda _: None)
    analyzer.run([STATE['ffmpeg'], '-v', 'error', '-xerror', '-i', str(output), '-map', '0:v:0', '-map', '0:a?', '-f', 'null', '-'])



def recommend_quality(items, settings):
    encoder = settings.get('encoder', '')
    codec = settings.get('codec')
    if encoder not in ENCODERS.get(codec, []):
        raise ValueError('Select a codec and encoder first')
    if codec not in ['h264', 'hevc', 'av1']:
        raise ValueError('Quality recommendations support H.264, H.265, and AV1. Set a bitrate manually for extended codecs.')
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
    return {'mode': mode, 'value': min(values), 'note': 'Estimated from source codec, bitrate and frame density; not a recorded CRF/QP or a measured quality result. Uses the most conservative suggestion for this selection.', 'warnings': list(dict.fromkeys(warnings))}


def output_name(item, settings, index=1):
    settings=match_container(item,settings)
    if settings.get('qualityMode')=='proxy':return proxy_media.output_path(item,settings).name
    if settings.get('qualityMode') == 'archive':
        profile = settings.get('archiveProfile', 'ffv1')
        settings = {**settings, 'container': 'mov' if profile == 'prores' else 'mkv',
                    'qualityMode': 'original' if profile == 'copy' else 'archive'}
    source = Path(item['path'])
    action = settings.get('mode', 'preserve')
    if action == 'overwrite':
        return source.name
    naming = settings.get('naming', 'default')
    extension = source.suffix if action in ['copy', 'move'] or settings.get('qualityMode') == 'original' else '.' + settings.get('container', 'mp4')
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
    elif naming in ['resolution', 'framerate', 'quality', 'settings', 'template']:
        width, height = item['width'], item['height']
        resolution = settings.get('resolution', 'original') if action not in ['copy', 'move'] else 'original'
        if resolution != 'original':
            if resolution not in ['2160', '1440', '1080', '720', '480']:
                raise ValueError('Invalid resolution')
            limit = int(resolution)
            ratio = min(1, (round(limit * 16 / 9 / 2) * 2) / width, limit / height)
            width, height = math.floor(width * ratio + .5) // 2 * 2, math.floor(height * ratio + .5) // 2 * 2
        elif action not in ['copy', 'move']:
            width, height = width // 2 * 2, height // 2 * 2
        fps = settings.get('fps', 'original') if action not in ['copy', 'move'] else 'original'
        fps = f"{item['fps']:.3f}".rstrip('0').rstrip('.') if fps == 'original' else fps
        quality = settings.get('bitrate', 'auto')
        if quality in ['crf', 'cqp', 'cq', 'icq']:
            quality += '-' + str(settings.get('qualityValue', ''))
        elif quality == 'custom':
            quality = str(settings.get('customBitrate', '')) + 'Mbps'
        quality = 'original' if action in ['copy', 'move'] else settings.get('qualityMode') if settings.get('qualityMode', 'custom') != 'custom' else {'auto': 'source-bitrate', 'average': 'source-bitrate'}.get(quality, quality)
        requested_quality = settings.get('requestedQualityMode', settings.get('qualityMode'))
        if requested_quality == 'auto':
            quality = 'auto-' + settings.get('autoPreset', 'pending')
        elif requested_quality == 'source':
            quality = 'source-' + settings.get('sourcePreset', '100')
        tags = {'resolution': f'{width}x{height}', 'framerate': f'{fps}fps', 'quality': quality}
        if naming == 'template':
            template = settings.get('filenameTemplate', '{original}_{archiver}')
            if not isinstance(template, str) or len(template) > 500:
                raise ValueError('Filename template is too long')
            if action == 'preserve' and '{original}' not in template:
                raise ValueError('Keep originals requires Original name in the filename')
            if action == 'preserve' and not re.sub(r'[\s_.-]+','',template.replace('{original}','').replace('{archiver}','')) and '{archiver}' not in template:
                template += ('' if template.endswith('_') else '_') + '{archiver}'
            tags.update(archiver='archiver',original=source.stem, codec={'h264':'H264','hevc':'H265','av1':'AV1','prores':'ProRes'}.get(settings.get('abCodec') if settings.get('requestedQualityMode') == 'auto' else settings.get('codec'), settings.get('codec', 'video')), sequence=f'{index:03d}')
            if settings.get('archiveProfile') == 'prores' and settings.get('qualityMode') == 'archive':
                tags['codec'] = 'ProRes'
            def substitute(match):
                key = match.group(1)
                if key not in tags:
                    raise ValueError('Unknown filename part: ' + key)
                return str(tags[key])
            base = re.sub(r'\{([^{}]+)\}', substitute, template).strip()
            if not base or len(base + extension) > 255 or re.search(r'[<>:"/\\|?*\x00-\x1f{}]', base) or base.endswith(('.', ' ')):
                raise ValueError('Enter a valid filename without path separators or reserved characters (maximum 255 characters)')
            if base.split('.')[0].upper() in ['CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(1, 10)], *[f'LPT{i}' for i in range(1, 10)]]:
                raise ValueError('Choose a filename that is not a reserved device name')
            return base + extension
        suffix = '_' + safe('_'.join(tags.values()) if naming == 'settings' else tags[naming])
    else:
        raise ValueError('Invalid output naming option')
    return source.stem + suffix + extension


def enqueue(ids, settings, auto_start=False, dry_run=False, source_items=None):
    if settings.get('qualityMode') in POLICIES:
        settings = {**settings, 'priority': 'balanced'}
    if RECOVERY['jobs'] or RECOVERY['tests']:raise ValueError('Restore or dismiss the saved queue in Encoding Queue first')
    if settings.get('preservation'):preservation.settings(settings['preservation'])
    if not ids:
        raise ValueError('Select at least one video')
    requested = settings.get('qualityMode', 'custom')
    if requested == 'proxy':
        if settings.get('mode','preserve') not in ('preserve','directory'):raise ValueError('Proxy presets keep originals. Choose Keep originals or Save to another folder.')
        settings={**settings,'requestedQualityMode':'proxy','codec':settings.get('proxyCodec','prores'),'encoder':proxy_media.encoder_for(settings,[*STATE.get('archive_encoders',[]),*STATE.get('encoders',[])]),'container':proxy_media.container_for(settings),'fps':'original','resolution':'original','audio':'pcm_s24le','bitrate':'proxy'}
    if requested == 'archive':
        profile = settings.get('archiveProfile', 'ffv1')
        if profile != 'prores':
            raise ValueError('ProRes is the only supported archival output codec')
        if settings.get('mode', 'preserve') not in ['preserve', 'directory']:
            raise ValueError('Archival mode keeps originals. Choose Keep originals or Save to another folder.')
        settings = {**settings, 'requestedQualityMode': 'archive', 'archiveProfile': profile,
                    'qualityMode': 'original' if profile == 'copy' else 'archive',
                    'container': 'mov' if profile == 'prores' else 'mkv', 'resolution': 'original', 'fps': 'original', 'audio': 'pcm_s24le'}
    auto_report = None
    if requested == 'auto':
        profile = settings.get('autoPreset', '')
        auto_report = next((j for j in reversed(auto_reports()) if (not settings.get('autoTestId') or j['id'] == settings['autoTestId']) and profile in usable_profiles(j, settings)), None)
        if not auto_report:
            raise ValueError('Automated (Test) requires a completed matching test. Set up a quality test, then apply its settings.')
        settings = {**settings, 'autoEngine': auto_report['settings'].get('autoEngine'), 'abTarget': auto_report['settings'].get('abTarget'), 'abCodec': auto_report['settings'].get('abCodec'),
                    'xpsnrTarget': ab_av1.target_for(auto_report['settings']),
                    'qualityMode': profile, 'priority': 'balanced', 'requestedQualityMode': 'auto', 'autoTestId': auto_report['id']}
    mode = settings.get('mode', 'preserve')
    if mode=='overwrite' and settings.get('replacementTempDirectory'):
        working=Path(settings['replacementTempDirectory']).expanduser()
        if not working.is_absolute() or not working.is_dir():raise ValueError('Choose an existing full path for the replacement working folder')
        settings={**settings,'replacementTempDirectory':str(working.resolve())}
    quality_mode = settings.get('qualityMode', 'custom')
    if quality_mode not in ['custom', 'original', 'source', 'archive', 'proxy', *POLICIES]:
        raise ValueError('Invalid quality mode')
    measured = quality_mode in POLICIES and mode not in ['copy', 'move']
    original = quality_mode == 'original' and mode not in ['copy', 'move']
    if original and mode == 'overwrite':
        raise ValueError('Original quality already preserves the source exactly. Choose Keep originals or Save to another folder.')
    if measured:
        metric = 'xpsnr'
        if not STATE.get(metric):
            raise ValueError('Automatic quality requires FFmpeg with ' + 'XPSNR')
        candidates(STATE['encoders'], settings.get('encodingMode'), settings.get('priority'), settings.get('container', 'mp4'), settings.get('hardwareBackend', 'nvenc'))
        if settings.get('resolution', 'original') != 'original' or settings.get('fps', 'original') != 'original':
            raise ValueError('Automated (Test) uses the source resolution and frame rate')
    if mode not in ['preserve', 'overwrite', 'directory', 'copy', 'move']:
        raise ValueError('Invalid file action')
    if mode == 'overwrite' and settings.get('deleteOriginal') is True and settings.get('confirmDelete') is not True:
        raise ValueError('Confirm that you understand the original files will be permanently deleted')
    container = settings.get('container', 'mp4')
    if container not in (['mp4', 'mkv', 'webm', 'mov'] if quality_mode in ('archive','proxy') else ['mp4', 'mkv', 'webm', 'mov', 'source']):
        raise ValueError('Invalid container')
    if container == 'webm' and not (measured or original or requested == 'source') and mode not in ['copy', 'move'] and settings.get('codec') not in ['av1', 'vp9']:
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
        names=output_names.Names(reserved)
        for index, fid in enumerate(dict.fromkeys(ids), int(settings.get('_batchSequence',1))):
            item = (source_items if source_items is not None else STATE['files']).get(fid)
            if not item:
                raise ValueError('A selected file is no longer in the library. Scan again.')
            require_metadata(item)
            source = Path(item['path'])
            stat=source.stat()
            if stat.st_size!=item.get('size',stat.st_size) or (item.get('sourceMtimeNs') and stat.st_mtime_ns!=item['sourceMtimeNs']):raise ValueError('Source changed since import. Import the file again before queueing.')
            file_settings = match_container(item, source_preset(item, settings) if requested == 'source' else settings)
            if requested=='proxy':file_settings={**file_settings,'encoder':proxy_media.encoder_for(settings,[*STATE.get('archive_encoders',[]),*STATE.get('encoders',[])],item)}
            if measured:
                validate_source(item)
            if str(source) in busy_sources:
                raise ValueError(f'{source.name} is already queued')
            if requested == 'proxy':
                output = proxy_media.output_path(item,file_settings)
            elif mode in ['copy', 'move']:
                output = destination / output_name(item, file_settings, index)
            elif mode == 'overwrite':
                if source.suffix.lower() != '.' + file_settings.get('container', 'mp4'):
                    raise ValueError('Replacing originals requires the output container to match every selected file extension. Choose Match source container or save to another folder.')
                output = source
            else:
                output = (destination or source.parent) / output_name(item, file_settings, index)
            output_base=output
            if mode!='overwrite':output=names.reserve(output)
            if output == source and mode != 'overwrite':
                raise ValueError('Source and destination must differ')
            job_settings = {**file_settings, 'sourceMetadata': dict(item)}
            if quality_mode=='archive':job_settings['proresRecommendation']=prores.resolve(item,file_settings)
            if measured and auto_report:
                job_settings['qualitySeed'] = {r['encoder']: r['qualityValue'] for r in auto_report['result']['profiles'][quality_mode]['alternatives']}
            elif measured:
                previous = next((j for j in reversed(TEST_JOBS) if j['status'] == 'completed' and all(j['settings'].get(key) == settings.get(key) for key in ['qualityMode', 'encodingMode', 'hardwareBackend', 'priority', 'container'])), None)
                if previous:
                    job_settings['qualitySeed'] = {r['encoder']: r['qualityValue'] for r in previous['result']['alternatives']}
            if mode not in ['copy', 'move'] and not (measured or original):
                command_for(source, output, job_settings)
            reserved.add(os.path.normcase(str(output)))
            bound = auto_report['result']['profiles'][quality_mode] if measured and auto_report and auto_report['source']==item['path'] else None
            bound_key = auto_report['result']['profileKeys'].get(quality_mode) if bound else None
            if bound:job_settings.update({k:bound['winner'][k] for k in ['codec','encoder','bitrate','qualityValue','encoderPriority']})
            new_jobs.append({'conversionNotes':preservation.conversion_notes(item,job_settings),'workflowOptions':dict(WORKFLOW_OPTIONS),'testedAnalysis':bound,'testedAnalysisKey':bound_key,'id': secrets.token_hex(10), 'name': source.name, 'source': str(source), 'outputBase':str(output_base), 'output': str(output), 'settings': job_settings, 'duration': item['duration'], 'source_size': stat.st_size,'source_mtime_ns':stat.st_mtime_ns, 'output_size': None, 'status': 'queued', 'percent': 0, 'speed': '', 'fps': '', 'eta': None, 'log': collections.deque(maxlen=1500), 'cancel': False, 'error': ''})
        if dry_run:return
        for job in new_jobs:
            job['encodingDetails']=encoding_details([job['settings']['sourceMetadata']],{**job['settings'],'qualityMode':'custom' if job['settings'].get('qualityMode') in POLICIES else job['settings'].get('qualityMode','custom')})['files'][0]
        STATE['jobs'].extend(new_jobs)
    checkpoint()
    with LOCK:
        if auto_start and not STATE['queue_paused']:
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
    if WORKFLOW_READY and WORKFLOW_OPTIONS['storage']:
        with LOCK:pending=list(STATE['jobs'])
        check=storage_checks.snapshot(pending)
        if check['blocked']:raise ValueError('Output storage is unavailable or has less than 64 MiB free. Open Storage details and recheck.')
    with LOCK:
        if not any(j['status'] == 'queued' for j in STATE['jobs']):
            raise ValueError('Add files to the queue first')
        STATE['queue_paused'] = False
        WAKE.set()


def pause_queue(stop=False):
    with LOCK:
        STATE['queue_paused'] = True
        WAKE.clear()
        if stop:
            for job in STATE['jobs']:
                if job['status'] == 'running' and not job.get('committing'):
                    job['cancel'] = True
            for process in set(PROCESSES.values()) | ({PROCESS} if PROCESS else set()):
                try:process.terminate()
                except OSError:pass


def copy_job(job, temp):
    total = Path(job['source']).stat().st_size
    done = 0
    with open(job['source'], 'rb') as src, open(temp, 'wb') as dst:
        while chunk := src.read(4 * 1024 * 1024):
            if job['cancel']:
                return
            if job.get('storagePaused'):raise ValueError(job['storagePaused'])
            dst.write(chunk)
            done += len(chunk)
            with LOCK:
                job['percent'] = done / max(total, 1) * 100
        dst.flush()
        os.fsync(dst.fileno())
    shutil.copystat(job['source'], temp)


def encoding_preview_command(command, target):
    # A second tiny output shares the already-decoded input frames. It does not
    # alter the encoder's video filters, frame timing or output parameters.
    return command + ['-map','0:v:0','-an','-sn','-dn','-vf','fps=1/2,scale=192:-2',
                      '-c:v','mjpeg','-q:v','5','-threads','1','-fps_mode','vfr',
                      '-f','image2','-update','1','-atomic_writing','1',str(target)]


def publish_unique(job,temp,output):
    while True:
        try:
            try:os.link(temp,output)
            except OSError as exc:
                if isinstance(exc,FileExistsError) or os.path.lexists(output):raise FileExistsError(str(output)) from exc
                with open(temp,'rb') as src,open(output,'xb') as dst:
                    try:shutil.copyfileobj(src,dst)
                    except BaseException:
                        dst.close();output.unlink(missing_ok=True);raise
            return output
        except FileExistsError:
            base=Path(job.get('outputBase',output))
            allocator=output_names.Names();allocator.names_in(base.parent) # Network enumeration stays outside LOCK.
            with LOCK:
                allocator.reserved={output_names.key(j['output']) for j in STATE['jobs'] if j is not job and j['status'] in ('queued','running')}
                output=allocator.reserve(base);job['output']=str(output)
                job['log'].append('Output name adjusted to avoid a collision: '+output.name)


def verify_job_output(job,temp,source_stamp):
    options=job.get('workflowOptions',{})
    if not options.get('verify'):return
    source=job['settings'].get('sourceMetadata') or probe(Path(job['source']))
    result=job.setdefault('verification',{});result.update(status='running',checks=result.get('checks',[]))
    def progress(message):
        with LOCK:job['phase']=message
    def telemetry(data):
        if data.get('operationPercent') is not None:result['percent']=data['operationPercent']
    analyzer=Analyzer(STATE['ffmpeg'],STATE['ffprobe'],command_for,lambda:job['cancel'] or bool(job.get('storagePaused')),progress,telemetry=telemetry)
    acquired=False
    try:
        progress('Verifying output · Waiting for verification slot')
        while not acquired:
            analyzer.check();acquired=VERIFY_LOCK.acquire(timeout=.25)
        progress('Verifying output · File and stream checks')
        if options.get('verify'):
            output=probe(temp);result['checks']=output_verification.inspect(source,output,job['settings'])
            if options.get('decode'):
                progress('Verifying output · Full decode check');analyzer.operation_duration=job['duration']
                analyzer.run([STATE['ffmpeg'],'-hide_banner','-v','error','-xerror','-err_detect','explode','-nostdin','-i',str(temp),'-map','0:v:0','-map','0:a?','-progress','pipe:1','-f','null','-'])
                result['decode']='passed'
        stat=Path(job['source']).stat()
        if source_stamp!=(stat.st_size,stat.st_mtime_ns):raise ValueError('Source changed during encoding. Original retained.')
        result.update(status='passed',percent=100)
    except Exception as exc:
        result.update(status='failed',error=str(exc));raise
    finally:
        if acquired:VERIFY_LOCK.release()


def execute_job(job):
    global PROCESS
    output = Path(job['output'])
    temp = None
    process = None
    reader = None
    try:
        workflow_store.cleanup_stage(job)
        job['toolVersions']={'FFmpeg':STATE.get('ffmpegVersion','Not recorded'),'FFprobe':STATE.get('ffprobeVersion','Not recorded'),'ab-av1':ab_av1.installation().get('version','Not recorded')}
        mode = job['settings']['mode']
        quality_mode = job['settings'].get('qualityMode', 'custom')
        exact = quality_mode == 'original'
        if mode not in ('copy','move') and not exact:require_metadata(job['settings'].get('sourceMetadata') or {})
        metadata = None
        source_stamp = (Path(job['source']).stat().st_size, Path(job['source']).stat().st_mtime_ns)
        if job.get('source_mtime_ns') and source_stamp!=(job['source_size'],job['source_mtime_ns']):raise ValueError('Source changed after queueing. Import and queue it again.')
        if quality_mode in POLICIES and mode not in ['copy', 'move']:
            metadata = probe(Path(job['source']))
            def progress(message):
                with LOCK:
                    job['phase'] = message
                    job['log'].append(message)
            if job.get('testedAnalysis'):
                if job['testedAnalysisKey'] != fingerprint(metadata,job['settings'],STATE['ffmpeg'],STATE['ffprobe']):
                    raise ValueError('Source or settings changed after testing; run the test again')
                result=job['testedAnalysis']
                progress('Using this file’s completed quality test')
            else:
                result = quality_analysis(metadata, job['settings'], lambda: job['cancel'], progress)
            job['qualityResult'] = result
            if result['keepOriginal']:
                job.update(status='skipped', percent=100, phase='Original retained', error=result['note'])
                return
            winner = result['winner']
            job['settings'].update({k: winner[k] for k in ['codec', 'encoder', 'bitrate', 'qualityValue', 'encoderPriority']})
            job['encodingDetails']=encoding_details([job['settings'].get('sourceMetadata') or metadata],{**job['settings'],'qualityMode':'custom'})['files'][0]
            progress('Encoding with validated settings')
        if job['cancel']:
            raise InterruptedError('Job cancelled')
        if WORKFLOW_READY and WORKFLOW_OPTIONS['storage']:
            try:storage_checks.guard(job)
            except (OSError,ValueError) as exc:job['storagePaused']=str(exc);raise ValueError(str(exc))
        if quality_mode == 'proxy':output.parent.mkdir(parents=True,exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.archiver-', suffix=output.suffix, dir=job['settings'].get('replacementTempDirectory') if mode=='overwrite' and job['settings'].get('replacementTempDirectory') else output.parent)
        os.close(fd)
        temp = Path(tmp)
        job['temporaryOutput']=str(temp)
        if mode in ['copy', 'move'] or exact:
            copy_job(job, temp)
        else:
            cmd = command_for(Path(job['source']), temp, job['settings'])
            if STATE.get('framePreview'):
                frame = Path(CACHE.name) / ('encoding-' + job['id'] + '.jpg')
                cmd = encoding_preview_command(cmd, frame)
                job['framePreview'] = True
            with LOCK:job['command']=cmd
            process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            with LOCK:
                PROCESSES[job['id']] = process
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
                            seconds = max(0,int(value) / 1_000_000)
                            job['encodedSeconds'] = seconds
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
                PROCESSES.pop(job['id'],None)
                PROCESS = next(iter(PROCESSES.values()),None)
            if job.get('storagePaused'):raise ValueError(job['storagePaused'])
            if code and not job['cancel']:
                raise ValueError('FFmpeg failed. See verbose output for details. Hardware encoders also require compatible hardware and drivers.')
        if metadata and not job['cancel']:
            job['phase'] = 'Verifying final output quality'
            verified = probe(temp)
            if abs(verified['duration'] - metadata['duration']) > max(.15, 2 / metadata['fps']):
                raise ValueError('Output duration does not match source; original retained')
            acquired=False
            try:
                job['phase']='Waiting for output quality verification'
                while not acquired:
                    if job['cancel']:raise InterruptedError('Job cancelled')
                    acquired=VERIFY_LOCK.acquire(timeout=.25)
                job['phase']='Verifying final output quality'
                analyzer=Analyzer(STATE['ffmpeg'],STATE['ffprobe'],command_for,lambda:job['cancel'] or bool(job.get('storagePaused')),progress)
                rows=output_verification.quality(analyzer,metadata,temp,job['settings'],job['settings'].get('xpsnrTarget',38),progress,result.get('sampleWindows',[]))
                job.setdefault('verification',{})['quality']=rows
            finally:
                if acquired:VERIFY_LOCK.release()
            stat = Path(job['source']).stat()
            if source_stamp != (stat.st_size, stat.st_mtime_ns):
                raise ValueError('Source changed during encoding; original retained')
        if quality_mode == 'archive' and not job['cancel']:
            job['phase'] = 'Verifying archival output'
            verify_archive(job, temp)
            stat = Path(job['source']).stat()
            if source_stamp != (stat.st_size, stat.st_mtime_ns):
                raise ValueError('Source changed during archival encoding; original retained')
        if quality_mode == 'proxy' and not job['cancel']:
            job['phase']='Verifying proxy'
            proxy_source={**job['settings']['sourceMetadata'],'audio_streams':preservation.audio_metadata(job['settings']['sourceMetadata'],job['settings'])}
            if not proxy_source['audio_streams']:proxy_source['audio']=''
            proxy_media.verify(proxy_source,probe(temp),job['settings'])
            if source_stamp != (Path(job['source']).stat().st_size,Path(job['source']).stat().st_mtime_ns):raise ValueError('Source changed during proxy encoding; original retained')
        if not job['cancel']:
            verify_job_output(job,temp,source_stamp)
            if job['settings'].get('preservation',{}).get('dates'):
                stat=Path(job['source']).stat();os.utime(temp,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        # After this commit point cancellation cannot discard a successfully
        # published output. Slow network filesystem I/O must not hold STATE's
        # lock and block the progress readers of other hardware encodes.
        with LOCK:
            publish=not job['cancel']
            if publish:job.update(committing=True,phase='Saving output')
            else:job['status']='cancelled'
        if publish:
            if not temp.stat().st_size:
                raise ValueError('The output file is empty')
            if mode == 'overwrite':
                verified = probe(temp)
                if verified['duration'] <= 0:
                    raise ValueError('Output validation failed: no video duration')
                if job['settings'].get('replacementTempDirectory'):
                    replacement_stage.publish(temp,output,lambda backup:backup.unlink() if job['settings'].get('deleteOriginal') is True else recycle_file(backup),job,checkpoint)
                else:replace_original(temp, output, job['settings'].get('deleteOriginal') is True)
            else:
                output=publish_unique(job,temp,output)
                if mode == 'move':
                    Path(job['source']).unlink()
            with LOCK:job.update(output_size=output.stat().st_size,phase='Saving encode report',finished=time.time())
            if WORKFLOW_READY:
                try:workflow_store.receipt(VERSION,job);checkpoint()
                except OSError as exc:job['recoveryWarning']='Completion journal could not be saved: '+str(exc)
            if job.get('workflowOptions',{}).get('reports'):
                try:job['report']=encode_reports.save(job,VERSION,job['toolVersions'])
                except (OSError,ValueError) as exc:job['reportError']='Output saved, but its report could not be written: '+str(exc)
            with LOCK:job.update(status='completed',percent=100,eta=0,phase='Complete')
    except Exception as exc:
        if not job.get('replacementRecoveryRequired') and not job['cancel'] and job.get('workflowOptions',{}).get('storage',WORKFLOW_OPTIONS['storage']) and storage_checks.write_failure(exc,job.get('log',[])):
            job['storagePaused']='Output storage is full or unavailable. Check the drive, then resume.'
        with LOCK:
            if job.get('storagePaused'):
                job.update(status='queued',error='',phase='Paused for storage · '+job['storagePaused']);STATE['queue_paused']=True;WAKE.clear()
            elif not job['cancel'] and job.get('encodedSeconds',0)<.1 and job.get('hardwareRetries',0)<2 and hardware_queue.hardware_key(job) and hardware_queue.session_exhausted(job['log']):
                QUEUE_ADMISSION.busy(hardware_queue.hardware_key(job))
                job.update(status='queued',error='',phase='Hardware session unavailable; retrying one at a time',hardwareRetries=job.get('hardwareRetries',0)+1,retryAfter=time.monotonic()+2)
            else:
                job.update(status='cancelled' if job['cancel'] else 'failed', error=str(exc))
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        if reader:reader.join(timeout=5)
        if process:
            for stream in (process.stdout,process.stderr):
                if stream and not stream.closed:stream.close()
        if temp and not job.get('replacementRecoveryRequired'):
            try:
                temp.unlink(missing_ok=True)
                job.pop('temporaryOutput',None)
            except OSError:job['recoveryWarning']='Staging cleanup pending: '+str(temp)
        with LOCK:
            job.pop('committing',None)
            PROCESSES.pop(job['id'],None)
            PROCESS = next(iter(PROCESSES.values()),None)



def worker():
    # One scheduler owns the media slot for a batch. Quality tests and software
    # work remain exclusive; ready hardware encodes may share the batch.
    while not SHUTTING_DOWN.is_set():
        if not WAKE.wait(.25):continue
        with MEDIA_LOCK:
            active={}
            try:
                while not SHUTTING_DOWN.is_set() or active:
                    for ident,(job,thread) in list(active.items()):
                        if not thread.is_alive():
                            thread.join();active.pop(ident);notify_queue_result(job,'encoding')
                    with LOCK:
                        running=[value[0] for value in active.values()]
                        test_waiting=runnable_test_work()
                        allowed=dependency_status()['ready'] and WAKE.is_set() and not STATE['queue_paused'] and not SHUTTING_DOWN.is_set() and not test_waiting
                        candidate=next((j for j in STATE['jobs'] if j['status']=='queued' and not j['cancel']),None) if allowed else None
                        if candidate and candidate.get('retryAfter',0)>time.monotonic():candidate=None
                    capacity=QUEUE_ADMISSION.desired(running,candidate,STATE.get('parallel_hardware',True))
                    if any(j.get('committing') or 'verif' in j.get('phase','').lower() for j in running):capacity=min(capacity,max(1,len(running)))
                    if candidate and capacity==0 and not active:
                        with LOCK:candidate['phase']='Waiting for an available hardware encoder session'
                    if candidate and len(active)<capacity and (not running or hardware_queue.hardware_key(candidate) and all(hardware_queue.hardware_key(j)==hardware_queue.hardware_key(candidate) for j in running)):
                        with LOCK:
                            if candidate['status']!='queued' or candidate['cancel'] or STATE['queue_paused'] or not WAKE.is_set():continue
                            candidate.pop('storagePaused',None)
                            candidate.update(status='running',encodedSeconds=0,started=time.time(),phase='Encoding')
                            thread=threading.Thread(target=execute_job,args=(candidate,),daemon=True)
                            active[candidate['id']]=(candidate,thread)
                            thread.start()
                    elif not active:
                        with LOCK:
                            queued=any(j['status']=='queued' and not j['cancel'] for j in STATE['jobs'])
                            if not queued:WAKE.clear()
                        if not queued or not WAKE.is_set() or STATE['queue_paused'] or test_waiting:break
                    if test_waiting and not active:break
                    time.sleep(.2)
            finally:
                for job,thread in active.values():
                    job['cancel']=True
                    process=PROCESSES.get(job['id'])
                    if process:
                        try:process.terminate()
                        except OSError:pass
                for job,thread in active.values():thread.join()
        if not TEST_PAUSED and any(j['status']=='waiting' for j in TEST_JOBS):time.sleep(.1)


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

    def send_preview(self, target, content_type='video/mp4'):
        size = target.stat().st_size
        first, last, status = 0, size - 1, 200
        requested = self.headers.get('Range')
        if requested:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
            if not match or not any(match.groups()):
                self.send_response(416);self.send_header('Content-Range', f'bytes */{size}');self.send_header('Content-Length', '0');self.end_headers();return
            if match[1]:
                first = int(match[1]);last = min(last, int(match[2])) if match[2] else last
            else:
                first = max(0, size - int(match[2]))
            if first > last or first >= size:
                self.send_response(416);self.send_header('Content-Range', f'bytes */{size}');self.send_header('Content-Length', '0');self.end_headers();return
            status = 206
        self.send_response(status)
        self.send_header('Content-Type', content_type);self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(last-first+1));self.send_header('Cache-Control', 'private, max-age=3600')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if status == 206:self.send_header('Content-Range', f'bytes {first}-{last}/{size}')
        self.end_headers()
        try:
            with target.open('rb') as stream:
                stream.seek(first);remaining=last-first+1
                while remaining:
                    data=stream.read(min(65536,remaining))
                    if not data:break
                    self.wfile.write(data);remaining-=len(data)
        except (BrokenPipeError,ConnectionResetError):pass

    def do_GET(self):
        if not self.valid_host():
            return self.send({'error': 'Invalid host'}, 403)
        url = urlparse(self.path)
        if url.path == '/':
            html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN)
            return self.send(html.encode(), content_type='text/html; charset=utf-8')
        if url.path == '/third-party-notices.txt':
            return self.send((ROOT/'third_party/THIRD_PARTY_NOTICES.txt').read_bytes(),content_type='text/plain; charset=utf-8')
        if url.path in ['/assets/icon.svg', '/assets/wordmark.svg', '/assets/archiver.ico']:
            file = ROOT / 'web' / url.path[1:]
            return self.send(file.read_bytes(), content_type='image/svg+xml' if file.suffix == '.svg' else 'image/x-icon')
        if url.path in ['/app.js', '/workflows.js', '/style.css', '/theme.css','/workflows.css']:
            file = ROOT / 'web' / url.path[1:]
            return self.send(file.read_bytes(), content_type='text/javascript' if file.suffix == '.js' else 'text/css')
        if self.headers.get('X-Token') != TOKEN and parse_qs(url.query).get('token', [''])[0] != TOKEN:
            return self.send({'error': 'Unauthorized'}, 403)
        if url.path == '/api/notifications':
            try:return self.send(notification_history.snapshot(parse_qs(url.query).get('revision',[None])[0]))
            except (OSError,ValueError) as exc:return self.send({'error':str(exc)},400)
        if url.path == '/api/output-presets':
            try:return self.send(output_presets.load())
            except ValueError as exc:return self.send({'error':str(exc)},400)
        if url.path == '/api/import-exclusions':
            with LOCK:return self.send(exclusion_preferences.load())
        if url.path == '/api/state':
            # Snapshot only in-memory data under the application lock. No path stats,
            # tool execution or socket writes may hold up cancellation/progress.
            with LOCK:
                snapshot=workflow_store.clean({'workflows':{'options':dict(WORKFLOW_OPTIONS),'storage':STORAGE,'watch':WATCH_STATE,'error':'; '.join(v for v in (WORKFLOW_LOAD_WARNING,WORKFLOW_ERROR) if v),'comparison':None,'recovery':{'available':bool(RECOVERY['jobs'] or RECOVERY['tests']),'loading':RECOVERY.get('loading',False),'done':RECOVERY.get('done',0),'total':RECOVERY.get('total',0),'encodes':sum(j['status'] in ('queued','running','waiting') for j in RECOVERY['jobs']),'tests':sum(j['status'] in ('queued','running','waiting') for j in RECOVERY['tests']),'completed':sum(j['status']=='completed' for j in RECOVERY['jobs']),'error':RECOVERY.get('error','')}},'dependencies':None,'ab_av1':None,'version': VERSION, 'test_jobs': [{**j, 'usableProfiles': []} for j in TEST_JOBS], 'preset_reports': [{**j, 'usableProfiles': []} for j in auto_reports()], 'test_files': list(TEST_FILES.values()), 'test_scan': dict(TEST_SCAN), 'test_queue_paused': TEST_PAUSED, 'test_queue_running':TEST_WAKE.is_set(), 'xpsnr': STATE.get('xpsnr', False), 'files': list(STATE['files'].values()), 'scan': STATE['scan'], 'jobs': [{**j, 'log': list(j['log'])} for j in STATE['jobs']], 'parallel_hardware': STATE.get('parallel_hardware',True), 'queue_running': WAKE.is_set(), 'queue_paused': STATE['queue_paused'], 'ffmpeg': STATE['ffmpeg'], 'ffprobe': STATE['ffprobe'], 'encoders': STATE['encoders'], 'archive_encoders': STATE.get('archive_encoders',[])})
            snapshot['dependencies']=dependency_status()
            snapshot['ab_av1']=ab_av1.installation()
            snapshot['workflows']['comparison']=comparison.public()
            for job in [*snapshot['test_jobs'],*snapshot['preset_reports']]:
                job['usableProfiles']=PROFILE_STATUS.get(job['id'],[])
            return self.send(snapshot)
        if url.path == '/api/comparison-media':
            try:
                query=parse_qs(url.query);key=query.get('key',[''])[0];kind=query.get('kind',[''])[0]
                return self.send_preview(comparison.media(key,kind),comparison.mime(key,kind))
            except (OSError,ValueError) as exc:return self.send({'error':str(exc)},404)
        if url.path == '/api/encode-report':
            query=parse_qs(url.query);job=next((j for j in STATE['jobs'] if j['id']==query.get('id',[''])[0] and j['status']=='completed'),None)
            if not job:return self.send({'error':'Completed job not found'},404)
            data=encode_reports.document(job,VERSION,job.get('toolVersions',{'FFmpeg':'Not recorded in this older job'}))
            return self.send(encode_reports.render(data).encode(),content_type='text/html; charset=utf-8') if query.get('format',[''])[0]=='html' else self.send(data)
        if url.path == '/api/quality-preview':
            query = parse_qs(url.query)
            kind = query.get('kind', [''])[0]
            job = next((j for j in TEST_JOBS if j['id'] == query.get('id', [''])[0]), None)
            if kind not in ['source', 'candidate'] or not job or job['status'] != 'completed' or not (job.get('result') or {}).get('preview'):
                return self.send({'error': 'Preview unavailable'}, 404)
            target = Path(job['outputDirectory']) / f'quality-{kind}.mp4'
            if not target.is_file():
                return self.send({'error': 'Preview unavailable'}, 404)
            return self.send(target.read_bytes(), content_type='video/mp4')
        if url.path == '/api/test-source-preview':
            query=parse_qs(url.query)
            with LOCK:job=next((j for j in TEST_JOBS if j['id']==query.get('id',[''])[0]),None)
            if not job or not Path(job['source']).is_file():return self.send({'error':'Source preview unavailable'},404)
            return self.send_preview(Path(job['source']),job.get('progress',{}).get('nativePreview',{}).get('mime','application/octet-stream').split(';')[0])
        if url.path == '/api/encoding-frame':
            query=parse_qs(url.query)
            with LOCK:job=next((j for j in STATE['jobs'] if j['id']==query.get('id',[''])[0]),None)
            if not job:return self.send({'error':'Job not found'},404)
            target=Path(CACHE.name)/('encoding-'+job['id']+'.jpg')
            try:return self.send(target.read_bytes(),content_type='image/jpeg')
            except OSError:return self.send({'error':'Encoding frame not yet available'},404)
        if url.path == '/api/test-sample-preview':
            query = parse_qs(url.query)
            job = next((j for j in TEST_JOBS if j['id'] == query.get('id', [''])[0]), None)
            try:
                index = int(query.get('sample', ['-1'])[0])
                windows = job.get('progress', {}).get('sampleWindows', []) if job else []
                if not job or not 0 <= index < len(windows):
                    return self.send({'error': 'Sample unavailable'}, 404)
                directory = Path(job['outputDirectory']) / 'thumbnails'
                directory.mkdir(exist_ok=True)
                window = windows[index]
                if 'start' in query and abs(float(query['start'][0])-window['start'])>.000001:
                    return self.send({'error':'Sample selection changed; refresh the preview'},409)
                target = directory / f'sample-{window["start"]:.6f}-{window["duration"]:.6f}-source-timing.mp4'
                if not target.is_file():
                    with PREVIEW_WORK.generation('loop', target):
                        if not target.is_file():
                            if job['status'] != 'running' or job['cancel']:
                                return self.send({'error': 'Sample is no longer active'}, 409)
                            window = windows[index]
                            sample_preview.create(STATE['ffmpeg'], job['source'], target, window['start'], window['duration'],
                                                  lambda: job['cancel'] or SHUTTING_DOWN.is_set(), STATE['encoders'] if job.get('progress',{}).get('stage') in ('previews','sample-previews') and not PROCESSES else ())
                return self.send_preview(target)
            except Exception:
                return self.send({'error': 'Animated preview unavailable'}, 422)
        if url.path == '/api/test-thumbnail':
            query = parse_qs(url.query)
            job = next((j for j in TEST_JOBS if j['id'] == query.get('id', [''])[0]), None)
            if not job:
                return self.send({'error': 'Test not found'}, 404)
            try:
                length = job.get('progress', {}).get('sourceDuration', 0)
                second = float(query.get('t', ['0'])[0])
                if not length or not 0 <= second < length:
                    return self.send({'error': 'Invalid thumbnail position'}, 400)
                # Quantization bounds the cache during scrubbing. Store all test artifacts beside source.
                second = int(second)
                directory = Path(job['outputDirectory']) / 'thumbnails'
                directory.mkdir(exist_ok=True)
                target = directory / f'{second}.jpg'
                if not target.exists():
                    with PREVIEW_WORK.generation('thumbnail', target):
                        if not target.exists():
                            fd, temporary = tempfile.mkstemp(suffix='.jpg', dir=directory)
                            os.close(fd)
                            try:
                                completed = run([STATE['ffmpeg'], '-v', 'error', '-threads', '1', '-ss', str(second), '-i', job['source'],
                                                 '-frames:v', '1', '-filter_threads', '1', '-vf', 'scale=320:-2', '-threads', '1', '-y', temporary], 20)
                                if completed.returncode or not Path(temporary).stat().st_size:
                                    raise ValueError('Thumbnail unavailable')
                                os.replace(temporary, target)
                            finally:
                                Path(temporary).unlink(missing_ok=True)
                return self.send(target.read_bytes(), content_type='image/jpeg')
            except Exception:
                return self.send({'error': 'Thumbnail unavailable'}, 422)
        if url.path == '/api/import-cache':return self.send(metadata_cache.info())
        if url.path in ['/api/thumbnail', '/api/media']:
            query = parse_qs(url.query)
            fid=query.get('id', [''])[0]
            item = STATE['files'].get(fid) or (TEST_FILES.get(fid) if url.path == '/api/thumbnail' else None)
            if url.path == '/api/thumbnail' and query.get('job'):
                with LOCK:
                    job = next((j for j in STATE['jobs'] if j['id'] == query['job'][0]), None)
                    metadata = (job.get('settings', {}).get('sourceMetadata') or {}) if job else {}
                    item = {**metadata, 'id': metadata.get('id', 'job-' + job['id']), 'path': job['source'], 'duration': job['duration']} if job else None
                    if item and not Path(item['path']).is_file() and Path(job['output']).is_file():
                        item['path'] = job['output']
            if not item:
                return self.send({'error': 'File not found'}, 404)
            path = Path(item['path'])
            if url.path == '/api/thumbnail':
                if item.get('metadataPending'):return self.send({'error':'Analyze this file to load previews'},404)
                try:
                    second = max(0, min(float(query.get('t', ['0'])[0]), max(0, item['duration'] - .1)))
                    target = Path(CACHE.name) / f"{item['id']}-{int(second)}.jpg"
                    if not target.exists():
                        with PREVIEW_WORK.generation('thumbnail',target):
                            if not target.exists():
                                fd,temporary=tempfile.mkstemp(suffix='.jpg',dir=CACHE.name);os.close(fd)
                                try:
                                    result=run([STATE['ffmpeg'],'-v','error','-threads','1','-ss',str(second),'-i',str(path),'-frames:v','1','-filter_threads','1','-vf','scale=480:-2','-threads','1','-y',temporary],20)
                                    if result.returncode or not Path(temporary).stat().st_size:return self.send({'error':'Preview unavailable'},422)
                                    os.replace(temporary,target)
                                finally:Path(temporary).unlink(missing_ok=True)
                    return self.send(target.read_bytes(), content_type='image/jpeg')
                except Exception:
                    return self.send({'error': 'Preview unavailable'}, 422)
            return self.send({'error': 'Use thumbnail scrubbing'}, 404)
        self.send({'error': 'Not found'}, 404)

    def do_POST(self):
        global TEST_PAUSED
        if SHUTTING_DOWN.is_set():
            return self.send({'error': 'Archiver is shutting down'}, 503)
        if not self.valid_host() or self.headers.get('X-Token') != TOKEN:
            return self.send({'error': 'Unauthorized'}, 403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length < 1_000_000:
                raise ValueError('Invalid request size')
            body = json.loads(self.rfile.read(length))
            path = urlparse(self.path).path
            if path=='/api/scan' and body.get('files_only') is not True:require_video_tools()
            if path in {'/api/analyze-files','/api/test-scan','/api/test-queue','/api/start-tests','/api/queue','/api/start'}:require_video_tools()
            if path == '/api/ab-av1-check':
                return self.send(ab_av1.installation(recheck=True))
            elif path == '/api/setup-tools':
                start_tool_setup()
                return self.send(dict(TOOL_SETUP))
            elif path == '/api/workflow-options':
                updated=workflow_store.save_options(body)
                with LOCK:WORKFLOW_OPTIONS.update(updated)
                if not updated['recovery']:workflow_store.save(VERSION,[],[])
                return self.send(updated)
            elif path == '/api/recovery':
                if body.get('action') not in ('restore','discard'):raise ValueError('Choose Restore paused or Dismiss saved queue')
                restore_queues(body.get('action')=='discard')
                return self.send({'ok':True})
            elif path == '/api/storage-check':
                with LOCK:pending=list(STATE['jobs'])
                return self.send(storage_checks.snapshot(pending))
            elif path == '/api/watch-folders':
                with watch_folders.LOCK:
                    result=watch_folders.change(body,VIDEO_EXT)
                    globals()['WATCH_STATE']=result
                return self.send(result)
            elif path == '/api/comparison':
                require_video_tools()
                job=next((j for j in TEST_JOBS if j['id']==body.get('id')),None)
                if not job:raise ValueError('Test not found')
                key=comparison.prepare(job,body.get('index'),STATE['ffmpeg'],STATE['ffprobe'],MEDIA_LOCK,SHUTTING_DOWN.is_set,command_for,body.get('fullResolution') is True)
                return self.send({'key':key})
            elif path == '/api/preservation-preview':
                with LOCK:items=[STATE['files'][fid] for fid in body.get('ids',[])[:24] if fid in STATE['files']]
                return self.send({'files':[preservation.summary(item,match_container(item,body['settings'])) for item in items]})
            elif path == '/api/preset-export':
                return self.send(output_presets.portable_export(body.get('id')))
            elif path == '/api/preset-import':
                imported=output_presets.portable_import(body.get('document'));available=[*STATE['encoders'],*STATE.get('archive_encoders',[])]
                if body.get('encoder'):
                    encoder=body['encoder']
                    if encoder not in available:raise ValueError('Select an available encoder')
                    config=imported['settings'];codec=config['outputCodec']
                    if encoder not in ENCODERS.get(codec,['prores_ks'] if codec=='prores' else []):raise ValueError('Encoder does not match the imported codec')
                    output_presets.override_encoder(config,encoder)
                missing=imported['settings'].get('encoder') not in available
                if body.get('commit') is True:
                    if missing:raise ValueError('Choose an available encoder before importing')
                    return self.send(output_presets.change({'action':'save','name':body.get('name',imported['name']),'settings':imported['settings']}))
                return self.send({**imported,'needsEncoder':missing,'encoders':[e for e in available if e in ENCODERS.get(imported['settings']['outputCodec'],['prores_ks'])]})
            elif path == '/api/notifications':
                if body.get('action') in ('read','clear'):return self.send(notification_history.change(body['action']))
                return self.send(notification_history.add(body.get('title',''),body.get('message',''),body.get('level','info')))
            elif path == '/api/output-presets':
                return self.send(output_presets.change(body))
            elif path == '/api/import-exclusions':
                with LOCK:return self.send(exclusion_preferences.save(body))
            elif path == '/api/config':
                with LOCK:
                    if TOOL_SETUP['running']:raise ValueError('Wait for video tools setup to finish before changing paths')
                    if TEST_SCAN['running'] or any(j['status'] in ['waiting', 'running'] for j in TEST_JOBS) or any(j['status']=='running' for j in STATE['jobs']) or STATE['scan']['running']:
                        raise ValueError('Wait for scans and the queue to finish before changing tools')
                    configure(body['ffmpeg'], body['ffprobe'])
                    if any(j['status']=='queued' for j in STATE['jobs']):STATE['queue_paused']=True;WAKE.clear()
                    if any(j['status']=='queued' for j in TEST_JOBS):TEST_PAUSED=True;TEST_WAKE.clear()
            elif path == '/api/encoding-details':
                with LOCK:items=[STATE['files'][fid] for fid in dict.fromkeys(body.get('ids',[])) if fid in STATE['files']]
                return self.send(encoding_details(items,body['settings']))
            elif path == '/api/prores-preview':
                return self.send({'recommendations':prores_recommendations(body.get('ids',[]),body['settings'])})
            elif path == '/api/browse':
                return self.send({'directory': browse_directory(body.get('initial',''),body.get('kind','general'),body.get('fallback',''))})
            elif path == '/api/stop-scan':
                with LOCK:
                    if STATE['scan']['running']:
                        SCAN_STOP.set()
                        STATE['scan']['stopping'] = True
            elif path == '/api/import-cache':
                with LOCK:
                    if STATE['scan']['running']:raise ValueError('Wait for importing or analysis to finish before changing the cache folder')
                    return self.send(metadata_cache.configure(body.get('directory','')))
            elif path == '/api/analyze-files':
                with LOCK:
                    if STATE['scan']['running']:raise ValueError('An import or analysis is already running')
                    ids=[fid for fid in dict.fromkeys(body.get('ids',[])) if fid in STATE['files'] and STATE['files'][fid].get('metadataPending')]
                    if not ids:raise ValueError('Select files whose metadata has not been read')
                    SCAN_STOP.clear()
                    STATE['scan']={'running':True,'phase':'probing','started':time.time(),'done':0,'total':len(ids),'errors':[],'current':'','directory':STATE['scan'].get('directory',''),'recent':[]}
                threading.Thread(target=analyze_pool,args=(ids,),daemon=True).start()
            elif path == '/api/scan':
                workers = import_workers(body)
                excluded_folders=body.get('excluded_folders')
                import_filters.folder_names(excluded_folders)
                skip_parent_copies=False # Older clients cannot hide matching-name source files.
                exclude_test_folders=body.get('exclude_test_folders') is not False
                with LOCK:
                    if STATE['scan']['running']:
                        raise ValueError('A scan is already running')
                    if not body.get('files_only') and not STATE['encoders']:
                        raise ValueError('Locate FFmpeg and FFprobe in FFmpeg settings first')
                    SCAN_STOP.clear()
                    STATE['scan'] = {'running': True, 'done': 0, 'total': 0, 'errors': []}
                threading.Thread(target=scan, args=(body['directory'], bool(body.get('recursive')), workers, excluded_folders, skip_parent_copies, exclude_test_folders), kwargs={'adaptive':body.get('workers','auto')=='auto','files_only':body.get('files_only') is True}, daemon=True).start()
            elif path == '/api/test-scan':
                with LOCK:
                    if TEST_SCAN['running']:
                        raise ValueError('Test source scan is already running')
                    if not STATE['ffprobe']:
                        raise ValueError('Locate FFmpeg and FFprobe in FFmpeg settings first')
                    directory = Path(body['directory']).expanduser().resolve(strict=True)
                    if not directory.is_dir():
                        raise ValueError('Choose an existing test source directory')
                    TEST_FILES.clear()
                    TEST_SCAN_STOP.clear()
                    TEST_SCAN.update(running=True, done=0, errors=[], current='')
                threading.Thread(target=scan_test_sources, args=(directory, body.get('recursive') is True), daemon=True).start()
            elif path == '/api/stop-test-scan':
                TEST_SCAN_STOP.set()
            elif path in ['/api/analyze-quality', '/api/test-queue']:
                return self.send({'ids': enqueue_tests(body.get('ids') or [body.get('id')], body['settings'], body.get('directory', ''), body.get('encode_settings'), body.get('encode_auto_start') is True, auto_start=body.get('auto_start') is True)})
            elif path == '/api/start-tests':
                with LOCK:
                    TEST_PAUSED = False
                    TEST_WAKE.set()
            elif path == '/api/pause-tests':
                with LOCK:
                    TEST_PAUSED = True
                    TEST_WAKE.clear()
            elif path == '/api/cancel-test':
                with LOCK:
                    job = next(j for j in TEST_JOBS if j['id'] == body['id'])
                    if job['status'] in ['queued', 'waiting', 'running']:
                        job['cancel'] = True
                        if job['status'] == 'queued':
                            job.update(status='cancelled', phase='Cancelled', finished=time.time())
            elif path == '/api/clear-tests':
                with LOCK:
                    TEST_JOBS[:] = [j for j in TEST_JOBS if j['status'] in ['queued', 'waiting', 'running']]
            elif path == '/api/queue':
                enqueue(body['ids'], body['settings'], body.get('auto_start') is True)
            elif path == '/api/output-size-preview':
                with LOCK:
                    items=[dict(STATE['files'][fid]) for fid in dict.fromkeys(body.get('ids',[])) if fid in STATE['files']]
                    return self.send(output_size_estimate(items,body['settings'],auto_reports()))
            elif path == '/api/source-preview':
                estimates = []
                with LOCK:
                    for fid in body.get('ids', [])[:3]:
                        item = STATE['files'].get(fid)
                        if not item:
                            continue
                        try:
                            resolved = source_preset(item, body['settings'])
                            estimates.append({'name': item['name'], 'inputCodec': item['codec'], 'inputMbps': item['video_bitrate'] / 1_000_000,
                                              'outputCodec': resolved['codec'], 'outputMbps': resolved['customBitrate'], **resolved['sourceEstimate']})
                        except ValueError as exc:
                            estimates.append({'name': item['name'], 'error': str(exc)})
                return self.send({'estimates': estimates, 'model': CODEC_ESTIMATES})
            elif path == '/api/recommend-quality':
                with LOCK:
                    items = [STATE['files'][fid] for fid in body.get('ids', []) if fid in STATE['files']]
                    return self.send(recommend_quality(items, body['settings']))
            elif path == '/api/naming-preview':
                with LOCK:
                    items = [STATE['files'][fid] for fid in dict.fromkeys(body.get('ids', [])) if fid in STATE['files']]
                    if not items:
                        items = [{'path':'Video.mp4','name':'Video.mp4','width':1920,'height':1080,'fps':30,'duration':1,'pixel_format':'yuv420p','audio':'','audio_streams':[]}]
                    settings=body['settings'];mode=settings.get('mode','preserve')
                    allocator=output_names.Names(j['output'] for j in STATE['jobs'] if j['status'] in ('queued','running'))
                    names=[];renamed=False
                    for index,item in enumerate(items[:3],int(settings.get('_batchSequence',1))):
                        if not body.get('ids') or (mode=='directory' and not settings.get('destination','').strip()):
                            names.append(output_name(item,settings,index));continue
                        resolved=source_preset(item,settings) if settings.get('qualityMode')=='source' else match_container(item,settings)
                        source=Path(item['path'])
                        desired=proxy_media.output_path(item,resolved) if settings.get('qualityMode')=='proxy' else (Path(settings['destination']).expanduser().resolve() if mode in ('directory','copy','move') else source.parent)/output_name(item,resolved,index)
                        actual=desired if mode=='overwrite' else allocator.reserve(desired)
                        renamed=renamed or actual!=desired;names.append(actual.name)
                return self.send({'names':names,'example':not bool(body.get('ids')),'renamed':renamed})
            elif path == '/api/pause-queue':
                pause_queue()
            elif path == '/api/stop-queue':
                pause_queue(stop=True)
            elif path == '/api/queue-parallel':
                if type(body.get('enabled')) is not bool:raise ValueError('Choose whether to parallelize hardware encoding')
                with LOCK:STATE['parallel_hardware']=body['enabled']
            elif path == '/api/start':
                start_queue()
            elif path == '/api/cancel':
                with LOCK:
                    job = next(j for j in STATE['jobs'] if j['id'] == body['id'])
                    if job['status'] in ['queued', 'running'] and not job.get('committing'):
                        job['cancel'] = True
                        if job['status'] == 'queued':
                            job['status'] = 'cancelled'
                        else:
                            process=PROCESSES.get(job['id'])
                            if process:
                                try:process.terminate()
                                except OSError:pass
            elif path == '/api/open-directory':
                with LOCK:
                    job = next((j for j in STATE['jobs'] if j['id'] == body.get('id')), None)
                    if not job or job['status'] != 'completed':
                        raise ValueError('Only completed jobs have an output directory to open')
                    directory = Path(job['output']).parent.resolve()
                if not directory.is_dir():
                    raise ValueError('The output directory is no longer available')
                if sys.platform == 'win32':
                    os.startfile(str(directory))
                else:
                    subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(directory)])
            elif path == '/api/clear-queue':
                with LOCK:
                    STATE['jobs'] = [j for j in STATE['jobs'] if j['status'] != 'queued']
            elif path == '/api/clear':
                with LOCK:
                    STATE['jobs'] = [j for j in STATE['jobs'] if j['status'] in ['queued', 'running']]
            else:
                raise ValueError('Unknown action')
            checkpoint()
            self.send({'ok': True})
        except Exception as exc:
            self.send({'error': str(exc)}, 400)


def stop_application(server):
    """Cancel active work, let its temporary files clean up, then stop HTTP."""
    checkpoint() # Persist pending work before shutdown cancellation changes its status.
    SHUTTING_DOWN.set()
    with LOCK:
        SCAN_STOP.set()
        TEST_SCAN_STOP.set()
        WAKE.clear()
        TEST_WAKE.clear()
        STATE['queue_paused'] = True
        for job in STATE['jobs']:
            if job['status'] in ['queued', 'running'] and not job.get('committing'):
                job['cancel'] = True
                if job['status'] == 'queued':
                    job['status'] = 'cancelled'
        for job in TEST_JOBS:
            if job['status'] in ['queued', 'waiting', 'running']:
                job['cancel'] = True
                if job['status'] == 'queued':
                    job['status'] = 'cancelled'
        for process in set(PROCESSES.values()) | ({PROCESS} if PROCESS else set()):
            try:process.terminate()
            except OSError:pass
    while True:
        with LOCK:
            active = STATE['scan']['running'] or TEST_SCAN['running'] or any(j['status'] == 'running' for j in STATE['jobs']) or any(j['status'] in ['waiting', 'running'] for j in TEST_JOBS)
        if not active:
            break
        time.sleep(.1)
    # A worker can mark its job finished just before releasing the processing slot.
    with MEDIA_LOCK:
        pass
    server.shutdown()


def run_tray(server):
    global TEST_PAUSED
    import ctypes
    from windows_tray import Tray
    def status():
        with LOCK:
            encodes = sum(j['status'] == 'running' for j in STATE['jobs'])
            tests = sum(j['status'] in ['waiting', 'running'] for j in TEST_JOBS)
            waiting = sum(j['status'] == 'queued' for j in [*STATE['jobs'], *TEST_JOBS])
            return f'{encodes} encoding, {tests} testing, {waiting} queued' if encodes or tests or waiting else 'Idle'
    def test_pause():
        global TEST_PAUSED
        with LOCK:
            TEST_PAUSED = True
            TEST_WAKE.clear()
    def test_resume():
        global TEST_PAUSED
        with LOCK:
            TEST_PAUSED = False
            TEST_WAKE.set()
    def quit_app(force=False):
        with LOCK:
            active = STATE['scan']['running'] or TEST_SCAN['running'] or any(j['status'] in ['queued', 'running'] for j in STATE['jobs']) or any(j['status'] in ['queued', 'waiting', 'running'] for j in TEST_JOBS)
        if active and not force:
            if ctypes.windll.user32.MessageBoxW(None, ('Quit Archiver? Active work will stop and pending items will be saved for paused recovery. Originals are retained for interrupted work.' if WORKFLOW_OPTIONS['recovery'] else 'Quit Archiver and cancel active work and queued items? Originals will be retained for cancelled work.'), 'Quit Archiver', 0x124) != 6:
                return False
        stop_application(server)
        return True
    actions = [
        ('Open Archiver', lambda: True, lambda: webbrowser.open(f'http://127.0.0.1:{server.server_port}')),
        ('Start / resume encoding queue', lambda: not WAKE.is_set() and any(j['status'] == 'queued' for j in STATE['jobs']), start_queue),
        ('Pause encoding after current file', lambda: WAKE.is_set(), pause_queue),
        ('Start / resume test queue', lambda: not TEST_WAKE.is_set() and any(j['status'] == 'queued' for j in TEST_JOBS), test_resume),
        ('Pause tests after current test', lambda: not TEST_PAUSED and any(j['status'] in ['queued', 'waiting', 'running'] for j in TEST_JOBS), test_pause),
    ]
    Tray(f'Archiver {VERSION}', actions, status, quit_app).run()


def main():
    global WORKFLOW_READY,WORKFLOW_ERROR,WORKFLOW_LOAD_WARNING,WATCH_STATE
    parser = argparse.ArgumentParser(description='Archiver local video utility')
    parser.add_argument('--version', action='version', version=f'Archiver {VERSION}')
    preview_number = int(VERSION.rsplit('.', 1)[-1]) if '-preview.' in VERSION else 0
    parser.add_argument('--port', type=int, default=8872 + preview_number if preview_number else 8765)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--tray', action='store_true', help='Run with a Windows notification-area icon')
    args = parser.parse_args()
    instance_lock = None
    if args.tray:
        if sys.platform != 'win32':
            parser.error('--tray requires Windows')
        from windows_tray import InstanceLock
        instance_lock = InstanceLock(args.port)
        if instance_lock.existing:
            if not args.no_browser:
                webbrowser.open(f'http://127.0.0.1:{args.port}')
            instance_lock.close()
            return
    try:
        tools=tool_config.load_paths()
        configure(tools['ffmpeg'], tools['ffprobe'])
    except Exception:
        pass
    try:
        WORKFLOW_OPTIONS.update(workflow_store.options())
        saved=workflow_store.load(VERSION) if WORKFLOW_OPTIONS['recovery'] else {'jobs':[],'tests':[]}
        if any(j.get('status') in ('queued','waiting','running') for j in [*saved['jobs'],*saved['tests']]):RECOVERY.update(saved)
        else:
            STATE['jobs']=[workflow_store.restored_job(j,VERSION) for j in saved['jobs']]
            TEST_JOBS.extend(saved['tests'])
        if saved.get('warnings'):WORKFLOW_LOAD_WARNING='; '.join(saved['warnings'])+'; original journal backed up.'
    except (ValueError,OSError,TypeError,KeyError) as exc:RECOVERY['error']=str(exc)
    try:WATCH_STATE=watch_folders.public()
    except (ValueError,OSError,TypeError,KeyError) as exc:
        try:
            backup=watch_folders.quarantine()
            WORKFLOW_LOAD_WARNING=(WORKFLOW_LOAD_WARNING+'; ' if WORKFLOW_LOAD_WARNING else '')+str(exc)+'. Watch settings backed up to '+str(backup)
            WATCH_STATE=watch_folders.public()
        except OSError:WATCH_STATE={'rules':[],'error':str(exc)}
    WORKFLOW_READY=True
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=test_worker, daemon=True).start()
    threading.Thread(target=workflow_worker,daemon=True).start()
    threading.Thread(target=profile_worker,daemon=True).start()
    threading.Thread(target=watch_worker,daemon=True).start()
    http_thread = threading.Thread(target=server.serve_forever, daemon=True)
    http_thread.start()
    try:
        print(f'Archiver is running at http://127.0.0.1:{args.port}')
        if not args.no_browser:
            webbrowser.open(f'http://127.0.0.1:{args.port}')
        if args.tray:
            run_tray(server)
        else:
            http_thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        if not SHUTTING_DOWN.is_set():
            stop_application(server)
        server.server_close()
        if instance_lock:
            instance_lock.close()


if __name__ == '__main__':
    main()
