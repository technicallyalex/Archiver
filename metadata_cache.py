"""Disposable, local metadata index. Source files are never changed."""
import tempfile
import tool_config
import json
from contextlib import closing
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time

SCHEMA = 3  # Bump when the imported metadata contract changes.


def cache_path():
    override = os.environ.get('ARCHIVER_CACHE_DIR')
    if override:return Path(override) / 'metadata.sqlite'
    configured=tool_config.read(settings_path()).get('directory')
    if isinstance(configured,str) and configured:return Path(configured)/'metadata.sqlite'
    return default_path()


def default_path():
    root = Path(os.environ.get('LOCALAPPDATA', Path.home()))/'Archiver'/'cache' if os.name=='nt' else Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'archiver'
    return root/'metadata.sqlite'


def settings_path():
    return tool_config.user_config().with_name('metadata-cache.json')


def info():
    path=cache_path();count=0;error=''
    if path.is_file():
        try:
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
                count=db.execute('SELECT COUNT(*) FROM metadata').fetchone()[0]
        except sqlite3.Error as exc:error=str(exc)
    return {'directory':str(path.parent),'defaultDirectory':str(default_path().parent),
            'entries':count,'bytes':sum(p.stat().st_size for p in (path,Path(str(path)+'-wal'),Path(str(path)+'-shm')) if p.is_file()),
            'override':bool(os.environ.get('ARCHIVER_CACHE_DIR')),'error':error}


def configure(directory):
    if os.environ.get('ARCHIVER_CACHE_DIR'):
        raise ValueError('The cache location is controlled by ARCHIVER_CACHE_DIR for this session.')
    if not isinstance(directory,str):raise ValueError('Enter a cache folder path')
    value=directory.strip();target=Path(value).expanduser() if value else default_path().parent
    if not target.is_absolute():raise ValueError('Enter a full cache folder path')
    target=target.resolve();target.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryFile(dir=target) as test:test.write(b'Archiver cache location check');test.flush()
    old=cache_path();new=target/'metadata.sqlite'
    # SQLite backup includes committed WAL data. Keep the old cache for rollback.
    if old.is_file() and old.resolve()!=new and not new.exists():
        fd,name=tempfile.mkstemp(prefix='metadata-copy-',suffix='.sqlite',dir=target);os.close(fd)
        temporary=Path(name)
        try:
            with closing(sqlite3.connect(old.as_uri()+'?mode=ro',uri=True,timeout=2.5)) as source:
                with closing(sqlite3.connect(temporary)) as destination:source.backup(destination)
            os.replace(temporary,new)
        finally:temporary.unlink(missing_ok=True)
    tool_config.write_json(settings_path(),{'directory':str(target) if value else ''})
    return info()


def signature(path):
    stat=Path(path).stat()
    return (stat.st_size,stat.st_mtime_ns)


def tool_signature(executable):
    try:return json.dumps([SCHEMA,os.path.normcase(os.path.abspath(executable)),*signature(executable)])
    except OSError:return json.dumps([SCHEMA,str(executable)])


def valid(item):
    return isinstance(item,dict) and all(k in item for k in ('codec','width','height','fps','duration','pixel_format','audio_streams','frame_rate','timecode','rotation','sample_aspect_ratio','field_order','video_bitrate','rate_mode','source_quality','color_transfer'))


class Cache:
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else cache_path()
        self.lock=threading.Lock();self.ready=False;self.error='';self.writes=0

    def connect(self):
        with self.lock:
            if self.error:return None
            try:
                if not self.ready:
                    self.path.parent.mkdir(parents=True,exist_ok=True)
                    with closing(sqlite3.connect(self.path,timeout=2.5)) as db:
                        db.execute('PRAGMA journal_mode=WAL')
                        db.execute('CREATE TABLE IF NOT EXISTS metadata (path TEXT PRIMARY KEY, size INTEGER NOT NULL, modified INTEGER NOT NULL, tool TEXT NOT NULL, payload TEXT NOT NULL, updated REAL NOT NULL)')
                        db.commit()
                    self.ready=True
                return sqlite3.connect(self.path,timeout=2.5)
            except (OSError,sqlite3.Error) as exc:
                self.error=f'Metadata cache unavailable; files will be inspected normally. {exc}'
                return None

    def get(self,path,stamp,tool):
        db=self.connect()
        if db is None:return None
        try:
            with db:
                row=db.execute('SELECT payload FROM metadata WHERE path=? AND size=? AND modified=? AND tool=?',(os.path.normcase(os.path.abspath(path)),*stamp,tool)).fetchone()
            if not row:return None
            item=json.loads(row[0])
            if not valid(item):return None
            return {**item,'id':secrets.token_hex(12),'path':str(path),'name':Path(path).name,'size':stamp[0]}
        except (sqlite3.Error,ValueError,TypeError) as exc:
            if isinstance(exc,sqlite3.Error):self.error=f'Metadata cache unavailable; files will be inspected normally. {exc}'
            return None
        finally:db.close()

    def put(self,path,stamp,tool,item):
        if not valid(item):return
        payload={k:v for k,v in item.items() if k not in ('id','path','name','size','metadataSource')}
        try:encoded=json.dumps(payload,allow_nan=False)
        except (ValueError,TypeError):return
        db=self.connect()
        if db is None:return
        try:
            with db:
                db.execute('INSERT INTO metadata VALUES (?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET size=excluded.size, modified=excluded.modified, tool=excluded.tool, payload=excluded.payload, updated=excluded.updated',(os.path.normcase(os.path.abspath(path)),*stamp,tool,encoded,time.time()))
                with self.lock:self.writes+=1;prune=self.writes%256==0
                if prune:
                    db.execute('DELETE FROM metadata WHERE path IN (SELECT path FROM metadata ORDER BY updated DESC LIMIT -1 OFFSET 50000)')
        except sqlite3.Error as exc:self.error=f'Metadata cache unavailable; files will be inspected normally. {exc}'
        finally:db.close()
