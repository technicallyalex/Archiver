"""Recoverable replacement when encoding on a different working disk."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import tool_config


def stamp(path):
    s=path.stat();return s.st_size,s.st_mtime_ns


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.digest()


def copy_verified(source,target,on_create=lambda:None):
    before=stamp(source)
    with source.open('rb') as src,target.open('xb') as dst:
        on_create()
        shutil.copyfileobj(src,dst,4*1024*1024);dst.flush();os.fsync(dst.fileno())
    shutil.copystat(source,target)
    if stamp(source)!=before or digest(source)!=digest(target):raise OSError('Replacement transfer verification failed')


def publish(temp,output,dispose,job,checkpoint=lambda:None):
    temp,output=Path(temp),Path(output)
    expected=(job.get('source_size'),job.get('source_mtime_ns'))
    if all(v is not None for v in expected) and stamp(output)!=expected:raise ValueError('Source changed; original retained')
    if shutil.disk_usage(output.parent).free+output.stat().st_size<temp.stat().st_size+64*1024*1024:
        raise OSError('The replacement will not fit on the source disk even after removing the original')
    directory=Path(tempfile.mkdtemp(prefix='.archiver-replacement-',dir=temp.parent))
    backup=directory/output.name;manifest=directory/'recovery.json'
    record={'source':str(output),'backup':str(backup),'encoded':str(temp),'state':'backing-up'}
    def save(state):
        record['state']=state;tool_config.write_json(manifest,record)
        job['replacementRecovery']=str(manifest);checkpoint()
    save('backing-up')
    removed=False;owned=None
    try:
        job['phase']='Backing up original to working folder'
        copy_verified(output,backup)
        if all(v is not None for v in expected) and stamp(output)!=expected:raise ValueError('Source changed; original retained')
        save('backup-verified')
        output.unlink();removed=True;save('transferring')
        job['phase']='Transferring verified output to source folder'
        # Exclusive creation cannot overwrite a file created by another program.
        if output.exists():raise FileExistsError('The output path was occupied during replacement')
        def claimed():
            nonlocal owned
            stat=output.stat();owned=(stat.st_dev,stat.st_ino)
        copy_verified(temp,output,claimed)
        save('output-verified')
    except Exception as exc:
        # Keep both working files and the manifest if anything interrupts publication.
        if removed:
            try:
                if owned and output.exists() and (output.stat().st_dev,output.stat().st_ino)==owned:output.unlink()
                if not output.exists():copy_verified(backup,output);save('original-restored')
            except Exception:pass
        job['replacementRecoveryRequired']=True
        raise OSError(f'Replacement interrupted. Recovery files retained in {directory}. {exc}') from exc
    try:
        dispose(backup)
    except Exception as exc:
        job['replacementRecoveryRequired']=True
        raise OSError(f'Output saved to {output}. Original backup retained at {backup}: {exc}') from exc
    save('complete');job.pop('replacementRecovery',None);job.pop('replacementRecoveryRequired',None)
    manifest.unlink();directory.rmdir();temp.unlink()
