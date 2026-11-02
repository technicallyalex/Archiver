"""Final-file checks performed before an original can be replaced."""
import math,tempfile
from pathlib import Path
import preservation

def dimensions(source,settings):
    width,height=source['width'],source['height']
    if settings.get('mode') in ('copy','move') or settings.get('qualityMode')=='original':return width,height
    if abs(source.get('rotation',0))%180==90:width,height=height,width
    if settings.get('qualityMode')=='proxy':
        import proxy_media
        resolved=proxy_media.resolve(source,settings)
        return resolved['width'],resolved['height']
    resolution=settings.get('resolution','original')
    if resolution!='original':
        box=int(resolution);factor=min(1,box/height,(round(box*16/9/2)*2)/width);width*=factor;height*=factor
    return max(2,int(width)//2*2),max(2,int(height)//2*2)

def expected_duration(source,config):
    if config.get('mode') in ('copy','move') or config.get('qualityMode')=='original':return source['duration']
    video=source.get('videoDuration') or source['duration']
    p=preservation.settings(config.get('preservation'))
    audio=preservation.selected(source,'audio',p['audioTracks']) if config.get('audio')!='none' else []
    subs=preservation.selected(source,'subtitle',p['subtitleTracks']) if p['subtitles']!='none' else []
    durations=[video,*[s.get('duration',0) or 0 for s in [*audio,*subs]]]
    # Missing stream durations cannot prove a shorter intended output.
    if audio and any(not s.get('duration') for s in audio):durations.append(source['duration'])
    return max(durations)


def inspect(source,output,settings):
    expected=dimensions(source,settings);checks=[]
    def check(name,passed,detail):
        checks.append({'name':name,'passed':bool(passed),'detail':detail})
        if not passed:raise ValueError(name+' verification failed: '+detail+'. Original retained.')
    duration=expected_duration(source,settings)
    check('Duration',abs(output['duration']-duration)<=max(.25,3/max(source.get('fps',1),1)),f"{output['duration']:.3f}s output / {duration:.3f}s expected")
    check('Resolution',(output['width'],output['height'])==tuple(expected),f"{output['width']} × {output['height']} / expected {expected[0]} × {expected[1]}")
    exact=settings.get('mode') in ('copy','move') or settings.get('qualityMode')=='original'
    fps=source.get('fps',0) if exact or settings.get('fps','original')=='original' else float(settings['fps'])
    if fps:check('Frame rate',abs(output['fps']-fps)<=max(.05,fps*.005),f"{output['fps']:.3f} fps / expected {fps:.3f}")
    p=preservation.settings(settings.get('preservation'));audio=preservation.selected(source,'audio','all' if exact else p['audioTracks'])
    if not source.get('streams'):audio=source.get('audio_streams',[])
    if settings.get('audio')=='none' and not exact:audio=[]
    check('Audio tracks',len(output.get('audio_streams',[]))==len(audio),f"{len(output.get('audio_streams',[]))} / expected {len(audio)}")
    if settings.get('audio')=='copy' and source.get('streams') and output.get('streams'):
        actual=[s for s in output['streams'] if s['type']=='audio']
        check('Copied audio codecs',[s['codec'] for s in audio]==[s['codec'] for s in actual],' / '.join(s['codec'] for s in actual))
    if settings.get('preservation') and not exact:
        subs=preservation.selected(source,'subtitle',p['subtitleTracks']) if p['subtitles']!='none' else []
        check('Subtitle tracks',len([s for s in output.get('streams',[]) if s['type']=='subtitle'])==len(subs),f'{len(subs)} expected subtitle tracks')
        if p['chapters'] and source.get('chapters'):check('Chapters',len(output.get('chapters',[]))==len(source['chapters']),f"{len(source['chapters'])} expected chapters")
        if p['color'] and settings.get('codec')!='prores':
            for field in ('color_space','color_transfer','color_primaries','color_range'):
                if source.get(field) not in (None,'','unknown','unspecified'):
                    actual=output.get(field)
                    # AVC/HEVC/AV1 omit an explicit limited-range flag when it is
                    # the coded-video default. Do not reject that equivalent intent.
                    if field=='color_range' and actual in (None,'','unknown','unspecified') and output.get('codec') in ('h264','hevc','av1') and output.get('pixel_format','').startswith('yuv') and not output.get('pixel_format','').startswith('yuvj'):actual='tv'
                    check(field.replace('_',' ').capitalize(),source[field]==actual,str(actual))
    target=preservation.pixel_format(source,settings)
    if not exact and target and output.get('pixel_format'):
        actual=output['pixel_format'];formats={target}
        # ProRes 4444's decoder exposes the coded precision as 12-bit, including
        # encodes fed by a 10-bit encoder surface. Higher decoded precision is valid.
        if settings.get('qualityMode')=='archive' and '444' in target:formats.add(target.replace('10le','12le'))
        check('Pixel format',actual in formats,f"{actual} / expected {target}")
    return checks

def quality_windows(duration,used=()):
    length=min(8.,duration);chosen=[]
    for fraction in (.19,.57,.83,.37,.71,.07):
        w={'start':round(max(0,(duration-length)*fraction),6),'duration':length}
        if not any(abs(w['start']-s['start'])<length for s in [*used,*chosen]):chosen.append(w)
        if len(chosen)==3:break
    if not chosen:chosen=[{'start':0.,'duration':length}]
    return chosen

def quality(analyzer,source,output,settings,target,progress,used=()):
    rows=[];directory=Path(output).parent
    from ab_av1 import target_for
    target=target_for({'xpsnrTarget':target})
    with tempfile.TemporaryDirectory(prefix='.archiver-quality-',dir=directory) as tmp:
        tmp=Path(tmp)
        for i,w in enumerate(quality_windows(source['duration'],used)):
            progress(f"Quality verification · Clip {i+1} · {w['start']:.1f}s")
            clips=[]
            for name,path in [('source',source['path']),('output',str(output))]:
                clip=tmp/(name+'.mkv');filters=['setpts=PTS-STARTPTS']
                width,height=dimensions(source,settings)
                if name=='source' and (width,height)!=(source['width'],source['height']):filters.insert(0,f'scale={width}:{height}')
                if settings.get('fps','original')!='original':filters.append('fps='+settings['fps'])
                analyzer.run([analyzer.ffmpeg,'-v','error','-nostdin','-y','-ss',str(w['start']),'-i',str(path),'-t',str(w['duration']),'-map','0:v:0','-an','-sn','-dn','-vf',','.join(filters),'-c:v','ffv1','-threads','2','-fps_mode','passthrough','-enc_time_base','demux',str(clip)])
                clips.append(clip)
            fps=source['fps'] if settings.get('fps','original')=='original' else float(settings['fps'])
            score=analyzer.score_xpsnr(*clips,tmp,fps,0)
            passed=score>=target and not math.isnan(score);rows.append({**w,'xpsnr':score if math.isfinite(score) else None,'identical':score==math.inf,'passed':passed})
            if not passed:raise ValueError(f"Quality verification clip at {w['start']:.1f}s missed {target:g} dB XPSNR ({score:.2f} dB). Original retained.")
    return rows
