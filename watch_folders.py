"""Explicitly enabled, restart-safe watch rules; never changes the Media Pool."""
import json,os,secrets,threading,time
from contextlib import contextmanager
from pathlib import Path
import tool_config,workflow_store,import_filters,output_presets

LOCK=threading.RLock()

@contextmanager
def lease():
    """Only one build may discover/dispatch watched files at a time."""
    file=workflow_store.directory()/'watch-service.lock';file.parent.mkdir(parents=True,exist_ok=True)
    stream=file.open('a+b');acquired=False
    try:
        stream.seek(0,2)
        if not stream.tell():stream.write(b'0');stream.flush()
        stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            acquired=True
        except OSError:pass
        yield acquired
    finally:
        if acquired:
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
        stream.close()

def path():return workflow_store.directory()/'watch-folders.json'

def load():
    with LOCK:
        if not path().exists():return {'rules':[],'seen':{}}
        try:data=json.loads(path().read_text(encoding='utf-8'))
        except (ValueError,OSError):raise ValueError('Watch folder settings could not be read; the file was not changed') from None
        if not isinstance(data,dict) or not isinstance(data.get('rules'),list) or not isinstance(data.get('seen'),dict):raise ValueError('Invalid watch folder settings')
        for rule in data['rules']:
            if not isinstance(rule,dict) or any(not isinstance(rule.get(k),str) for k in ('id','source','destination','presetId','name')) or not isinstance(rule.get('settings'),dict) or any(type(rule.get(k)) is not bool for k in ('enabled','recursive','autoStart')):
                raise ValueError('Invalid watch folder rule; settings were not changed')
        if any(not isinstance(v,dict) for v in data['seen'].values()):raise ValueError('Invalid watch folder history')
        return data

def public(data=None):
    data=data or load();return {'rules':[{k:v for k,v in r.items() if k!='baseline'} for r in data['rules']]}

def candidates(rule,extensions):
    root=Path(rule['source']);destination=Path(rule['destination']).resolve()
    if not root.is_dir():raise ValueError('Source folder is unavailable')
    excluded=import_filters.folder_names(None)
    for folder,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if not Path(folder,d).is_symlink() and not import_filters.is_test_folder(d) and not import_filters.is_system_folder(d) and d.casefold() not in excluded and Path(folder,d).resolve()!=destination]
        if not rule['recursive']:dirs[:]=[]
        for name in files:
            file=Path(folder,name)
            if file.suffix.lower() in extensions and not file.is_symlink() and not name.startswith('.archiver-'):yield file

def change(body,extensions):
    with LOCK:
        data=load();action=body.get('action');row=next((r for r in data['rules'] if r['id']==body.get('id')),None)
        if action=='delete':
            if not row:raise ValueError('Watch folder no longer exists')
            data['rules'].remove(row);data['seen'].pop(row['id'],None)
        elif action=='toggle':
            if not row or type(body.get('enabled')) is not bool:raise ValueError('Invalid watch folder toggle')
            row['enabled']=body['enabled'];row['status']='Watching' if row['enabled'] else 'Paused'
        elif action=='retry':
            if not row:raise ValueError('Watch folder no longer exists')
            for file in row.get('failed',{}):data['seen'].setdefault(row['id'],{}).pop(file,None)
            row.update(failed={},error='',status='Watching' if row['enabled'] else 'Paused')
        elif action=='save':
            source=Path(body.get('source','')).expanduser().resolve(strict=True);destination=Path(body.get('destination','')).expanduser().resolve(strict=True)
            if not source.is_dir() or not destination.is_dir():raise ValueError('Choose existing source and output folders')
            if destination==source or destination.is_relative_to(source):raise ValueError('Choose an output folder outside the watched source folder to prevent reimporting outputs')
            preset=next((r for r in output_presets.load()['presets'] if r['id']==body.get('presetId')),None)
            if not preset:raise ValueError('Choose a saved output preset')
            if preset['settings'].get('mode')=='overwrite':raise ValueError('Watch folders cannot replace or delete originals. Save a preset that keeps originals.')
            for flag in ('recursive','autoStart'):
                if type(body.get(flag,False)) is not bool:raise ValueError('Invalid watch folder option')
            if any(r is not row and Path(r['source'])==source for r in data['rules']):raise ValueError('This source folder is already watched')
            new=row is None
            new_source=new or row.get('source')!=str(source)
            if new:
                if len(data['rules'])>=20:raise ValueError('Create up to 20 watch folders')
                row={'id':secrets.token_hex(8),'enabled':True};data['rules'].append(row)
            row.update(name=str(body.get('name') or source.name)[:80],source=str(source),destination=str(destination),recursive=body.get('recursive',False),autoStart=body.get('autoStart',False),presetId=preset['id'],presetName=preset['name'],settings=preset['settings'],status='Watching',error='')
            if new_source:
                # Baseline is captured before enabling the rule: existing recordings are not queued.
                seen={}
                for file in candidates(row,extensions):
                    stat=file.stat();seen[str(file)]=[stat.st_size,stat.st_mtime_ns]
                data['seen'][row['id']]=seen
        else:raise ValueError('Unknown watch folder action')
        tool_config.write_json(path(),data);return public(data)

class Engine:
    def __init__(self,extensions,dispatch,notify):
        self.extensions=extensions;self.dispatch=dispatch;self.notify=notify;self.pending={};self.last_error={}

    def tick(self,clock=time.monotonic):
        with lease() as acquired:
            if acquired:self._tick(clock)

    def _tick(self,clock):
        with LOCK:data=load()
        if not data['rules']:return
        for rule in data['rules']:
            if not rule.get('enabled'):continue
            seen=data['seen'].setdefault(rule['id'],{});waiting=0
            try:
                for file in candidates(rule,self.extensions):
                    stat=file.stat();stamp=[stat.st_size,stat.st_mtime_ns];key=(rule['id'],str(file))
                    if seen.get(str(file))==stamp:continue
                    waiting+=1;old=self.pending.get(key)
                    if not old or old[0]!=stamp:self.pending[key]=(stamp,clock());continue
                    if clock()-old[1]<30 or not stat.st_size:continue
                    with LOCK:
                        current=load();live=next((r for r in current['rules'] if r['id']==rule['id']),None)
                        if not live or not live.get('enabled') or any(live.get(k)!=rule.get(k) for k in ('source','destination','presetId')):break
                    try:
                        # Dispatch durably journals its job. A repeat after a crash is deduplicated by source stamp.
                        self.dispatch(file,rule,stamp);rule['queued']=rule.get('queued',0)+1;rule.setdefault('failed',{}).pop(str(file),None);self.notify('Watch folder queued '+file.name,'success')
                    except Exception as exc:
                        rule['error']=file.name+': '+str(exc);rule.setdefault('failed',{})[str(file)]=stamp;self.notify('Watch folder could not queue '+file.name+': '+str(exc),'error')
                    seen[str(file)]=stamp
                    with LOCK:
                        current=load()
                        if any(r['id']==rule['id'] for r in current['rules']):current['seen'][rule['id']]=seen;tool_config.write_json(path(),current)
                    self.pending.pop(key,None)
                rule['status']=f'Watching · {waiting} waiting for copying to finish' if waiting else 'Watching';rule['waiting']=waiting
            except (OSError,ValueError) as exc:
                rule['status']='Needs attention';rule['error']=str(exc)
                if self.last_error.get(rule['id'])!=str(exc):self.notify('Watch folder '+rule['name']+': '+str(exc),'error');self.last_error[rule['id']]=str(exc)
        with LOCK:
            current=load()
            # An edit/toggle made during a slow network scan takes precedence.
            for r in current['rules']:
                old=next((v for v in data['rules'] if v['id']==r['id']),None)
                if old:
                    for key in ('status','error','queued','waiting','failed'):
                        if key in old:r[key]=old[key]
            tool_config.write_json(path(),current)


def quarantine():
    """Preserve unusable settings and unblock new rules without losing evidence."""
    with LOCK:
        target=path();backup=target.with_name(target.stem+'.invalid-'+str(time.time_ns())+'.json')
        if target.exists():target.replace(backup)
        tool_config.write_json(target,{'rules':[],'seen':{}})
        return backup
