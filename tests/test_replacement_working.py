import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import replacement_stage as stage
import storage_checks
import workflow_store

class ReplacementWorkingFolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'source').mkdir();(self.root/'work').mkdir()
        self.source=self.root/'source/video.mp4';self.temp=self.root/'work/.archiver-test.mp4'
        self.source.write_bytes(b'original'*100);self.temp.write_bytes(b'encoded'*30)
        self.job={'id':'workingtest','source':str(self.source),'output':str(self.source),'source_size':self.source.stat().st_size,'source_mtime_ns':self.source.stat().st_mtime_ns,'temporaryOutput':str(self.temp),'status':'running','settings':{'mode':'overwrite','replacementTempDirectory':str(self.temp.parent)},'log':[]}
    def tearDown(self):self.tmp.cleanup()
    def publish(self):stage.publish(self.temp,self.source,lambda p:p.unlink(),self.job)
    def test_verified_transfer_disposes_backup_only_after_success(self):
        def dispose(backup):
            self.assertEqual(backup.read_bytes(),b'original'*100);self.assertEqual(self.source.read_bytes(),b'encoded'*30);backup.unlink()
        stage.publish(self.temp,self.source,dispose,self.job)
        self.assertFalse(self.temp.exists());self.assertFalse(list(self.temp.parent.glob('.archiver-replacement-*')));self.assertNotIn('replacementRecovery',self.job)
    def test_transfer_failure_restores_original_and_keeps_encoded_and_backup(self):
        original=stage.copy_verified
        def failed(source,target,*args):
            if source==self.temp:raise OSError('injected disconnect')
            return original(source,target,*args)
        with patch.object(stage,'copy_verified',side_effect=failed):
            with self.assertRaisesRegex(OSError,'Recovery files retained'):self.publish()
        self.assertEqual(self.source.read_bytes(),b'original'*100);self.assertTrue(self.temp.exists());self.assertTrue(self.job['replacementRecoveryRequired'])
    def test_another_programs_file_is_not_removed(self):
        original=stage.copy_verified
        def raced(source,target,*args):
            if source==self.temp:self.source.write_bytes(b'external');raise FileExistsError('race')
            return original(source,target,*args)
        with patch.object(stage,'copy_verified',side_effect=raced):
            with self.assertRaises(OSError):self.publish()
        self.assertEqual(self.source.read_bytes(),b'external');self.assertTrue(self.temp.exists())
    def test_backup_failure_keeps_source_intact(self):
        with patch.object(stage,'copy_verified',side_effect=OSError('backup disk full')):
            with self.assertRaises(OSError):self.publish()
        self.assertEqual(self.source.read_bytes(),b'original'*100);self.assertTrue(self.temp.exists())
    def test_insufficient_final_space_fails_before_removing_original(self):
        with patch.object(stage.shutil,'disk_usage',return_value=type('Usage',(),{'free':0})()):
            with self.assertRaisesRegex(OSError,'will not fit'):self.publish()
        self.assertEqual(self.source.read_bytes(),b'original'*100)
    def test_restart_keeps_recovery_artifacts_after_interrupted_transfer(self):
        def crash():
            if self.job.get('replacementRecovery') and json.loads(Path(self.job['replacementRecovery']).read_text())['state']=='transferring':raise SystemExit('crash')
        with self.assertRaises(SystemExit):stage.publish(self.temp,self.source,lambda p:p.unlink(),self.job,crash)
        self.assertFalse(self.source.exists());self.assertTrue(self.temp.exists())
        restored=workflow_store.restored_job(self.job,'test');self.assertEqual(restored['status'],'failed');self.assertTrue(self.temp.exists());self.assertTrue(Path(restored['replacementRecovery']).exists())
        with self.assertRaisesRegex(ValueError,'interrupted replacement'):workflow_store.cleanup_stage(restored)
    def test_storage_checks_use_working_drive(self):
        self.assertEqual(storage_checks.location(self.job),self.temp.parent)
