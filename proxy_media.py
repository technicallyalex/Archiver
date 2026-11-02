"""Editing proxy presets: ProRes or short-GOP delivery codecs at reduced dimensions.

The profile controls VBR; Apple's 1080p29.97 45 Mb/s rate is an estimate,
not a forced bitrate or a promise of source-quality retention.
"""
import math
from fractions import Fraction
from pathlib import Path
import prores


CODECS={'h264':('H.264',['libx264']),'hevc':('H.265',['libx265']),'av1':('AV1',['libsvtav1','libaom-av1']),'prores':('ProRes 422 Proxy',['prores_ks'])}


def container_for(settings):return 'mp4' if settings.get('proxyCodec')=='av1' else 'mov'


def encoder_for(settings, available, item=None):
    codec=settings.get('proxyCodec','prores')
    if codec not in CODECS:raise ValueError('Choose H.264, H.265, AV1 or ProRes for proxies')
    if codec=='prores' or settings.get('encodingMode','software')=='software':
        choices=CODECS[codec][1]
        if codec=='av1' and item and min(resolve(item,settings)[k] for k in ('width','height'))<64:choices=['libaom-av1']
        encoder=next((e for e in choices if e in available),None)
    elif settings.get('encodingMode')=='hardware' and settings.get('hardwareBackend','nvenc') in ('nvenc','qsv','amf'):
        encoder=codec+'_'+settings.get('hardwareBackend','nvenc')
    else:raise ValueError('Choose a software or hardware encoding method for proxies')
    if encoder not in available:raise ValueError('No encoder is available for this proxy format and method. Choose another method or configure FFmpeg.')
    return encoder


def resolve(item, settings):
    scale = str(settings.get('proxyScale', '2'))
    if scale not in ('2', '4'):
        raise ValueError('Choose half or quarter proxy resolution')
    codec = settings.get('proxyCodec', 'prores')
    if codec not in CODECS:raise ValueError('Choose H.264, H.265, AV1 or ProRes for proxies')
    # Reuse the existing SDR/chroma/alpha safeguards for the selected profile.
    prores.resolve(item, {'proresProfile': 'proxy'})
    if item.get('field_order', 'unknown') not in ('unknown', 'progressive', ''):
        raise ValueError('Proxy presets currently support progressive video only')
    divisor = int(scale)
    width, height = int(item['width']) // (2 * divisor) * 2, int(item['height']) // divisor
    if codec != 'prores':height = height // 2 * 2
    if min(width, height) < 2:
        raise ValueError('The source is too small for this proxy resolution')
    rate = (45e6 if codec == 'prores' else 8e6) * width * height / (1920 * 1080) * item['fps'] / 29.97
    if codec != 'prores':rate = max(500000, round(rate / 1000) * 1000)
    streams = item.get('audio_streams', [])
    if item.get('audio') and (not streams or any(not s.get('sample_rate') or not s.get('channels') for s in streams)):
        raise ValueError('Rescan this file to read its audio channels and sample rate before creating proxies')
    audio_rate = sum(s['sample_rate'] * s['channels'] * 24 for s in streams)
    return {'width': width, 'height': height, 'scale': scale,
            'folder': 'Half' if scale == '2' else 'Quarter',
            'codec':codec, 'label':CODECS[codec][0], 'videoBitrate': rate,
            'gop':max(1,round(item['fps'] / 2)),
            'estimatedVideoBytes': rate * item['duration'] / 8,
            'estimatedBytes': (rate + audio_rate) * item['duration'] / 8}


def output_path(item, settings):
    resolved = resolve(item, settings)
    mode = settings.get('mode', 'preserve')
    if mode not in ('preserve', 'directory'):
        raise ValueError('Proxy presets keep originals. Choose Keep originals or Save to another folder.')
    source = Path(item['path'])
    root = Path(settings['destination']).expanduser().resolve() if mode == 'directory' else source.parent
    location=settings.get('proxyLocation','subfolder')
    if location not in ('subfolder','next-to','custom'):raise ValueError('Choose a proxy output location')
    if location=='custom' and mode!='directory':raise ValueError('Choose a custom proxy output folder')
    if location=='next-to':root=source.parent
    extension='.'+container_for(settings)
    if location in ('next-to','custom'):
        return root/(source.stem+'_proxy'+extension)
    folder=root/'Proxies'/resolved['folder']
    if resolved['codec']!='prores':folder/={'h264':'H264','hevc':'HEVC','av1':'AV1'}[resolved['codec']]
    return folder/(source.stem+extension)



def command(ffmpeg, source, output, item, settings, encoder=None):
    r = resolve(item, settings)
    if Path(output).suffix.lower() != '.'+container_for(settings):raise ValueError('This proxy codec requires '+container_for(settings).upper())
    vf = f"scale={r['width']}:{r['height']}:flags=lanczos"
    if prores.FORMATS[item['pixel_format']][1] == 'rgb':
        matrix = 'bt709' if item['height'] >= 720 else 'bt601'
        vf += f':in_range=full:out_range=tv:out_color_matrix={matrix}'
    encoder = encoder or CODECS[r['codec']][1][0]
    if encoder not in [*CODECS[r['codec']][1],*[r['codec']+'_'+b for b in ('nvenc','qsv','amf') if r['codec']!='prores']]:
        raise ValueError('Encoder does not match the proxy codec')
    cmd = [ffmpeg, '-hide_banner', '-nostdin', '-y', '-xerror', '-noautorotate', '-i', str(source),
           '-map', '0:v:0', '-map', '0:a?', '-map_metadata', '0', '-map_chapters', '0', '-c:v', encoder]
    if r['codec'] == 'prores':
        cmd += ['-profile:v', '0', '-pix_fmt', 'yuv422p10le']
    else:
        rate = int(r['videoBitrate']/1000)
        cmd += ['-pix_fmt','yuv420p','-g',str(r['gop']),'-bf','0','-flags','+cgop',
                '-b:v',f'{rate}k','-maxrate',f'{round(rate*1.5)}k','-bufsize',f'{rate*2}k']
        if r['codec']=='h264':cmd+=['-profile:v','high']
        elif r['codec']=='hevc':cmd+=['-tag:v','hvc1']
        if encoder.endswith('_amf'):cmd+=['-quality','speed']
        elif encoder.endswith('_nvenc'):cmd+=['-preset','p3']
        elif encoder.endswith('_qsv'):cmd+=['-preset','fast']
        elif encoder in ('libx264','libx265'):cmd+=['-preset','veryfast']
        elif encoder=='libsvtav1':cmd+=['-preset','8','-svtav1-params','pred-struct=1:enable-tf=0:rc=2','-minrate',f'{rate}k','-maxrate',f'{rate}k']
        elif encoder=='libaom-av1':cmd+=['-cpu-used','8','-lag-in-frames','0','-usage','realtime']
        if encoder=='libx264':cmd+=['-refs','1','-sc_threshold','0']
        elif encoder=='libx265':cmd+=['-x265-params','bframes=0:scenecut=0:rc-lookahead=0']
    cmd += ['-vf', vf, '-fps_mode:v', 'passthrough', '-enc_time_base:v', 'demux', '-c:a', 'pcm_s24le']
    if item.get('timecode'):
        cmd += ['-timecode', item['timecode']]
    if prores.FORMATS[item['pixel_format']][1] == 'rgb':
        cmd += ['-color_range', 'tv', '-colorspace', 'bt709' if item['height'] >= 720 else 'smpte170m']
    return cmd + ['-movflags', '+faststart', '-progress', 'pipe:1', '-stats_period', '0.5', '-stats', str(output)]


def verify(source, result, settings):
    r = resolve(source, settings)
    if (result['width'], result['height']) != (r['width'], r['height']):
        raise ValueError('Proxy dimensions did not match the preset; output was not published')
    valid_format = (result['codec'] == 'prores' and result.get('profile', '').lower() == 'proxy' and result.get('pixel_format') == 'yuv422p10le') if r['codec']=='prores' else (result['codec']==r['codec'] and result.get('pixel_format')=='yuv420p')
    if not valid_format:
        raise ValueError('Proxy format verification failed; output was not published')
    if not math.isclose(result['fps'], source['fps'], rel_tol=1e-5) or abs(result['duration'] - source['duration']) > max(.15, 2 / source['fps']):
        raise ValueError('Proxy frame rate or duration changed; output was not published')
    if source.get('timecode') and result.get('timecode') != source['timecode']:
        raise ValueError('Proxy timecode did not match the source; output was not published')
    if int(result.get('rotation', 0)) % 360 != int(source.get('rotation', 0)) % 360:
        raise ValueError('Proxy orientation did not match the source; output was not published')
    def aspect(item):
        try:sar=Fraction(item.get('sample_aspect_ratio','1:1').replace(':','/'))
        except (ValueError,ZeroDivisionError):sar=Fraction(1)
        return float(sar)*item['width']/item['height'] if sar>0 else item['width']/item['height']
    if not math.isclose(aspect(source),aspect(result),rel_tol=.001):raise ValueError('Proxy display aspect ratio changed; output was not published')
    original_audio, output_audio = source.get('audio_streams', []), result.get('audio_streams', [])
    if len(original_audio) != len(output_audio) or any((a['channels'], a['sample_rate']) != (b['channels'], b['sample_rate']) for a, b in zip(original_audio, output_audio)):
        raise ValueError('Proxy audio layout changed; output was not published')

    if any(a.get('channel_layout') and b.get('channel_layout') and a['channel_layout']!=b['channel_layout'] for a,b in zip(original_audio,output_audio)):
        raise ValueError('Proxy audio channel order changed; output was not published')
