"""Regressions for the preview.122 systems audit (A01–A25)."""
import collections,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import app,workflow_store,watch_folders,folder_history,output_presets,output_verification,preservation,storage_checks

class SystemsAuditTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'source.mp4';self.source.write_bytes(b'source')
  self.item={'id':'source','name':self.source.name,'path':str(self.source),'size':6,'sourceMtimeNs':self.source.stat().st_mtime_ns,'duration':60,'videoDuration':60,'width':1920,'height':1080,'fps':30,'codec':'h264','pixel_format':'yuv420p','audio':'','streams':[],'audio_streams':[]}
  self.config={'qualityMode':'custom','codec':'h264','outputCodec':'h264','encoder':'libx264','container':'mp4','mode':'preserve','bitrate':'crf','qualityValue':'20','resolution':'original','fps':'original','audio':'aac','preservation':dict(preservation.DEFAULTS)}
  self.job={'id':'audit','source':str(self.source),'output':str(self.root/'out.mp4'),'settings':{**self.config,'sourceMetadata':self.item},'status':'queued','log':[],'source_size':6}
  self.env=patch.dict(os.environ,{'ARCHIVER_WORKFLOW_DIR':str(self.root/'workflows')});self.env.start()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def test_a01_watch_root_and_rule_validation(self):
  file=watch_folders.path();file.parent.mkdir(parents=True)
  for value in ([],{'rules':[{}],'seen':{}},{'rules':[],'seen':{'a':None}}):
   file.write_text(json.dumps(value))
   with self.assertRaises(ValueError):watch_folders.load()
   self.assertEqual(json.loads(file.read_text()),value)
 def test_a02_enqueue_is_durable_before_return(self):
  with patch.dict(app.STATE,{'files':{'source':self.item},'jobs':[],'queue_paused':True}),patch.object(app,'WORKFLOW_READY',True),patch.object(app,'TEST_JOBS',[]),patch.object(app,'RECOVERY',{'jobs':[],'tests':[],'error':''}),patch.object(app,'command_for',return_value=['ffmpeg']):
   app.enqueue(['source'],self.config)
   self.assertEqual(len(workflow_store.load(app.VERSION)['jobs']),1)
 def test_a03_offline_staging_keeps_deferred_cleanup(self):
  stage=self.root/'.archiver-interrupted.mp4';stage.write_bytes(b'partial');job={**self.job,'temporaryOutput':str(stage)};unlink=Path.unlink
  def offline(p,*a,**kw):
   if p==stage:raise OSError('offline')
   return unlink(p,*a,**kw)
  with patch.object(Path,'unlink',offline):restored=workflow_store.restored_job(job,'test')
  self.assertEqual(restored['temporaryOutput'],str(stage));self.assertTrue(stage.exists())
  workflow_store.cleanup_stage(restored);self.assertFalse(stage.exists());self.assertNotIn('temporaryOutput',restored)
 def test_a04_batch_sequence_survives_sanitizing(self):self.assertEqual(workflow_store.clean({'_batchSequence':7,'_transient':1}),{'_batchSequence':7})
 def test_a05_handoff_uses_queued_source(self):
  test={'id':'test','source':str(self.source),'settings':{},'encodeSettings':self.config,'recoverySource':self.item}
  with patch.dict(app.STATE,{'files':{}}),patch.object(app,'usable_profiles',return_value=['perceptual']),patch.object(app,'enqueue') as enqueue,patch.object(app,'checkpoint'):
   app.queue_test_result(test)
   self.assertEqual(enqueue.call_args.kwargs['source_items']['source'],self.item)
 def test_a06_format_conversion_is_visible_and_verified(self):
  source={**self.item,'pixel_format':'yuv444p10le'}
  self.assertTrue(preservation.summary(source,self.config)['conversions'])
  self.assertTrue(output_verification.inspect(source,{**source,'pixel_format':'yuv420p'},self.config))
  with self.assertRaisesRegex(ValueError,'Pixel format'):output_verification.inspect(source,source,self.config)
 def test_a07_storage_failure_classifier(self):
  self.assertTrue(storage_checks.write_failure(ValueError('FFmpeg exited'),['No space left on device']))
  self.assertFalse(storage_checks.write_failure(ValueError('Invalid argument'),[]))
 def test_a07_fast_write_failure_pauses_before_monitor(self):
  import io
  class Process:
   def __init__(self,*a,**kw):self.stdout=io.StringIO('');self.stderr=io.StringIO('No space left on device\n')
   def wait(self,*a,**kw):return 1
   def poll(self):return 1
  job={**self.job,'name':'source.mp4','cancel':False,'duration':60,'log':collections.deque(),'workflowOptions':{'verify':False,'reports':False,'storage':True}}
  with patch.dict(app.STATE,{'jobs':[job],'queue_paused':False}),patch.object(app.ab_av1,'installation',return_value={}),patch.object(app,'command_for',return_value=['ffmpeg','output']),patch.object(app.subprocess,'Popen',Process),patch.object(app.storage_checks,'guard',return_value=None):
   app.execute_job(job)
   self.assertEqual(job['status'],'queued');self.assertTrue(app.STATE['queue_paused']);self.assertTrue(self.source.exists())
 def test_a08_encoder_override_requires_review_and_valid_backend(self):
  config={**self.config,'encoder':'h264_nvenc','bitrate':'cqp','qualityValue':'26','encoderPriority':'slow'}
  output_presets.override_encoder(config,'libx264')
  self.assertEqual(config['qualityMode'],'auto');self.assertNotIn('qualityValue',config);self.assertEqual(config['hardwareBackend'],'nvenc')
  config.update(outputCodec='prores');output_presets.override_encoder(config,'prores_ks');self.assertEqual(config['hardwareBackend'],'nvenc');self.assertEqual(config['qualityMode'],'archive')
 def test_a09_changed_source_rejected_before_queue(self):
  self.source.write_bytes(b'changed bytes')
  with patch.dict(app.STATE,{'files':{'source':self.item},'jobs':[]}),patch.object(app,'command_for',return_value=[]):
   with self.assertRaisesRegex(ValueError,'changed since import'):app.enqueue(['source'],self.config)
 def test_a10_bad_entry_quarantined_healthy_queue_retained(self):
  workflow_store.save('test',[self.job,{**self.job,'id':'bad','log':None}],[])
  result=workflow_store.load('test');self.assertEqual(len(result['jobs']),1);self.assertTrue(result['warnings']);self.assertTrue(workflow_store.journal('test').with_suffix('.invalid.json').exists())
 def test_a22_explicit_infinite_measurement_is_not_unknown(self):
  import ab_av1
  tool=self.root/'tool.exe';tool.write_bytes(b'tool')
  event={'crf':28,'xpsnr':None,'predicted_encode_percent':50,'predicted_encode_size':1000,'predicted_encode_seconds':1}
  def stream(*args):
   line=args[-1];line('stderr','- crf 28: Sample 1 (17%) XPSNR inf')
   line('stdout',json.dumps({**event,'type':'sample-encode-done'}));line('stdout',json.dumps({**event,'type':'crf-search-done'}))
  config={'abCodec':'h264','encodingMode':'software','qualityMode':'perceptual','container':'mkv'}
  with patch.object(ab_av1,'binary',return_value=str(tool)),patch.object(ab_av1,'stream',side_effect=stream):
   result=ab_av1.analyze(self.item,config,['libx264'],str(tool),str(tool),self.root/'run',lambda:False,lambda _:None,None)
  self.assertTrue(result['winner']['scores'][0]['identical']);self.assertIsNone(result['winner']['scores'][0]['mean']);json.dumps(result,allow_nan=False)
 def test_a23_duration_matches_selected_streams(self):
  source={**self.item,'duration':120,'videoDuration':60,'streams':[{'type':'audio','duration':120}]}
  config={**self.config,'preservation':{**preservation.DEFAULTS,'audioTracks':[]}}
  self.assertEqual(output_verification.expected_duration(source,config),60)
  self.assertEqual(output_verification.expected_duration(source,self.config),120)
 def test_a24_archive_uses_display_dimensions(self):
  source={**self.item,'rotation':90};self.assertEqual(output_verification.dimensions(source,{'qualityMode':'archive'}),(1080,1920))
 def test_a25_watch_picker_contexts_registered(self):
  for kind in ('watchSource','watchDestination'):self.assertEqual(folder_history.initial_folder(str(self.root),kind),self.root)

if __name__=='__main__':unittest.main()
