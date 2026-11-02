from pathlib import Path
import tempfile,threading,unittest
from unittest.mock import patch
import app

class ImportConcurrencyTests(unittest.TestCase):
 def test_parallel_default_and_serial_override(self):
  self.assertEqual(app.import_workers({}),16)
  self.assertEqual(app.import_workers({'parallel':True}),16)
  self.assertEqual(app.import_workers({'workers':'auto'}),16)
  self.assertEqual(app.import_workers({'parallel':False,'workers':16}),1)
  for workers in [4,8,16]:self.assertEqual(app.import_workers({'workers':workers}),workers)
  for workers in [True,0,1,32,'16',None,8.5]:
   with self.subTest(workers=workers),self.assertRaises(ValueError):app.import_workers({'workers':workers})
 def test_sixteen_workers_complete_without_metadata_loss(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for i in range(32):(root/f'{i}.mp4').write_bytes(b'media')
   barrier=threading.Barrier(16);lock=threading.Lock();active=0;peak=0
   def probe(path,**kwargs):
    nonlocal active,peak
    with lock:active+=1;peak=max(peak,active)
    try:
     barrier.wait(timeout=5)
     return {'id':path.name,'name':path.name}
    finally:
     with lock:active-=1
   with patch.dict(app.STATE,files={},scan={'running':True,'done':0,'total':0,'errors':[]}),patch.object(app,'probe',side_effect=probe):
    app.SCAN_STOP.clear();app.scan(str(root),False,workers=16)
    self.assertEqual(peak,16);self.assertEqual(len(app.STATE['files']),32)
    self.assertEqual(app.STATE['scan']['done'],32);self.assertEqual(app.STATE['scan']['errors'],[])
