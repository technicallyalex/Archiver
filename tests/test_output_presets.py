import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import output_presets as presets
class OutputPresetTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.file=Path(self.tmp.name)/'presets.json';self.mock=patch.object(presets,'path',return_value=self.file);self.mock.start()
  self.settings={'qualityMode':'custom','outputCodec':'av1','qualityValue':'27','container':'mkv','destination':'D:/Exports','filenameTemplate':'{original}_{codec}','mode':'preserve','proresPreferFidelity':False}
 def tearDown(self):self.mock.stop();self.tmp.cleanup()
 def save(self,name='My workflow',**kwargs):return presets.change({'action':'save','name':name,'settings':self.settings,**kwargs})
 def test_save_reload_update_rename_delete(self):
  value=self.save();key=value['selectedId'];self.assertEqual(presets.load()['presets'][0]['settings'],self.settings)
  self.settings['qualityValue']='30';self.save(id=key)
  self.assertEqual(presets.load()['presets'][0]['settings']['qualityValue'],'30')
  presets.change({'action':'rename','id':key,'name':'New name'});self.assertEqual(presets.load()['presets'][0]['name'],'New name')
  presets.change({'action':'delete','id':key});self.assertEqual(presets.load()['presets'],[])
 def test_names_ids_and_duplicates(self):
  self.save()
  for name in ('',' ','x'*81,'MY WORKFLOW'):
   with self.subTest(name=name),self.assertRaises(ValueError):self.save(name)
  with self.assertRaises(ValueError):self.save(id='missing')
  with self.assertRaises(ValueError):presets.change({'action':'delete'})
 def test_sources_bindings_and_confirmation_are_not_saved(self):
  self.settings.update(sourceMetadata={'path':'original'},autoTestId='old-test',autoPreset='old-profile',confirmDelete=True,deleteOriginal=True,ids=['file'],directory='D:/Source')
  saved=self.save()['presets'][0]['settings']
  for key in ('sourceMetadata','autoTestId','autoPreset','confirmDelete','deleteOriginal','ids','directory'):self.assertNotIn(key,saved)
  self.assertEqual(saved['destination'],'D:/Exports')
 def test_proxy_and_automated_configs(self):
  for mode,codec in [('proxy','prores'),('proxy','h264'),('proxy','hevc'),('proxy','av1'),('auto','av1'),('source','hevc'),('archive','prores')]:
   self.settings.update(qualityMode=mode,outputCodec=codec,outputPreset='proxy-quarter',xpsnrTarget='38')
   self.save(mode+codec)
  self.assertEqual(len(presets.load()['presets']),7)
 def test_invalid_settings_do_not_modify_existing_file(self):
  self.save();original=self.file.read_bytes()
  for settings in [[],{},dict(self.settings,qualityMode='bad'),dict(self.settings,qualityMode='proxy',outputCodec='vp9'),dict(self.settings,qualityValue=27),dict(self.settings,proresPreferFidelity='yes')]:
   with self.subTest(settings=settings),self.assertRaises(ValueError):presets.change({'action':'save','name':'Invalid','settings':settings})
  self.assertEqual(self.file.read_bytes(),original)
 def test_corrupt_file_not_overwritten(self):
  self.file.write_text('{bad')
  with self.assertRaises(ValueError):self.save()
  self.assertEqual(self.file.read_text(),'{bad')
 def test_parallel_saves_are_not_lost(self):
  with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda i:self.save(f'Workflow {i}'),range(12)))
  self.assertEqual(len(presets.load()['presets']),12)
 def test_startup_default_survives_reload_rename_update_and_delete(self):
  record=self.save();key=record['selectedId'];self.assertEqual(record['defaultId'],'')
  presets.change({'action':'set-default','id':key});self.assertEqual(presets.load()['defaultId'],key)
  presets.change({'action':'rename','id':key,'name':'Startup'});self.save('Startup',id=key)
  self.assertEqual(presets.load()['defaultId'],key)
  presets.change({'action':'delete','id':key});self.assertEqual(presets.load()['defaultId'],'')
 def test_builtin_default_and_legacy_file(self):
  self.file.write_text(json.dumps({'version':1,'presets':[]}));self.assertEqual(presets.load()['defaultId'],'')
  key=self.save()['selectedId'];presets.change({'action':'set-default','id':key})
  presets.change({'action':'set-default','id':''});self.assertEqual(presets.load()['defaultId'],'')
  with self.assertRaises(ValueError):presets.change({'action':'set-default','id':'missing'})
if __name__=='__main__':unittest.main()
