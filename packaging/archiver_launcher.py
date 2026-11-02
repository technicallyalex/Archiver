"""Windowless executable entry point; browser UI and tray remain unchanged."""
import contextlib
import ctypes
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import traceback

if not getattr(sys,'frozen',False):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    if len(sys.argv)>1 and sys.argv[1]=='--setup-tools':
        # A user-invoked batch file owns the console; normal launches stay windowless.
        kernel=ctypes.windll.kernel32
        kernel.AttachConsole(ctypes.c_ulong(-1))
        try:sys.stdout=sys.stderr=open('CONOUT$','w',encoding='utf-8',buffering=1)
        except OSError:pass
        try:
            import dependency_setup,app
            base=Path(sys.argv[2]).resolve()
            paths=dependency_setup.setup(base,app.VERSION)
            if dependency_setup.apply_running(base,paths,app.VERSION):print('Paths applied to the running Archiver instance.')
            else:print('Ready. Start or restart Archiver to use these tools. If it is busy, let current work finish first.')
        except Exception as exc:
            print('Setup did not complete: '+str(exc));raise SystemExit(1)
        return
    if len(sys.argv)>1 and sys.argv[1]=='--pick-folder':
        import folder_picker
        initial,report=sys.argv[2:4]
        sys.argv=[sys.argv[0],initial]
        output=io.StringIO()
        with contextlib.redirect_stdout(output):folder_picker.main()
        Path(report).write_text(output.getvalue(),encoding='utf-8')
        return
    if len(sys.argv)>1 and sys.argv[1]=='--self-test':
        report=Path(sys.argv[2]);result={}
        try:
            import app,ab_av1,folder_picker,terminal_capture
            import tkinter,sqlite3
            with sqlite3.connect(':memory:') as database:
                database.execute('CREATE TABLE cache_check (value TEXT)');database.execute("INSERT INTO cache_check VALUES ('ready')")
                cache_ready=database.execute('SELECT value FROM cache_check').fetchone()[0]=='ready'
            root=tkinter.Tk();root.withdraw();root.destroy()
            chunks=[]
            terminal_capture.run([str(Path(os.environ['SystemRoot'])/'System32/cmd.exe'),'/d','/c','ping -n 2 127.0.0.1 >nul & echo Archiver runtime check'],Path(sys.executable).parent,dict(os.environ),lambda:False,chunks.append)
            # Quality validation must work even after the inherited console handle
            # is invalidated. This is the launch condition missed by manual-encode smoke tests.
            from quality import Analyzer
            kernel=ctypes.windll.kernel32
            kernel.GetStdHandle.restype=ctypes.c_void_p
            kernel.SetStdHandle.argtypes=[ctypes.c_ulong,ctypes.c_void_p]
            previous=kernel.GetStdHandle(-10)
            kernel.SetStdHandle(ctypes.c_ulong(-10),ctypes.c_void_p(-1))
            try:
                media_ready='Archiver media check' in Analyzer('','',None,lambda:False,lambda _:None).run([str(Path(os.environ['SystemRoot'])/'System32/cmd.exe'),'/d','/c','echo Archiver media check'])
            finally:kernel.SetStdHandle(ctypes.c_ulong(-10),previous)
            result={'ok':True,'version':app.VERSION,'frozen':bool(getattr(sys,'frozen',False)),
                    'webAssets':(app.ROOT/'web/index.html').is_file(),
                    'abAv1':app.run([ab_av1.binary(),'--version']).stdout.strip(),
                    'mediaProcessRuntime':media_ready,'nativeTerminal':any('Archiver runtime check' in s for s in chunks),'folderPickerRuntime':True,'metadataCacheRuntime':cache_ready}
            assert result['mediaProcessRuntime'] and result['webAssets'] and result['nativeTerminal'] and result['abAv1'] and result['metadataCacheRuntime']
        except BaseException:result={'ok':False,'error':traceback.format_exc()}
        report.write_text(json.dumps(result,indent=2),encoding='utf-8')
        return
    log_root=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Archiver'/'logs'
    log_root.mkdir(parents=True,exist_ok=True)
    log=log_root/'archiver.log'
    stream=log.open('a',encoding='utf-8',buffering=1)
    sys.stdout=sys.stderr=stream
    logging.basicConfig(stream=stream,level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        import app
        if '--tray' not in sys.argv:sys.argv.append('--tray')
        app.main()
    except Exception as exc:
        logging.exception('Archiver startup failed')
        ctypes.windll.user32.MessageBoxW(None,f'Archiver could not start.\n\n{exc}\n\nDetails: {log}','Archiver',0x10)
        raise SystemExit(1)

if __name__=='__main__':main()
