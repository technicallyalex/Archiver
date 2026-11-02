"""Exact-codec comparisons: original source plus stream-copy test output.

No comparison path re-encodes, resizes, or substitutes proxy video.
"""
import hashlib
import json
import threading
from pathlib import Path
from quality import Analyzer
import sample_preview

LOCK=threading.RLock()
JOBS={}
REMUX_LOCK=threading.Lock()

def clips(job):
    result=job.get('result') or {};result=(result.get('profiles') or {}).get('perceptual',result)
    return job.get('progress',{}).get('comparisonClips') or result.get('comparisonClips') or result.get('validation',{}).get('checks',[])

def public():
    with LOCK:return {k:{x:v for x,v in value.items() if x!='paths'} for k,value in JOBS.items()}

def prepare(job,index,ffmpeg,ffprobe,media_lock,cancelled,command_for,full_resolution=False):
    if job['status'] not in ('running','completed','failed','cancelled'):raise ValueError('Wait for a sample evaluation to finish before comparing')
    rows=clips(job)
    if type(index) is not int or not 0<=index<len(rows):raise ValueError('Choose an available measured clip')
    row=dict(rows[index]);root=Path(job['outputDirectory']).resolve()
    reference,encoded=[Path(row.get(name,'')).resolve() for name in ('reference','encoded')]
    if any(not p.is_relative_to(root) or not p.is_file() for p in (reference,encoded)):
        raise ValueError('Exact measured clips are unavailable. Run a new test.')
    source=Path(job['source']).resolve()
    if not source.is_file():raise ValueError('The original source is unavailable')
    stamp=hashlib.sha256(str((reference,encoded)).encode()).hexdigest()[:16]
    key=job['id']+':native:'+stamp
    with LOCK:
        if key in JOBS and (JOBS[key]['status'] in ('waiting','running') or JOBS[key]['status']=='ready' and all(Path(p).is_file() for p in JOBS[key]['paths'].values())):return key
        directory=root/'comparison'/stamp/'original-codec';directory.mkdir(parents=True,exist_ok=True)
        JOBS[key]={'status':'waiting','message':'Preparing original-codec playback','paths':{},'index':index,'duration':row['duration'],'sourceStart':row['start'],'fullResolution':True,'reencoded':False}
    def generate():
        def update(**kw):
            with LOCK:JOBS[key].update(kw)
        try:
            with REMUX_LOCK:
                analyzer=Analyzer(ffmpeg,ffprobe,command_for,cancelled,lambda _:None)
                def metadata(path):
                    data=json.loads(analyzer.run([ffprobe,'-v','error','-select_streams','v:0','-show_streams','-show_format','-of','json',str(path)]))
                    stream=data['streams'][0]
                    return data,{'path':str(path),'codec':stream.get('codec_name','')}
                original,source_item=metadata(source);_,output_item=metadata(encoded)
                if output_item['codec'] not in ('h264','hevc','av1'):raise ValueError('Browser comparison does not support this test codec. No proxy has been substituted.')
                update(status='running',message='Remuxing measured output without re-encoding')
                target=directory/'output.mp4';temporary=directory/'output.partial.mp4'
                if not target.exists():
                    try:
                        analyzer.run([ffmpeg,'-hide_banner','-v','error','-nostdin','-y','-i',str(encoded),'-map','0:v:0','-c:v','copy','-an','-sn','-dn','-avoid_negative_ts','make_zero','-video_track_timescale','1000000','-movflags','+faststart',str(temporary)])
                        temporary.replace(target)
                    finally:temporary.unlink(missing_ok=True)
                output_item['path']=str(target)
                # Locate the first presentation timestamp selected by the exact
                # reference extraction. Packet inspection avoids another decode.
                origin=float(original.get('format',{}).get('start_time',0) or 0)
                start=row['start']+origin
                packet_data=json.loads(analyzer.run([ffprobe,'-v','error','-select_streams','v:0','-read_intervals',f'{start}%{start+.25}','-show_packets','-show_entries','packet=pts_time','-of','json',str(source)]))
                times=[float(p['pts_time']) for p in packet_data.get('packets',[]) if p.get('pts_time') is not None and float(p['pts_time'])>=start-.000001]
                if not times:raise ValueError('Could not locate the original sample frame for synchronized playback. No proxy has been substituted.')
                update(status='ready',message='Original source and actual encoded test video · No video re-encoding',paths={'source':str(source),'output':str(target),'reference':str(reference)},sourceStart=max(0,min(times)-origin),sourceMime=sample_preview.native_mime(source_item),outputMime=sample_preview.native_mime(output_item))
        except Exception as exc:update(status='failed',message=str(exc))
    threading.Thread(target=generate,daemon=True).start();return key

def media(key,kind):
    with LOCK:
        value=JOBS.get(key,{})
        if value.get('status')!='ready' or kind not in ('source','output','reference'):raise ValueError('Original-codec comparison is not ready')
        return Path(value['paths'][kind])


def mime(key,kind):
    with LOCK:
        value=JOBS.get(key,{})
        if kind=='source':return value.get('sourceMime','application/octet-stream').split(';')[0]
        return 'video/mp4' if kind=='output' else 'video/x-matroska'
