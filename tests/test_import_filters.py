from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
import app,import_filters

class ImportFilterTests(unittest.TestCase):
 def test_folder_name_validation(self):
  self.assertEqual(import_filters.folder_names(),{'proxy','proxies','proxy media','final cut proxy media'})
  self.assertEqual(import_filters.folder_names([' Low Res ','PROXY']),{'low res','proxy'})
  self.assertEqual(import_filters.folder_names([]),set())
  for value in ['Proxy',['../Proxy'],['a/b'],['a\\b'],['*proxy*'],['..'],[''],[None]]:
   with self.subTest(value=value),self.assertRaises(ValueError):import_filters.folder_names(value)
 def test_recursive_folder_and_ancestor_filters(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   names=['clip.mp4','clip.mov','pRoXy/clip.mp4','Proxies/nested/other.mp4','Low Res/clip.mov','Proxy Footage/unique.mp4','A/scene.mp4','A/small/SCENE.mov','B/scene.mp4','other/CLIP.mkv']
   for name in names:
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'unchanged')
   def probe(path,**kwargs):return {'id':str(path.relative_to(root)),'path':str(path)}
   with patch.dict(app.STATE,files={},scan={'running':True,'done':0,'total':0,'errors':[]}),patch.object(app,'probe',side_effect=probe):
    app.SCAN_STOP.clear();app.scan(str(root),True,workers=4,excluded_folders=['Proxy','Proxies','Low Res'],skip_parent_copies=True)
    found={Path(f['path']).relative_to(root).as_posix() for f in app.STATE['files'].values()}
    self.assertEqual(found,{'clip.mp4','clip.mov','Proxy Footage/unique.mp4','A/scene.mp4','A/small/SCENE.mov','B/scene.mp4','other/CLIP.mkv'})
    self.assertEqual(app.STATE['scan']['excludedFolders'],3)
    self.assertNotIn('duplicateFiles',app.STATE['scan'])
    self.assertEqual(app.STATE['scan']['errors'],[])
   self.assertTrue(all((root/n).read_bytes()==b'unchanged' for n in names))
 def test_explicit_root_and_same_folder_variants_preserved(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'Proxies';root.mkdir()
   for name in ['clip.mp4','clip.mov']:(root/name).write_bytes(b'media')
   with patch.dict(app.STATE,files={},scan={'running':True,'done':0,'total':0,'errors':[]}),patch.object(app,'probe',side_effect=lambda path,**kwargs:{'id':path.name}):
    app.SCAN_STOP.clear();app.scan(str(root),True,skip_parent_copies=True)
    self.assertEqual(set(app.STATE['files']),{'clip.mp4','clip.mov'})
 def test_legacy_duplicate_rule_is_ignored(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'small').mkdir()
   (root/'clip.mp4').touch();(root/'small'/'clip.mov').touch()
   with patch.dict(app.STATE,files={},scan={'running':True,'done':0,'total':0,'errors':[]}),patch.object(app,'probe',side_effect=lambda path,**kwargs:{'id':str(path)}):
    app.SCAN_STOP.clear();app.scan(str(root),True,skip_parent_copies=True)
    self.assertEqual(len(app.STATE['files']),2)

 def test_archiver_folders_default_excluded_and_can_be_included(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);folder=root/'ARCHIVER-TEST-older-run';folder.mkdir()
   (folder/'sample.mp4').touch();(root/'original.mp4').touch()
   with patch.dict(app.STATE,files={},scan={'running':True,'done':0,'total':0,'errors':[]}),patch.object(app,'probe',side_effect=lambda path,**kwargs:{'id':str(path)}):
    app.SCAN_STOP.clear();app.scan(str(root),True)
    self.assertEqual(len(app.STATE['files']),1);self.assertEqual(app.STATE['scan']['excludedFolders'],1)
    app.STATE['scan'].update(done=0,total=0,errors=[])
    app.scan(str(root),True,exclude_test_folders=False)
    self.assertEqual(len(app.STATE['files']),2)

 def test_deleted_test_folders_and_system_storage_are_not_imported(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   names=['original.mp4','$RECYCLE.BIN/user/$Renamed/thumbnails/sample-0-source-timing.mp4','System Volume Information/hidden.mp4','normal/clip.mp4','Archiver-test-live/sample.mp4']
   for name in names:
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'unchanged')
   with patch.dict(app.STATE,files={},scan={'running':True,'done':0,'total':0,'errors':[]}),patch.object(app,'probe',side_effect=lambda path,**kwargs:{'id':str(path),'path':str(path)}):
    app.SCAN_STOP.clear();app.scan(str(root),True)
    self.assertEqual({Path(f['path']).relative_to(root).as_posix() for f in app.STATE['files'].values()},{'original.mp4','normal/clip.mp4'})
    self.assertEqual(app.STATE['scan']['excludedFolders'],3)
    app.scan(str(root),True,excluded_folders=[],exclude_test_folders=False)
    self.assertEqual({Path(f['path']).relative_to(root).as_posix() for f in app.STATE['files'].values()},{'original.mp4','normal/clip.mp4','Archiver-test-live/sample.mp4'})
   self.assertTrue(all((root/name).read_bytes()==b'unchanged' for name in names))
   self.assertTrue(import_filters.is_system_folder('$recycle.bin'))
   self.assertTrue(import_filters.is_system_folder('SYSTEM VOLUME INFORMATION'))

 def test_editor_proxy_layouts_preserve_originals(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   proxies=['Resolve/Proxy/nested/clip.mov','Premiere/Proxies/clip.mp4','Library.fcpbundle/Event/Transcoded Media/Proxy Media/clip.mov','External/Final Cut Proxy Media/2026-11-01/clip.mov']
   originals=['Original Media/clip.mov','Final Cut Original Media/clip.mov','Transcoded Media/High Quality Media/clip.mov','Proxy Footage/clip.mov']
   for name in proxies+originals:
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'unchanged')
   with patch.dict(app.STATE,files={},scan={'running':True,'done':0,'total':0,'errors':[]}),patch.object(app,'probe',side_effect=lambda path,**kwargs:{'id':str(path),'path':str(path)}):
    app.SCAN_STOP.clear();app.scan(str(root),True)
    self.assertEqual({Path(f['path']).relative_to(root).as_posix() for f in app.STATE['files'].values()},set(originals))
    app.scan(str(root),True,excluded_folders=[])
    self.assertEqual(len(app.STATE['files']),8)
   self.assertTrue(all((root/name).read_bytes()==b'unchanged' for name in proxies+originals))
