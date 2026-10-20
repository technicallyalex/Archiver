"""Native folder picker helper; stdout contains only the JSON result."""
import json
import sys


def enable_dpi_awareness():
    if sys.platform == 'win32':
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                pass



def main():
    enable_dpi_awareness()
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        directory = filedialog.askdirectory(
            parent=root,
            title='Archiver — Select a directory',
            initialdir=sys.argv[1] if len(sys.argv) > 1 else None,
            mustexist=True,
        )
        print(json.dumps({'directory': directory or ''}))
    finally:
        root.destroy()


if __name__ == '__main__':
    main()
