from pathlib import Path
import json,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
import app

class FrozenFolderPickerTests(unittest.TestCase):
 def test_frozen_picker_uses_result_file_and_cleans_it(self):
  with tempfile.TemporaryDirectory() as tmp:
   reports=[]
   def run(command,**kwargs):
    self.assertEqual(command[1],'--pick-folder');self.assertEqual(command[2],tmp)
    report=Path(command[3]);reports.append(report);report.write_text(json.dumps({'directory':tmp}))
    return SimpleNamespace(returncode=0,stdout='')
   with patch.object(app.sys,'frozen',True,create=True),patch.object(app.subprocess,'run',side_effect=run):
    self.assertEqual(app.browse_directory(tmp),tmp)
   self.assertFalse(reports[0].exists());self.assertFalse(app.BROWSE_LOCK.locked())
 def test_frozen_picker_failure_releases_lock_and_removes_report(self):
  with tempfile.TemporaryDirectory() as tmp:
   reports=[]
   def run(command,**kwargs):reports.append(Path(command[3]));return SimpleNamespace(returncode=1,stdout='')
   with patch.object(app.sys,'frozen',True,create=True),patch.object(app.subprocess,'run',side_effect=run):
    with self.assertRaisesRegex(ValueError,'Could not open'):app.browse_directory(tmp)
   self.assertFalse(reports[0].exists());self.assertFalse(app.BROWSE_LOCK.locked())
