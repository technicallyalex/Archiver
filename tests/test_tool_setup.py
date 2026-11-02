import io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import tool_config,dependency_setup
class ToolSetupTests(unittest.TestCase):
 def test_portable_paths_survive_copy_and_shared_fallback(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);base=root/'app';base.mkdir();shared=root/'shared.json'
   paths={name:str(base/(name+'.exe')) for name in ('ffmpeg','ffprobe')}
   for path in paths.values():Path(path).touch()
   with patch.object(tool_config,'user_config',return_value=shared):
    tool_config.save_paths(base,paths);self.assertEqual(tool_config.load_paths(base),paths)
    self.assertFalse(Path(json.loads((base/'archiver-tools.json').read_text())['ffmpeg']).is_absolute())
    other=root/'other';other.mkdir()
    self.assertEqual(tool_config.load_paths(other),paths)
    for name in ('ffmpeg','ffprobe'):(other/(name+'.exe')).touch()
    (other/'archiver-tools.json').write_text((base/'archiver-tools.json').read_text())
    self.assertEqual(tool_config.load_paths(other)['ffmpeg'],str(other/'ffmpeg.exe'))
 def test_missing_or_corrupt_config_falls_back(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'archiver-tools.json').write_text('{bad')
   with patch.object(tool_config,'user_config',return_value=root/'missing'),patch.object(tool_config.shutil,'which',side_effect=lambda name:'PATH/'+name):self.assertEqual(tool_config.load_paths(root)['ffmpeg'],'PATH/ffmpeg')
 def test_archive_traversal_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);archive=root/'unsafe.zip'
   with zipfile.ZipFile(archive,'w') as package:package.writestr('../outside.txt','bad')
   with self.assertRaisesRegex(ValueError,'unsafe'):dependency_setup.extract(archive,root/'extract')
   self.assertFalse((root/'outside.txt').exists())
 def test_existing_local_tools_do_not_download(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for name in ('ffmpeg','ffprobe'):(root/(name+'.exe')).touch()
   tool_config.save_paths(root,{name:str(root/(name+'.exe')) for name in ('ffmpeg','ffprobe')},shared=False)
   with patch.object(dependency_setup,'validate'),patch.object(dependency_setup,'request',side_effect=AssertionError('unnecessary download')):
    paths=dependency_setup.setup(root,progress=lambda _:None,shared=False)
    self.assertEqual(paths['ffmpeg'],str(root/'ffmpeg.exe'))
 def test_checksum_failure_retains_previous_configuration(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);config=root/'archiver-tools.json';config.write_text('{"previous":"kept"}')
   assets=[dict(name=dependency_setup.ASSET,browser_download_url='archive'),dict(name='checksums.sha256',browser_download_url='checksums')]
   def request(url):return io.BytesIO(json.dumps({'assets':assets}).encode() if url==dependency_setup.RELEASE_API else ('0'*64+'  '+dependency_setup.ASSET+'\n').encode())
   def download(url,target,progress):target.write_bytes(b'wrong download')
   with patch.object(dependency_setup,'request',side_effect=request),patch.object(dependency_setup,'download',side_effect=download),self.assertRaisesRegex(ValueError,'Checksum mismatch'):dependency_setup.setup(root,progress=lambda _:None,shared=False)
   self.assertEqual(config.read_text(),'{"previous":"kept"}');self.assertFalse(list((root/'dependencies').iterdir()))
