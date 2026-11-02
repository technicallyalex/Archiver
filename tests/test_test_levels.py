import random
import unittest
import test_levels
import motion_selection

class CoverageLevelsTests(unittest.TestCase):
 def test_unknown_level_is_rejected(self):
  for value in ('maximum','',None,[],True):
   with self.subTest(value=value),self.assertRaises(ValueError):test_levels.policy(value)
 def test_coverage_increases_without_overlapping_samples(self):
  counts=[]
  for level in ('fast','balanced','extensive'):
   probes=motion_selection.probes(10800,random.Random(7),level=level)
   measured=[{**w,'mean':float(i)} for i,w in enumerate(probes)]
   clips=motion_selection.select(10800,measured,level=level)
   counts.append((len(probes),len(clips)))
   self.assertTrue(all(a['start']+a['duration']<=b['start'] for a,b in zip(clips,clips[1:])))
   self.assertIn(max(0,min(10800-8,measured[-1]['start']-3)),[w['start'] for w in clips])
   held=motion_selection.holdouts(10800,measured,clips,test_levels.holdout_count(level,len(clips)))
   self.assertTrue(held)
   self.assertTrue(all(w['start']+w['duration']<=c['start'] or c['start']+c['duration']<=w['start'] for w in held for c in clips))
  self.assertEqual(counts,[(20,3),(40,8),(60,12)])
 def test_every_depth_uses_full_very_short_file(self):
  for level in test_levels.LEVELS:
   self.assertEqual(motion_selection.select(8,[],level=level),[{'start':0.,'duration':8}])

 def test_queue_rejects_unknown_depth_before_tool_or_source_work(self):
  import app
  with self.assertRaisesRegex(ValueError,'Fast, Balanced or Extensive'):
   app.enqueue_tests([],{'qualityMode':'auto','testLevel':'unbounded'})
