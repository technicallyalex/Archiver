import copy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import app
import import_admission
import import_metadata
import metadata_cache


def item():
    return dict(id='old',codec='h264',width=1920,height=1080,fps=30,duration=60,pixel_format='yuv420p',audio_streams=[],frame_rate='30/1',timecode='',rotation=0,sample_aspect_ratio='1:1',field_order='progressive',video_bitrate=8000000,rate_mode='',source_quality=None,color_transfer='',audio='')


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.source=self.root/'clip.mp4';self.source.write_bytes(b'unchanged')
        self.cache=metadata_cache.Cache(self.root/'cache'/'metadata.sqlite')
        self.cancel=threading.Event()
    def tearDown(self):self.tmp.cleanup()
    def read(self,probe,**kwargs):
        return import_metadata.read(self.source,probe,self.cache,'tool-one',self.cancel,**kwargs)

    def test_persists_across_instances_and_does_not_reuse_ui_ids(self):
        reader=Mock(return_value=item());first=self.read(reader)
        self.assertEqual(first['metadataSource'],'fast');reader.assert_called_once()
        self.cache=metadata_cache.Cache(self.cache.path)
        reader.reset_mock();second=self.read(reader);reader.assert_not_called()
        self.assertEqual(second['metadataSource'],'cache');self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(second['name'],self.source.name)
        self.assertEqual(self.source.read_bytes(),b'unchanged')

    def test_size_timestamp_tool_and_parser_changes_invalidate(self):
        stamp=metadata_cache.signature(self.source);self.cache.put(self.source,stamp,'one',item())
        self.assertIsNotNone(self.cache.get(self.source,stamp,'one'))
        self.assertIsNone(self.cache.get(self.source,stamp,'two'))
        self.source.write_bytes(b'changed size');self.assertIsNone(self.cache.get(self.source,metadata_cache.signature(self.source),'one'))
        self.cache.put(self.source,metadata_cache.signature(self.source),'one',item())
        now=self.source.stat();os.utime(self.source,ns=(now.st_atime_ns,now.st_mtime_ns+1000000000))
        self.assertIsNone(self.cache.get(self.source,metadata_cache.signature(self.source),'one'))
        parser_one=metadata_cache.tool_signature(self.source)
        self.cache.put(self.source,metadata_cache.signature(self.source),parser_one,item())
        with patch.object(metadata_cache,'SCHEMA',999):
            parser_two=metadata_cache.tool_signature(self.source)
            self.assertNotEqual(parser_one,parser_two)
            self.assertIsNone(self.cache.get(self.source,metadata_cache.signature(self.source),parser_two))

    def test_incomplete_fast_pass_falls_back_and_caches_only_final_result(self):
        incomplete={**item(),'pixel_format':''};reader=Mock(side_effect=[incomplete,item()]);events=[]
        result=self.read(reader,notify=events.append)
        self.assertEqual(result['metadataSource'],'full');self.assertEqual(reader.call_count,2)
        self.assertTrue(reader.call_args_list[0].kwargs['light']);self.assertNotIn('light',reader.call_args_list[1].kwargs)
        self.assertIn(('fallback',None),events)
        self.read(Mock(side_effect=AssertionError('Cache was not reused')))

    def test_failed_and_changed_reads_are_not_cached(self):
        with self.assertRaises(ValueError):self.read(Mock(side_effect=ValueError('bad media')))
        self.assertIsNone(self.cache.get(self.source,metadata_cache.signature(self.source),'tool-one'))
        def changing(*args,**kwargs):self.source.write_bytes(b'new file');return item()
        with self.assertRaisesRegex(ValueError,'File changed'):self.read(changing)
        self.assertIsNone(self.cache.get(self.source,metadata_cache.signature(self.source),'tool-one'))

    def test_cancellation_never_publishes_inflight_metadata(self):
        def stopping(*args,**kwargs):self.cancel.set();return item()
        with self.assertRaises(InterruptedError):self.read(stopping)
        self.assertIsNone(self.cache.get(self.source,metadata_cache.signature(self.source),'tool-one'))

    def test_fast_timeout_uses_remaining_normal_budget(self):
        clock=Mock(side_effect=[0,8]);reader=Mock(side_effect=[TimeoutError('slow'),item()])
        self.read(reader,clock=clock)
        self.assertEqual(reader.call_args_list[0].kwargs['timeout'],8)
        self.assertEqual(reader.call_args_list[1].kwargs['timeout'],82)

    def test_unusable_cache_is_nonfatal_and_deleted_sources_are_not_served(self):
        self.cache.path.parent.mkdir();self.cache.path.write_bytes(b'not sqlite')
        result=self.read(Mock(return_value=item()))
        self.assertEqual(result['metadataSource'],'fast');self.assertIn('unavailable',self.cache.error)
        self.source.unlink()
        with self.assertRaises(FileNotFoundError):self.read(Mock(return_value=item()))

    def test_concurrent_cache_writes_and_restart(self):
        paths=[self.root/f'{n}.mp4' for n in range(32)]
        for path in paths:path.write_bytes(b'video')
        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(lambda p:self.cache.put(p,metadata_cache.signature(p),'tool',item()),paths))
        self.assertEqual(self.cache.error,'');cache=metadata_cache.Cache(self.cache.path)
        self.assertTrue(all(cache.get(p,metadata_cache.signature(p),'tool') for p in paths))

    def test_nonindexed_container_skips_fast_pass(self):
        source=self.root/'clip.ts';source.write_bytes(b'ts');reader=Mock(return_value=item())
        import_metadata.read(source,reader,self.cache,'tool',self.cancel)
        reader.assert_called_once();self.assertNotIn('light',reader.call_args.kwargs)


class ImportAdmissionTests(unittest.TestCase):
    def window(self,a,start,count,interval):
        for i in range(count):a.observe(start+(i+1)*interval,True)
    def test_ramps_only_when_fresh_throughput_improves(self):
        a=import_admission.Admission(16,0);self.window(a,0,8,.25);self.assertEqual(a.limit,8)
        self.window(a,2,16,.125);self.assertEqual(a.limit,16)
        self.window(a,4,32,.0625);self.assertEqual(a.limit,16);self.assertTrue(a.stable)
    def test_no_gain_returns_to_lower_concurrency(self):
        a=import_admission.Admission(16,0);self.window(a,0,8,.25)
        self.window(a,2,16,.25);self.assertEqual(a.limit,4);self.assertTrue(a.stable)
    def test_errors_and_stalls_back_off_without_canceling_work(self):
        a=import_admission.Admission(16,0);self.assertEqual(a.stalled(16),2)
        a.observe(17,failed=True);self.assertEqual(a.limit,1)
    def test_cache_hits_do_not_inflate_probe_throughput(self):
        a=import_admission.Admission(16,0)
        for i in range(100):a.observe(i/100)
        self.assertEqual(a.limit,4)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Video tools required')
class ImportIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.source=cls.root/'source.mov'
        p=app.run([shutil.which('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=size=192x108:rate=30000/1001:duration=1.001',
                   '-f','lavfi','-i','sine=sample_rate=48000:duration=1.001','-map','0:v','-map','1:a','-map','1:a','-c:v','libx264',
                   '-pix_fmt','yuv420p','-c:a','pcm_s16le','-ac:a:0','2','-ac:a:1','1','-timecode','01:00:00:00',str(cls.source)])
        if p.returncode:raise RuntimeError(p.stderr)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.old=copy.deepcopy(app.STATE);app.configure(shutil.which('ffmpeg'),shutil.which('ffprobe'))
        self.override=patch.dict(os.environ,ARCHIVER_CACHE_DIR=str(self.root/'cache'));self.override.start()
    def tearDown(self):self.override.stop();app.STATE.clear();app.STATE.update(self.old);app.SCAN_STOP.clear()
    def test_cold_warm_scan_matches_full_metadata_without_second_probe(self):
        expected=app.probe(self.source)
        app.STATE['scan']={'running':True,'done':0,'errors':[]};app.SCAN_STOP.clear()
        app.scan(str(self.root),False,workers=4,adaptive=True)
        self.assertEqual(app.STATE['scan']['errors'],[])
        first=next(f for f in app.STATE['files'].values() if f['path']==str(self.source))
        for key in expected:
            if key!='id':self.assertEqual(first[key],expected[key],key)
        app.STATE['scan']={'running':True,'done':0,'errors':[]}
        with patch.object(app,'probe',side_effect=AssertionError('Warm import invoked FFprobe')):app.scan(str(self.root),False,workers=16,adaptive=True)
        self.assertEqual(app.STATE['scan']['errors'],[]);self.assertEqual(app.STATE['scan']['cached'],len(app.STATE['files']))
        # Verification remains a direct normal probe, even with cached metadata present.
        with patch.object(app,'run',wraps=app.run) as run:
            app.probe(self.source)
            self.assertNotIn('-probesize',run.call_args.args[0])

    def test_bounded_analysis_matches_full_for_hdr_av1_and_prores(self):
        variants=[('hevc.mp4',['-c:v','libx265','-preset','ultrafast','-x265-params','pools=1','-pix_fmt','yuv420p10le','-color_trc','smpte2084','-color_primaries','bt2020','-colorspace','bt2020nc']),
                  ('av1.mkv',['-c:v','libaom-av1','-cpu-used','8','-threads','1']),
                  ('prores.mov',['-c:v','prores_ks','-profile:v','0','-pix_fmt','yuv422p10le'])]
        cache=metadata_cache.Cache(self.root/'variants-cache.sqlite')
        for name,args in variants:
            with self.subTest(codec=name):
                path=self.root/name
                r=app.run([app.STATE['ffmpeg'],'-v','error','-y','-i',str(self.source),'-map','0:v:0','-frames:v','4',*args,str(path)])
                self.assertEqual(r.returncode,0,r.stderr)
                expected=app.probe(path)
                actual=import_metadata.read(path,app.probe,cache,'tool',threading.Event())
                for key in expected:
                    if key!='id':self.assertEqual(expected[key],actual[key],key)
