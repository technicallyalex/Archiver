"""Windowless Windows entry point with visible startup errors and local diagnostics."""
import ctypes
import logging
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
log = root / 'build' / 'logs' / 'archiver-desktop.log'
log.parent.mkdir(parents=True,exist_ok=True)
try:
    logging.basicConfig(filename=log, level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')
    # pythonw has no console streams; keep unexpected output available for diagnosis.
    stream = log.open('a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = stream
    sys.path.insert(0,str(root))
    import app
    if '--tray' not in sys.argv:
        sys.argv.append('--tray')
    app.main()
except Exception as exc:
    logging.exception('Archiver desktop startup failed')
    ctypes.windll.user32.MessageBoxW(None, f'Archiver could not start.\n\n{exc}\n\nDetails: {log}', 'Archiver', 0x10)
    sys.exit(1)
