from pathlib import Path
import json,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
import app,folder_history

class FolderHistoryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.path=self.root/'settings'/'history.json';self.mock=patch.object(folder_history,'history_path',return_value=self.path);self.mock.start()
  self.a=self.root/'a';self.b=self.root/'b';self.c=self.root/'c'
  for p in [self.a,self.b,self.c]:p.mkdir()
 def tearDown(self):self.mock.stop();self.temp.cleanup()
 def test_contexts_persist_and_explicit_paths_take_priority(self):
  folder_history.remember(self.a,'source');folder_history.remember(self.b,'destination')
  self.assertEqual(folder_history.initial_folder(kind='source'),self.a)
  self.assertEqual(folder_history.initial_folder(kind='destination',fallback=str(self.c)),self.b)
  self.assertEqual(folder_history.initial_folder(str(self.c),'source'),self.c)
  self.assertEqual(json.loads(self.path.read_text())['source'],str(self.a))
 def test_missing_and_corrupt_history_fall_back(self):
  folder_history.remember(self.a,'source');self.a.rmdir()
  self.assertEqual(folder_history.initial_folder(kind='source',fallback=str(self.c)),self.c)
  self.path.write_text('invalid json');self.assertEqual(folder_history.initial_folder(kind='source',fallback=str(self.b)),self.b)
 def test_cancel_does_not_replace_history(self):
  folder_history.remember(self.a,'source');before=self.path.read_bytes()
  with patch.object(app.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"directory":""}')) as run:
   self.assertEqual(app.browse_directory(kind='source'),'')
   self.assertEqual(run.call_args.args[0][-1],str(self.a))
  self.assertEqual(before,self.path.read_bytes())
 def test_success_updates_only_context_and_write_failure_is_nonfatal(self):
  folder_history.remember(self.a,'source')
  with patch.object(app.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps({'directory':str(self.b)}))):
   self.assertEqual(app.browse_directory(kind='destination'),str(self.b))
  self.assertEqual(folder_history.initial_folder(kind='source'),self.a)
  with patch.object(folder_history.os,'replace',side_effect=PermissionError):folder_history.remember(self.c,'source')
  self.assertEqual(folder_history.initial_folder(kind='source'),self.a)
