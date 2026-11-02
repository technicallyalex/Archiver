"""Batch-aware filename allocation without modifying existing files."""
import os
from pathlib import Path


def key(path):return os.path.normcase(os.path.abspath(path))


class Names:
    def __init__(self,reserved=()):
        self.reserved={key(p) for p in reserved};self.folders={};self.next={}

    def names_in(self,folder):
        ident=key(folder)
        if ident not in self.folders:
            try:
                with os.scandir(folder) as entries:self.folders[ident]={os.path.normcase(e.name) for e in entries}
            except FileNotFoundError:self.folders[ident]=set()
        return self.folders[ident]

    def reserve(self,path):
        path=Path(path);names=self.names_in(path.parent);base=key(path)
        candidate=path;index=self.next.get(base,2)
        while os.path.normcase(candidate.name) in names or key(candidate) in self.reserved:
            suffix=f'_{index:03d}';room=255-len(path.suffix)-len(suffix)
            if room<1:raise ValueError('Output filename is too long to add a sequence number')
            candidate=path.with_name(path.stem[:room]+suffix+path.suffix);index+=1
        self.next[base]=index;self.reserved.add(key(candidate));names.add(os.path.normcase(candidate.name))
        return candidate
