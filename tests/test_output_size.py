import unittest
from unittest.mock import patch
import app
class OutputSizeTests(unittest.TestCase):
 def setUp(self):
  self.item=dict(id='a',path='a.mp4',name='a.mp4',size=110000000,duration=100,video_bitrate=8000000,codec='h264',width=3840,height=2160,fps=60,pixel_format='yuv420p',color_transfer='bt709',audio='aac',audio_streams=[dict(bitrate=800000,sample_rate=48000,channels=2)])
  self.settings=dict(qualityMode='custom',bitrate='custom',customBitrate=4,codec='h264',encoder='libx264',audio='copy')
 def test_target_rate_audio_and_reduction(self):
  r=app.output_size_estimate([self.item],self.settings)
  self.assertEqual(r['bytes'],60000000);self.assertAlmostEqual(r['reduction'],1-60/110)
  r=app.output_size_estimate([self.item],{**self.settings,'audio':'aac','audioBitrate':'192k'})
  self.assertEqual(r['bytes'],52400000)
 def test_estimate_applies_resolution_fps_and_all_selected(self):
  settings={**self.settings,'qualityMode':'source','sourcePreset':'100','sourceCodec':'h264','encodingMode':'software','resolution':'1080','fps':'30'}
  with patch.dict(app.STATE,encoders=['libx264']):r=app.output_size_estimate([self.item,{**self.item,'id':'b'}],settings)
  self.assertEqual(r['bytes'],45000000);self.assertEqual(r['count'],2)
 def test_unknown_quality_and_partial_total_are_unavailable(self):
  r=app.output_size_estimate([self.item],{**self.settings,'bitrate':'crf','qualityValue':22})
  self.assertIsNone(r['bytes'])
  r=app.output_size_estimate([self.item,{**self.item,'duration':0}],self.settings)
  self.assertIsNone(r['bytes']);self.assertEqual(r['estimatedCount'],1)
 def test_copy_increase_and_matched_test(self):
  self.assertEqual(app.output_size_estimate([self.item],{**self.settings,'mode':'copy'})['bytes'],self.item['size'])
  self.assertLess(app.output_size_estimate([self.item],{**self.settings,'customBitrate':20})['reduction'],0)
  report=dict(id='t',source=self.item['path'],status='completed',result={'winner':dict(encoder='libx264',qualityValue=22,bytesPerSecond=250000)})
  settings={**self.settings,'bitrate':'crf','qualityValue':'22','testedEncoder':'libx264'}
  self.assertEqual(app.output_size_estimate([self.item],settings,[report])['bytes'],35000000)
  self.assertIsNone(app.output_size_estimate([{**self.item,'path':'other.mp4'}],settings,[report])['bytes'])
 def test_prores_includes_pcm_and_missing_metadata_is_unavailable(self):
  r=app.output_size_estimate([self.item],{'qualityMode':'archive','archiveProfile':'prores'})
  self.assertGreater(r['bytes'],110000000)
  r=app.output_size_estimate([{**self.item,'audio_streams':[]}],{'qualityMode':'archive','archiveProfile':'prores'})
  self.assertIsNone(r['bytes'])

 def test_full_range_estimate_ignores_stale_quality_controls(self):
  item={**self.item,'pixel_format':'yuvj420p'}
  settings={**self.settings,'qualityMode':'source','sourcePreset':'100','sourceCodec':'h264','encodingMode':'software','resolution':'1080','fps':'30','bitrate':'crf','qualityValue':22}
  with patch.dict(app.STATE,encoders=['libx264']):
   r=app.output_size_estimate([item],settings)
   resolved=app.source_preset(item,settings)
   from pathlib import Path
   cmd=app.command_for(Path('input.mp4'),Path('output.mp4'),{**resolved,'sourceMetadata':item})
  self.assertEqual(r['bytes'],22500000);self.assertEqual(r['issues'],[])
  self.assertEqual(cmd[cmd.index('-b:v')+1],'1000k')
  self.assertNotIn('-crf',cmd)
  self.assertIn('in_range=pc:out_range=tv',cmd[cmd.index('-vf')+1])
  self.assertEqual(cmd[cmd.index('-color_range')+1],'tv')

 def test_missing_bitrate_and_unsupported_format_have_specific_reasons(self):
  settings={**self.settings,'qualityMode':'source','sourcePreset':'100','sourceCodec':'h264','encodingMode':'software'}
  with patch.dict(app.STATE,encoders=['libx264']):
   missing=app.output_size_estimate([{**self.item,'video_bitrate':0}],settings)
   hdr=app.output_size_estimate([{**self.item,'color_transfer':'smpte2084'}],settings)
  self.assertEqual(missing['reasonCode'],'missing_video_bitrate');self.assertEqual(hdr['reasonCode'],'source_format')
  self.assertIsNone(missing['bytes']);self.assertIsNone(missing['partialBytes'])
  self.assertNotIn('Automated (Test)',hdr['reason'])

 def test_partial_budget_is_distinguished_from_complete_total(self):
  settings={**self.settings,'qualityMode':'source','sourcePreset':'100','sourceCodec':'h264','encodingMode':'software'}
  missing={**self.item,'id':'missing','name':'Missing.mp4','video_bitrate':0}
  with patch.dict(app.STATE,encoders=['libx264']):r=app.output_size_estimate([self.item,missing],settings)
  self.assertIsNone(r['bytes']);self.assertEqual(r['partialBytes'],110000000)
  self.assertEqual((r['estimatedCount'],r['count']),(1,2))
  self.assertEqual(r['issues'][0]['id'],'missing')
