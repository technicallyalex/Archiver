"""Import-only fast path. Tests and final-output verification use normal probing."""
import math
from pathlib import Path
import time
import metadata_cache


def complete(item):
    if not metadata_cache.valid(item):return False
    if item.get('codec') in ('?',None,'') or item.get('pixel_format') in ('',None,'unknown'):return False
    if any(not isinstance(item.get(k),(int,float)) or not math.isfinite(item[k]) or item[k]<=0 for k in ('width','height','fps','duration')):return False
    if item['codec'] in ('h264','hevc','prores') and item.get('field_order') not in ('progressive','tt','bb','tb','bt'):return False
    if '?' in item.get('audio',''):return False
    return all(s.get('channels',0)>0 and s.get('sample_rate',0)>0 for s in item['audio_streams'])


def read(path,probe,cache,tool,cancel,notify=lambda _:None,timeout=90,clock=time.monotonic):
    started=clock()
    def check():
        if cancel.is_set():raise InterruptedError('Media import stopped')
    check();stamp=metadata_cache.signature(path)
    item=cache.get(path,stamp,tool)
    if cache.error:notify(('cache-warning',cache.error))
    if item:
        check();notify(('cached',None));return {**item,'metadataSource':'cache'}
    item=None;method='full'
    # Indexed containers can usually describe themselves with a small packet read.
    # Do not use this bounded analysis for transport streams or raw media.
    if Path(path).suffix.lower() in ('.mp4','.mov','.m4v','.mkv','.webm'):
        notify(('fast-start',None))
        try:
            candidate=probe(path,cancel=cancel,timeout=min(8,timeout),light=True)
            if complete(candidate):item=candidate;method='fast'
        except InterruptedError:raise
        except (OSError,ValueError,TimeoutError):pass
        if item is None:notify(('fallback',None))
    if item is None:
        check();remaining=timeout-(clock()-started)
        if remaining<=0:raise TimeoutError('Media inspection exceeded its time budget')
        item=probe(path,cancel=cancel,timeout=remaining)
    check()
    if stamp!=metadata_cache.signature(path):raise ValueError('File changed while its metadata was being read. Import it again when recording or copying has finished.')
    cache.put(path,stamp,tool,item)
    if cache.error:notify(('cache-warning',cache.error))
    notify(('inspected',method))
    return {**item,'metadataSource':method}
