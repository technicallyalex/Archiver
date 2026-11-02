"""Persistent, per-dialog folder history shared across application builds."""
import json
import os
from pathlib import Path
import tempfile

KINDS={'source','destination','test-output','general','watchSource','watchDestination'}

def history_path():
    if os.name=='nt':return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Archiver'/'folder-history.json'
    return Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'archiver'/'folder-history.json'

def load():
    try:
        data=json.loads(history_path().read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):return {}

def initial_folder(initial='',kind=None,fallback=''):
    if kind is not None and kind not in KINDS:raise ValueError('Unknown folder picker context')
    data=load() if kind else {}
    for value in [initial,data.get(kind),fallback,data.get('last'),str(Path.home())]:
        if not isinstance(value,str) or not value.strip():continue
        try:
            path=Path(value).expanduser()
            if path.is_dir():return path
        except (OSError,ValueError):continue
    return Path.home()

def remember(directory,kind):
    if not directory or kind not in KINDS:return
    temporary=None
    try:
        target=history_path();target.parent.mkdir(parents=True,exist_ok=True)
        data=load();data[kind]=str(directory);data['last']=str(directory)
        fd,name=tempfile.mkstemp(prefix='folder-history-',suffix='.tmp',dir=target.parent);temporary=Path(name)
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(data,f,indent=2)
        os.replace(temporary,target)
    except OSError:pass  # A preference-write failure must not fail the chosen folder.
    finally:
        if temporary:temporary.unlink(missing_ok=True)
