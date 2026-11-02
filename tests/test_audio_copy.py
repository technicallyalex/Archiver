import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import app


class AudioCopyCommandTests(unittest.TestCase):
    def test_webm_copy_requires_compatible_original_codecs(self):
        settings=dict(qualityMode='custom',codec='av1',encoder='libaom-av1',container='webm',bitrate='custom',customBitrate=1,audio='copy',audioBitrate='source')
        with patch.dict(app.STATE,encoders=['libaom-av1']):
            for codec in ('opus','vorbis','opus, vorbis',''):
                cmd=app.command_for(Path('source'),Path('out.webm'),{**settings,'sourceMetadata':{'audio':codec}})
                self.assertEqual(cmd[cmd.index('-c:a')+1],'copy');self.assertNotIn('-b:a',cmd)
            for codec in ('aac','flac','aac, opus'):
                with self.assertRaisesRegex(ValueError,'Choose MKV'):
                    app.command_for(Path('source'),Path('out.webm'),{**settings,'sourceMetadata':{'audio':codec}})


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Video tools required')
class AudioCopyIntegrationTests(unittest.TestCase):
    def test_all_audio_tracks_are_copied_without_changing_packet_data(self):
        old=copy.deepcopy(app.STATE)
        try:
            app.configure(shutil.which('ffmpeg'),shutil.which('ffprobe'))
            with tempfile.TemporaryDirectory() as directory:
                source=Path(directory)/'original.mp4';target=Path(directory)/'encoded.mp4'
                result=app.run([app.STATE['ffmpeg'],'-v','error','-f','lavfi','-i','testsrc2=s=192x108:r=30:d=1',
                    '-f','lavfi','-i','sine=sample_rate=48000:duration=1','-map','0:v','-map','1:a','-map','1:a',
                    '-c:v','libx264','-c:a','aac','-ac:a:0','2','-ac:a:1','1',str(source)])
                self.assertEqual(result.returncode,0,result.stderr)
                metadata=app.probe(source)
                settings=dict(qualityMode='custom',codec='h264',encoder='libx264',container='mp4',bitrate='custom',customBitrate=1,audio='copy',audioBitrate='source',sourceMetadata=metadata)
                cmd=app.command_for(source,target,settings)
                self.assertNotIn('-b:a',cmd);self.assertNotIn('-ac',cmd)
                result=app.run(cmd);self.assertEqual(result.returncode,0,result.stderr)
                actual=app.probe(target)
                self.assertEqual([s['channels'] for s in actual['audio_streams']],[2,1])
                self.assertEqual(actual['audio'],'aac')
                def packets(path):
                    r=app.run([app.STATE['ffprobe'],'-v','error','-select_streams','a','-show_packets','-show_data_hash','sha256','-show_entries','packet=stream_index,data_hash','-of','json',str(path)])
                    self.assertEqual(r.returncode,0,r.stderr)
                    return [(p['stream_index'],p['data_hash']) for p in json.loads(r.stdout)['packets']]
                self.assertEqual(packets(source),packets(target))
        finally:app.STATE.clear();app.STATE.update(old)
