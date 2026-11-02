import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import test_folders
import import_filters

class TestFolderNames(unittest.TestCase):
 def test_readable_local_start_time_and_exclusion(self):
  stamp=datetime(2026,11,2,10,45,30).timestamp()
  path=test_folders.planned('footage',stamp)
  self.assertEqual(path.name,'Archiver-test-2026-11-02_10-45-30')
  self.assertTrue(import_filters.is_test_folder(path.name))
 def test_same_second_tests_get_unique_folders_without_overwriting(self):
  with tempfile.TemporaryDirectory() as temp:
   started=datetime(2026,11,2,10,45,30).timestamp()
   with ThreadPoolExecutor(max_workers=4) as pool:
    paths=list(pool.map(lambda _:test_folders.create(temp,started),range(8)))
   self.assertEqual(len(set(paths)),8)
   self.assertEqual({p.name for p in paths},{'Archiver-test-2026-11-02_10-45-30'}|{'Archiver-test-2026-11-02_10-45-30_'+str(i) for i in range(2,9)})
 def test_existing_file_is_not_overwritten(self):
  with tempfile.TemporaryDirectory() as temp:
   stamp=datetime(2026,11,2,10,45,30).timestamp();original=test_folders.planned(temp,stamp);original.write_bytes(b'keep')
   path=test_folders.create(temp,stamp)
   self.assertTrue(path.name.endswith('_2'));self.assertEqual(original.read_bytes(),b'keep')
