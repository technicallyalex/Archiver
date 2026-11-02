"""Persist user-defined import exclusions across application builds/restarts."""
import tool_config
from import_filters import folder_names,DEFAULT_FOLDERS

def path():return tool_config.user_config().with_name('import-exclusions.json')

def validate(data):
    if not isinstance(data,dict):raise ValueError('Invalid exclusion preferences')
    custom=data.get('custom',[])
    if not isinstance(custom,list) or len(custom)>30:raise ValueError('Add up to 30 custom folder exclusions')
    builtins={name.casefold() for name in DEFAULT_FOLDERS};seen=builtins|{'archiver test folders'};entries=[]
    legacy='proxyFolders' not in data
    for key in ('proxy','proxies'):
        if key in data and not isinstance(data[key],bool):raise ValueError('Invalid checkbox state')
    proxy=data.get('proxyFolders',data.get('proxy',True) or data.get('proxies',True))
    if not isinstance(proxy,bool):raise ValueError('Invalid checkbox state')
    for entry in custom:
        if not isinstance(entry,dict) or not isinstance(entry.get('name'),str):raise ValueError('Enter a folder name')
        name=entry['name'].strip();key=next(iter(folder_names([name])))
        if not isinstance(entry.get('enabled',True),bool):raise ValueError('Invalid checkbox state')
        if legacy and key in builtins:
            proxy=proxy or entry.get('enabled',True);continue
        if key in seen:raise ValueError('This folder exclusion already exists')
        entries.append({'name':name,'enabled':entry.get('enabled',True)});seen.add(key)
    result={'custom':entries,'proxyFolders':proxy,'proxyFolderNames':list(DEFAULT_FOLDERS)}
    for key in ('testFolders',):
        value=data.get(key,True)
        if not isinstance(value,bool):raise ValueError('Invalid checkbox state')
        result[key]=value
    return result

def load():
    try:return validate(tool_config.read(path()))
    except ValueError:return validate({})

def save(data):
    result=validate(data);tool_config.write_json(path(),{k:v for k,v in result.items() if k!='proxyFolderNames'});return result
