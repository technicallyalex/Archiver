import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import app


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class TimestampAlignmentTests(unittest.TestCase):
    def test_auto_output_preserves_variable_and_fractional_frame_times(self):
        ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
        def run(command):
            return subprocess.run(command, capture_output=True, text=True, check=True)
        def times(path):
            data = json.loads(run([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_frames',
                                   '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)]).stdout)
            values = [float(f['best_effort_timestamp_time']) for f in data['frames']]
            return [t-values[0] for t in values]
        available = run([ffmpeg, '-hide_banner', '-encoders']).stdout
        encoders = [(codec, encoder) for codec, encoder in [('h264', 'libx264'), ('hevc', 'libx265'), ('av1', 'libsvtav1')]
                    if encoder in available]
        self.assertTrue(encoders, 'No supported software encoder available')
        with tempfile.TemporaryDirectory() as temp, patch.dict(app.STATE, ffmpeg=ffmpeg, encoders=[e for _,e in encoders]):
            for name, rate, filters in [('fractional', '60000/1001', []),
                                         ('variable', '60', ['-vf', "select='not(eq(mod(n,7),0))'", '-fps_mode', 'vfr'])]:
                source, output = Path(temp)/f'{name}.mkv', Path(temp)/f'{name}.mp4'
                run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size=128x96:rate={rate}:duration=2',
                     *filters, '-c:v', 'ffv1', str(source)])
                for codec, encoder in encoders:
                    with self.subTest(timing=name, encoder=encoder):
                        output = Path(temp)/f'{name}-{encoder}.mp4'
                        settings = dict(autoEngine='ab-av1', abCodec=codec, codec=codec, encoder=encoder,
                                        encodingMode='software', qualityMode='perceptual', qualityValue=18, bitrate='crf',
                                        encoderPriority='balanced', container='mp4', audio='none', sourceMetadata={'fps': float(60)})
                        run(app.command_for(source, output, settings))
                        reference, distorted = times(source), times(output)
                        self.assertEqual(len(reference), len(distorted))
                        self.assertTrue(all(abs(a-b)<.0001 for a,b in zip(reference, distorted)), (reference[:8], distorted[:8]))
