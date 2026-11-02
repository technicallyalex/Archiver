"""Hidden terminal execution with pywinpty; no visible console window."""
import queue
import subprocess
import threading
from winpty import PtyProcess, Backend


def run(command, directory, env, cancelled, callback):
    process = PtyProcess.spawn(command, cwd=str(directory), env=env, dimensions=(35, 180), backend=Backend.ConPTY)
    messages = queue.Queue()
    def read():
        try:
            while True:
                messages.put(process.read(8192))
        except EOFError:
            pass
        except Exception as exc:
            messages.put(exc)
        finally:
            messages.put(None)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        while True:
            if cancelled():
                raise InterruptedError('Quality test cancelled')
            try:
                chunk = messages.get(timeout=.2)
            except queue.Empty:
                continue
            if chunk is None:
                break
            if isinstance(chunk, Exception):
                raise ValueError(f'Terminal capture failed: {chunk}')
            callback(chunk)
        code = process.wait()
        if code:
            raise ValueError(f'ab-av1 exited with code {code}. See its console output.')
    finally:
        if process.isalive():
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        process.close(force=True)
        reader.join(5)
