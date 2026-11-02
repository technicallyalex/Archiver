from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
import app
from quality import fingerprint

class PerFileTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  tool=self.root/'tool';tool.write_bytes(b'tool')
  self.files={}
  for i in range(2):
   path=self.root/f'input{i}.mp4';path.write_bytes(b'source')
   self.files[str(i)]=dict(id=str(i),path=str(path),name=path.name,size=6,duration=10+i,fps=30,width=128,height=96,pixel_format='yuv420p',codec='h264')
  self.settings=dict(qualityMode='auto',autoEngine='ab-av1',abCodec='h264',abTarget='perceptual',encodingMode='software',hardwareBackend='nvenc',container='mp4',xpsnrTarget=38,priority='balanced')
  self.output=dict(mode='preserve',naming='batch',batchName='tested',audio='none')
  self.contexts=[patch.dict(app.STATE,files=self.files,jobs=[],ffmpeg=str(tool),ffprobe=str(tool),encoders=['libx264'],xpsnr=True,vmafmotion=False,queue_paused=False),patch.object(app,'TEST_JOBS',[]),patch.object(app,'TEST_FILES',{}),patch.object(app,'AUTO_REPORTS',{}),patch.object(app,'TEST_PAUSED',True),patch.object(app,'prepare_test_previews'),patch.object(app.motion_selection,'prepare',side_effect=lambda analyzer,item,*args,**kwargs:{'windows':[{'start':0.,'duration':item['duration']}],'sampleMotion':[]})]
  for c in self.contexts:c.start()
 def tearDown(self):
  for c in reversed(self.contexts):c.stop()
  self.tmp.cleanup()
 def analyze(self,item,*args,**kwargs):
  value=20 if item['id']=='0' else 28
  winner=dict(codec='h264',encoder='libx264',bitrate='crf',qualityValue=value,encoderPriority='balanced',bytesPerSecond=1000,secondsPerSecond=.1,scores=[{'mean':38.2,'p05':None}])
  return dict(engine='ab-av1',metric='xpsnr',winner=winner,alternatives=[winner],trials=1,policy={'metric':'xpsnr','mean':38},keepOriginal=False,failures=[])
 def test_each_result_bound_to_own_file_and_stable_batch_name(self):
  app.enqueue_tests(['0','1'],self.settings,encode_settings=self.output)
  self.assertEqual(app.STATE['jobs'],[])
  self.output['batchName']='changed-after-start'
  with patch.object(app,'probe',side_effect=lambda path,**kwargs:next(f for f in self.files.values() if f['path']==str(path))),patch.object(app,'quality_analysis',side_effect=self.analyze):
   for job in app.TEST_JOBS:app.run_test_job(job)
  self.assertEqual(len(app.STATE['jobs']),2)
  self.assertEqual([Path(j['output']).name for j in app.STATE['jobs']],['tested_001.mp4','tested_002.mp4'])
  self.assertEqual([j['testedAnalysis']['winner']['qualityValue'] for j in app.STATE['jobs']],[20,28])
  self.assertTrue(all(j['queuedForEncoding'] for j in app.TEST_JOBS))
  for j in app.STATE['jobs']:
   self.assertEqual(j['testedAnalysisKey'],fingerprint(j['settings']['sourceMetadata'],j['settings'],app.STATE['ffmpeg'],app.STATE['ffprobe']))
 def test_invalid_output_rejected_before_tests_added(self):
  with self.assertRaises(ValueError):app.enqueue_tests(['0','1'],self.settings,encode_settings={**self.output,'mode':'directory','destination':str(self.root/'missing')})
  self.assertFalse(app.TEST_JOBS);self.assertFalse(app.STATE['jobs'])
 def test_failed_test_does_not_enqueue(self):
  app.enqueue_tests(['0'],self.settings,encode_settings=self.output)
  with patch.object(app,'probe',return_value=self.files['0']),patch.object(app,'quality_analysis',side_effect=ValueError('Target unavailable')):
   with self.assertRaises(ValueError):app.run_test_job(app.TEST_JOBS[0])
  self.assertFalse(app.STATE['jobs'])
 def test_changed_source_refuses_handoff(self):
  job={'status':'completed','source':self.files['0']['path'],'settings':self.settings,'result':{'profiles':{'perceptual':{}},'profileKeys':{'perceptual':'old'}},'encodeSettings':self.output,'id':'old'}
  with self.assertRaises(ValueError):app.queue_test_result(job)
  self.assertFalse(app.STATE['jobs'])

 def test_pool_root_default_and_output_override(self):
  nested=self.root/'nested';nested.mkdir()
  source=Path(self.files['0']['path']);moved=nested/source.name;source.rename(moved);self.files['0']['path']=str(moved)
  with patch.dict(app.STATE,scan={'directory':str(self.root)}):
   app.enqueue_tests(['0'],self.settings)
   self.assertEqual(Path(app.TEST_JOBS[-1]['outputDirectory']).parent,self.root)
   app.TEST_JOBS.clear()
   custom=self.root/'custom';custom.mkdir()
   app.enqueue_tests(['0'],self.settings,directory=str(custom))
   self.assertEqual(Path(app.TEST_JOBS[-1]['outputDirectory']).parent,custom)

 def test_test_queue_waits_by_default_even_when_not_paused(self):
  import threading
  with patch.object(app,'TEST_PAUSED',False),patch.object(app,'TEST_WAKE',threading.Event()):
   app.enqueue_tests(['0'],self.settings)
   self.assertFalse(app.TEST_WAKE.is_set())
   self.assertEqual(app.TEST_JOBS[0]['status'],'queued')
 def test_test_queue_auto_start_is_opt_in_and_respects_pause(self):
  import threading
  for paused,automatic,starts in [(False,True,True),(True,True,False),(False,False,False),(False,'true',False)]:
   with self.subTest(paused=paused,automatic=automatic),patch.object(app,'TEST_PAUSED',paused),patch.object(app,'TEST_JOBS',[]),patch.object(app,'TEST_WAKE',threading.Event()):
    app.enqueue_tests(['0'],self.settings,auto_start=automatic)
    self.assertEqual(app.TEST_WAKE.is_set(),starts)
 def test_adding_to_active_test_queue_does_not_pause_it(self):
  import threading
  wake=threading.Event();wake.set()
  with patch.object(app,'TEST_PAUSED',False),patch.object(app,'TEST_WAKE',wake):
   app.enqueue_tests(['0'],self.settings)
   self.assertTrue(app.TEST_WAKE.is_set())

 def test_held_tests_do_not_reserve_encode_capacity(self):
  import threading
  wake=threading.Event()
  with patch.object(app,'TEST_PAUSED',False),patch.object(app,'TEST_WAKE',wake):
   app.enqueue_tests(['0'],self.settings)
   self.assertFalse(app.runnable_test_work())
   wake.set();self.assertTrue(app.runnable_test_work())

 def test_folder_uses_actual_start_time_instead_of_queue_time(self):
  from datetime import datetime
  app.enqueue_tests(['0'],self.settings)
  job=app.TEST_JOBS[-1];job['started']=datetime(2020,1,2,3,4,5).timestamp()
  with patch.object(app,'probe',return_value=self.files['0']),patch.object(app,'quality_analysis',side_effect=self.analyze):
   app.run_test_job(job)
  self.assertEqual(Path(job['outputDirectory']).name,'Archiver-test-2020-01-02_03-04-05')
  self.assertTrue(Path(job['outputDirectory']).is_dir())
