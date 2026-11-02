import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import comparison

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class ExactComparisonTests(unittest.TestCase):
 def test_finished_sample_uses_stream_copy_with_identical_decoded_frames(self):
  ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);source=root/'source.mp4';encoded=root/'encoded.mkv'
   subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','testsrc2=size=128x96:rate=24:duration=2','-c:v','libx264',str(source)],capture_output=True,check=True)
   subprocess.run([ffmpeg,'-v','error','-i',str(source),'-c:v','libx264','-crf','25',str(encoded)],capture_output=True,check=True)
   row={'start':0.,'duration':2.,'reference':str(source),'encoded':str(encoded),'passed':True}
   job={'id':'exact-'+str(time.time_ns()),'status':'running','source':str(source),'outputDirectory':str(root),'progress':{'comparisonClips':[row]}}
   held=threading.Lock();held.acquire()
   try:
    key=comparison.prepare(job,0,ffmpeg,ffprobe,held,lambda:False,None)
    deadline=time.monotonic()+10
    while comparison.public()[key]['status'] in ('waiting','running') and time.monotonic()<deadline:time.sleep(.02)
    info=comparison.public()[key];self.assertEqual(info['status'],'ready',info)
    self.assertFalse(info['reencoded']);self.assertEqual(comparison.media(key,'source'),source)
    self.assertEqual(comparison.media(key,'reference'),source)
    def hashes(path):
     result=subprocess.run([ffmpeg,'-v','error','-i',str(path),'-map','0:v:0','-an','-f','framemd5','-'],capture_output=True,text=True,check=True)
     return [line.rsplit(',',1)[-1].strip() for line in result.stdout.splitlines() if line and not line.startswith('#')]
    self.assertEqual(hashes(encoded),hashes(comparison.media(key,'output')))
   finally:held.release()
 def test_unfinished_or_outside_measured_pair_is_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);source=root/'source';source.write_bytes(b'x');outside=root.parent/'outside-does-not-exist.mkv'
   job={'id':'invalid','status':'queued','source':str(source),'outputDirectory':str(root),'progress':{'comparisonClips':[{'reference':str(source),'encoded':str(outside)}]}}
   with self.assertRaises(ValueError):comparison.prepare(job,0,'ffmpeg','ffprobe',threading.Lock(),lambda:False,None)
   job['status']='running'
   with self.assertRaisesRegex(ValueError,'Exact measured clips'):comparison.prepare(job,0,'ffmpeg','ffprobe',threading.Lock(),lambda:False,None)

 def test_source_mime_matches_original_container(self):
  with patch.dict(comparison.JOBS,{'mime-check':{'sourceMime':'video/x-matroska; codecs="avc1"'}}):
   self.assertEqual(comparison.mime('mime-check','source'),'video/x-matroska')
   self.assertEqual(comparison.mime('mime-check','output'),'video/mp4')
