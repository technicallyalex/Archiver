import unittest
from pathlib import Path
from unittest.mock import patch
import app

class OutputCodecTests(unittest.TestCase):
    def test_only_supported_delivery_encoders_can_be_queued(self):
        self.assertEqual(set(app.ENCODERS), {'h264', 'hevc', 'av1'})
        for codec, encoder in [('mpeg2','mpeg2video'), ('mpeg4','mpeg4'), ('mjpeg','mjpeg'), ('vp9','libvpx-vp9')]:
            with patch.dict(app.STATE, encoders=[encoder]):
                with self.assertRaises(ValueError):
                    app.command_for(Path('input'), Path('output.mkv'), dict(codec=codec, encoder=encoder, container='mkv', bitrate='custom', customBitrate=2))
