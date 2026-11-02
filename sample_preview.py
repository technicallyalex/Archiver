"""Small source-timed H.264 proxies, separate from quality measurements."""
from pathlib import Path
import os
import subprocess
import threading

_FAILED_HARDWARE=set()
_HARDWARE_LOCK=threading.Lock()


def native_mime(item):
    suffix=Path(item['path']).suffix.lower()
    container='video/mp4' if suffix in ('.mp4','.m4v','.mov') else 'video/webm' if suffix=='.webm' else 'video/x-matroska' if suffix=='.mkv' else 'application/octet-stream'
    codec={'h264':'avc1','hevc':'hvc1','av1':'av01','vp9':'vp9','vp8':'vp8'}.get(item.get('codec'))
    return container+('; codecs="'+codec+'"' if codec else '')


def command(ffmpeg, source, output, start, length, encoder="libx264"):
    tuning = {"libx264":["-preset","ultrafast","-crf","28"],"h264_nvenc":["-preset","p1","-rc","vbr","-cq","30"],"h264_qsv":["-preset","veryfast","-global_quality","28"],"h264_amf":["-quality","speed","-rc","cqp","-qp_i","28","-qp_p","28"]}[encoder]
    return [ffmpeg, '-v', 'error', '-nostdin', '-y', '-threads', '1', '-ss', str(start), '-i', str(source),
            '-t', str(min(30, length)), '-map', '0:v:0', '-an', '-sn', '-dn', '-filter_threads', '1',
            '-vf', 'scale=320:-2', '-c:v', encoder, *tuning, '-pix_fmt', 'yuv420p',
            '-threads', '1', '-fps_mode', 'passthrough', '-enc_time_base', 'filter', '-movflags', '+faststart', str(output)]


def create(ffmpeg, source, output, start, length, cancelled, encoders=()):
    for encoder in ['h264_nvenc','h264_qsv','h264_amf','libx264']:
        with _HARDWARE_LOCK:
            failed=(str(ffmpeg),encoder) in _FAILED_HARDWARE
        if encoder!='libx264' and (encoder not in encoders or failed):continue
        try:
            _create(ffmpeg, source, output, start, length, cancelled, encoder)
            return encoder
        except ValueError:
            if encoder=='libx264':raise
            with _HARDWARE_LOCK:_FAILED_HARDWARE.add((str(ffmpeg),encoder))


def _create(ffmpeg, source, output, start, length, cancelled, encoder):
    output = Path(output)
    temporary = output.with_name(output.stem + '.partial.mp4')
    if cancelled():
        raise InterruptedError('Preview cancelled')
    process = subprocess.Popen(command(ffmpeg, source, temporary, start, length, encoder), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0))
    try:
        while True:
            if cancelled():
                raise InterruptedError('Preview cancelled')
            try:
                _, error = process.communicate(timeout=.2)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode or not temporary.is_file() or not temporary.stat().st_size:
            raise ValueError(error[-1000:] or 'Preview unavailable')
        if cancelled():
            raise InterruptedError('Preview cancelled')
        os.replace(temporary, output)
    finally:
        if process.poll() is None:
            process.kill();process.communicate()
        temporary.unlink(missing_ok=True)
