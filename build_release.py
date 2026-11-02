"""Build a portable Windows application folder; ZIP is explicitly opt-in."""
import argparse
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile,ZIP_DEFLATED


def main():
    root=Path(__file__).resolve().parent
    version=(root/'VERSION').read_text().strip()
    parser=argparse.ArgumentParser();parser.add_argument('--zip',action='store_true');args=parser.parse_args()
    if sys.platform!='win32':raise SystemExit('Build the Windows executable on Windows. Run python app.py for source development.')
    folder=root/'dist'/f'Archiver-{version}'
    if folder.exists():raise SystemExit('Build already exists. Use a new version to preserve rollback builds.')
    stage=root/'build'/version
    stage.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed','--name','Archiver',
             '--icon',str(root/'web/assets/archiver.ico'),
             '--distpath',str(stage/'dist'),'--workpath',str(stage/'work'),'--specpath',str(stage),
             '--paths',str(root),'--paths',str(root/'.dependencies'),
             '--hidden-import','dependency_setup','--hidden-import','terminal_capture','--hidden-import','tkinter.filedialog',
             '--add-data',f'{root/"third_party"}:third_party','--add-data',f'{root/"web"}:web','--add-data',f'{root/"VERSION"}:.',
             '--add-data',f'{root/"tools/ab-av1"}:tools/ab-av1']
    for binary in (root/'.dependencies/winpty').iterdir():
        if binary.suffix.lower() in ('.dll','.exe'):
            command+=['--add-binary',f'{binary}:winpty']
    for license_file in [Path(sys.base_prefix)/'LICENSE.txt']:
        if license_file.exists():command+=['--add-data',f'{license_file}:licenses/python']
    for metadata in (root/'.dependencies').glob('pywinpty-*.dist-info'):
        command+=['--add-data',f'{metadata}:licenses/pywinpty']
    command.append(str(root/'packaging/archiver_launcher.py'))
    subprocess.run(command,cwd=root,check=True)
    built=stage/'dist/Archiver'
    report=stage/'self-test.json'
    subprocess.run([str(built/'Archiver.exe'),'--self-test',str(report)],check=True,timeout=40)
    import json
    result=json.loads(report.read_text())
    if not result.get('ok'):raise SystemExit('Packaged application self-test failed: '+str(result))
    forbidden=[p for p in built.rglob('*') if p.is_file() and p.name.lower() in ('ffmpeg.exe','ffprobe.exe')]
    if forbidden:raise SystemExit('External video tools must not be bundled: '+str(forbidden))
    if not (built/'_internal/third_party/THIRD_PARTY_NOTICES.txt').is_file():raise SystemExit('Missing third-party notices')
    shutil.copytree(built,folder)
    shutil.copy2(root/'packaging/Setup video tools.cmd',folder/'Setup video tools.cmd')
    (folder/'README.txt').write_text(f'''Archiver {version}

START: Double-click Archiver.exe. The interface opens in your browser.
Archiver runs locally; the tray icon lets you reopen it, pause work, or quit.
No Python installation is required. Keep the _internal folder beside Archiver.exe.

VIDEO TOOLS: FFmpeg and FFprobe are still required. Existing installations on
PATH are detected. Or double-click Setup video tools.cmd to download and verify
FFmpeg/FFprobe into dependencies beside this launcher and save their paths.
No administrator permissions or PATH changes are needed. Internet required.
Restart Archiver if setup cannot apply paths while it is running.
Use Video tools in the app to install missing tools or choose other executables.
This build includes ab-av1 and its license inside _internal/tools/ab-av1.

LOGS: %LOCALAPPDATA%\\Archiver\\logs\\archiver.log
ROLLBACK: Quit the current version before opening a previous build.
''',encoding='utf-8')
    print(folder)
    if args.zip:
        # Version names contain dots, so append rather than replacing a suffix.
        archive=Path(str(folder)+'.zip')
        if archive.exists():raise SystemExit('Archive already exists')
        with ZipFile(archive,'w',ZIP_DEFLATED) as output:
            for path in folder.rglob('*'):
                if path.is_file():output.write(path,Path('Archiver')/path.relative_to(folder))
        archive.with_name(archive.name+'.sha256').write_text(sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')

if __name__=='__main__':main()
