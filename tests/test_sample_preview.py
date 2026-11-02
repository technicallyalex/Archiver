import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import app
import sample_preview


class PreviewTests(unittest.TestCase):
    def test_range_serving(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'clip.mp4';target.write_bytes(b'0123456789')
            for requested,code,body in [(None,200,b'0123456789'),('bytes=2-5',206,b'2345'),('bytes=-3',206,b'789'),('bytes=7-',206,b'789'),('bytes=90-',416,b''),('bytes=0-1,5-6',416,b'')]:
                handler=object.__new__(app.Handler);handler.headers={'Range':requested} if requested else {};handler.wfile=io.BytesIO();status=[];headers={}
                handler.send_response=status.append;handler.send_header=lambda k,v:headers.update({k:v});handler.end_headers=lambda:None
                handler.send_preview(target)
                self.assertEqual(status,[code]);self.assertEqual(handler.wfile.getvalue(),body)
                if code!=416:self.assertEqual(headers['Accept-Ranges'],'bytes')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_fractional_fps_and_variable_timing_are_preserved(self):
        ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
        def timestamps(path):
            result=app.run([ffprobe,'-v','error','-select_streams','v:0','-show_entries','frame=best_effort_timestamp_time','-of','json',str(path)])
            return [float(f['best_effort_timestamp_time']) for f in json.loads(result.stdout)['frames']]
        with tempfile.TemporaryDirectory() as tmp:
            for name,rate,filtering in [('fractional','60000/1001',[]),('variable','30',['-vf',"select='not(mod(n,2))+gte(t,1)'",'-fps_mode','vfr'])]:
                source=Path(tmp)/(name+'.mkv');output=Path(tmp)/(name+'.mp4')
                result=app.run([ffmpeg,'-v','error','-f','lavfi','-i',f'testsrc2=size=128x96:rate={rate}:duration=2',*filtering,'-c:v','ffv1',str(source)])
                self.assertEqual(result.returncode,0,result.stderr)
                sample_preview.create(ffmpeg,source,output,0,2,lambda:False)
                original,preview=timestamps(source),timestamps(output)
                self.assertEqual(len(original),len(preview))
                self.assertTrue(all(abs(a-b)<=.0011 for a,b in zip(original,preview)),(original[:6],preview[:6]))
                info=json.loads(app.run([ffprobe,'-v','error','-show_streams','-of','json',str(output)]).stdout)
                self.assertEqual(len(info['streams']),1);self.assertEqual(info['streams'][0]['codec_name'],'h264');self.assertEqual(info['streams'][0]['width'],320)
                self.assertFalse(output.with_name(output.stem+'.partial.mp4').exists())

    def test_cancelled_preview_does_not_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'sample.mp4'
            with self.assertRaises(InterruptedError):sample_preview.create('ffmpeg','source',output,0,10,lambda:True)
            self.assertFalse(output.exists())
