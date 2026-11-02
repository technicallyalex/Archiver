import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app
from quality import POLICIES

class QualityLevelTests(unittest.TestCase):
    def test_auto_runs_only_perceptual_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';source.write_bytes(b'source')
            item=dict(path=str(source),duration=60,fps=24,width=640,height=360,pixel_format='yuv420p')
            settings=dict(qualityMode='auto',autoEngine='ab-av1',abCodec='h264',abTarget='suite',encodingMode='software',hardwareBackend='nvenc',container='mkv',priority='balanced')
            job=dict(id='suite-test',source=str(source),settings=settings,outputDirectory=str(Path(tmp)/'test'),cancel=False,progress={},activity=[],status='running')
            calls=[]
            def analyze(item, config, *args, **kwargs):
                target=config['qualityMode'];calls.append(target)
                winner=dict(codec='h264',encoder='libx264',bitrate='crf',qualityValue=22,encoderPriority='balanced')
                return dict(engine='ab-av1',winner=winner,trials=2,keepOriginal=False,alternatives=[winner],policy=POLICIES[target])
            with patch.dict(app.STATE,ffmpeg=str(source),ffprobe=str(source),vmafmotion=False),patch.object(app,'probe',return_value=item),patch.object(app,'quality_analysis',side_effect=analyze),patch.object(app,'AUTO_REPORTS',{}),patch.object(app,'prepare_test_previews'),patch.object(app.motion_selection,'prepare',return_value={'windows':[{'start':0.,'duration':8.}],'sampleMotion':[]}):
                app.run_test_job(job)
                self.assertEqual(app.usable_profiles(job),['perceptual'])
            self.assertEqual(calls,['perceptual'])
            self.assertEqual(job['result']['trials'],2)
            self.assertEqual(job['result']['profileFailures'], {})
            self.assertNotIn('match', POLICIES)
            self.assertEqual(job['progress']['profileTotal'],1)
            self.assertEqual(job['status'],'completed')
            self.assertTrue((Path(job['outputDirectory'])/'results.json').exists())
