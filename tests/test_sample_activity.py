import json,tempfile,unittest,threading
from pathlib import Path
from unittest.mock import patch
import ab_av1

class ActivityTests(unittest.TestCase):
 def test_joined_clips_follow_real_scoring_position(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);tool=root/'tool';tool.write_bytes(b'tool');updates=[];position_seen=threading.Event()
   item={'path':str(tool),'duration':100,'size':1000,'_motionSelection':{'path':str(tool),'referenceDuration':24,'windows':[{'start':i*20,'duration':8} for i in range(3)]}}
   event=dict(crf=20,xpsnr=40,predicted_encode_size=100,predicted_encode_seconds=1,predicted_encode_percent=10)
   def stream(command,directory,env,cancel,line):
    line('stderr','encoding sample 1/1 crf 20')
    self.assertEqual(updates[-2].get('activeSampleIndices',[]),[])
    line('stderr','[INFO ab_av1::xpsnr] xpsnr encoded.mkv vs reference reference.mkv')
    self.assertEqual(updates[-1]['activeSampleIndices'],[])
    (directory/'scoring-progress.txt').write_text('frame:300 pts:300 pts_time:10\narchiver_preview=1\n')
    self.assertTrue(position_seen.wait(2))
    self.assertEqual(updates[-1]['activeSampleIndices'],[1])
    line('stdout',json.dumps({**event,'type':'sample-encode-done'}))
    self.assertTrue(any(u.get('stage')=='search' and u.get('activeSampleIndices')==[] for u in updates))
    line('stdout',json.dumps({**event,'type':'crf-search-done'}))
   def telemetry(update):
    updates.append(update)
    if update.get('activeSampleIndices')==[1]:position_seen.set()
   with patch.object(ab_av1,'binary',return_value=str(tool)),patch.object(ab_av1,'stream',side_effect=stream):
    ab_av1.analyze(item,{'abCodec':'h264','encodingMode':'software','qualityMode':'perceptual'},['libx264'],str(tool),str(tool),root/'run',lambda:False,lambda _:None,telemetry)
   self.assertEqual(updates[-2]['activeSampleIndices'],[])
