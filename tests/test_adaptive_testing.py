import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import adaptive_testing as adaptive
import motion_selection


class AdaptiveTests(unittest.TestCase):
 def fixture(self):
  measured=[{'start':i*300.+10,'mean':float(i)} for i in range(40)]
  plan=motion_selection.select(13393,measured)
  return {'path':'source.mp4','duration':13393,'fps':60,'_motionSelection':{'windows':plan,'probes':measured,'sampleMotion':[], 'referenceDuration':64,'path':'reference.mkv'}}
 def search(self,item,settings,*args):
  q=45 if '_searchMaxCrf' not in settings else min(40,settings['_searchMaxCrf'])
  winner={'codec':'h264','encoder':'libx264','qualityValue':q,'encoderPriority':'balanced','scores':[{'mean':38.18}],'bytesPerSecond':100}
  return {'winner':winner,'alternatives':[winner],'estimatedVideoBytes':1000000,'trials':1,'measurements':[{'crf':q,'xpsnr':38.18}],'metric':'xpsnr'}
 def check(self,analyzer,item,settings,winner,w,directory):
  return {**w,'xpsnr':39.,'identical':False,'bytesPerSecond':100.,'qualityValue':winner['qualityValue'],'encoder':winner['encoder'],'reference':'reference.mkv'}
 def run_analysis(self,root,item=None,check=None,search=None,analyzer=None,settings=None):
  item=item or self.fixture()
  with patch.object(adaptive.ab_av1,'analyze',side_effect=search or self.search) as searching,patch.object(adaptive,'clip_check',side_effect=check or self.check) as checking,patch.object(adaptive.motion_selection,'reference',return_value={'referenceDuration':96,'path':'expanded.mkv','sampleMotion':[]}):
   result=adaptive.analyze(item,{'xpsnrTarget':38,**(settings or {})},['libx264'],'ffmpeg','ffprobe',root,lambda:False,lambda _:None,lambda _:None,analyzer or Mock())
   return result,searching,checking
 def test_independent_clips_disjoint_and_each_score_required(self):
  with tempfile.TemporaryDirectory() as tmp:
   result,search,check=self.run_analysis(tmp)
   self.assertEqual(search.call_count,1);self.assertEqual(check.call_count,12)
   self.assertEqual(len(result['validation']['independentClips']),4)
   self.assertTrue(all(r['passed'] for r in result['validation']['checks']))
   self.assertTrue((Path(tmp)/'validation-history.json').is_file())
 def test_combined_pass_cannot_hide_failed_clip_and_holdout_is_promoted(self):
  failed_start=None
  def check(*args):
   nonlocal failed_start
   r=self.check(*args)
   if args[3]['qualityValue']==45:
    if failed_start is None:failed_start=args[4]['start']
    if args[4]['start']==failed_start:r['xpsnr']=35.
   return r
  with tempfile.TemporaryDirectory() as tmp:
   result,search,_=self.run_analysis(tmp,check=check)
   self.assertEqual(result['winner']['qualityValue'],40)
   self.assertEqual(search.call_count,2)
   self.assertEqual(search.call_args_list[1].args[1]['_searchMaxCrf'],44)
   self.assertGreater(search.call_args_list[1].args[1]['_searchTarget'],38)
   self.assertEqual(len(result['measurements']),2)
   self.assertEqual(len(result['validationHistory']),2)
   reserved={adaptive.window_key(w) for w in result['validationHistory'][0]['independentClips']} & {adaptive.window_key(w) for w in result['validation']['independentClips']}
   self.assertTrue(reserved)
   self.assertTrue(all(not reserved.intersection({adaptive.window_key(w) for w in h['searchClips']}) for h in result['validationHistory']))
 def test_variation_expands_then_stops_when_stable_and_reuses_matching_checks(self):
  count=0
  def search(*args):
   nonlocal count
   count+=1;return self.search(*args)
  def check(*args):
   r=self.check(*args)
   if count==1:r['xpsnr']=39.+(4 if args[4]['start']==self.fixture()['_motionSelection']['windows'][0]['start'] else 0)
   return r
  # Results from the first check are intentionally cached: persistent spread expands to the budget.
  with tempfile.TemporaryDirectory() as tmp:
   result,search,checking=self.run_analysis(tmp,check=check,search=search)
   self.assertEqual(search.call_count,1)
   self.assertTrue(result['validation']['variable'])
   self.assertIn('limited reliability',result['coverage'])
   self.assertEqual(checking.call_count,15)
 def test_retry_searches_weak_clip_and_preserves_fixed_coverage(self):
  def check(*args):
   r=self.check(*args)
   if args[3]['qualityValue']==45:r['xpsnr']=35. if args[4]['start']==self.fixture()['_motionSelection']['windows'][0]['start'] else 39.
   return r
  with tempfile.TemporaryDirectory() as tmp:
   result,search,checking=self.run_analysis(tmp,check=check)
   focused=search.call_args_list[1].args[0]['_motionSelection']
   self.assertEqual(len(focused['windows']),1)
   self.assertEqual(focused['path'],'reference.mkv')
   self.assertEqual(len(result['validation']['checks']),12)
   self.assertTrue(all(r['passed'] for r in result['validation']['checks']))
 def test_failed_focused_retry_checks_weak_clip_first_and_stops_on_plateau(self):
  def check(*args):return {**self.check(*args),'xpsnr':37.5}
  with tempfile.TemporaryDirectory() as tmp,self.assertRaises(ValueError):
   self.run_analysis(tmp,check=check)
  # A deterministic unchanged score cannot consume four complete validation passes.
 def test_searched_holdout_is_replaced_before_final_validation(self):
  original_holdouts=motion_selection.holdouts(self.fixture()['duration'],self.fixture()['_motionSelection']['probes'],self.fixture()['_motionSelection']['windows'],count=4)
  weak=original_holdouts[0]['start']
  def check(*args):
   r=self.check(*args)
   if args[3]['qualityValue']==45 and args[4]['start']==weak:r['xpsnr']=35.
   return r
  with tempfile.TemporaryDirectory() as tmp:
   result,search,_=self.run_analysis(tmp,check=check)
   self.assertEqual(search.call_count,2)
   self.assertIn(weak,[w['start'] for w in result['validation']['searchClips']])
   self.assertNotIn(weak,[w['start'] for w in result['validation']['independentClips']])
   self.assertTrue(result['validation']['independentClips'])
 def test_depth_controls_independent_coverage_and_expansion_not_quality(self):
  for level,independent in [('fast',1),('balanced',4),('extensive',4)]:
   with self.subTest(level=level),tempfile.TemporaryDirectory() as tmp:
    result,search,_=self.run_analysis(tmp,settings={'testLevel':level})
    self.assertEqual(len(result['validation']['independentClips']),independent)
    self.assertEqual(result['testLevel'],level)
    self.assertTrue(all(c['xpsnr']>=38 for c in result['validation']['checks']))
    self.assertEqual(search.call_count,1)
  def varied(*args):
   r=self.check(*args);r['bytesPerSecond']=1000 if args[4]['start']==self.fixture()['_motionSelection']['windows'][0]['start'] else 100
   return r
  for level,passes in [('fast',1),('balanced',2),('extensive',3)]:
   with self.subTest(level=level),tempfile.TemporaryDirectory() as tmp:
    result,search,_=self.run_analysis(tmp,check=varied,settings={'testLevel':level})
    self.assertEqual(len(result['validationHistory']),passes)
    self.assertEqual(search.call_count,1)
 def test_fast_does_not_accept_a_failed_target(self):
  def check(*args):return {**self.check(*args),'xpsnr':37.}
  with tempfile.TemporaryDirectory() as tmp,self.assertRaises(ValueError):
   self.run_analysis(tmp,check=check,settings={'testLevel':'fast'})
 def test_motion_scores_cover_initial_and_independent_clips(self):
  item=self.fixture();first=item['_motionSelection']['windows'][0]
  item['_motionSelection']['sampleMotion']=[{**first,'mean':0.,'p95':0.,'peak':0.,'frames':240}]
  def check(*args):
   row=self.check(*args);w=args[4]
   return {**row,'motion':{**w,'mean':w['start']/1000,'p95':2.,'peak':3.,'frames':240}}
  with tempfile.TemporaryDirectory() as tmp:
   result,_,_=self.run_analysis(tmp,item=item,check=check)
   windows=result['validation']['searchClips']+result['validation']['independentClips']
   self.assertEqual(len(result['sampleMotion']),len(windows))
   self.assertTrue(all('mean' in m for m in result['sampleMotion']))
   self.assertEqual([adaptive.window_key(m) for m in result['sampleMotion']],[adaptive.window_key(w) for w in windows])
 def test_comparison_records_first_target_attempt_and_final_setting(self):
  weak=self.fixture()['_motionSelection']['windows'][0]['start']
  def search(item,settings,*args):
   r=self.search(item,settings,*args)
   if settings.get('_searchMaxCrf')==39:r['winner']['qualityValue']=39
   return r
  def check(*args):
   r=self.check(*args);q=args[3]['qualityValue']
   if args[4]['start']==weak:r['xpsnr']={45:35.,40:37.,39:39.}[q]
   return {**r,'encoded':'check-'+str(args[4]['start'])+'-'+str(q)}
  with tempfile.TemporaryDirectory() as tmp:
   result,_,_=self.run_analysis(tmp,check=check,search=search)
   attempts=[r for r in result['comparisonClips'] if r['start']==weak]
   self.assertEqual([r['attempt'] for r in attempts],[1,2,3])
   self.assertEqual([r['passed'] for r in attempts],[False,False,True])
   self.assertEqual(result['winner']['qualityValue'],39)
 def test_failure_budget_never_yields_a_recommendation(self):
  def check(*args):return {**self.check(*args),'xpsnr':30.}
  with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(ValueError,'No setting passed every clip'):
   self.run_analysis(tmp,check=check)
 def test_cancellation_propagates_without_recommendation(self):
  analyzer=Mock();analyzer.check.side_effect=InterruptedError('cancelled')
  with tempfile.TemporaryDirectory() as tmp,self.assertRaises(InterruptedError):self.run_analysis(tmp,analyzer=analyzer)
 def test_short_full_file_requires_no_independent_window(self):
  item=self.fixture();item['duration']=8;item['_motionSelection']['windows']=[{'start':0.,'duration':8.}]
  with tempfile.TemporaryDirectory() as tmp:
   result,_,checking=self.run_analysis(tmp,item=item)
   self.assertEqual(checking.call_count,1);self.assertIn('Full recording checked',result['coverage'])
 def test_new_scouting_cannot_reuse_another_jobs_result(self):
  import app
  item={**self.fixture(),'width':320,'height':180,'pixel_format':'yuv420p'}
  with tempfile.TemporaryDirectory() as tmp,patch.object(app,'fingerprint',return_value='same-source'),patch.object(app,'QUALITY_CACHE',{'same-source':{'old':True}}),patch.object(app.adaptive_testing,'analyze',return_value={'validated':'new-windows'}) as analyze:
   result=app.quality_analysis(item,{'qualityMode':'perceptual','autoEngine':'ab-av1'},lambda:False,lambda _:None,work_directory=tmp)
   self.assertEqual(result,{'validated':'new-windows'});analyze.assert_called_once()

if __name__=='__main__':unittest.main()

class MotionClipIntegrationTests(unittest.TestCase):
 def test_new_validation_clip_measures_motion_in_reference_pass(self):
  import shutil,subprocess
  import app
  from quality import Analyzer
  ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
  if not ffmpeg or not ffprobe:self.skipTest('FFmpeg required')
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.mkv'
   subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','testsrc2=size=128x96:rate=24:duration=3','-c:v','ffv1',str(source)],check=True,capture_output=True)
   with patch.dict(app.STATE,ffmpeg=ffmpeg,ffprobe=ffprobe,encoders=['libx264']):
    item=app.probe(source);item['_motionSelection']={'sampleMotion':[{'start':0.,'duration':1.,'mean':0.}]}
    analyzer=Analyzer(ffmpeg,ffprobe,app.command_for,lambda:False,lambda _:None)
    settings={'abCodec':'h264','encodingMode':'software'}
    winner={'codec':'h264','encoder':'libx264','qualityValue':20,'encoderPriority':'balanced'}
    with patch.object(adaptive.motion,'measure',wraps=adaptive.motion.measure) as separate_pass:
     result=adaptive.clip_check(analyzer,item,settings,winner,{'start':1.,'duration':1.},root/'checks/1')
    separate_pass.assert_not_called()
    self.assertEqual(result['motion']['start'],1.)
    self.assertGreater(result['motion']['frames'],0)
    self.assertGreater(result['motion']['mean'],0)
