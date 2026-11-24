import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
import app
import import_metadata
import metadata_cache
from quality import validate_source
from test_metadata_import import item

class UnreadableVideoTests(unittest.TestCase):
    def test_unknown_format_is_not_reported_as_unsupported_color(self):
        with self.assertRaisesRegex(ValueError,'could not determine') as error:validate_source({'pixel_format':'','color_transfer':'bt709'})
        self.assertNotIn('supports 8-bit',str(error.exception))
    def test_actual_unsupported_format_keeps_format_error(self):
        with self.assertRaisesRegex(ValueError,'supports 8-bit'):validate_source({'pixel_format':'yuv420p10le','color_transfer':'bt709'})
    def test_header_only_video_track_is_rejected_before_import(self):
        data={'streams':[{'codec_type':'video','codec_name':'h264','width':1920,'height':1080,'avg_frame_rate':'0/0','r_frame_rate':'59940/1','color_transfer':'bt709','duration':'33953.1'}],'format':{'duration':'33953.1'}}
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'clip.mp4';source.write_bytes(b'placeholder')
            with patch.object(app,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(data),'')):
                with self.assertRaisesRegex(ValueError,'video index may be incomplete or damaged'):app.probe(source)
    def test_incomplete_legacy_cache_is_reprobed_instead_of_reused(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'clip.mp4';source.write_bytes(b'placeholder');cache=metadata_cache.Cache(Path(d)/'metadata.sqlite');incomplete=item();incomplete['pixel_format']=''
            cache.put(source,metadata_cache.signature(source),'tool',incomplete)
            reader=Mock(return_value=item())
            full=import_metadata.read(source,reader,cache,'tool',threading.Event())
            reader.assert_called_once();self.assertEqual(full['pixel_format'],'yuv420p');self.assertNotEqual(full['metadataSource'],'cache')
