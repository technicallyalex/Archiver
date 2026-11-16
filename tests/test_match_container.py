import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import app

class MatchContainerTests(unittest.TestCase):
    def test_resolution_is_per_file_and_rejects_unsupported_extensions(self):
        settings={'container':'source','codec':'av1'}
        for ext in ('mp4','mov','mkv','webm'):
            self.assertEqual(app.match_container({'path':'clip.'+ext.upper()},settings)['container'],ext)
        self.assertEqual(settings['container'],'source')
        with self.assertRaisesRegex(ValueError,'Cannot match'):app.match_container({'path':'clip.avi'},settings)
        with self.assertRaisesRegex(ValueError,'requires AV1'):app.match_container({'path':'clip.webm'},{**settings,'codec':'h264'})

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Video tools required')
    def test_mixed_batch_resolves_names_commands_and_overwrite_without_touching_sources(self):
        old=copy.deepcopy(app.STATE)
        try:
            app.configure(shutil.which('ffmpeg'),shutil.which('ffprobe'))
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);items=[]
                for ext in ('mp4','mov','mkv'):
                    source=root/('clip.'+ext)
                    result=app.run([app.STATE['ffmpeg'],'-v','error','-f','lavfi','-i','testsrc2=s=96x64:r=10:d=1','-c:v','libx264',str(source)])
                    self.assertEqual(result.returncode,0,result.stderr);items.append(app.probe(source))
                app.STATE['files']={i['id']:i for i in items};app.STATE['jobs']=[]
                settings=dict(qualityMode='custom',codec='h264',encoder='libx264',container='source',audio='copy',bitrate='crf',qualityValue=22,mode='overwrite')
                before={i['path']:Path(i['path']).read_bytes() for i in items}
                app.enqueue([i['id'] for i in items],settings)
                self.assertEqual([j['settings']['container'] for j in app.STATE['jobs']],['mp4','mov','mkv'])
                for job in app.STATE['jobs']:self.assertEqual(job['source'],job['output'])
                for item in items:
                    self.assertEqual(Path(item['path']).read_bytes(),before[item['path']])
                    self.assertTrue(app.output_name(item,{**settings,'mode':'preserve','nameSuffix':'archiver'}).endswith(Path(item['path']).suffix))
        finally:app.STATE.clear();app.STATE.update(old)
