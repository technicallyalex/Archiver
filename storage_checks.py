"""Conservative queue storage budgets and live low-space guards."""
import os,shutil
from pathlib import Path

MIN_FREE=64*1024*1024

def location(job):
    path=Path(job['settings'].get('replacementTempDirectory') or Path(job['output']).parent) if job['settings'].get('mode')=='overwrite' else Path(job['output']).parent
    if job['settings'].get('qualityMode')=='proxy':
        while not path.exists() and path.parent!=path:path=path.parent
    if not path.is_dir():raise ValueError('Output folder is unavailable: '+str(Path(job['output']).parent))
    return path

def budget(job):
    config=job['settings'];item=config.get('sourceMetadata',{});duration=job.get('duration',0)
    audio=0;audio_known=True
    import preservation
    streams=preservation.audio_metadata(item,config)
    if config.get('audio')=='copy' and streams:
        audio_known=all(s.get('bitrate',0)>0 for s in streams);audio=sum(s.get('bitrate',0) for s in streams)*duration/8
    elif config.get('audio') in ('aac','mp3','opus'):
        try:audio=float(config.get('audioBitrate','192k').rstrip('k'))*1000*len(streams)*duration/8
        except (ValueError,TypeError):audio_known=False
    elif config.get('audio')=='pcm_s24le':audio=sum(s.get('sample_rate',0)*s.get('channels',0)*24 for s in streams)*duration/8
    if not audio_known:audio=job.get('source_size',0)
    if config.get('qualityMode')=='proxy' and item:
        import proxy_media
        try:return int(proxy_media.resolve(item,config)['estimatedBytes']),True
        except (ValueError,KeyError):pass
    if config.get('qualityMode')=='archive' and item:
        import prores
        try:return int(prores.resolve(item,config)['estimatedVideoBytes']+audio),audio_known
        except (ValueError,KeyError):pass
    result=job.get('qualityResult') or job.get('testedAnalysis') or {}
    if result.get('estimatedVideoBytes'):return int(result['estimatedVideoBytes']+audio),audio_known
    rate=job['settings'].get('customBitrate') if job['settings'].get('bitrate')=='custom' else None
    if rate:
        try:return int(float(rate)*1e6/8*job['duration']+audio),audio_known
        except (ValueError,TypeError):pass
    # Unknown CQ size is a planning allowance, never presented as a prediction.
    return int(job.get('source_size',0)),False

def snapshot(jobs):
    rows=[];seen={}
    for job in jobs:
        if job.get('status') not in ('queued','running'):continue
        folder_name=str(job['settings'].get('replacementTempDirectory') or Path(job['output']).parent) if job['settings'].get('mode')=='overwrite' else str(Path(job['output']).parent)
        try:key='device:'+str(location(job).stat().st_dev)
        except (OSError,ValueError):key='unavailable:'+folder_name
        if key not in seen:
            try:
                folder=location(job);usage=shutil.disk_usage(folder)
                row={'folder':folder_name,'folders':[folder_name],'free':usage.free,'total':usage.total,'budget':0,'estimated':True,'available':True,'neededForStart':0}
            except (OSError,ValueError) as exc:row={'folder':folder_name,'folders':[folder_name],'free':0,'total':0,'budget':0,'estimated':False,'available':False,'error':str(exc),'neededForStart':0}
            rows.append(row);seen[key]=row
        amount,estimated=budget(job);amount+=job.get('source_size',0) if job['settings'].get('mode')=='overwrite' and job['settings'].get('replacementTempDirectory') else 0;row=seen[key];row['budget']+=amount;row['estimated']=row['estimated'] and estimated
        if folder_name not in row['folders']:row['folders'].append(folder_name);row['folder']=str(Path(folder_name).anchor or folder_name)+f' · {len(row["folders"])} output folders'
        # The stage file sits in the output folder; allow another copy during publication.
        row['neededForStart']=max(row['neededForStart'],amount*2+MIN_FREE)
    blocked=any(not r['available'] or r['free']<MIN_FREE for r in rows)
    warning=any(r['free']<max(r['budget'],r['neededForStart']) for r in rows if r['available'])
    return {'locations':rows,'blocked':blocked,'warning':warning,'minimumFree':MIN_FREE,
            'note':'Encode staging uses the selected replacement working folder when set, otherwise the output folder. Replacement working-folder budgets include an original backup. Unknown quality-based sizes use the source size as a planning allowance.'}

def guard(job):
    folder=location(job)
    if shutil.disk_usage(folder).free<MIN_FREE:raise ValueError('Less than 64 MiB free in '+str(folder))


def write_failure(error,log):
    import errno
    if isinstance(error,OSError) and (error.errno in (errno.ENOSPC,errno.EDQUOT,errno.ENODEV,errno.ENXIO) or getattr(error,'winerror',None) in (21,39,53,64,112,1167)):return True
    text=' '.join([str(error),*list(log)[-30:]]).lower()
    return any(v in text for v in ('no space left on device','disk full','not enough space','device is not ready','network name is no longer available','network path was not found','input/output error'))
