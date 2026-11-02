import copy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import app


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Video tools required')
class EstimateRangeTests(unittest.TestCase):
    def test_full_range_estimate_encode_preserves_black_and_white(self):
        old=copy.deepcopy(app.STATE)
        try:
            app.configure(shutil.which('ffmpeg'),shutil.which('ffprobe'))
            with tempfile.TemporaryDirectory() as directory:
                source=Path(directory)/'full.mp4';target=Path(directory)/'limited.mp4'
                result=app.run([app.STATE['ffmpeg'],'-v','error','-f','lavfi','-i','color=black:s=96x64:r=10:d=1',
                    '-f','lavfi','-i','color=white:s=96x64:r=10:d=1','-filter_complex','[0:v][1:v]hstack,scale=in_range=tv:out_range=pc,format=yuvj420p[v]',
                    '-map','[v]','-c:v','libx264','-b:v','1000k','-minrate','1000k','-maxrate','1000k','-bufsize','1000k',
                    '-x264-params','nal-hrd=cbr','-color_range','pc',str(source)])
                self.assertEqual(result.returncode,0,result.stderr)
                item=app.probe(source);self.assertEqual(item['pixel_format'],'yuvj420p')
                settings=dict(qualityMode='source',sourcePreset='100',sourceCodec='h264',encodingMode='software',container='mp4',audio='copy')
                resolved=app.source_preset(item,settings)
                command=app.command_for(source,target,{**resolved,'sourceMetadata':item})
                result=app.run(command);self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(app.probe(target)['pixel_format'],'yuv420p')
                def tones(path):
                    r=subprocess.run([app.STATE['ffmpeg'],'-v','error','-i',str(path),'-frames:v','1','-vf','format=gray','-f','rawvideo','-'],capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    self.assertEqual(r.returncode,0,r.stderr)
                    rows=[r.stdout[n:n+192] for n in range(0,len(r.stdout),192)]
                    return [sum(sum(row[start:start+96]) for row in rows)/(96*len(rows)) for start in (0,96)]
                a,b=tones(source),tones(target)
                self.assertLess(abs(a[0]-b[0]),3);self.assertLess(abs(a[1]-b[1]),3)
                self.assertLess(b[0],3);self.assertGreater(b[1],252)
        finally:app.STATE.clear();app.STATE.update(old)
