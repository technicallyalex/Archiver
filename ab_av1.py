"""Pinned ab-av1 adapter: streamed logs and cancellable process trees."""
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
from functools import lru_cache

from quality import POLICIES, SAMPLING_VERSION

ROOT = Path(__file__).resolve().parent
BINARY = ROOT / 'tools' / 'ab-av1' / 'ab-av1.exe'
TARGET_XPSNR = 38.0
MIN_XPSNR, MAX_XPSNR = 30.0, 50.0
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def target_for(settings):
    value = settings.get('xpsnrTarget', TARGET_XPSNR)
    try:
        target = float(value)
    except (TypeError, ValueError):
        raise ValueError('Choose an XPSNR target from 30 to 50 dB') from None
    if isinstance(value, bool) or not math.isfinite(target) or not MIN_XPSNR <= target <= MAX_XPSNR:
        raise ValueError('Choose an XPSNR target from 30 to 50 dB')
    return target


def binary():
    return str(BINARY) if BINARY.is_file() else shutil.which('ab-av1')


@lru_cache(maxsize=4)
def _installation(executable,size,modified):
    version=''
    try:
        result=subprocess.run([executable,'--version'],stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        version=result.stdout.strip()
        if result.returncode or not version.startswith('ab-av1 '):raise ValueError('The executable did not report a valid ab-av1 version')
        help_result=subprocess.run([executable,'crf-search','--help'],stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if help_result.returncode or any(flag not in help_result.stdout for flag in ('--min-xpsnr','--stdout-format')):raise ValueError('This ab-av1 does not support XPSNR CRF search and JSON results. Restore the bundled copy.')
        return {'available':True,'version':version,'path':executable,'bundled':Path(executable).resolve()==BINARY.resolve(),'error':''}
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
        return {'available':False,'version':version,'path':executable,'bundled':Path(executable).resolve()==BINARY.resolve(),'error':str(exc)}

def installation(recheck=False):
    if recheck:_installation.cache_clear()
    executable=binary()
    if not executable:return {'available':False,'version':'','path':'','bundled':False,'error':'ab-av1 was not found in this build or on PATH'}
    try:
        path=Path(executable).resolve();stat=path.stat();return dict(_installation(str(path),stat.st_size,stat.st_mtime_ns))
    except OSError as exc:return {'available':False,'version':'','path':str(executable),'bundled':False,'error':str(exc)}


def encoder_for(settings, available):
    codec = settings.get('abCodec', 'av1')
    if codec not in ['av1', 'hevc', 'h264']:
        raise ValueError('Choose AV1, HEVC, or H.264 for ab-av1')
    name = {'av1': 'libsvtav1', 'hevc': 'libx265', 'h264': 'libx264'}[codec]
    if settings.get('encodingMode') == 'hardware':
        backend = settings.get('hardwareBackend', 'nvenc')
        if backend not in ['nvenc', 'qsv']:
            raise ValueError('Automated (Test) is not available for AMD AMF. Choose Software, NVIDIA NVENC or Intel Quick Sync, or use Automated (Estimate) or Manual.')
        name = codec + '_' + backend
    if name not in available:
        raise ValueError(f'{name} is not available in the configured FFmpeg. Choose another codec or encoding method.')
    if settings.get('container') == 'webm' and codec != 'av1':
        raise ValueError('WebM output requires AV1. Choose MP4 or MKV for H.264/HEVC.')
    return name


def windows(duration, count=3, length=10):
    # ab-av1 v0.11.7 sample_encode::sample; >=85% becomes a full pass.
    if count * length >= duration * .85:
        return [{'start': 0., 'duration': duration}]
    gap = (duration - count * length) / (count + 1)
    return [{'start': float(math.floor(gap * (i + 1) + length * i)), 'duration': float(length)} for i in range(count)]


def stop_tree(process):
    if process.poll() is None:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            process.terminate()
        process.wait()


class SamplePositionTracker:
    """Map FFmpeg progress timestamps to clips in the joined reference."""
    def __init__(self, directory, plan, duration, telemetry):
        self.directory=Path(directory);self.plan=plan;self.duration=duration;self.telemetry=telemetry
        self.stage=None;self.previous=None;self.baseline=None;self.lock=threading.Lock();self.stop=threading.Event()
        self.thread=threading.Thread(target=self.watch,daemon=True)
    def set_stage(self, stage):
        with self.lock:
            if self.stage==stage:return
            self.stage=stage;self.previous=None
            path=self.directory/('encoding-progress.txt' if stage=='search-encoding' else 'scoring-progress.txt')
            try:self.baseline=(path.stat().st_mtime_ns,path.stat().st_size)
            except OSError:self.baseline=None
            self.telemetry({'stage':stage,'activeSampleIndices':[], 'sampleIndex':None})
    def poll(self):
        with self.lock:
            if self.stage not in ('search-encoding','search-scoring'):return
            path=self.directory/('encoding-progress.txt' if self.stage=='search-encoding' else 'scoring-progress.txt')
            try:
                stamp=(path.stat().st_mtime_ns,path.stat().st_size)
                if stamp==self.baseline:return
                with path.open('rb') as stream:
                    stream.seek(0,2);stream.seek(max(0,stream.tell()-16384));text=stream.read().decode('utf-8',errors='replace')
            except OSError:return
            values=re.findall(r'out_time_us=(\d+)' if self.stage=='search-encoding' else r'pts_time:([\d.]+)',text)
            if not values:return
            seconds=float(values[-1])/(1000000 if self.stage=='search-encoding' else 1)
            if not math.isfinite(seconds):return
            total=sum(w['duration'] for w in self.plan)
            position=min(total,seconds/self.duration*total) if self.duration else 0
            boundary=0;index=len(self.plan)-1
            for i,window in enumerate(self.plan):
                boundary+=window['duration']
                if position<boundary:index=i;break
            marker=(self.stage,index)
            if marker!=self.previous:
                self.previous=marker;self.telemetry({'activeSampleIndices':[index],'sampleIndex':index+1})
    def watch(self):
        while not self.stop.wait(.15):self.poll()
    def close(self):
        self.stop.set()
        if self.thread.is_alive():self.thread.join(timeout=1)


def stream(command, directory, env, cancelled, line_callback):
    if cancelled():
        raise InterruptedError('Quality test cancelled')
    native_terminal = False
    if os.name == 'nt' and Path(command[0]).name.lower() == 'ab-av1.exe':
        try:
            import winpty
            native_terminal = True
        except ImportError:
            line_callback('stderr', 'Native terminal unavailable for this Python installation; streaming pipe output without a CLI ETA.')
    if native_terminal:
        from terminal_capture import run
        from terminal_screen import Screen
        screen = Screen()
        def terminal_chunk(chunk):
            for channel, line in screen.feed(chunk):
                line_callback(channel, line)
        run(command, directory, env, cancelled, terminal_chunk)
        return
    process = subprocess.Popen(command, cwd=directory, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    messages = queue.Queue(maxsize=2048)
    def read(pipe, channel):
        import codecs
        decoder = codecs.getincrementaldecoder('utf-8')('replace')
        pending = ''
        try:
            while True:
                chunk = pipe.read1(4096)
                if not chunk:
                    break
                pending += decoder.decode(chunk)
                parts = re.split(r'[\r\n]', pending)
                pending = parts.pop()
                for line in parts:
                    if line:
                        messages.put((channel, ANSI.sub('', line)))
            pending += decoder.decode(b'', final=True)
            if pending:
                messages.put((channel, ANSI.sub('', pending)))
        finally:
            pipe.close()
            messages.put((channel, None))
    threads = [threading.Thread(target=read, args=(pipe, channel), daemon=True)
               for pipe, channel in [(process.stdout, 'stdout'), (process.stderr, 'stderr')]]
    for thread in threads:
        thread.start()
    ended = 0
    try:
        while ended < 2:
            if cancelled():
                stop_tree(process)
                raise InterruptedError('Quality test cancelled')
            try:
                channel, line = messages.get(timeout=.2)
            except queue.Empty:
                continue
            if line is None:
                ended += 1
            else:
                line_callback(channel, line)
        code = process.wait()
        if code:
            raise ValueError(f'ab-av1 exited with code {code}. See its console log for details.')
    finally:
        stop_tree(process)
        # Drain before joining so cancelled readers cannot block on the bounded queue.
        while any(t.is_alive() for t in threads):
            try:
                messages.get(timeout=.1)
            except queue.Empty:
                pass
        for thread in threads:
            thread.join()


def analyze(item, settings, available, ffmpeg, ffprobe, directory, cancelled, progress, telemetry):
    executable = binary()
    if not executable:
        raise ValueError('ab-av1 is missing. Extract the complete Archiver preview including its tools folder.')
    encoder = encoder_for(settings, available)
    directory = Path(directory or Path(item['path']).parent)
    directory.mkdir(parents=True, exist_ok=True)
    target = settings.get('qualityMode', 'perceptual')
    if target not in POLICIES:
        target = settings.get('abTarget', 'perceptual')
    if target not in POLICIES:
        raise ValueError('Choose an ab-av1 quality target')
    minimum = target_for(settings)
    search_target = max(minimum,min(50.,float(settings.get('_searchTarget',minimum))))
    selection = item.get('_motionSelection')
    plan = selection['windows'] if selection else windows(item['duration'])
    search_duration = selection['referenceDuration'] if selection else item['duration']
    scale = item['duration'] / search_duration
    source_bytes = (item.get('video_bitrate', 0) / 8 * item['duration']) or item.get('size', 1)
    telemetry = telemetry or (lambda _: None)
    telemetry({'engine': 'ab-av1', 'encoder': encoder, 'sampleWindows': plan, 'sourceDuration': item['duration'],
               'stage':'search','activeSampleIndices':[], 'combinedSamples': bool(selection), 'sampleTotal': len(plan), 'encoderTotal': 1, 'trialsCompleted': 0, 'searchEta': None})
    preset = '8' if encoder == 'libsvtav1' else 'p5' if encoder.endswith('_nvenc') else 'medium'
    maximum = 63 if encoder == 'libsvtav1' else 51 if encoder.endswith(('_nvenc', '_qsv')) else 46
    maximum = min(maximum,int(settings.get('_searchMaxCrf',maximum)))
    env = dict(os.environ)
    # ab-av1 invokes tools by name. Isolate aliases to ensure the configured binaries are used.
    tool_dir = directory / 'tool-bin'
    tool_dir.mkdir(exist_ok=True)
    for name, source in [('ffmpeg', ffmpeg), ('ffprobe', ffprobe)]:
        dest = tool_dir / (name + ('.exe' if os.name == 'nt' else ''))
        if not dest.exists():
            try:
                os.link(Path(source).resolve(), dest)
            except OSError:
                shutil.copy2(source, dest)
    env['PATH'] = str(tool_dir.resolve()) + os.pathsep + env.get('PATH', '')
    env['RUST_LOG'] = 'ab_av1=info'
    env['TERM'] = 'xterm-256color'
    final, attempts = None, 0
    current_sample = 1
    measurements=[]
    infinite_crfs=set()
    command = [executable, 'crf-search', '-i', selection['path'] if selection else item['path'], '-e', encoder, '--preset', preset,
               '--min-xpsnr', str(search_target), '--max-encoded-percent', '10000', '--samples', '1' if selection else '3', '--sample-duration', f'{search_duration + 1}s' if selection else '10s',
               '--cache', 'false', '--crf-increment', '1', '--max-crf', str(maximum),
               '--pix-format', 'yuv420p', '--xpsnr-fps', '0', '--xpsnr-pix-format', 'yuv420p',
               '--temp-dir', str(directory.resolve()), '--stdout-format', 'json', '-v']
    # Stable keyframe / scene-change behavior must also be used in final output.
    # Keep source timestamp precision: the default encoder time base rounds VFR
    # frames to an average-FPS grid, making nearest-timestamp metrics compare
    # different frames. Mirror this option in the final encode.
    command += ['--keyint', '10s', '--enc', 'enc_time_base=demux']
    if encoder == 'libsvtav1':
        command += ['--scd', 'false']
    tracker = SamplePositionTracker(directory,plan,search_duration,telemetry) if selection else None
    if tracker:
        command += ['--enc', 'progress=' + str((directory/'encoding-progress.txt').resolve()),
                    '--reference-vfilter', 'metadata=mode=add:key=archiver_preview:value=1,metadata=mode=print:key=archiver_preview:file=scoring-progress.txt:direct=1']
        if encoder.endswith('_qsv'):command += ['--min-crf','1']
        for name in ('encoding-progress.txt','scoring-progress.txt'):
            (directory/name).unlink(missing_ok=True)
        tracker.thread.start()
    with (directory / 'ab-av1.log').open('a', encoding='utf-8') as log:
        def line(channel, text):
            nonlocal final, attempts, current_sample
            log.write(f'[{channel}] {text}\n'); log.flush()
            if not ('eta' in text.lower() and 'crf ' in text.lower()) and not (selection and ('predicted' in text.lower() or text.lstrip().startswith('{'))):
                progress(text)
            if 'encoding sample ' in text.lower():
                tracker.set_stage('search-encoding') if tracker else telemetry({'stage':'search-encoding','activeSampleIndices':[max(0,current_sample-1)]})
            if 'ab_av1::xpsnr' in text and ' vs reference ' in text:
                tracker.set_stage('search-scoring') if tracker else telemetry({'stage':'search-scoring','activeSampleIndices':[max(0,current_sample-1)]})
            infinite=re.search(r'crf\s+([\d.]+).*XPSNR\s+inf\b',text,re.I)
            if infinite:infinite_crfs.add(float(infinite[1]))
            cli = re.search(r'crf ([\d.]+) (\d+)/(\d+)', text, re.I)
            if cli:
                current_sample=int(cli[2])
                telemetry({**({'sampleIndex': int(cli[2])} if not selection else {}), 'qualityValue': float(cli[1]), 'qualityControl': 'ICQ' if encoder.endswith('_qsv') else 'CQ' if encoder.endswith('_nvenc') else 'CRF'})
            eta = re.search(r'eta\s+([^)]*)', text, re.I)
            if eta:
                telemetry({'searchEtaText': eta[1].strip(), 'terminalProgress': text})
            bar = re.search(r'([#█▓━]+)([░▒─\- ]{2,})\s*\(', text)
            if bar:
                telemetry({'searchPercent': min(99, 100 * len(bar[1]) / (len(bar[1]) + len(bar[2])))})
            match = re.search(r'(?:encoding )?sample (\d+)/(\d+).*?crf ([\d.]+)', text, re.I)
            if match:
                current_sample=int(match[1])
                telemetry({**({'sampleIndex': int(match[1])} if not selection else {}), 'qualityValue': float(match[3]), 'qualityControl': 'ICQ' if encoder.endswith('_qsv') else 'CQ' if encoder.endswith('_nvenc') else 'CRF'})
            if channel != 'stdout':
                return
            try:
                event = json.loads(text)
            except ValueError:
                return
            if event.get('xpsnr') is None and event.get('crf') in infinite_crfs:event['identical']=True
            if selection and event.get('type') in ('sample-encode-done', 'crf-search-done'):
                event['predicted_encode_size'] *= scale
                event['predicted_encode_seconds'] *= scale
                event['predicted_encode_percent'] = event['predicted_encode_size'] / source_bytes * 100
            if event.get('type') == 'sample-encode-done':
                if selection:
                    progress(f"{'ICQ' if encoder.endswith('_qsv') else 'CQ' if encoder.endswith('_nvenc') else 'CRF'} {event['crf']:g} · XPSNR {format(event['xpsnr'],'.2f')+' dB' if event.get('xpsnr') is not None else 'Identical' if event.get('identical') else 'Unavailable'} · Estimated video size {event['predicted_encode_percent']:.0f}% of original")
                tracker.set_stage('search') if tracker else telemetry({'stage':'search','activeSampleIndices':[]})
                attempts += 1
                measurements.append(dict(event))
                telemetry({'measurements':list(measurements)})
                telemetry({'trialsCompleted': attempts, 'latestScore': {'mean': event['xpsnr'], 'metric':'xpsnr', 'unit':'dB'},
                           'predictedEncodeSeconds': event['predicted_encode_seconds'], 'predictedEncodeSize': event['predicted_encode_size'],
                           'predictedPercent': event['predicted_encode_percent'], 'fromCache': event.get('from_cache', False)})
            elif event.get('type') == 'crf-search-done':
                final = event
        try:
            stream(command, directory, env, cancelled, line)
        finally:
            if tracker:tracker.close()
            telemetry({'activeSampleIndices':[]})
            (directory/'crf-search-measurements.json').write_text(json.dumps({'encoder':encoder,'preset':preset,'metric':'xpsnr','unit':'dB','targetScore':minimum,'measurements':measurements},indent=2),encoding='utf-8')
            shutil.rmtree(tool_dir, ignore_errors=True)
    if not final or not all(math.isfinite(float(final.get(k, float('nan')))) for k in ['crf', 'predicted_encode_size', 'predicted_encode_seconds', 'predicted_encode_percent']):
        raise ValueError('ab-av1 returned no valid final recommendation. See ab-av1.log.')
    if not final.get('identical') and (not isinstance(final.get('xpsnr'),(int,float)) or not math.isfinite(final['xpsnr'])):raise ValueError('ab-av1 returned no measured XPSNR recommendation')
    if (not final.get('identical') and final['xpsnr'] < minimum) or not (1 if encoder.endswith('_qsv') else 0) <= final['crf'] <= maximum:
        raise ValueError('ab-av1 recommendation did not satisfy the requested limits')
    rate = final['predicted_encode_size'] / item['duration']
    score = {'mean': final['xpsnr'], 'p05': None,'identical':final.get('identical',False)}
    winner = {'codec': settings.get('abCodec', 'av1'), 'encoder': encoder, 'bitrate': 'cqp' if encoder.endswith(('_nvenc', '_qsv')) else 'crf',
              'qualityValue': int(final['crf']), 'encoderPriority': 'balanced', 'bytesPerSecond': rate,
              'secondsPerSecond': final['predicted_encode_seconds'] / item['duration'], 'scores': [score]}
    telemetry({'encodersCompleted': 1})
    keep=False
    return {'engine': 'ab-av1', 'winner': winner, 'alternatives': [winner], 'keepOriginal': keep,
            'sourceDuration': item['duration'], 'sourceWidth':item.get('width'), 'sourceHeight':item.get('height'), 'sourceFps':item.get('fps'), 'estimatedVideoBytes': final['predicted_encode_size'],
            'videoSavings': 1 - final['predicted_encode_percent'] / 100, 'sizeComparison':'source-video' if selection and item.get('video_bitrate',0)>0 else 'source-file', 'model': 'XPSNR', 'metric':'xpsnr', 'unit':'dB', 'trials': attempts,
            'sampleWindows': plan, 'motionSelection': selection and {k:v for k,v in selection.items() if k != 'path'}, 'samplingVersion': SAMPLING_VERSION, 'encoderTimeBase': 'demux',
            'policy': {'metric':'xpsnr','mean': minimum, 'p05': 0, 'second': 0}, 'failures': [], 'preview': False,
            'note': 'Quality target reached. Estimated size and time are based on samples; output size does not restrict encoding.',
            'measurements':measurements,'targetScore':minimum,'encoderPreset':preset,
            'coverage': 'Motion-selected footage covering typical and higher motion; size estimates may vary across the full recording.' if selection else 'Three distributed samples; size estimates may vary across the full recording.',
            'calibration': f'Mean sample XPSNR target: {minimum:g} dB. Not a guarantee of visually lossless output. Frame-percentile floors are not measured by ab-av1.'}
