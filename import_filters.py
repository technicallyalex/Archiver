"""Conservative, read-only filters for recursive media discovery."""

DEFAULT_FOLDERS=('Proxy','Proxies','Proxy Media','Final Cut Proxy Media')

def folder_names(values=None):
    values=DEFAULT_FOLDERS if values is None else values
    if not isinstance(values,(list,tuple)) or len(values)>64:raise ValueError('Enter up to 64 folder names')
    names=set()
    for value in values:
        if not isinstance(value,str):raise ValueError('Enter folder names as text')
        name=value.strip()
        if not name or len(name)>100 or name in ('.','..') or any(c in name for c in '/\\:*?"<>|'):
            raise ValueError('Use folder names only, without paths or wildcards')
        names.add(name.casefold())
    return names


def is_test_folder(name):
    return name.casefold().startswith('archiver-test-')


def is_system_folder(name):
    """Never recursively import Windows trash or protected volume metadata."""
    return name.casefold() in {'$recycle.bin', 'system volume information'}
