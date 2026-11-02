import unittest,tempfile,io,json,hashlib
from pathlib import Path
from unittest.mock import patch
import app,dependency_setup

class ToolInstallTests(unittest.TestCase):
 def setUp(self):
  self.old=dict(app.TOOL_SETUP)
  app.TOOL_SETUP.update(running=False,status='idle',revision=0,message='')
 def tearDown(self):
  app.TOOL_SETUP.clear();app.TOOL_SETUP.update(self.old)
 def test_reuses_working_tools_and_saves_paths(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);paths={k:str(root/k) for k in ('ffmpeg','ffprobe')}
   for p in paths.values():Path(p).touch()
   with patch.dict(app.STATE,{**paths,'tools_verified':True,'xpsnr':True,'vmafmotion':True,'ffv1':True,'encoders':['libx264']}),patch.object(app.ab_av1,'installation',return_value={'available':True}),patch.object(app.dependency_setup,'setup') as setup,patch.object(app,'configure') as configure,patch.object(app.tool_config,'save_paths') as save:
    app.install_video_tools();setup.assert_not_called();configure.assert_called_once_with(paths['ffmpeg'],paths['ffprobe']);save.assert_called_once();self.assertEqual(app.TOOL_SETUP['status'],'success')
 def test_download_failure_is_reported_and_retry_allowed(self):
  with patch.dict(app.STATE,{'tools_verified':False}),patch.object(app.dependency_setup,'setup',side_effect=ValueError('Download failed')):
   app.install_video_tools();self.assertFalse(app.TOOL_SETUP['running']);self.assertEqual(app.TOOL_SETUP['status'],'error');self.assertEqual(app.TOOL_SETUP['message'],'Download failed')
 def test_running_setup_and_active_jobs_are_rejected(self):
  app.TOOL_SETUP['running']=True
  with self.assertRaisesRegex(ValueError,'already running'):app.start_tool_setup()
  app.TOOL_SETUP['running']=False
  with patch.object(app,'tools_busy',return_value=True),self.assertRaisesRegex(ValueError,'Wait for'):app.start_tool_setup()
 def test_ab_restore_checks_digest_before_replacing(self):
  with tempfile.TemporaryDirectory() as tmp:
   target=Path(tmp)/'ab-av1.exe';target.write_bytes(b'original')
   release={'assets':[{'name':'ab-av1.exe','digest':'sha256:'+'0'*64,'browser_download_url':'asset'}]}
   with patch.object(dependency_setup,'request',return_value=io.BytesIO(json.dumps(release).encode())),patch.object(dependency_setup,'download',side_effect=lambda url,path,progress:path.write_bytes(b'bad')),self.assertRaisesRegex(ValueError,'checksum mismatch'):
    dependency_setup.restore_ab_av1(target,lambda _:None)
   self.assertEqual(target.read_bytes(),b'original')
 def test_ab_restore_verifies_and_installs(self):
  with tempfile.TemporaryDirectory() as tmp:
   target=Path(tmp)/'ab-av1.exe';payload=b'new binary'
   release={'assets':[{'name':'ab-av1.exe','digest':'sha256:'+hashlib.sha256(payload).hexdigest(),'browser_download_url':'asset'}]}
   with patch.object(dependency_setup,'request',return_value=io.BytesIO(json.dumps(release).encode())),patch.object(dependency_setup,'download',side_effect=lambda url,path,progress:path.write_bytes(payload)),patch.object(app.ab_av1,'_installation',return_value={'available':True}):dependency_setup.restore_ab_av1(target,lambda _:None)
   self.assertEqual(target.read_bytes(),payload)
