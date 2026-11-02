import tempfile,unittest,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import app
class QueueThumbnailTests(unittest.TestCase):
 def test_thumbnail_uses_job_after_pool_is_cleared_and_output_after_move(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);source=root/'source.mp4';output=root/'output.mp4';source.touch()
   job=dict(id='queue1',source=str(source),output=str(output),duration=3,settings={'sourceMetadata':{'id':'media1'}})
   handler=object.__new__(app.Handler);handler.path='/api/thumbnail?job=queue1';handler.server=SimpleNamespace(server_port=9999);handler.headers={'X-Token':app.TOKEN,'Host':'127.0.0.1:9999'};responses=[];handler.send=lambda *a,**k:responses.append((a,k))
   def run(command,*a,**k):Path(command[-1]).write_bytes(b'jpeg');return subprocess.CompletedProcess(command,0)
   with patch.dict(app.STATE,files={},jobs=[job]),patch.object(app,'CACHE',SimpleNamespace(name=directory)),patch.object(app,'run',side_effect=run) as launch:
    handler.do_GET();self.assertEqual(responses[-1][0][0],b'jpeg');self.assertEqual(launch.call_args.args[0][launch.call_args.args[0].index('-i')+1],str(source))
    (root/'media1-0.jpg').unlink();source.unlink();output.touch();handler.do_GET();self.assertEqual(launch.call_args.args[0][launch.call_args.args[0].index('-i')+1],str(output))
    handler.path='/api/thumbnail?job=unknown';handler.do_GET();self.assertEqual(responses[-1][0][1],404)

