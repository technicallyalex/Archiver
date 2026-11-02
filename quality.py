"""XPSNR scoring, shared encoder utilities, and final-output verification."""
import hashlib
import json
import math
import re
from pathlib import Path
import subprocess
import tempfile
import time

POLICY_VERSION = 3
SAMPLING_VERSION = 6
CODEC_ESTIMATES = {
    'version': 1,
    # Conservative application priors, not codec-standard guarantees. See docs/CODEC_ESTIMATES.md.
    'relativeBitrate': {'h264': 1., 'hevc': .65, 'vp9': .65, 'av1': .50},
    'sources': ['https://www.itu.int/en/ITU-T/studygroups/2022-2024/16/video/Pages/jctvc.aspx',
                'https://developers.google.com/media/vp9', 'https://arxiv.org/abs/2008.06091'],
}
MODEL = 'XPSNR'
# Preview policies: conservative engineering defaults, pending subjective calibration.
POLICIES = {'perceptual': {'metric':'xpsnr','mean':38.0,'p05':0,'second':0}}

PRESETS = {
    'libx264': ['veryfast', 'medium', 'slow'],
    'libx265': ['fast', 'medium', 'slow'],
    'libsvtav1': ['10', '8', '6'],
}


def preset_args(encoder, priority):
    index = {'fast': 0, 'balanced': 1, 'smallest': 2}[priority]
    if encoder in PRESETS:
        return ['-preset', PRESETS[encoder][index]]
    if encoder.endswith('_nvenc'):
        return ['-preset', ['p3', 'p5', 'p7'][index]]
    if encoder.endswith('_qsv'):
        return ['-preset', ['fast', 'medium', 'slow'][index]]
    if encoder.endswith('_amf'):
        return ['-quality', ['speed', 'balanced', 'quality'][index]]
    if encoder in ['libaom-av1', 'libvpx-vp9']:
        return ['-cpu-used', ['6', '4', '2'][index]]
    raise ValueError('Unsupported automatic encoder')


def candidates(available, encoding_mode, priority, container, hardware_backend='nvenc'):
    if encoding_mode not in ['software', 'hardware'] or priority not in ['fast', 'balanced', 'smallest']:
        raise ValueError('Invalid automatic quality preference')
    if hardware_backend not in ['nvenc', 'qsv', 'amf']:
        raise ValueError('Choose NVIDIA, Intel, or AMD hardware encoding')
    codecs = ['av1'] if container == 'webm' else ['h264', 'hevc', 'av1']
    result = []
    for codec in codecs:
        software = {'h264': 'libx264', 'hevc': 'libx265', 'av1': 'libsvtav1'}[codec]
        names = [software] if encoding_mode == 'software' else [f'{codec}_{hardware_backend}']
        if encoding_mode == 'software' and codec == 'av1' and software not in available:
            names.append('libaom-av1')
        result.extend((codec, name) for name in names if name in available)
    if not result:
        raise ValueError('No encoders available for this encoding method and container. Choose another method or use Manual.')
    return result


def validate_source(item):
    if item.get('color_transfer') in ['smpte2084', 'arib-std-b67'] or item.get('pixel_format') != 'yuv420p':
        raise ValueError('Automated (Test) supports 8-bit SDR YUV 4:2:0 sources only. Keep this source unchanged or review Manual controls.')
    if not item.get('duration') or not item.get('fps') or item['width'] % 2 or item['height'] % 2:
        raise ValueError('Automatic quality requires known duration/frame rate and even video dimensions.')


def fingerprint(item, settings, ffmpeg, ffprobe):
    path = Path(item['path'])
    stat = path.stat()
    tools = [(str(Path(p).resolve()), Path(p).stat().st_size, Path(p).stat().st_mtime_ns) for p in [ffmpeg, ffprobe]]
    identity = [str(path.resolve()), stat.st_size, stat.st_mtime_ns, tools, MODEL, POLICY_VERSION, SAMPLING_VERSION,
                {k: settings.get(k) for k in ['qualityMode', 'encodingMode', 'hardwareBackend', 'priority', 'container', 'autoEngine', 'abTarget', 'abCodec']}, POLICIES]
    if settings.get('autoEngine') == 'ab-av1':
        import ab_av1
        executable = ab_av1.binary()
        if not executable:
            raise OSError('ab-av1 executable missing')
        tool = Path(executable)
        identity.append(settings.get('testLevel') or 'balanced')
        identity.append([str(tool.resolve()), tool.stat().st_size, tool.stat().st_mtime_ns, 'adapter-3-motion-xpsnr', ab_av1.target_for(settings)])
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()










class Analyzer:
    def __init__(self, ffmpeg, ffprobe, command_for, cancelled, progress, work_directory=None, telemetry=None):
        self.ffmpeg, self.ffprobe, self.command_for = ffmpeg, ffprobe, command_for
        self.cancelled, self.progress = cancelled, progress
        self.trials = 0
        self.work_directory = work_directory
        self.telemetry = telemetry or (lambda _: None)
        self.operation_duration = 0
        self.shared_directory = None
        self.shared_references = {}
        self.shared_packets = []
        self.trial_cache = {}
        self.frame_cache = {}


    def report(self, message, **details):
        self.progress(message)
        self.telemetry({'operationPercent': None, **details})

    def check(self):
        if self.cancelled():
            raise InterruptedError('Quality analysis cancelled')

    def run(self, command, cwd=None, include_stderr=False):
        self.check()
        process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8', errors='replace',
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            while True:
                self.check()
                try:
                    stdout, stderr = process.communicate(timeout=.25)
                    if '-progress' in command:
                        self.telemetry({'operationPercent': 100})
                    break
                except subprocess.TimeoutExpired as exc:
                    # communicate retains partial progress while draining both pipes.
                    # The quality score itself is always read from the completed JSON log.
                    if '-progress' in command:
                        output = exc.output or b''
                        if isinstance(output, bytes):
                            output = output.decode('utf-8', errors='replace')
                        times = re.findall(r'out_time_us=(\d+)', output)
                        if times and self.operation_duration:
                            self.telemetry({'operationPercent': min(99.9, int(times[-1]) / 1_000_000 / self.operation_duration * 100)})
                    continue
            if process.returncode:
                raise ValueError(stderr[-1800:] or 'Media processing failed')
            return stdout + '\n' + stderr if include_stderr else stdout
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def frames(self, path):
        path=Path(path)
        stat=path.stat()
        key=(str(path.resolve()),stat.st_size,stat.st_mtime_ns)
        if key in self.frame_cache:return self.frame_cache[key]
        data = json.loads(self.run([self.ffprobe, '-v', 'error', '-select_streams', 'v:0',
                                   '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time,width,height,pix_fmt',
                                   '-of', 'json', str(path)]))
        frames = data.get('frames', [])
        if not frames:
            raise ValueError('Sample contains no decoded frames')
        # References are decoded repeatedly across candidates. Cache only short
        # sample inventories and invalidate on file replacement or modification.
        if len(frames)<=10000:
            if len(self.frame_cache)>=64:self.frame_cache.pop(next(iter(self.frame_cache)))
            self.frame_cache[key]=frames
        return frames



    def score_xpsnr(self, reference, encoded, directory, fps, lead):
        original, distorted = self.frames(reference), self.frames(encoded)
        if len(original) != len(distorted):
            raise ValueError('Sample frame counts do not match')
        a0, b0 = (float(f[0]['best_effort_timestamp_time']) for f in [original, distorted])
        for a, b in zip(original, distorted):
            if (a['width'], a['height']) != (b['width'], b['height']) or abs(float(a['best_effort_timestamp_time'])-a0-float(b['best_effort_timestamp_time'])+b0) > .003:
                raise ValueError('Sample dimensions or frame timestamps do not match')
        skip = min(round(lead*fps), max(0,len(original)-1))
        formats={f.get('pix_fmt','yuv420p') for f in [original[0],distorted[0]]}
        if len(formats)!=1:raise ValueError('XPSNR requires matching pixel formats and bit depths; choose matching output precision before quality verification')
        pixel_format=next(iter(formats))
        graph = (f'[0:v]trim=start_frame={skip},format={pixel_format},setpts=PTS-STARTPTS,settb=AVTB[r];'
                 f'[1:v]trim=start_frame={skip},format={pixel_format},setpts=PTS-STARTPTS,settb=AVTB[d];'
                 '[r][d]xpsnr=shortest=true:ts_sync_mode=nearest')
        text = self.run([self.ffmpeg,'-hide_banner','-i',str(reference),'-i',str(encoded),'-filter_complex',graph,
                         '-an','-sn','-dn','-f','null','-'],cwd=directory,include_stderr=True)
        values = re.findall(r'\(minimum:\s*([+-]?(?:inf|[\d.]+))\)',text)
        if not values:
            raise ValueError('FFmpeg returned no XPSNR score; original retained')
        return float(values[-1])

    def verify_output(self, item, output, policy):
        """Check distributed final-file regions before publishing/replacing anything."""
        with tempfile.TemporaryDirectory(prefix='archiver-verify-', dir=self.work_directory or Path(item['path']).parent) as tmp:
            directory = Path(tmp)
            if policy.get('metric')!='xpsnr':raise ValueError('Only XPSNR quality verification is supported')
            from ab_av1 import windows as ab_windows
            windows = [(s['start'],s['duration']) for s in ab_windows(item['duration'])]
            measured = []
            for index in sorted(set([0, len(windows) // 2, len(windows) - 1])):
                start, length = windows[index]
                paths = []
                for name, source in [('reference', item['path']), ('output', str(output))]:
                    path = directory / f'{name}.mkv'
                    self.run([self.ffmpeg, '-v', 'error', '-y', '-ss', str(start), '-i', source, '-t', str(length),
                              '-map', '0:v:0', '-an', '-c:v', 'ffv1', '-fps_mode', 'passthrough', '-enc_time_base', 'demux', str(path)])
                    paths.append(path)
                measured.append(self.score_xpsnr(*paths, directory, item['fps'], 0))
            if measured and not sum(measured)/len(measured) >= policy['mean']:
                raise ValueError(f"Final output failed mean XPSNR {policy['mean']:g} dB verification. Original retained.")
