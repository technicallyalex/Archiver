"""Native folder picker helper; stdout contains only the JSON result."""
import json
import sys


def main():
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        directory = filedialog.askdirectory(
            parent=root,
            title='Archiver — Select a directory to scan',
            initialdir=sys.argv[1] if len(sys.argv) > 1 else None,
            mustexist=True,
        )
        print(json.dumps({'directory': directory or ''}))
    finally:
        root.destroy()


if __name__ == '__main__':
    main()
