import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import app
class DependencyReadinessTests(unittest.TestCase):
 def test_every_required_tool_and_feature_participates(self):
  with tempfile.TemporaryDirectory() as tmp:
   ffmpeg=Path(tmp)/'ffmpeg';probe=Path(tmp)/'ffprobe';ffmpeg.touch();probe.touch()
   flags={'tools_verified':True,'ffmpeg':str(ffmpeg),'ffprobe':str(probe),'encoders':['libx264'],'ffv1':True,'xpsnr':True,'vmafmotion':True}
   with patch.dict(app.STATE,flags),patch.object(app.ab_av1,'installation',return_value={'available':True}):
    self.assertTrue(app.dependency_status()['ready'])
    for feature in ['ffv1','xpsnr','vmafmotion','tools_verified']:
     with patch.dict(app.STATE,{feature:False}):
      self.assertFalse(app.dependency_status()['ready'])
      with self.assertRaisesRegex(ValueError,'Video tools setup required'):app.require_video_tools()
    probe.unlink();self.assertIn('FFprobe',app.dependency_status()['missing'])
   with patch.dict(app.STATE,flags),patch.object(app.ab_av1,'installation',return_value={'available':False}):self.assertIn('ab-av1',app.dependency_status()['missing'])
if __name__=='__main__':unittest.main()
