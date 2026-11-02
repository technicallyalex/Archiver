import unittest
from unittest.mock import patch,Mock
import sample_preview
import motion_selection

class PreviewPriorityTests(unittest.TestCase):
 def test_failed_hardware_falls_back(self):
  with patch.object(sample_preview,'_FAILED_HARDWARE',set()),patch.object(sample_preview,'_create',side_effect=[ValueError('driver unavailable'),None]) as create:
   self.assertEqual(sample_preview.create('ffmpeg','in','out',0,1,lambda:False,['h264_nvenc']),'libx264')
   self.assertEqual([c.args[-1] for c in create.call_args_list],['h264_nvenc','libx264'])
 def test_cancel_does_not_retry(self):
  with patch.object(sample_preview,'_FAILED_HARDWARE',set()),patch.object(sample_preview,'_create',side_effect=InterruptedError) as create:
   with self.assertRaises(InterruptedError):sample_preview.create('ffmpeg','in','out',0,1,lambda:False,['h264_nvenc'])
   self.assertEqual(create.call_count,1)
 def test_selected_previews_precede_reference_encoding(self):
  import tempfile
  order=[]
  analyzer=Mock(ffmpeg='ffmpeg',ffprobe='ffprobe')
  def run(args,**kwargs):
   order.append('reference' if args[0]=='ffmpeg' else 'probe')
   return '{"format":{"duration":24}}'
  analyzer.run.side_effect=run
  with tempfile.TemporaryDirectory() as tmp,patch.object(motion_selection.motion,'measure',return_value={'start':0,'mean':1}),patch.object(motion_selection,'select',return_value=[{'start':0,'duration':8}]):
   motion_selection.prepare(analyzer,{'path':'source','duration':100},tmp,lambda _:None,lambda _:None,previews=lambda _:order.append('previews'))
  self.assertLess(order.index('previews'),order.index('reference'))
