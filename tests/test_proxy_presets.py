import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import app
import proxy_media


class ProxyPresetTests(unittest.TestCase):
    def test_h264_rate_and_hardware_selection(self):
        source=dict(width=3840,height=2160,fps=59.94,duration=60,pixel_format='yuv420p',audio='')
        half=proxy_media.resolve(source,{'proxyScale':'2','proxyCodec':'h264'})
        self.assertEqual(half['videoBitrate'],16e6);self.assertEqual(half['gop'],30)
        for backend in ('nvenc','qsv','amf'):
            encoder='h264_'+backend
            self.assertEqual(proxy_media.encoder_for({'proxyCodec':'h264','encodingMode':'hardware','hardwareBackend':backend},[encoder]),encoder)
        with self.assertRaises(ValueError):proxy_media.encoder_for({'proxyCodec':'h264'},['prores_ks'])
        with self.assertRaises(ValueError):proxy_media.resolve(source,{'proxyCodec':'vp9'})

    def test_all_codecs_and_output_locations(self):
        source=dict(path='original.mov',width=1920,height=1080,fps=30,duration=60,pixel_format='yuv420p',audio='')
        for codec,encoder in [('h264','libx264'),('hevc','libx265'),('av1','libsvtav1'),('prores','prores_ks')]:
            self.assertEqual(proxy_media.encoder_for({'proxyCodec':codec},[encoder]),encoder)
        self.assertEqual(proxy_media.output_path(source,{'proxyLocation':'next-to'}),Path('original_proxy.mov'))
        with tempfile.TemporaryDirectory() as tmp:
            config={'mode':'directory','destination':tmp,'proxyLocation':'custom','proxyCodec':'av1'}
            self.assertEqual(proxy_media.output_path(source,config),Path(tmp).resolve()/'original_proxy.mp4')
        with self.assertRaises(ValueError):proxy_media.output_path(source,{'proxyLocation':'custom'})

    def test_dimensions_and_profile_rate_scale_with_pixels_and_fps(self):
        source = dict(width=3840,height=2160,fps=59.94,duration=60,pixel_format='yuv420p',audio='')
        half = proxy_media.resolve(source, {'proxyScale':'2'})
        quarter = proxy_media.resolve(source, {'proxyScale':'4'})
        self.assertEqual((half['width'],half['height']),(1920,1080))
        self.assertEqual((quarter['width'],quarter['height']),(960,540))
        self.assertAlmostEqual(half['videoBitrate'],90e6)
        self.assertAlmostEqual(quarter['videoBitrate'],22.5e6)
        portrait = proxy_media.resolve({**source,'width':1080,'height':1920},{'proxyScale':'4'})
        self.assertEqual((portrait['width'],portrait['height']),(270,480))

    def test_incompatible_sources_and_actions_are_rejected(self):
        source=dict(path='original.mov',width=1920,height=1080,fps=30,duration=60,pixel_format='yuv420p')
        for change in ({'color_transfer':'smpte2084'},{'pixel_format':'yuva444p10le'},{'pixel_format':'yuv422p12le'},{'field_order':'tt'}):
            with self.assertRaises(ValueError):proxy_media.resolve({**source,**change},{'proxyScale':'2'})
        for mode in ('overwrite','copy','move'):
            with self.assertRaisesRegex(ValueError,'keep originals'):proxy_media.output_path(source,{'mode':mode})


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Video tools required')
class ProxyIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.source=cls.root/'Camera.mov'
        p=app.run([shutil.which('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30000/1001:duration=1.001',
                   '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=1.001',
                   '-map','0:v','-map','1:a','-map','1:a','-c:v','libx264','-pix_fmt','yuv420p','-c:a','pcm_s16le',
                   '-ac:a:0','2','-ac:a:1','1','-timecode','12:34:56:00',str(cls.source)])
        if p.returncode:raise RuntimeError(p.stderr)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def setUp(self):
        self.old=copy.deepcopy(app.STATE)
        app.configure(shutil.which('ffmpeg'),shutil.which('ffprobe'))
        self.item=app.probe(self.source);app.STATE['files']={self.item['id']:self.item};app.STATE['jobs']=[]

    def tearDown(self):app.STATE.clear();app.STATE.update(self.old)

    def settings(self,scale):return dict(qualityMode='proxy',proxyScale=scale,mode='preserve',naming='template',filenameTemplate='INVALID/{original}',container='mp4')

    def test_queue_executes_both_sizes_and_preserves_linking_metadata(self):
        before=self.source.read_bytes()
        for scale,folder,size in [('2','Half',(160,90)),('4','Quarter',(80,45))]:
            app.STATE['jobs']=[]
            app.enqueue([self.item['id']],self.settings(scale))
            job=app.STATE['jobs'][0];target=Path(job['output'])
            self.assertEqual(target,self.root/'Proxies'/folder/'Camera.mov')
            self.assertFalse(target.exists())
            with patch.object(app,'encoding_preview_command',side_effect=lambda c,f:c):app.execute_job(job)
            self.assertEqual(job['status'],'completed',job['error'])
            info=app.probe(target)
            self.assertEqual((info['width'],info['height']),size)
            self.assertEqual(info['timecode'],self.item['timecode'])
            self.assertEqual(info['frame_rate'],self.item['frame_rate'])
            self.assertEqual([(a['channels'],a['sample_rate']) for a in info['audio_streams']],[(2,48000),(1,48000)])
            self.assertEqual(info['audio'],'pcm_s24le')
            self.assertEqual(info['profile'],'Proxy')
            self.assertEqual(self.source.read_bytes(),before)
            # A frame-rate match alone can hide frame drops: compare decoded counts.
            def count(path):
                r=app.run([app.STATE['ffprobe'],'-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=nb_read_frames','-of','json',str(path)])
                return json.loads(r.stdout)['streams'][0]['nb_read_frames']
            self.assertEqual(count(target),count(self.source))
            app.enqueue([self.item['id']],self.settings(scale))
            self.assertEqual(Path(app.STATE['jobs'][-1]['output']).name,'Camera_002.mov')

    def test_estimates_and_details_use_same_preset(self):
        settings=self.settings('2')
        estimate=app.output_size_estimate([self.item],settings)
        self.assertEqual(estimate['bytes'],round(proxy_media.resolve(self.item,settings)['estimatedBytes']))
        row=app.encoding_details([self.item],settings)['files'][0]
        self.assertEqual(row['encoder'],'prores_ks');self.assertEqual(row['control'],'ProRes profile')
        self.assertIn('160 × 90',row['value']);self.assertIn('profile-controlled',row['provenance'])
        self.assertEqual(app.output_name(self.item,settings),'Camera.mov')

    def test_orientation_survives_without_rotating_the_encoded_dimensions(self):
        rotated=self.root/'Rotated.mov';target=self.root/'Rotated-proxy.mov'
        r=app.run([app.STATE['ffmpeg'],'-v','error','-y','-display_rotation:v:0','90','-i',str(self.source),'-map','0','-c','copy',str(rotated)])
        self.assertEqual(r.returncode,0,r.stderr)
        source=app.probe(rotated);self.assertNotEqual(source['rotation'],0)
        settings={**self.settings('4'),'sourceMetadata':source}
        r=app.run(app.command_for(rotated,target,settings));self.assertEqual(r.returncode,0,r.stderr)
        result=app.probe(target);proxy_media.verify(source,result,settings)
        self.assertEqual((result['width'],result['height']),(80,45))
        self.assertEqual(result['sample_aspect_ratio'],source['sample_aspect_ratio'])

    def test_h264_both_sizes_preserve_timing_audio_and_short_gops(self):
        for scale,size in [('2',(160,90)),('4',(80,44))]:
            app.STATE['jobs']=[]
            settings={**self.settings(scale),'proxyCodec':'h264','encodingMode':'software'}
            app.enqueue([self.item['id']],settings)
            job=app.STATE['jobs'][0];target=Path(job['output'])
            self.assertEqual(target.parent.name,'H264')
            with patch.object(app,'encoding_preview_command',side_effect=lambda c,f:c):app.execute_job(job)
            self.assertEqual(job['status'],'completed',job['error'])
            info=app.probe(target);proxy_media.verify(self.item,info,settings)
            self.assertEqual((info['width'],info['height']),size)
            cmd=job['command'];self.assertEqual(cmd[cmd.index('-bf')+1],'0')
            data=app.run([app.STATE['ffprobe'],'-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=pict_type,key_frame','-of','json',str(target)])
            frames=json.loads(data.stdout)['frames'];self.assertEqual(len(frames),30)
            self.assertNotIn('B',[f['pict_type'] for f in frames])
            keys=[i for i,f in enumerate(frames) if f['key_frame']]
            self.assertGreaterEqual(len(keys),2)
            self.assertTrue(all(b-a<=15 for a,b in zip(keys,keys[1:])))
            row=app.encoding_details([self.item],settings)['files'][0]
            self.assertEqual(row['encoder'],'libx264');self.assertEqual(row['control'],'Target bitrate')
            self.assertEqual(row['preset'],'veryfast')
            self.assertIn('short GOP',row['provenance'])

    def test_hevc_and_av1_proxy_queue_executes_both_sizes(self):
        for codec in ('hevc','av1'):
            for scale in ('2','4'):
                app.STATE['jobs']=[]
                settings={**self.settings(scale),'proxyCodec':codec,'encodingMode':'software'}
                app.enqueue([self.item['id']],settings)
                job=app.STATE['jobs'][0]
                with patch.object(app,'encoding_preview_command',side_effect=lambda c,f:c):app.execute_job(job)
                self.assertEqual(job['status'],'completed',str((codec,scale,job['error'],list(job['log'])[-30:])))
                result=app.probe(Path(job['output']));self.assertEqual(result['codec'],codec);proxy_media.verify(self.item,result,settings)
                self.assertEqual(job['settings']['encoder'],job['command'][job['command'].index('-c:v')+1])

    def test_h264_nvenc_when_hardware_is_available(self):
        if 'h264_nvenc' not in app.STATE['encoders']:self.skipTest('NVENC is not in this FFmpeg build')
        check=app.run([app.STATE['ffmpeg'],'-v','error','-i',str(self.source),'-frames:v','1','-c:v','h264_nvenc','-an','-f','null','-'])
        if check.returncode:self.skipTest('NVIDIA encoder hardware/driver is not available')
        settings={**self.settings('2'),'proxyCodec':'h264','encodingMode':'hardware','hardwareBackend':'nvenc','sourceMetadata':self.item}
        output=self.root/'Hardware-proxy.mov';r=app.run(app.command_for(self.source,output,settings))
        self.assertEqual(r.returncode,0,r.stderr)
        proxy_media.verify(self.item,app.probe(output),settings)
        import hardware_queue
        key=hardware_queue.hardware_key({'settings':{**settings,'encoder':'h264_nvenc'}})
        self.assertIsNotNone(key)
        self.assertNotEqual(key,hardware_queue.hardware_key({'settings':{**settings,'proxyScale':'4','encoder':'h264_nvenc'}}))

    def test_dry_run_and_invalid_batch_leave_queue_and_folders_untouched(self):
        # Use another root so prior integration outputs cannot affect this test.
        destination=self.root/'Alternative';destination.mkdir(exist_ok=True)
        settings={**self.settings('2'),'mode':'directory','destination':str(destination)}
        app.enqueue([self.item['id']],settings,dry_run=True)
        self.assertEqual(app.STATE['jobs'],[]);self.assertFalse((destination/'Proxies').exists())
        bad={**self.item,'id':'bad','name':'HDR.mov','color_transfer':'smpte2084'};app.STATE['files']['bad']=bad
        with self.assertRaises(ValueError):app.enqueue([self.item['id'],'bad'],settings)
        self.assertEqual(app.STATE['jobs'],[]);self.assertFalse((destination/'Proxies').exists())
        with self.assertRaisesRegex(ValueError,'keep originals'):app.enqueue([self.item['id']],{**settings,'mode':'overwrite'})
