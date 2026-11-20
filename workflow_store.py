"""Durable, atomic workflow preferences and per-build queue recovery journal."""
import collections
import json
import math
import os
import re
from pathlib import Path
import threading
import tool_config

LOCK=threading.RLock()
DEFAULTS={'verify':True,'decode':True,'reports':True,'recovery':True,'storage':True}
_LAST_JOURNAL={}

def directory():
    return Path(os.environ.get('ARCHIVER_WORKFLOW_DIR') or tool_config.user_config().parent/'workflows')

def clean(value):
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if not str(k).startswith('_') or k=='_batchSequence'}
    if isinstance(value,(list,tuple,collections.deque)):return [clean(v) for v in value]
    if isinstance(value,Path):return str(value)
    return value

def options():
    return {**DEFAULTS,**{k:v for k,v in tool_config.read(directory()/'options.json').items() if k in DEFAULTS and type(v) is bool}}

def save_options(value):
    if not isinstance(value,dict) or any(k not in DEFAULTS or type(v) is not bool for k,v in value.items()):raise ValueError('Invalid queue options')
    with LOCK:
        result={**options(),**value};tool_config.write_json(directory()/'options.json',result);return result

def journal(version):return directory()/('queue-'+version+'.json')

def save(version,jobs,tests):
    with LOCK:
        # Never store a partially read live list; the caller supplies a locked snapshot.
        target=journal(version);value={'version':1,'jobs':clean(jobs),'tests':clean(tests)};signature=json.dumps(value,separators=(',',':'),allow_nan=False)
        if _LAST_JOURNAL.get(str(target))==signature and target.exists():return
        tool_config.write_json(target,value);_LAST_JOURNAL[str(target)]=signature

def load(version):
    with LOCK:
        file=journal(version)
        if not file.exists():return {'jobs':[],'tests':[]}
        try:data=json.loads(file.read_text(encoding='utf-8'))
        except (OSError,ValueError):raise ValueError('Saved queue could not be read. The journal was not changed.') from None
        if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('jobs'),list) or not isinstance(data.get('tests'),list):raise ValueError('Saved queue has an unsupported format')
        warnings=[]
        for kind in ('jobs','tests'):
            healthy=[]
            for job in data[kind]:
                required=('id','source','output','settings','status') if kind=='jobs' else ('id','source','directory','outputDirectory','settings','status')
                valid=isinstance(job,dict) and all(k in job for k in required)
                valid=valid and isinstance(job.get('settings'),dict) and isinstance(job.get('id'),str) and bool(re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',job['id']))
                valid=valid and all(isinstance(job[k],str) for k in required if k!='settings')
                valid=valid and job.get('status') in ('queued','waiting','running','completed','failed','cancelled','skipped')
                if valid:
                    for key in ('sourceMetadata',):
                        meta=job['settings'].get(key)
                        if meta is not None and (not isinstance(meta,dict) or not isinstance(meta.get('id'),str)):valid=False
                    for key in ('log','activity'):
                        if key in job and (not isinstance(job[key],list) or any(not isinstance(v,str) for v in job[key])):valid=False
                    for key in ('result','progress','recoverySource','encodeSettings'):
                        if job.get(key) is not None and not isinstance(job[key],dict):valid=False
                    meta=job.get('recoverySource')
                    if meta and (not isinstance(meta,dict) or not isinstance(meta.get('id'),str) or not isinstance(meta.get('path'),str)):valid=False
                    for key in ('percent','duration','source_size','source_mtime_ns'):
                        if key in job and (type(job[key]) not in (int,float) or not math.isfinite(job[key]) or job[key]<0):valid=False
                    if job.get('temporaryOutput') is not None and not isinstance(job['temporaryOutput'],str):valid=False
                if valid:healthy.append(job)
                else:warnings.append(f"Invalid {kind} entry excluded from recovery")
            data[kind]=healthy
        if warnings:
            # Preserve the original before a later checkpoint replaces the journal.
            backup=file.with_suffix('.invalid.json')
            if backup.exists() and backup.read_bytes()!=file.read_bytes():
                import time
                backup=file.with_suffix('.invalid-'+str(time.time_ns())+'.json')
            if not backup.exists():backup.write_bytes(file.read_bytes())
            data['warnings']=warnings
        return data

def receipt(version,job):
    target=directory()/('completed-'+version)/(job['id']+'.json')
    stat=Path(job['output']).stat()
    tool_config.write_json(target,{'id':job['id'],'source':job['source'],'output':job['output'],'size':stat.st_size,'modifiedNs':stat.st_mtime_ns})

def completed(version,job):
    data=tool_config.read(directory()/('completed-'+version)/(job['id']+'.json'))
    try:return data.get('source')==job['source'] and data.get('output')==job['output'] and data.get('size',0)>0 and (Path(job['output']).stat().st_size,Path(job['output']).stat().st_mtime_ns)==(data['size'],data.get('modifiedNs'))
    except OSError:return False

def restored_job(job,version):
    result=dict(job);result['log']=collections.deque(job.get('log') or [],maxlen=1500)
    result.update(cancel=False,committing=False,eta=None,speed='',fps='')
    if job.get('replacementRecovery'):
        result.update(status='failed',phase='Replacement recovery required',error='Replacement was interrupted. Keep the recovery files and inspect '+job['replacementRecovery'])
        return result
    temporary=Path(job['temporaryOutput']) if job.get('temporaryOutput') else None
    output=Path(job['output']);owned=False
    if temporary:
        owned=temporary.name.startswith('.archiver-') and temporary.suffix.lower()==output.suffix.lower() and temporary.parent.resolve()==Path(job.get('settings',{}).get('replacementTempDirectory') or output.parent).resolve() and temporary!=Path(job['source']) and not temporary.is_symlink()
        try:
            # A published hard link can survive a crash just before its receipt write.
            if owned and output.is_file() and temporary.samefile(output):receipt(version,result)
        except OSError:pass
    if completed(version,result):result.update(status='completed',percent=100,output_size=Path(result['output']).stat().st_size,phase='Completed output recovered')
    elif result.get('status') in ('queued','waiting','running'):
        result.update(status='queued',percent=0,encodedSeconds=0,phase='Restored · Waiting to restart')
        source=Path(result['source'])
        try:
            stat=source.stat();metadata=result.get('settings',{}).get('sourceMetadata',{})
            if stat.st_size!=result.get('source_size',stat.st_size) or (metadata.get('sourceMtimeNs') and stat.st_mtime_ns!=metadata['sourceMtimeNs']):raise ValueError('Source changed since this job was saved. Import and queue it again.')
        except (OSError,ValueError) as exc:result.update(status='failed',error=str(exc),phase='Recovery needs attention')
    for key in ('retryAfter','framePreview','storagePaused'):result.pop(key,None)
    if owned:
        try:
            temporary.unlink()
            result.pop('temporaryOutput',None)
        except OSError:result['recoveryWarning']='Interrupted staging file cleanup is pending: '+str(temporary)
    elif temporary:
        result.pop('temporaryOutput',None)
    return result


def cleanup_stage(job):
    """Retry only the validated staging ownership retained by recovery."""
    if job.get('replacementRecovery'):raise ValueError('Resolve the interrupted replacement before retrying: '+job['replacementRecovery'])
    value=job.get('temporaryOutput')
    if not value:return
    stage=Path(value);output=Path(job['output'])
    if not stage.name.startswith('.archiver-') or stage.parent.resolve()!=Path(job.get('settings',{}).get('replacementTempDirectory') or output.parent).resolve() or stage.suffix.lower()!=output.suffix.lower() or stage==Path(job['source']) or stage.is_symlink():raise ValueError('Invalid interrupted staging path')
    stage.unlink(missing_ok=True);job.pop('temporaryOutput',None)
