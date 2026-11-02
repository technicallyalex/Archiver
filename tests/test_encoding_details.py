import unittest
from unittest.mock import patch
from pathlib import Path
import app


class EncodingDetailsTests(unittest.TestCase):
    def setUp(self):
        self.item={'id':'one','name':'Clip.mp4','path':'Clip.mp4','codec':'h264','width':1920,'height':1080,'fps':30,'duration':60,'video_bitrate':8000000,'source_quality':20,'rate_mode':'crf','pixel_format':'yuv420p'}
        self.settings={'codec':'h264','encoder':'libx264','qualityMode':'custom','bitrate':'auto','container':'mp4','audio':'aac','resolution':'original','fps':'original','encoderPriority':'balanced'}

    def test_recorded_quality_and_bitrate_fallback_are_distinct_and_read_only(self):
        other={**self.item,'name':'Other.mp4','path':'Other.mp4','source_quality':None,'rate_mode':''}
        with patch.dict(app.STATE,encoders=['libx264']),patch.object(app,'probe',side_effect=AssertionError('Details must not probe files')):
            result=app.encoding_details([self.item,other],self.settings)
            a,b=result['files']
            self.assertEqual((a['control'],a['value'],a['provenance']),('CRF','20','Recorded CRF'))
            self.assertEqual((b['control'],b['value'],b['provenance']),('Target bitrate','8 Mbps','Reported average video bitrate'))
            self.assertEqual(a['preset'],'medium')
            self.assertEqual(a['command'],app.command_for(Path('Clip.mp4'),Path('OUTPUT.mp4'),{**self.settings,'sourceMetadata':self.item}))

    def test_estimate_is_labeled_as_estimate_and_auto_requires_applied_result(self):
        with patch.dict(app.STATE,encoders=['libx264']):
            settings={**self.settings,'qualityMode':'source','sourcePreset':'75','sourceCodec':'h264','encodingMode':'software','priority':'balanced'}
            row=app.encoding_details([self.item],settings)['files'][0]
            self.assertEqual(row['provenance'],'Adjusted bitrate estimate')
            self.assertEqual(row['value'],'6 Mbps')
            self.assertTrue(app.encoding_details([self.item],{**settings,'qualityMode':'auto'})['files'][0]['pending'])

    def test_icq_range_matches_lookahead_mode(self):
        settings={**self.settings,'encoder':'h264_qsv','encodingMode':'hardware','hardwareBackend':'qsv','abCodec':'h264','autoEngine':'ab-av1','bitrate':'icq','testedEncoder':'h264_qsv','qualityValue':1,'sourceMetadata':self.item}
        with patch.dict(app.STATE,encoders=['h264_qsv']):
            row=app.encoding_details([self.item],settings)['files'][0]
            self.assertEqual(row['control'],'ICQ');self.assertTrue(row['lookahead'])
            for invalid in (0,52):
                with self.assertRaisesRegex(ValueError,'ICQ must be between 1 and 51'):
                    app.command_for(Path('Clip.mp4'),Path('OUTPUT.mp4'),{**settings,'qualityValue':invalid})
