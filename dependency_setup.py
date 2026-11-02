"""User-invoked download/install of external FFmpeg tools; never bundled in builds."""
import hashlib,json,os,re,shutil,stat,subprocess,tempfile,urllib.request,uuid,zipfile
from pathlib import Path
import tool_config
RELEASE_API='https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/latest'
RELEASE_PAGE='https://github.com/BtbN/FFmpeg-Builds/releases/tag/latest'
ASSET='ffmpeg-n8.1-latest-win64-gpl-8.1.zip'

def request(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Archiver dependency setup','Accept':'application/vnd.github+json' if 'api.github.com' in url else '*/*'}),timeout=60)

def download(url,target,progress=print):
    with request(url) as response,target.open('wb') as file:
        length=int(response.headers.get('Content-Length') or 0);done=0;last=-1
        while True:
            chunk=response.read(1024*1024)
            if not chunk:break
            file.write(chunk);done+=len(chunk);step=done//(10*1024*1024)
            if step!=last:
                progress(f'Downloaded {done//1048576} MB'+(f' of {length//1048576} MB' if length else ''));last=step

def validate(ffmpeg,ffprobe):
    def run(path,args):
        result=subprocess.run([str(path),*args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise ValueError('Tool check failed: '+str(path))
        return result.stdout
    for name,path in [('ffmpeg',ffmpeg),('ffprobe',ffprobe)]:
        if not run(path,['-version']).lower().startswith(name+' version'):raise ValueError('Invalid '+name+' executable')
    encoders=run(ffmpeg,['-hide_banner','-encoders']);filters=run(ffmpeg,['-hide_banner','-filters'])
    for name in ['libx264','libx265','libsvtav1','prores_ks','ffv1']:
        if not re.search(r'\b'+name+r'\s',encoders):raise ValueError('Download is missing encoder '+name)
    for name in ['xpsnr','vmafmotion']:
        if not re.search(r'\b'+name+r'\s',filters):raise ValueError('Download is missing filter '+name)

def extract(archive,destination):
    destination=Path(destination).resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target=(destination/member.filename).resolve()
            if not target.is_relative_to(destination) or stat.S_ISLNK(member.external_attr>>16):raise ValueError('Archive contains an unsafe path')
        package.extractall(destination)

def apply_running(base,paths,version):
    try:
        port=8872+int(version.rsplit('.',1)[-1]) if '-preview.' in version else 8765
        url=f'http://127.0.0.1:{port}'
        with request(url) as response:html=response.read().decode('utf-8')
        token=re.search(r'name="token" content="([^"]+)"',html)[1]
        req=urllib.request.Request(url+'/api/config',data=json.dumps(paths).encode(),headers={'X-Token':token,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=30) as response:response.read()
        return True
    except Exception:return False

def setup(base,version='',progress=print,shared=True):
    base=Path(base).resolve();base.mkdir(parents=True,exist_ok=True)
    # Re-running setup reuses a verified installation in this folder.
    local=tool_config.read(base/'archiver-tools.json')
    paths={name:str(base/local[name]) for name in ('ffmpeg','ffprobe') if local.get(name)}
    if len(paths)==2:
        try:
            validate(paths['ffmpeg'],paths['ffprobe']);tool_config.save_paths(base,paths,shared)
            progress('Existing tools verified.');return paths
        except (OSError,ValueError,subprocess.SubprocessError):pass
    progress('Downloading FFmpeg and FFprobe from BtbN/FFmpeg-Builds (GPL build).')
    progress('Source and license information: '+RELEASE_PAGE)
    with request(RELEASE_API) as response:release=json.load(response)
    assets={asset['name']:asset for asset in release['assets']}
    if ASSET not in assets or 'checksums.sha256' not in assets:raise ValueError('The supported FFmpeg 8.1 download is unavailable. Use FFmpeg settings to select an existing installation.')
    with request(assets['checksums.sha256']['browser_download_url']) as response:checksums=response.read().decode()
    match=re.search(r'^([a-fA-F0-9]{64})\s+\*?'+re.escape(ASSET)+r'\s*$',checksums,re.M)
    if not match:raise ValueError('No published checksum was found for the download')
    expected=match[1].lower();dependencies=base/'dependencies';dependencies.mkdir(exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.setup-',dir=dependencies)).resolve()
    try:
        archive=staging/'ffmpeg.zip';download(assets[ASSET]['browser_download_url'],archive,progress)
        with archive.open('rb') as file:actual=hashlib.file_digest(file,'sha256').hexdigest()
        if actual!=expected:raise ValueError('Checksum mismatch. No tools or settings were installed. Please run setup again.')
        progress('Checksum verified. Extracting tools and license documents...')
        package=staging/'package';extract(archive,package)
        ffmpegs=list(package.rglob('bin/ffmpeg.exe'));ffprobes=list(package.rglob('bin/ffprobe.exe'))
        if len(ffmpegs)!=1 or len(ffprobes)!=1 or ffmpegs[0].parent!=ffprobes[0].parent:raise ValueError('Expected tool executables were not found')
        validate(ffmpegs[0],ffprobes[0])
        installed=dependencies/('ffmpeg-'+expected[:12])
        if installed.exists():
            try:validate(installed/ffmpegs[0].relative_to(package),installed/ffprobes[0].relative_to(package))
            except (OSError,ValueError,subprocess.SubprocessError):installed=dependencies/('ffmpeg-'+expected[:12]+'-'+uuid.uuid4().hex[:8])
        if not installed.exists():os.replace(package,installed)
        paths={name:str(installed/path.relative_to(package)) for name,path in [('ffmpeg',ffmpegs[0]),('ffprobe',ffprobes[0])]}
        validate(paths['ffmpeg'],paths['ffprobe'])
        tool_config.write_json(installed/'archiver-download.json',{'source':RELEASE_PAGE,'asset':ASSET,'sha256':actual,'license':'GPL; see the included license and documentation files.'})
        tool_config.save_paths(base,paths,shared)
        progress('Tools installed and paths saved for Archiver.')
        return paths
    finally:
        if staging.is_relative_to(dependencies.resolve()) and staging.name.startswith('.setup-'):shutil.rmtree(staging)

def restore_ab_av1(destination,progress=print):
    """Restore the supported Windows build using GitHub's published asset digest."""
    destination=Path(destination)
    progress('Downloading ab-av1 0.11.7 from alexheretic/ab-av1…')
    with request('https://api.github.com/repos/alexheretic/ab-av1/releases/tags/v0.11.7') as response:release=json.load(response)
    assets=[a for a in release['assets'] if a['name']=='ab-av1.exe']
    if len(assets)!=1:raise ValueError('The supported Windows ab-av1 download was not found. Restore ab-av1 from your Archiver download.')
    asset=assets[0];digest=asset.get('digest') or ''
    if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}',digest):raise ValueError('No published checksum is available for ab-av1. Restore it from your Archiver download.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.ab-setup-',dir=destination.parent) as tmp:
        root=Path(tmp);archive=root/'ab-av1.exe';download(asset['browser_download_url'],archive,progress)
        with archive.open('rb') as file:actual=hashlib.file_digest(file,'sha256').hexdigest()
        if actual!=digest[7:].lower():raise ValueError('ab-av1 checksum mismatch. The existing tool was not changed.')
        from ab_av1 import _installation
        stat=archive.stat();info=_installation(str(archive),stat.st_size,stat.st_mtime_ns)
        if not info['available']:raise ValueError(info['error'])
        os.replace(archive,destination)
    progress('ab-av1 installed and verified.')
