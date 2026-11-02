import tempfile,unittest
from pathlib import Path
from ab_av1 import SamplePositionTracker
class SamplePositionTests(unittest.TestCase):
 def test_reference_time_maps_to_one_sample_and_old_files_are_ignored(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);events=[];plan=[{'duration':8}]*3
   tracker=SamplePositionTracker(root,plan,24,events.append)
   path=root/'encoding-progress.txt';path.write_text('out_time_us=23000000\n')
   tracker.set_stage('search-encoding');tracker.poll();self.assertEqual(events[-1]['activeSampleIndices'],[])
   for seconds,index in [(0,0),(7,0),(8,1),(17,2),(24,2)]:
    path.write_text(f'out_time_us={seconds*1000000}\n');tracker.poll();self.assertEqual(events[-1]['activeSampleIndices'],[index])
   tracker.set_stage('search-scoring')
   scoring=root/'scoring-progress.txt'
   for seconds,index in [(0,0),(9,1),(20,2)]:
    scoring.write_text(f'frame:1 pts:1 pts_time:{seconds}\narchiver_preview=1\n');tracker.poll();self.assertEqual(events[-1]['activeSampleIndices'],[index])
   tracker.set_stage('search');tracker.poll();self.assertEqual(events[-1]['activeSampleIndices'],[])
   tracker.close()
