from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
import metadata_cache
from test_metadata_import import item

class CacheLocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.environment=patch.dict(os.environ,{},clear=False);self.environment.start();self.override=os.environ.pop('ARCHIVER_CACHE_DIR',None)
        self.paths=patch.object(metadata_cache,'settings_path',return_value=self.root/'settings.json');self.paths.start()
        self.default=patch.object(metadata_cache,'default_path',return_value=self.root/'default/metadata.sqlite');self.default.start()
    def tearDown(self):
        self.default.stop();self.paths.stop();self.environment.stop();self.tmp.cleanup()
    def test_configured_directory_persists_and_copies_existing_metadata(self):
        source=self.root/'clip.mp4';source.write_bytes(b'clip');stamp=metadata_cache.signature(source)
        old=metadata_cache.Cache();old.put(source,stamp,'tool',item())
        result=metadata_cache.configure(str(self.root/'custom'))
        self.assertEqual(result['entries'],1);self.assertGreater(result['bytes'],0)
        self.assertEqual(metadata_cache.cache_path(),self.root/'custom/metadata.sqlite')
        self.assertIsNotNone(metadata_cache.Cache().get(source,stamp,'tool'))
        self.assertTrue(old.path.is_file())
        self.assertIsNone(metadata_cache.Cache().get(source,(stamp[0]+1,stamp[1]),'tool'))
        metadata_cache.configure('');self.assertEqual(metadata_cache.cache_path(),self.root/'default/metadata.sqlite')
    def test_relative_or_unwritable_location_does_not_change_preferences(self):
        with self.assertRaisesRegex(ValueError,'full cache'):metadata_cache.configure('relative')
        target=self.root/'file';target.write_bytes(b'x')
        with self.assertRaises(OSError):metadata_cache.configure(str(target))
        self.assertFalse((self.root/'settings.json').exists())
    def test_environment_override_cannot_be_silently_changed(self):
        with patch.dict(os.environ,ARCHIVER_CACHE_DIR=str(self.root/'override')):
            with self.assertRaisesRegex(ValueError,'controlled'):metadata_cache.configure(str(self.root/'custom'))
            self.assertTrue(metadata_cache.info()['override'])
