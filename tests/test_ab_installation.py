from pathlib import Path
import tempfile,unittest,subprocess
from unittest.mock import patch
import ab_av1
class InstallationTests(unittest.TestCase):
 def setUp(self):ab_av1._installation.cache_clear()
 def tearDown(self):ab_av1._installation.cache_clear()
 def test_missing_binary_does_not_spawn(self):
  with patch.object(ab_av1,'binary',return_value=None),patch.object(ab_av1.subprocess,'run') as run:
   self.assertFalse(ab_av1.installation()['available']);run.assert_not_called()
 def test_version_is_cached_and_recheck_or_file_change_revalidates(self):
  with tempfile.TemporaryDirectory() as tmp:
   executable=Path(tmp)/'ab-av1.exe';executable.write_bytes(b'binary')
   with patch.object(ab_av1,'binary',return_value=str(executable)),patch.object(ab_av1,'BINARY',executable),patch.object(ab_av1.subprocess,'run',side_effect=lambda command,**kwargs:subprocess.CompletedProcess([],0,'ab-av1 0.11.7\n' if '--version' in command else '--min-xpsnr --stdout-format','')) as run:
    first=ab_av1.installation();self.assertTrue(first['available']);self.assertTrue(first['bundled']);self.assertEqual(first['version'],'ab-av1 0.11.7')
    first['version']='mutated';self.assertEqual(ab_av1.installation()['version'],'ab-av1 0.11.7');self.assertEqual(run.call_count,2)
    ab_av1.installation(recheck=True);self.assertEqual(run.call_count,4)
    executable.write_bytes(b'changed binary');ab_av1.installation();self.assertEqual(run.call_count,6)
 def test_missing_xpsnr_search_capability_is_unavailable(self):
  with tempfile.TemporaryDirectory() as tmp:
   executable=Path(tmp)/'tool';executable.write_bytes(b'x')
   with patch.object(ab_av1,'binary',return_value=str(executable)),patch.object(ab_av1.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0,'ab-av1 0.11.7',''),subprocess.CompletedProcess([],0,'--min-vmaf','')]):
    info=ab_av1.installation();self.assertFalse(info['available']);self.assertIn('XPSNR',info['error'])
 def test_invalid_or_unlaunchable_executable_is_reported(self):
  with tempfile.TemporaryDirectory() as tmp:
   executable=Path(tmp)/'tool';executable.write_bytes(b'x')
   for result in [subprocess.CompletedProcess([],0,'unrelated tool',''),OSError('cannot launch'),subprocess.TimeoutExpired('tool',5)]:
    with patch.object(ab_av1,'binary',return_value=str(executable)),patch.object(ab_av1.subprocess,'run',**({'side_effect':result} if isinstance(result,Exception) else {'return_value':result})):
     info=ab_av1.installation(recheck=True);self.assertFalse(info['available']);self.assertTrue(info['error'])
if __name__=='__main__':unittest.main()
