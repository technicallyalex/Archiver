import concurrent.futures
import threading
import time
import unittest

from preview_work import PreviewWork


class PreviewWorkTests(unittest.TestCase):
    def test_loop_starts_while_thumbnail_workers_are_occupied(self):
        work=PreviewWork();release=threading.Event();barrier=threading.Barrier(3)
        # Select two different stripes so this checks the worker limit, not key collisions.
        first='a';second=next(str(i) for i in range(100) if hash(str(i))%32!=hash(first)%32)
        def thumbnail(key):
            with work.generation('thumbnail',key):
                barrier.wait(timeout=3);release.wait(3)
        def loop():
            with work.generation('loop','active'):
                return True
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            a=pool.submit(thumbnail,first);b=pool.submit(thumbnail,second)
            try:
                barrier.wait(timeout=3)
                self.assertTrue(pool.submit(loop).result(timeout=1))
            finally:release.set()
            a.result(timeout=3);b.result(timeout=3)

    def test_same_artifact_is_generated_once_and_errors_release_slots(self):
        work=PreviewWork();cache=set();count=0;guard=threading.Lock()
        def request():
            nonlocal count
            if 'same' not in cache:
                with work.generation('thumbnail','same'):
                    if 'same' not in cache:
                        with guard:count+=1
                        time.sleep(.02)  # Stand in for subprocess I/O, allowing competing requests to enter.
                        cache.add('same')
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _:request(),range(20)))
        self.assertEqual(count,1)
        with self.assertRaises(ValueError):
            with work.generation('loop','failed'):raise ValueError('fixture')
        with work.generation('loop','recovered'):pass
