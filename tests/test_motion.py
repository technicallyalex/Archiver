from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import app
import motion
from quality import Analyzer


class MotionTests(unittest.TestCase):
    def test_statistics_and_relative_labels(self):
        stats=motion.summarize('n:1 motion:0.00\nn:2 motion:2.00\nn:3 motion:4.00\n')
        self.assertEqual(stats['mean'],2);self.assertEqual(stats['peak'],4);self.assertEqual(stats['frames'],3)
        samples=motion.rank_samples([dict(stats),{**stats,'mean':8},{**stats,'mean':5}])
        self.assertEqual([s['relative'] for s in samples],['Lower within test','Higher within test','Middle within test'])
        self.assertEqual(motion.rank_samples([dict(stats),dict(stats)])[0]['relative'],'Similar within test')
        for data in ['','n:2 motion:1','n:1 motion:nan','n:1 motion:-1']:
            with self.assertRaises(ValueError):motion.summarize(data)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_native_motion_static_and_moving_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);analyzer=Analyzer(shutil.which('ffmpeg'),shutil.which('ffprobe'),None,lambda:False,lambda _:None)
            scores=[]
            for index,source_filter in enumerate(['color=c=blue:size=128x96:rate=12:duration=1','testsrc2=size=128x96:rate=12:duration=1']):
                source=root/f'{index}.mkv'
                done=app.run([analyzer.ffmpeg,'-v','error','-f','lavfi','-i',source_filter,'-c:v','ffv1',str(source)])
                self.assertEqual(done.returncode,0,done.stderr)
                result=motion.measure(analyzer,source,{'start':0,'duration':1},root,index)
                self.assertEqual(result['frames'],12);self.assertTrue((root/result['statsFile']).exists());scores.append(result['mean'])
                bounded=motion.measure(analyzer,source,{'start':.25,'duration':.5},root,index+10)
                self.assertEqual(bounded['frames'],6)
            self.assertEqual(scores[0],0);self.assertGreater(scores[1],scores[0])
