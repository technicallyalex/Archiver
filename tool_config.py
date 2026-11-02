"""Portable tool paths, with a shared per-user fallback for future builds."""
import json,os,shutil,sys,tempfile
from pathlib import Path

def app_directory():
    return Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

def user_config():
    return (Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Archiver' if os.name=='nt' else Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'archiver')/'tools.json'

def read(path):
    try:
        value=json.loads(path.read_text(encoding='utf-8-sig'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def load_paths(base=None):
    base=Path(base or app_directory())
    for config in [base/'archiver-tools.json',user_config()]:
        data=read(config);paths={}
        for name in ('ffmpeg','ffprobe'):
            value=data.get(name)
            if not isinstance(value,str) or not value:break
            path=Path(value);path=path if path.is_absolute() else config.parent/path
            if not path.is_file():break
            paths[name]=str(path.resolve())
        if len(paths)==2:return paths
    return {name:shutil.which(name) or '' for name in ('ffmpeg','ffprobe')}

def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='tools-',suffix='.json',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as file:json.dump(data,file,indent=2)
        os.replace(tmp,path)
    finally:
        Path(tmp).unlink(missing_ok=True)

def save_paths(base,paths,shared=True):
    base=Path(base).resolve();portable={}
    for name in ('ffmpeg','ffprobe'):
        path=Path(paths[name]).resolve()
        if not path.is_file():raise ValueError(name+' was not found')
        try:portable[name]=str(path.relative_to(base))
        except ValueError:portable[name]=str(path)
    write_json(base/'archiver-tools.json',portable)
    if shared:
        try:write_json(user_config(),{name:str(Path(paths[name]).resolve()) for name in ('ffmpeg','ffprobe')})
        except OSError:pass
