import io
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import app_updates as updates

def release(tag,prerelease=True):
    name='Archiver-'+tag.removeprefix('v')+'.zip'
    return {'tag_name':tag,'prerelease':prerelease,'assets':[{'name':n,'state':'uploaded','browser_download_url':updates.REPO+'/releases/download/'+tag+'/'+n} for n in (name,name+'.sha256')]}

class UpdateTests(unittest.TestCase):
    def test_install_validates_download_before_restart_and_preserves_current(self):
        for corrupt in (False,True):
            with self.subTest(corrupt=corrupt),tempfile.TemporaryDirectory() as temp:
                base=Path(temp);old=base/'Archiver-0.3.0-rc.15';old.mkdir();exe=old/'Archiver.exe';exe.write_bytes(b'old');(old/'_internal').mkdir();(old/'_internal/VERSION').write_text('0.3.0-rc.15')
                buffer=io.BytesIO()
                with zipfile.ZipFile(buffer,'w') as archive:
                    archive.writestr('Archiver/Archiver.exe',b'new')
                    archive.writestr('Archiver/_internal/VERSION','0.3.0-rc.16')
                data=buffer.getvalue();digest='0'*64 if corrupt else hashlib.sha256(data).hexdigest();shutdown=[]
                def self_test(command,**kwargs):Path(command[-1]).write_text(json.dumps({'ok':True}))
                updates.STATE.update(status='available',release={'version':'0.3.0-rc.16','archive':'archive','checksum':'checksum'})
                with patch.object(updates.sys,'frozen',True,create=True),patch.object(updates.sys,'platform','win32'),patch.object(updates.sys,'executable',str(exe)),patch.object(updates,'fetch',side_effect=lambda url,limit:data if url=='archive' else digest.encode()),patch.object(updates.subprocess,'run',side_effect=self_test),patch.object(updates.subprocess,'Popen') as launch,patch.object(updates.threading,'Thread') as thread:
                    thread.side_effect=lambda **kw:type('Immediate',(),{'start':lambda _:kw['target']()})()
                    updates.install(lambda:shutdown.append(True))
                self.assertEqual(exe.read_bytes(),b'old')
                self.assertEqual(launch.called,not corrupt);self.assertEqual(bool(shutdown),not corrupt)
                self.assertFalse((base/'Archiver-0.3.0-rc.16').exists())
                if not corrupt:
                    transaction=next(base.glob('.archiver-update-*'))
                    self.assertEqual(Path(launch.call_args.args[0][2]),exe)
                    updates.replace_installation(transaction/'Archiver',old,transaction)
                    self.assertEqual(exe.read_bytes(),b'new')
                if corrupt:self.assertIn('checksum',updates.snapshot()['message'])
    def test_numeric_order_and_stable_channels(self):
        releases=[release('v0.3.0-rc.9'),release('v0.3.0-rc.15'),release('v0.3.0',False),release('v0.4.0-rc.1')]
        self.assertEqual(updates.select(releases,'0.3.0-rc.14')['version'],'0.4.0-rc.1')
        self.assertIsNone(updates.select(releases,'0.3.0'))
        self.assertEqual(updates.select(releases[:3],'0.3.0-rc.14')['version'],'0.3.0')
    def test_rejects_drafts_missing_checksums_and_external_urls(self):
        row=release('v0.3.0-rc.16');row['draft']=True
        self.assertIsNone(updates.select([row],'0.3.0-rc.15'))
        row=release('v0.3.0-rc.16');row['assets'].pop()
        self.assertIsNone(updates.select([row],'0.3.0-rc.15'))
        row=release('v0.3.0-rc.16');row['assets'][0]['browser_download_url']='https://example.com/file.zip'
        self.assertIsNone(updates.select([row],'0.3.0-rc.15'))
    def test_archive_rejects_escape_absolute_and_windows_paths(self):
        for path in ('Archiver/../../outside','/outside','Archiver/C:evil','Archiver\\..\\outside','Other/Archiver.exe'):
            with self.subTest(path=path),tempfile.TemporaryDirectory() as temp:
                buffer=io.BytesIO()
                with zipfile.ZipFile(buffer,'w') as archive:archive.writestr(path,b'bad')
                buffer.seek(0)
                with self.assertRaises(ValueError):updates.unpack(buffer,Path(temp))
                self.assertEqual(list(Path(temp).iterdir()),[])
    def test_valid_portable_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w') as archive:
                archive.writestr('Archiver/Archiver.exe',b'fixture')
                archive.writestr('Archiver/_internal/VERSION','0.3.0-rc.16')
            buffer.seek(0)
            self.assertEqual(updates.unpack(buffer,Path(temp)),Path(temp)/'Archiver')
    def test_source_install_does_not_start_installer(self):
        with patch.object(updates.sys,'frozen',False,create=True):
            with self.assertRaisesRegex(ValueError,'packaged Windows'):updates.install(lambda:None)
    def test_failed_check_is_visible_and_retryable(self):
        with patch.object(updates,'fetch',side_effect=OSError('offline')),patch.object(updates.threading,'Thread') as thread:
            thread.side_effect=lambda **kw:type('Immediate',(),{'start':lambda _:kw['target']()})()
            updates.STATE.update(status='idle')
            updates.check('0.3.0-rc.15')
            self.assertEqual(updates.snapshot()['status'],'error')
            self.assertIn('offline',updates.snapshot()['message'])
            updates.check('0.3.0-rc.15')
            self.assertEqual(updates.snapshot()['status'],'error')

    def test_replacement_preserves_user_data_and_rolls_back_each_failed_step(self):
        for fail_at in (None,1,2,3,4,5,6,'validation'):
            with self.subTest(fail_at=fail_at),tempfile.TemporaryDirectory() as temp:
                parent=Path(temp);target=parent/'My Archiver';target.mkdir();transaction=parent/'.archiver-update-fixture';source=transaction/'Archiver';source.mkdir(parents=True)
                for root,value in ((target,'old'),(source,'new')):
                    (root/'Archiver.exe').write_text(value);(root/'_internal').mkdir();(root/'_internal/VERSION').write_text(value);(root/'README.txt').write_text(value)
                (target/'archiver-tools.json').write_text('saved paths');(target/'dependencies').mkdir();(target/'dependencies/ffmpeg.exe').write_text('external tool');(target/'custom-file.txt').write_text('user data')
                original=Path.rename;calls=[]
                def rename(path,dest):
                    calls.append(str(path))
                    if len(calls)==fail_at:raise PermissionError('injected locked file')
                    return original(path,dest)
                with patch.object(Path,'rename',rename):
                    if fail_at:
                        with self.assertRaisesRegex(PermissionError,'locked file'):
                            def validate():
                                if fail_at=='validation':raise PermissionError('injected locked file during runtime validation')
                            updates.replace_installation(source,target,transaction,validate)
                    else:updates.replace_installation(source,target,transaction)
                expected='old' if fail_at else 'new'
                for name in ('Archiver.exe','_internal/VERSION','README.txt'):self.assertEqual((target/name).read_text(),expected)
                self.assertEqual((target/'archiver-tools.json').read_text(),'saved paths');self.assertEqual((target/'dependencies/ffmpeg.exe').read_text(),'external tool');self.assertEqual((target/'custom-file.txt').read_text(),'user data')
