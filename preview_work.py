"""Bound preview generation without making active loops wait for still images."""
from contextlib import contextmanager
import threading


class PreviewWork:
    def __init__(self, thumbnail_workers=2, loop_workers=1):
        self.slots = {'thumbnail': threading.BoundedSemaphore(thumbnail_workers),
                      'loop': threading.BoundedSemaphore(loop_workers)}
        # Fixed stripes bound memory; separate lanes never share a key lock.
        self.keys = {kind: [threading.Lock() for _ in range(32)] for kind in self.slots}

    @contextmanager
    def generation(self, kind, target):
        locks = self.keys[kind]
        with locks[hash(str(target)) % len(locks)]:
            with self.slots[kind]:
                yield
