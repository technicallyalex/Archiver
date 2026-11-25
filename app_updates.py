"""User-invoked GitHub updates, installed in the existing application folder."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from urllib.request import Request, urlopen
import zipfile

REPO='https://github.com/technicallyalex/Archiver'
API='https://api.github.com/repos/technicallyalex/Archiver/releases?per_page=100'
LOCK=threading.RLock()
STATE={'status':'idle','message':'Check for a newer version of Archiver.','release':None}

def version(value):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?',value)
    if not match:return None
    a,b,c,rc=match.groups()
    return (int(a),int(b),int(c),1 if rc is None else 0,int(rc or 0))

def select(releases,current):
    baseline=version(current)
    if baseline is None:raise ValueError('Unrecognized installed version')
    candidates=[]
    for release in releases:
        tag=release.get('tag_name','');key=version(tag)
        if release.get('draft') or key is None or key<=baseline:continue
        if release.get('prerelease') and '-rc.' not in current:continue
        name='Archiver-'+tag.removeprefix('v')+'.zip'
        assets={a['name']:a for a in release.get('assets',[]) if a.get('state')=='uploaded'}
        if name not in assets or name+'.sha256' not in assets:continue
        urls=[assets[n].get('browser_download_url','') for n in (name,name+'.sha256')]
        if any(u!=REPO+'/releases/download/'+tag+'/'+n for u,n in zip(urls,(name,name+'.sha256'))):continue
        candidates.append((key,{'version':tag.removeprefix('v'),'url':REPO+'/releases/tag/'+tag,'archive':urls[0],'checksum':urls[1]}))
    return max(candidates,key=lambda row:row[0])[1] if candidates else None

def fetch(url,limit):
    with urlopen(Request(url,headers={'User-Agent':'Archiver-updater','Accept':'application/vnd.github+json' if url==API else 'application/octet-stream'}),timeout=30) as response:
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError('Update response exceeds the allowed size')
    return data

def snapshot():
    with LOCK:return dict(STATE)

def check(current):
    with LOCK:
        if STATE['status'] in ('checking','installing'):raise ValueError('An update operation is already running')
        STATE.update(status='checking',message='Checking GitHub…',release=None)
    def work():
        try:
            release=select(json.loads(fetch(API,4_000_000)),current)
            with LOCK:STATE.update(status='available' if release else 'current',message='Version '+release['version']+' is available.' if release else 'You are up to date.',release=release)
        except Exception as exc:
            with LOCK:STATE.update(status='error',message='Could not check for updates: '+str(exc))
    threading.Thread(target=work,daemon=True).start()

def unpack(archive,destination):
    with zipfile.ZipFile(archive) as bundle:
        total=0;seen=set()
        for item in bundle.infolist():
            path=PurePosixPath(item.filename)
            if '\\' in item.filename or ':' in item.filename or path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0]!='Archiver':raise ValueError('Unsafe update archive path')
            key=item.filename.casefold()
            if key in seen or (item.external_attr>>16)&0o170000==0o120000:raise ValueError('Invalid update archive entry')
            seen.add(key);total+=item.file_size
            if total>1_000_000_000:raise ValueError('Update archive is too large')
        bundle.extractall(destination)
    root=destination/'Archiver'
    if not (root/'Archiver.exe').is_file() or not (root/'_internal/VERSION').is_file():raise ValueError('Update is missing required application files')
    return root

def install(shutdown):
    if sys.platform!='win32' or not getattr(sys,'frozen',False):raise ValueError('Automatic installation is available in the packaged Windows app. Download a release for source installations.')
    with LOCK:
        if STATE['status']!='available':raise ValueError('Check for an available update first')
        release=dict(STATE['release']);STATE.update(status='installing',message='Downloading and verifying update…')
    def work():
        staging=None;handed_off=False
        try:
            target=Path(sys.executable).resolve().parent
            staging=Path(tempfile.mkdtemp(prefix='.archiver-update-',dir=target.parent))
            archive=staging/'update.zip'
            checksum=fetch(release['checksum'],1024).decode().split()[0]
            if not re.fullmatch('[0-9a-fA-F]{64}',checksum):raise ValueError('Invalid release checksum')
            archive.write_bytes(fetch(release['archive'],250_000_000))
            if hashlib.sha256(archive.read_bytes()).hexdigest()!=checksum.lower():raise ValueError('Update checksum did not match; nothing was installed')
            root=unpack(archive,staging)
            if (root/'_internal/VERSION').read_text().strip()!=release['version']:raise ValueError('Update version did not match')
            report=staging/'self-test.json'
            subprocess.run([str(root/'Archiver.exe'),'--self-test',str(report)],check=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
            if not json.loads(report.read_text()).get('ok'):raise ValueError('The downloaded application failed its runtime check')
            # A separate runtime lets Windows release every file in the installed build.
            helper=staging/'helper';helper.mkdir()
            shutil.copy2(target/'Archiver.exe',helper/'Archiver.exe')
            shutil.copytree(target/'_internal',helper/'_internal')
            (staging/'installation.json').write_text(json.dumps({'target':str(target),'version':release['version']}))
            subprocess.Popen([str(helper/'Archiver.exe'),'--finish-update',str(target/'Archiver.exe'),str(os.getpid())],creationflags=subprocess.CREATE_NO_WINDOW)
            handed_off=True
            with LOCK:STATE.update(message='Update installed. Restarting Archiver…')
            shutdown()
        except Exception as exc:
            with LOCK:STATE.update(status='error',message='Update failed: '+str(exc)+'. The current version is unchanged.')
        finally:
            if staging is not None and not handed_off:shutil.rmtree(staging)
    threading.Thread(target=work,daemon=True).start()

MANAGED=('Archiver.exe','_internal','README.txt','Setup video tools.cmd')

def replace_installation(source,target,transaction,validate=lambda:None):
    """Replace only shipped application entries; keep all user-owned siblings intact."""
    source=Path(source).resolve();target=Path(target).resolve();transaction=Path(transaction).resolve()
    if source!=transaction/'Archiver' or transaction.parent!=target.parent or not transaction.name.startswith('.archiver-update-') or source==target:raise ValueError('Invalid update transaction paths')
    if target.is_symlink() or any((target/name).is_symlink() or (source/name).is_symlink() for name in MANAGED):raise ValueError('Linked application files cannot be updated automatically')
    prepared=transaction/'prepared';backup=transaction/'rollback'
    prepared.mkdir();backup.mkdir()
    for name in MANAGED:
        src=source/name
        if src.is_dir():shutil.copytree(src,prepared/name)
        elif src.is_file():shutil.copy2(src,prepared/name)
    if not (prepared/'Archiver.exe').is_file() or not (prepared/'_internal/VERSION').is_file():raise ValueError('Incomplete staged application')
    moved=[];installed=[]
    journal=transaction/'transaction.json'
    def record(status):journal.write_text(json.dumps({'target':str(target),'status':status,'backedUp':moved,'installed':installed},indent=2))
    record('replacing')
    try:
        for name in MANAGED:
            old=target/name;new=prepared/name
            if old.exists():
                old.rename(backup/name);moved.append(name);record('replacing')
            if new.exists():
                new.rename(target/name);installed.append(name);record('replacing')
        validate()
        record('installed')
    except BaseException:
        # Move failed new files out of the way; never remove user files or backups.
        for name in reversed(installed):
            (target/name).rename(prepared/name)
        for name in reversed(moved):
            (backup/name).rename(target/name)
        record('rolled-back')
        raise
    return backup

def finish(executable,pid):
    import ctypes
    target=Path(executable).resolve();helper=Path(sys.executable).resolve().parent;transaction=helper.parent
    if helper.name!='helper' or not transaction.name.startswith('.archiver-update-') or transaction.parent!=target.parent.parent or target.name!='Archiver.exe':raise ValueError('Invalid update destination')
    manifest=json.loads((transaction/'installation.json').read_text())
    if Path(manifest['target']).resolve()!=target.parent:raise ValueError('Update destination does not match the prepared installation')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x100000,False,int(pid))
    if not handle and ctypes.get_last_error() not in (0,87):raise ctypes.WinError(ctypes.get_last_error())
    if handle:
        try:
            if kernel.WaitForSingleObject(handle,120_000)!=0:raise ValueError('Archiver did not exit in time. The installed version was not replaced.')
        finally:kernel.CloseHandle(handle)
    def validate():
        report=transaction/'installed-self-test.json'
        subprocess.run([str(target),'--self-test',str(report)],check=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
        result=json.loads(report.read_text())
        if not result.get('ok') or result.get('version')!=manifest['version']:raise ValueError('Installed runtime verification failed')
    try:replace_installation(transaction/'Archiver',target.parent,transaction,validate)
    except Exception as exc:
        # If rollback succeeds, restore service using the original executable.
        if target.is_file():subprocess.Popen([str(target)],cwd=target.parent)
        raise ValueError('Could not replace Archiver. Recovery files: '+str(transaction)+'. '+str(exc)) from exc
    subprocess.Popen([str(target)],cwd=target.parent)
