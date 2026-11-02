"""Local start-time names with atomic collision handling for test folders."""
from datetime import datetime
from pathlib import Path

def planned(parent, started=None):
    stamp=datetime.now() if started is None else datetime.fromtimestamp(started)
    return Path(parent)/('Archiver-test-'+stamp.strftime('%Y-%m-%d_%H-%M-%S'))

def create(parent, started=None):
    base=planned(parent,started)
    number=1
    while True:
        candidate=base if number==1 else base.with_name(base.name+'_'+str(number))
        try:
            candidate.mkdir(exist_ok=False)
            return candidate
        except FileExistsError:number+=1
