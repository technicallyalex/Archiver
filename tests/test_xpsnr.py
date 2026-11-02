import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from quality import Analyzer


class XpsnrVerificationTests(unittest.TestCase):
    def test_verification_uses_mean_xpsnr(self):
        analyzer=Analyzer('ffmpeg','ffprobe',None,lambda:False,lambda _:None)
        policy={'metric':'xpsnr','mean':38.0,'p05':0,'second':0}
        with tempfile.TemporaryDirectory() as tmp:
            item={'path':str(Path(tmp)/'source.mkv'),'duration':120,'fps':60}
            with patch.object(analyzer,'run'),patch.object(analyzer,'score_xpsnr',side_effect=[37.,39.,40.]):
                analyzer.verify_output(item,Path(tmp)/'out.mkv',policy)
            with patch.object(analyzer,'run'),patch.object(analyzer,'score_xpsnr',return_value=37.):
                with self.assertRaisesRegex(ValueError,'XPSNR 38'):
                    analyzer.verify_output(item,Path(tmp)/'out.mkv',policy)

    def test_frame_inventory_cache_invalidates_when_sample_changes(self):
        import json
        analyzer=Analyzer('ffmpeg','ffprobe',None,lambda:False,lambda _:None)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'sample.mkv';path.write_bytes(b'first')
            with patch.object(analyzer,'run',return_value=json.dumps({'frames':[{'width':128,'height':96}]})) as run:
                analyzer.frames(path);analyzer.frames(path)
                self.assertEqual(run.call_count,1)
                path.write_bytes(b'replacement')
                analyzer.frames(path)
                self.assertEqual(run.call_count,2)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_real_xpsnr_identical_and_damaged_video(self):
        ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
        filters=subprocess.run([ffmpeg,'-hide_banner','-filters'],capture_output=True,text=True).stdout
        if 'xpsnr' not in filters:self.skipTest('XPSNR filter unavailable')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);reference=root/'source.mkv';bad=root/'black.mkv'
            for path,source in [(reference,'testsrc2=size=128x96:rate=30:duration=2'),(bad,'color=black:size=128x96:rate=30:duration=2')]:
                subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i',source,'-c:v','ffv1',str(path)],capture_output=True,check=True)
            analyzer=Analyzer(ffmpeg,ffprobe,None,lambda:False,lambda _:None)
            self.assertTrue(math.isinf(analyzer.score_xpsnr(reference,reference,root,30,0)))
            self.assertLess(analyzer.score_xpsnr(reference,bad,root,30,0),38)
            item={'path':str(reference),'duration':2,'fps':30}
            with self.assertRaisesRegex(ValueError,'XPSNR 38'):
                analyzer.verify_output(item,bad,{'metric':'xpsnr','mean':38.0})
