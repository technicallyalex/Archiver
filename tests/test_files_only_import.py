import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import app

class FilesOnlyImportTests(unittest.TestCase):
    def setUp(self):
        self.old=copy.deepcopy(app.STATE);self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);app.SCAN_STOP.clear()
        app.STATE['scan']={'running':True,'done':0,'total':0,'errors':[]};app.STATE['files']={}
    def tearDown(self):
        app.STATE.clear();app.STATE.update(self.old);app.SCAN_STOP.clear();self.tmp.cleanup()
    def test_listing_never_reads_video_or_creates_cache_and_obeys_exclusions(self):
        (self.root/'source.mp4').write_bytes(b'not actually video')
        (self.root/'Proxies').mkdir();(self.root/'Proxies/skip.mp4').write_bytes(b'x')
        (self.root/'Archiver-test-2026-11-15').mkdir();(self.root/'Archiver-test-2026-11-15/skip.mkv').write_bytes(b'x')
        with patch.object(app,'probe',side_effect=AssertionError('Probe called')),patch.object(app.metadata_cache,'Cache',side_effect=AssertionError('Cache opened')),patch.object(app.notification_history,'add'):
            app.scan(str(self.root),True,workers=4,excluded_folders=['Proxies'],files_only=True)
        self.assertEqual(len(app.STATE['files']),1);item=next(iter(app.STATE['files'].values()))
        self.assertTrue(item['metadataPending']);self.assertEqual(item['name'],'source.mp4');self.assertGreater(item['size'],0)
        self.assertFalse(app.STATE['scan']['running']);self.assertEqual(app.STATE['scan']['errors'],[])
        with self.assertRaisesRegex(ValueError,'Analyze selected'):app.require_metadata(item)
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Video tools required')
    def test_explicit_analysis_retains_identity_and_populates_metadata(self):
        app.configure(shutil.which('ffmpeg'),shutil.which('ffprobe'));source=self.root/'source.mp4'
        result=app.run([app.STATE['ffmpeg'],'-v','error','-f','lavfi','-i','testsrc2=s=96x64:r=10:d=1','-c:v','libx264',str(source)])
        self.assertEqual(result.returncode,0,result.stderr);item=app.file_listing(source);app.STATE['files'][item['id']]=item
        app.STATE['scan'].update(total=1)
        with patch.object(app.notification_history,'add'):app.analyze_pool([item['id']])
        full=app.STATE['files'][item['id']];self.assertEqual(full['id'],item['id']);self.assertFalse(full['metadataPending']);self.assertEqual(full['width'],96);self.assertEqual(full['codec'],'h264');self.assertGreater(full['duration'],0);self.assertEqual(app.STATE['scan']['errors'],[])
