import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import ab_av1
import app
from quality import fingerprint


class AbAv1Tests(unittest.TestCase):
    def test_target_defaults_bounds_and_cache_separation(self):
        self.assertEqual(ab_av1.target_for({}),38)
        for value in [30,38.5,'42',50]:
            self.assertEqual(ab_av1.target_for({'xpsnrTarget':value}),float(value))
        for value in [None,True,False,'',29.9,50.1,'nan','inf','bad',[]]:
            with self.subTest(value=value),self.assertRaises(ValueError):
                ab_av1.target_for({'xpsnrTarget':value})
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'input';source.write_bytes(b'input')
            item={'path':str(source)};base={'autoEngine':'ab-av1','abCodec':'h264'}
            default=fingerprint(item,base,str(source),str(source))
            explicit=fingerprint(item,{**base,'xpsnrTarget':38},str(source),str(source))
            other=fingerprint(item,{**base,'xpsnrTarget':42},str(source),str(source))
            self.assertEqual(default,explicit);self.assertNotEqual(default,other)

    def test_sampling_matches_upstream_full_pass_and_distributed_windows(self):
        self.assertEqual(ab_av1.windows(30), [{'start': 0., 'duration': 30}])
        self.assertEqual(ab_av1.windows(100), [{'start': 17., 'duration': 10.}, {'start': 45., 'duration': 10.}, {'start': 72., 'duration': 10.}])
        for length in [1, 35, 36, 100, 7200]:
            self.assertTrue(all(w['start'] >= 0 and w['start'] + w['duration'] <= length for w in ab_av1.windows(length)))

    def test_encoders_and_container_are_explicit_no_vp9_output(self):
        for codec, name in [('av1', 'libsvtav1'), ('hevc', 'libx265'), ('h264', 'libx264')]:
            self.assertEqual(ab_av1.encoder_for({'abCodec': codec, 'encodingMode': 'software'}, [name]), name)
            self.assertEqual(ab_av1.encoder_for({'abCodec': codec, 'encodingMode': 'hardware', 'hardwareBackend': 'nvenc'}, [codec+'_nvenc']), codec+'_nvenc')
        for settings in [{'abCodec':'vp9'}, {'abCodec':'h264', 'container':'webm'}, {'abCodec':'av1','encodingMode':'hardware','hardwareBackend':'amf'}]:
            with self.assertRaises(ValueError):
                ab_av1.encoder_for(settings, ['libx264','libvpx-vp9','av1_amf'])
        self.assertNotIn('vp9', app.ENCODERS)

    def test_streaming_drains_both_pipes_carriage_returns_and_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines=[]
            code="import sys; print('one'); sys.stderr.write('\\x1b[31mtwo\\x1b[0m\\rthree\\n'); sys.stderr.flush()"
            ab_av1.stream([sys.executable,'-c',code], tmp, os.environ.copy(), lambda:False, lambda c,t:lines.append((c,t)))
            self.assertIn(('stdout','one'),lines)
            self.assertIn(('stderr','two'),lines)
            self.assertIn(('stderr','three'),lines)
            with self.assertRaises(ValueError):
                ab_av1.stream([sys.executable,'-c','raise SystemExit(4)'],tmp,os.environ.copy(),lambda:False,lambda *_:None)

    def test_cancellation_stops_active_process_without_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            started=time.monotonic()
            with self.assertRaises(InterruptedError):
                ab_av1.stream([sys.executable,'-c','import time; time.sleep(60)'],tmp,os.environ.copy(),lambda:time.monotonic()-started>.3,lambda *_:None)
            self.assertLess(time.monotonic()-started,10)

    def test_adapter_requires_final_json_and_preserves_target_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); tool=root/'fake.exe';tool.write_bytes(b'tool')
            settings={'abCodec':'h264','encodingMode':'software','qualityMode':'web','container':'mp4'}
            item={'path':str(root/'input.mp4'),'duration':100}
            captured=[]
            def fake(command, directory, env, cancel, line):
                captured.extend(command)
                line('stderr','encoding sample 2/3 crf 25')
                event='"crf":25,"xpsnr":39,"predicted_encode_percent":50,"predicted_encode_size":1000,"predicted_encode_seconds":10'
                line('stdout','{"type":"sample-encode-done",'+event+'}')
                line('stdout','{"type":"crf-search-done",'+event+'}')
            telemetry=[]
            with patch.object(ab_av1,'binary',return_value=str(tool)),patch.object(ab_av1,'stream',side_effect=fake):
                result=ab_av1.analyze(item,settings,['libx264'],str(tool),str(tool),root/'run',lambda:False,lambda _:None,telemetry.append)
            self.assertEqual(result['winner']['codec'],'h264')
            self.assertEqual(result['policy'],{'metric':'xpsnr','mean':38.0,'p05':0,'second':0})
            self.assertIn('--stdout-format',captured)
            self.assertIn('crf-search',captured)
            self.assertEqual(captured[captured.index('--min-xpsnr')+1],'38.0')
            self.assertNotIn('--min-vmaf',captured)
            self.assertEqual(captured[captured.index('--xpsnr-fps')+1],'0')
            self.assertEqual(result['metric'],'xpsnr')
            self.assertIn('enc_time_base=demux',captured)
            self.assertEqual(captured[captured.index('--max-encoded-percent')+1],'10000')
            self.assertEqual(len(result['measurements']),1)
            self.assertTrue((root/'run'/'crf-search-measurements.json').is_file())
            self.assertEqual(next(t['sampleIndex'] for t in telemetry if 'sampleIndex' in t),2)
            self.assertTrue((root/'run'/'ab-av1.log').is_file())
            self.assertFalse((root/'run'/'tool-bin').exists())
            with patch.object(ab_av1,'binary',return_value=str(tool)),patch.object(ab_av1,'stream'):
                with self.assertRaisesRegex(ValueError,'no valid final'):
                    ab_av1.analyze(item,settings,['libx264'],str(tool),str(tool),root/'invalid',lambda:False,lambda _:None,None)

    def test_large_recommendations_and_failed_search_measurements_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);tool=root/'fake.exe';tool.write_bytes(b'tool')
            settings=dict(abCodec='h264',encodingMode='software',qualityMode='perceptual',container='mkv')
            item=dict(path=str(root/'input.mkv'),duration=100)
            event=dict(crf=12,xpsnr=39,predicted_encode_percent=150,predicted_encode_size=150000,predicted_encode_seconds=10)
            def success(command,directory,env,cancel,line):
                import json
                line('stdout',json.dumps({**event,'type':'sample-encode-done'}))
                line('stdout',json.dumps({**event,'type':'crf-search-done'}))
            with patch.object(ab_av1,'binary',return_value=str(tool)),patch.object(ab_av1,'stream',side_effect=success):
                result=ab_av1.analyze(item,settings,['libx264'],str(tool),str(tool),root/'large',lambda:False,lambda _:None,None)
            self.assertFalse(result['keepOriginal']);self.assertEqual(result['winner']['qualityValue'],12)
            def failure(*args):
                import json
                args[-1]('stdout',json.dumps({**event,'type':'sample-encode-done'}))
                raise ValueError('No suitable CRF')
            with patch.object(ab_av1,'binary',return_value=str(tool)),patch.object(ab_av1,'stream',side_effect=failure):
                with self.assertRaises(ValueError):
                    ab_av1.analyze(item,settings,['libx264'],str(tool),str(tool),root/'failed',lambda:False,lambda _:None,None)
            import json
            saved=json.loads((root/'failed'/'crf-search-measurements.json').read_text())
            self.assertEqual(saved['measurements'][0]['crf'],12)

    def test_below_target_xpsnr_is_rejected(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);tool=root/'fake.exe';tool.write_bytes(b'tool')
            def low(command,directory,env,cancel,line):
                line('stdout',json.dumps(dict(type='crf-search-done',crf=30,xpsnr=37.9,predicted_encode_percent=50,predicted_encode_size=1000,predicted_encode_seconds=10)))
            with patch.object(ab_av1,'binary',return_value=str(tool)),patch.object(ab_av1,'stream',side_effect=low):
                with self.assertRaisesRegex(ValueError,'requested limits'):
                    ab_av1.analyze({'path':str(root/'source'),'duration':100},{'abCodec':'h264','encodingMode':'software','qualityMode':'perceptual'},['libx264'],str(tool),str(tool),root/'run',lambda:False,lambda _:None,None)

    def test_custom_target_reaches_cli_report_and_validation_policy(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);tool=root/'tool.exe';tool.write_bytes(b'tool');seen=[]
            def run(command,directory,env,cancel,line):
                seen.extend(command)
                line('stdout',json.dumps(dict(type='crf-search-done',crf=20,xpsnr=42.2,predicted_encode_percent=150,predicted_encode_size=1000,predicted_encode_seconds=10)))
            with patch.object(ab_av1,'binary',return_value=str(tool)),patch.object(ab_av1,'stream',side_effect=run):
                result=ab_av1.analyze({'path':str(root/'source'),'duration':100},{'abCodec':'h264','encodingMode':'software','qualityMode':'perceptual','xpsnrTarget':42},['libx264'],str(tool),str(tool),root/'run',lambda:False,lambda _:None,None)
            self.assertEqual(seen[seen.index('--min-xpsnr')+1],'42.0')
            self.assertEqual(result['targetScore'],42)
            self.assertEqual(result['policy']['mean'],42)
            self.assertIn('42 dB',result['calibration'])
            self.assertFalse(result['keepOriginal'])

    def test_final_encode_uses_tested_encoder_controls(self):
        old=app.STATE.copy()
        try:
            app.STATE.update(ffmpeg='ffmpeg',encoders=['libsvtav1','libx264','libx265','av1_nvenc','hevc_qsv'])
            for codec,encoder in [('av1','libsvtav1'),('h264','libx264'),('hevc','libx265'),('av1','av1_nvenc'),('hevc','hevc_qsv')]:
                hardware='_' in encoder
                settings=dict(autoEngine='ab-av1',abCodec=codec,qualityMode='perceptual',codec=codec,encoder=encoder,
                              encodingMode='hardware' if hardware else 'software',hardwareBackend='qsv' if encoder.endswith('_qsv') else 'nvenc',
                              qualityValue=24,bitrate='cqp' if hardware else 'crf',encoderPriority='balanced',container='mkv',audio='none',sourceMetadata={'fps':30})
                command=app.command_for(Path('input'),Path('output.mkv'),settings)
                manual={**settings,'qualityMode':'custom','testedEncoder':encoder,'bitrate':'cq' if encoder.endswith('_nvenc') else 'icq' if encoder.endswith('_qsv') else 'crf'}
                self.assertEqual(command,app.command_for(Path('input'),Path('output.mkv'),manual))
                self.assertIn('-g',command)
                self.assertEqual(command[command.index('-g')+1],'300')
                self.assertEqual(command[command.index('-enc_time_base')+1],'demux')
                self.assertIn('-cq' if encoder.endswith('_nvenc') else '-global_quality' if encoder.endswith('_qsv') else '-crf',command)
                self.assertNotIn('constqp',command)
        finally:
            app.STATE.clear();app.STATE.update(old)

    def test_cache_identity_includes_engine_codec_and_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'file';source.write_bytes(b'input')
            base={'path':str(source)}
            a=fingerprint(base,{},str(source),str(source))
            b=fingerprint(base,{'autoEngine':'ab-av1','abCodec':'av1'},str(source),str(source))
            c=fingerprint(base,{'autoEngine':'ab-av1','abCodec':'h264'},str(source),str(source))
            self.assertEqual(len({a,b,c}),3)
