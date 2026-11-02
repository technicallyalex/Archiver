import collections,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import app,workflow_store,preservation,output_verification,storage_checks,encode_reports,output_presets,watch_folders

class WorkflowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.env=patch.dict(os.environ,{'ARCHIVER_WORKFLOW_DIR':str(self.root/'workflows')});self.env.start()
  self.source=self.root/'source.mp4';self.source.write_bytes(b'source')
  self.item={'id':'source','path':str(self.source),'name':self.source.name,'width':1920,'height':1080,'fps':30,'duration':60,'size':6,'audio':'aac','audio_streams':[{'channels':2,'sample_rate':48000}],'streams':[{'index':0,'type':'video','codec':'h264'},{'index':1,'type':'audio','codec':'aac','channels':2},{'index':2,'type':'subtitle','codec':'ass'}],'chapters':[]}
  self.job={'id':'job','source':str(self.source),'name':'source.mp4','output':str(self.root/'output.mp4'),'duration':60,'source_size':6,'status':'running','settings':{'mode':'preserve','codec':'h264','fps':'original','resolution':'original','audio':'copy','sourceMetadata':self.item},'log':collections.deque(['line']),'percent':34,'cancel':False}
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def test_options_are_validated_and_persist(self):
  self.assertTrue(workflow_store.options()['verify']);workflow_store.save_options({'decode':False});self.assertFalse(workflow_store.options()['decode'])
  with self.assertRaises(ValueError):workflow_store.save_options({'reports':'yes'})
 def test_removed_optional_quality_flag_is_ignored(self):
  file=workflow_store.directory()/'options.json';file.parent.mkdir(parents=True,exist_ok=True);file.write_text(json.dumps({'quality':True,'verify':False}))
  self.assertNotIn('quality',workflow_store.options())
  self.job['workflowOptions']={'quality':True,'verify':False}
  with patch.object(app,'Analyzer') as analyzer:
   app.verify_job_output(self.job,self.root/'unused',None)
   analyzer.assert_not_called()
  with self.assertRaises(ValueError):workflow_store.save_options({'quality':True})
 def test_journal_roundtrip_and_interrupted_restart(self):
  workflow_store.save('test',[self.job],[]);loaded=workflow_store.load('test');self.assertEqual(loaded['jobs'][0]['log'],['line']);job=workflow_store.restored_job(loaded['jobs'][0],'test');self.assertEqual(job['status'],'queued');self.assertEqual(job['percent'],0)
 def test_source_change_prevents_recovery(self):
  self.source.write_bytes(b'changed');job=workflow_store.restored_job(self.job,'test');self.assertEqual(job['status'],'failed');self.assertIn('Source changed',job['error'])
 def test_completion_receipt_prevents_reencoding(self):
  Path(self.job['output']).write_bytes(b'complete');workflow_store.receipt('test',self.job);self.assertEqual(workflow_store.restored_job(self.job,'test')['status'],'completed')
 def test_recovery_cleans_only_owned_stage_file(self):
  stage=self.root/'.archiver-owned.mp4';stage.write_bytes(b'partial');self.job['temporaryOutput']=str(stage);workflow_store.restored_job(self.job,'test');self.assertFalse(stage.exists())
  unrelated=self.root/'unrelated.mp4';unrelated.write_bytes(b'keep');self.job['temporaryOutput']=str(unrelated);workflow_store.restored_job(self.job,'test');self.assertTrue(unrelated.exists())
 def test_published_hardlink_recovers_without_receipt(self):
  stage=self.root/'.archiver-owned.mp4';stage.write_bytes(b'complete')
  try:os.link(stage,self.job['output'])
  except OSError:self.skipTest('Hard links unavailable')
  self.job['temporaryOutput']=str(stage);result=workflow_store.restored_job(self.job,'test');self.assertEqual(result['status'],'completed');self.assertFalse(stage.exists());self.assertTrue(Path(self.job['output']).exists())
 def test_corrupt_journal_retained(self):
  file=workflow_store.journal('test');file.parent.mkdir(parents=True);file.write_text('{broken')
  with self.assertRaises(ValueError):workflow_store.load('test')
  self.assertEqual(file.read_text(),'{broken')
 def test_nonfinite_scores_safe_in_reports_and_journal(self):
  self.assertIsNone(workflow_store.clean({'score':float('inf')})['score'])
 def test_preservation_blocks_incompatible_subtitles(self):
  settings={'container':'mp4','audio':'copy','preservation':{'subtitles':'copy'}}
  self.assertTrue(preservation.summary(self.item,settings)['issues'])
  with self.assertRaises(ValueError):preservation.command(['ffmpeg','-i','a','-map','0:v:0','out.mp4'],self.item,settings)
 def test_preservation_mapping_has_no_duplicate_maps(self):
  config={'container':'mkv','audio':'copy','preservation':{'subtitles':'copy','audioTracks':[]}}
  command=preservation.command(['ffmpeg','-i','a','-map','0:v:0','-map','0:a?','-map_metadata','0','out.mkv'],self.item,config)
  self.assertNotIn('0:a?',command);self.assertIn('0:s?',command);self.assertEqual(command.count('0:v:0'),1);self.assertEqual(command,preservation.command(command,self.item,config))
 def test_invalid_track_selection_rejected(self):
  for value in ([-1],[True],'0',{'stream':1}):
   with self.subTest(value=value),self.assertRaises(ValueError):preservation.settings({'audioTracks':value})
 def test_hdr_h264_is_not_silently_retagged(self):
  item={**self.item,'color_transfer':'smpte2084'}
  with self.assertRaisesRegex(ValueError,'HDR preservation'):preservation.command(['ffmpeg','out.mp4'],item,{'codec':'h264','preservation':{'color':True}})
 def test_source_properties_are_checked_against_intent(self):
  output={**self.item,'audio_streams':[{}]};self.assertTrue(output_verification.inspect(self.item,output,self.job['settings']))
  with self.assertRaisesRegex(ValueError,'Resolution verification'):output_verification.inspect(self.item,{**output,'width':1280},self.job['settings'])
 def test_intentional_resolution_and_fps_changes_pass(self):
  config={**self.job['settings'],'resolution':'720','fps':'24'};self.assertTrue(output_verification.inspect(self.item,{**self.item,'width':1280,'height':720,'fps':24},config))
 def test_copy_ignores_transcode_controls(self):
  config={**self.job['settings'],'mode':'copy','fps':'24','resolution':'720'};self.assertTrue(output_verification.inspect(self.item,self.item,config))
 def test_missing_audio_track_fails(self):
  with self.assertRaisesRegex(ValueError,'Audio tracks'):output_verification.inspect(self.item,{**self.item,'audio_streams':[]},self.job['settings'])
 def test_quality_windows_avoid_search_and_each_other(self):
  used=[{'start':100,'duration':8}];windows=output_verification.quality_windows(600,used)
  self.assertEqual(len(windows),3);self.assertTrue(all(abs(w['start']-100)>=8 for w in windows))
 def test_storage_disconnection_and_low_free_space_block(self):
  with patch.object(storage_checks.shutil,'disk_usage',return_value=type('Usage',(),{'free':1,'total':100})()):self.assertTrue(storage_checks.snapshot([self.job])['blocked'])
  self.job['output']=str(self.root/'missing'/'out.mp4');self.assertTrue(storage_checks.snapshot([self.job])['blocked'])
 def test_unknown_quality_size_is_labeled_budget(self):
  result=storage_checks.snapshot([self.job]);self.assertFalse(result['locations'][0]['estimated']);self.assertEqual(result['locations'][0]['budget'],6)
 def test_report_escapes_paths_and_retains_versions(self):
  self.job.update(output_size=3,started=1,finished=5);data=encode_reports.document(self.job,'test',{'FFmpeg':'8.1'});data['source']['path']='<script>alert(1)</script>'
  rendered=encode_reports.render(data);self.assertNotIn('<script>',rendered);self.assertIn('&lt;script&gt;',rendered);self.assertEqual(data['output']['reductionPercent'],50)
 def test_report_does_not_overwrite_an_unrelated_sidecar(self):
  self.job.update(output_size=3,started=1,finished=5);file=Path(self.job['output']+'.archiver-report.json');file.write_text('keep');paths=encode_reports.save(self.job,'test',{});self.assertEqual(file.read_text(),'keep');self.assertNotEqual(paths['json'],str(file))
 def test_portable_presets_exclude_paths_and_measured_settings(self):
  file=self.root/'presets.json'
  config={'outputCodec':'av1','qualityMode':'custom','mode':'directory','destination':'private/path','encoder':'av1_nvenc','testedEncoder':'av1_nvenc','bitrate':'cq','qualityValue':'31'}
  with patch.object(output_presets,'path',return_value=file):
   saved=output_presets.change({'action':'save','name':'Archive','settings':config});exported=output_presets.portable_export(saved['selectedId']);self.assertNotIn('destination',exported['settings']);self.assertNotIn('qualityValue',exported['settings']);imported=output_presets.portable_import(exported);self.assertEqual(imported['settings']['mode'],'preserve');self.assertEqual(imported['settings']['qualityMode'],'auto')
 def test_import_rejects_unrelated_json(self):
  with self.assertRaises(ValueError):output_presets.portable_import({'settings':{}})

class WatchFolderTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'source';self.source.mkdir();self.dest=self.root/'dest';self.dest.mkdir();self.patch=patch.dict(os.environ,{'ARCHIVER_WORKFLOW_DIR':str(self.root/'workflows')});self.patch.start()
  self.preset={'id':'p','name':'Archive','settings':{'qualityMode':'custom','outputCodec':'h264','mode':'preserve'}};self.preset_patch=patch.object(output_presets,'load',return_value={'presets':[self.preset]});self.preset_patch.start()
 def tearDown(self):self.preset_patch.stop();self.patch.stop();self.tmp.cleanup()
 def add(self):return watch_folders.change({'action':'save','source':str(self.source),'destination':str(self.dest),'presetId':'p','recursive':True,'autoStart':False},{'.mp4'})['rules'][0]
 def test_baseline_excluded_and_stable_new_file_once(self):
  (self.source/'existing.mp4').write_bytes(b'old');self.add();events=[];engine=watch_folders.Engine({'.mp4'},lambda *args:events.append(args),lambda *a:None);now=[0]
  engine.tick(lambda:now[0]);self.assertFalse(events);new=self.source/'new.mp4';new.write_bytes(b'new');engine.tick(lambda:now[0]);now[0]=29;engine.tick(lambda:now[0]);self.assertFalse(events);now[0]=31;engine.tick(lambda:now[0]);engine.tick(lambda:now[0]);self.assertEqual(len(events),1)
 def test_proxy_and_test_folders_excluded(self):
  self.add()
  for folder in ('Proxies','Proxy','Archiver-test-abc'):
   directory=self.source/folder;directory.mkdir();(directory/'sample.mp4').touch()
  self.assertEqual(list(watch_folders.candidates(watch_folders.load()['rules'][0],{'.mp4'})),[])
 def test_destination_cannot_feed_back_into_source(self):
  inside=self.source/'output';inside.mkdir()
  with self.assertRaisesRegex(ValueError,'outside'):watch_folders.change({'action':'save','source':str(self.source),'destination':str(inside),'presetId':'p'},{'.mp4'})
 def test_failed_dispatch_is_individual_and_retryable(self):
  rule=self.add();file=self.source/'new.mp4';file.write_bytes(b'new');events=[]
  def fail(*a):raise ValueError('Tool unavailable')
  engine=watch_folders.Engine({'.mp4'},fail,lambda *args:events.append(args));engine.tick(lambda:0);engine.tick(lambda:31);engine.tick(lambda:32);self.assertEqual(len(events),1);self.assertIn('Tool unavailable',watch_folders.load()['rules'][0]['error']);watch_folders.change({'action':'retry','id':rule['id']},{'.mp4'});self.assertNotIn(str(file),watch_folders.load()['seen'][rule['id']])
