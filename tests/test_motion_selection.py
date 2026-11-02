import random
import unittest
import motion_selection


class SelectionTests(unittest.TestCase):
    def test_bounded_random_stratified_probes(self):
        a = motion_selection.probes(7200, random.Random(3))
        b = motion_selection.probes(7200, random.Random(4))
        self.assertNotEqual(a, b)
        self.assertEqual(len(a),40);self.assertEqual(sum(w['duration'] for w in a),80)
        self.assertTrue(all(0 <= w['start'] < w['start']+w['duration'] <= 7200 for w in a))
        self.assertEqual(a, sorted(a, key=lambda w:w['start']))

    def test_typical_and_demanding_not_only_mean(self):
        samples = [{'start':i*30., 'mean':float(i)} for i in range(9)]
        plan = motion_selection.select(300, samples)
        self.assertEqual(len(plan), 6)
        self.assertEqual(sum(w['duration'] for w in plan),48)
        self.assertIn(237., [w['start'] for w in plan])
        self.assertTrue(all(b['start'] >= a['start']+a['duration'] for a,b in zip(plan,plan[1:])))

    def test_short_file_and_invalid_probes(self):
        self.assertEqual(motion_selection.select(6, []), [{'start':0.,'duration':6}])
        with self.assertRaises(ValueError):motion_selection.select(300, [])

    def test_long_recording_budget_and_independent_holdouts(self):
        for duration,count in [(60,12),(600,20),(3600,32),(13393,40),(18000,48)]:
            with self.subTest(duration=duration):
                probes=motion_selection.probes(duration,random.Random(9));self.assertEqual(len(probes),count)
                measured=[{**w,'mean':i%7} for i,w in enumerate(probes)]
                plan=motion_selection.select(duration,measured)
                self.assertEqual(len(plan),min(8 if duration>=3600 else 6,max(1,duration//16)))
                extra=motion_selection.holdouts(duration,measured,plan,4)
                for w in extra:
                    self.assertTrue(all(w['start']+8<=u['start'] or u['start']+u['duration']<=w['start'] for u in plan+extra if w is not u))
                self.assertTrue(all(0<=w['start']<=duration-w['duration'] for w in plan+extra))
    def test_highest_motion_retained_and_missing_scores_rejected(self):
        measured=[{'start':i*100.,'mean':float(i)} for i in range(40)]
        plan=motion_selection.select(4000,measured)
        self.assertIn(3897.,[w['start'] for w in plan])
        with self.assertRaises(ValueError):motion_selection.select(4000,[{'start':0,'mean':float('nan')}]*4)

    def test_parallel_probe_progress_reports_positions_and_completion(self):
        import tempfile,threading
        from unittest.mock import Mock,patch
        windows=[{'start':10.,'duration':2.},{'start':80.,'duration':2.},{'start':170.,'duration':2.}]
        snapshots=[];barrier=threading.Barrier(2);analyzer=Mock();analyzer.cancelled.return_value=False
        def measure(worker,path,window,directory,index):
            if index<102:barrier.wait(timeout=2)
            return {**window,'mean':float(index)}
        with tempfile.TemporaryDirectory() as tmp,patch.object(motion_selection,'probes',return_value=windows),patch.object(motion_selection.motion,'measure',side_effect=measure),patch.object(motion_selection,'reference',return_value={'path':'reference.mkv','sampleMotion':[]}):
            motion_selection.prepare(analyzer,{'path':'source','duration':300},tmp,lambda _:None,snapshots.append,probe_factory=lambda:Mock())
        events=[s for s in snapshots if s.get('stage')=='motion-scout']
        self.assertTrue(any(sum(p['status']=='active' for p in s['motionProbes'])==2 for s in events))
        self.assertEqual(events[-1]['motionProbesCompleted'],3)
        self.assertEqual([(p['start'],p['duration']) for p in events[-1]['motionProbes']],[(10.,2.),(80.,2.),(170.,2.)])
        self.assertTrue(all(p['status']=='completed' for p in events[-1]['motionProbes']))
        self.assertEqual(snapshots[-1]['stage'],'sample-previews')
