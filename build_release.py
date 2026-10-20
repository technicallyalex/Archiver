"""Build a source distribution without bundling external media tools."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def main():
    root = Path(__file__).resolve().parent
    version = (root / 'VERSION').read_text().strip()
    files = ['app.py', 'folder_picker.py', 'build_release.py', 'Launch Archiver.bat',
             'README.md', 'CHANGELOG.md', 'VERSION']
    files += [str(p.relative_to(root)) for pattern in ['web/*', 'tests/*.py', 'docs/*.md']
              for p in sorted(root.glob(pattern)) if p.is_file()]
    destination = root / 'dist'
    destination.mkdir(exist_ok=True)
    archive = destination / f'Archiver-{version}.zip'
    with ZipFile(archive, 'w', ZIP_DEFLATED) as output:
        for name in files:
            output.write(root / name, 'Archiver/' + name.replace('\\', '/'))
    digest = sha256(archive.read_bytes()).hexdigest()
    (destination / f'{archive.name}.sha256').write_text(f'{digest}  {archive.name}\n')
    print(archive)


if __name__ == '__main__':
    main()
