import copy
import json
from pathlib import Path
import shutil
import tempfile
import subprocess
import threading
import time
import unittest
from unittest.mock import patch

import app
from quality import Analyzer, POLICIES, candidates, fingerprint, passes, sample_plan, sample_lead, summarize, validate_source


class QualityPolicyTests(unittest.TestCase):
    def test_scene_floor_cannot_be_hidden_by_average(self):
        good = summarize([99.] * 240, 24)
        bad = summarize([99.] * 216 + [70.] * 24, 24)
        self.assertFalse(passes([good, bad], POLICIES['perceptual']))
        with self.assertRaises(ValueError):
            summarize([float('nan')], 24)

    def test_samples_are_bounded_distinct_and_have_holdouts(self):
        for duration in [1, 11.9, 12, 17, 18, 33, 60, 900, 7200]:
            windows, training = sample_plan(duration)
            self.assertTrue(all(start >= 0 and 0 < length <= duration and start + length <= duration + .001 for start, length in windows))
            if duration >= 12:
                self.assertEqual(len(set(windows)), 3)
                self.assertLess(training, len(windows))
                self.assertEqual(training, 1)
                self.assertTrue(all(length <= 11 for _, length in windows))
                self.assertLessEqual(sum(length for _, length in windows), 33)
                self.assertLessEqual(sum(length - sample_lead(length) for _, length in windows), 30)
                ordered = sorted(windows)
                self.assertTrue(all(a + length <= b + .001 for (a, length), (b, _) in zip(ordered, ordered[1:])))

    def test_long_sources_search_ten_seconds_and_validate_thirty(self):
        for duration in [60, 900, 7200, 24 * 3600]:
            windows, training = sample_plan(duration)
            self.assertEqual(windows[0], ((duration - 11) / 2, 11))
            self.assertEqual(sum(length - sample_lead(length) for _, length in windows[:training]), 10)
            self.assertEqual(sum(length - sample_lead(length) for _, length in windows), 30)

    def test_encoding_method_and_hdr_guards(self):
        available = ['libx264', 'libsvtav1', 'av1_nvenc']
        self.assertEqual(candidates(available, 'software', 'balanced', 'mp4'), [('h264', 'libx264'), ('av1', 'libsvtav1')])
        self.assertIn(('av1', 'av1_nvenc'), candidates(available, 'hardware', 'fast', 'mp4', 'nvenc'))
        self.assertEqual(candidates(available, 'hardware', 'balanced', 'mp4', 'nvenc'), [('av1', 'av1_nvenc')])
        self.assertNotIn(('av1', 'av1_nvenc'), candidates(available, 'software', 'fast', 'mp4'))
        with self.assertRaises(ValueError):
            candidates(available, 'hardware', 'balanced', 'webm', 'qsv')
        with self.assertRaisesRegex(ValueError, '8-bit SDR'):
            validate_source({'pixel_format': 'yuv420p10le', 'color_transfer': 'smpte2084'})

    def test_cancellation_stops_before_dispatch(self):
        analyzer = Analyzer('', '', None, lambda: True, lambda _: None)
        with patch('quality.subprocess.Popen') as launch:
            with self.assertRaises(InterruptedError):
                analyzer.run(['unused'])
            launch.assert_not_called()

    def test_processing_can_finish_after_fifteen_minutes_or_longer(self):
        with patch('quality.time.monotonic', return_value=0):
            analyzer = Analyzer('', '', None, lambda: False, lambda _: None)
        with patch('quality.time.monotonic', return_value=86400), patch('quality.subprocess.Popen') as launch:
            process = launch.return_value
            process.communicate.side_effect = [subprocess.TimeoutExpired('ffmpeg', .25), subprocess.TimeoutExpired('ffmpeg', .25), ('finished', '')]
            process.returncode = 0
            process.poll.return_value = 0
            self.assertEqual(analyzer.run(['ffmpeg']), 'finished')
            process.kill.assert_not_called()

    def test_cancellation_terminates_active_processing(self):
        cancelled = iter([False, False, True])
        analyzer = Analyzer('', '', None, lambda: next(cancelled), lambda _: None)
        with patch('quality.subprocess.Popen') as launch:
            process = launch.return_value
            process.communicate.side_effect = [subprocess.TimeoutExpired('ffmpeg', .25), ('', '')]
            process.poll.return_value = None
            with self.assertRaises(InterruptedError):
                analyzer.run(['ffmpeg'])
            process.kill.assert_called_once()

    def test_test_metadata_inspection_has_no_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.mp4'
            source.write_bytes(b'source')
            metadata = {'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'avg_frame_rate': '24/1'}], 'format': {'duration': '3'}}
            with patch.object(app.subprocess, 'Popen') as launch, patch.object(app.time, 'monotonic', return_value=86400):
                process = launch.return_value
                process.communicate.side_effect = [subprocess.TimeoutExpired('ffprobe', .2), (json.dumps(metadata), '')]
                process.returncode = 0
                process.poll.return_value = 0
                result = app.probe(source, cancel=lambda: False, timeout=None)
                self.assertEqual(result['duration'], 3)
                process.kill.assert_not_called()


class SourcePresetTests(unittest.TestCase):
    def setUp(self):
        self.item = dict(name='source.mp4', path='source.mp4', codec='h264', video_bitrate=40_000_000,
                         width=1920, height=1080, fps=60, duration=60, pixel_format='yuv420p', color_transfer='bt709')
        self.settings = dict(qualityMode='source', sourcePreset='100', encodingMode='software', hardwareBackend='nvenc', container='mp4')

    def test_same_codec_budgets_and_optimized_codec_adjustment(self):
        with patch.dict(app.STATE, encoders=['libx264', 'libsvtav1']):
            for name, rate, codec in [('100', 40, 'h264'), ('75', 30, 'h264'), ('50', 20, 'h264'), ('optimized', 20, 'av1')]:
                result = app.source_preset(self.item, {**self.settings, 'sourcePreset': name})
                self.assertEqual(result['customBitrate'], rate)
                self.assertEqual(result['codec'], codec)
                self.assertEqual(result['qualityMode'], 'custom')

    def test_metadata_and_hardware_errors_do_not_fabricate_presets(self):
        with self.assertRaisesRegex(ValueError, 'bitrate is unavailable'):
            app.source_preset({**self.item, 'video_bitrate': 0}, self.settings)
        with patch.dict(app.STATE, encoders=['libx264']):
            with self.assertRaisesRegex(ValueError, 'No AV1 encoder'):
                app.source_preset(self.item, {**self.settings, 'sourceCodec': 'av1'})
            with self.assertRaisesRegex(ValueError, 'No H264 encoder'):
                app.source_preset(self.item, {**self.settings, 'encodingMode': 'hardware'})

    def test_codec_conversion_applies_before_quality_tier(self):
        with patch.dict(app.STATE, encoders=['libx264', 'libx265', 'libsvtav1', 'libvpx-vp9']):
            for preset, expected in [('100', 20), ('75', 15), ('50', 10)]:
                result = app.source_preset(self.item, {**self.settings, 'sourceCodec': 'av1', 'sourcePreset': preset})
                self.assertEqual(result['customBitrate'], expected)
                self.assertFalse(result['sourceEstimate']['measured'])
            inverse = app.source_preset({**self.item, 'codec': 'av1'}, {**self.settings, 'sourceCodec': 'h264'})
            self.assertEqual(inverse['customBitrate'], 80)
            hevc = app.source_preset(self.item, {**self.settings, 'sourceCodec': 'hevc'})
            self.assertEqual(hevc['customBitrate'], 26)
            av1_from_hevc = app.source_preset({**self.item, 'codec': 'hevc'}, {**self.settings, 'sourceCodec': 'av1'})
            self.assertAlmostEqual(av1_from_hevc['customBitrate'], 40 * .5 / .65)

    def test_optimized_does_not_choose_a_less_efficient_codec(self):
        with patch.dict(app.STATE, encoders=['libx264']):
            with self.assertRaisesRegex(ValueError, 'at least as efficient'):
                app.source_preset({**self.item, 'codec': 'av1'}, {**self.settings, 'sourcePreset': 'optimized'})

    def test_auto_cannot_queue_without_generated_presets(self):
        with patch.object(app, 'TEST_JOBS', []):
            with self.assertRaisesRegex(ValueError, 'requires a completed matching test'):
                app.enqueue(['source'], {**self.settings, 'qualityMode': 'auto', 'autoPreset': 'web'})

    def test_mixed_batch_resolves_each_files_bitrate(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {}
            for index, rate in enumerate([40_000_000, 12_000_000]):
                path = Path(tmp) / f'clip{index}.mp4'
                path.write_bytes(b'source')
                files[str(index)] = {**self.item, 'id': str(index), 'path': str(path), 'video_bitrate': rate}
            with patch.dict(app.STATE, encoders=['libx264'], files=files, jobs=[]):
                app.enqueue(list(files), {**self.settings, 'sourcePreset': '75', 'mode': 'preserve', 'naming': 'custom', 'nameSuffix': 'lower', 'audio': 'copy'})
                self.assertEqual([j['settings']['customBitrate'] for j in app.STATE['jobs']], [30, 9])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class QualityIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.configure(shutil.which('ffmpeg'), shutil.which('ffprobe'))
        if not app.STATE.get('vmaf'):
            raise unittest.SkipTest('libvmaf required')
        threading.Thread(target=app.worker, daemon=True).start()
        threading.Thread(target=app.test_worker, daemon=True).start()

    def setUp(self):
        self.saved = copy.deepcopy({k: app.STATE[k] for k in ['files', 'jobs', 'queue_paused']})
        self.saved_tests = list(app.TEST_JOBS)
        self.saved_test_files = dict(app.TEST_FILES)
        app.TEST_JOBS.clear()
        app.TEST_FILES.clear()
        app.TEST_WAKE.clear()
        app.TEST_PAUSED = False
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.mkv'
        result = app.run([app.STATE['ffmpeg'], '-v', 'error', '-f', 'lavfi', '-i',
                          'testsrc2=size=320x180:rate=24', '-t', '3', '-c:v', 'libx264', '-crf', '0', str(self.source)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.item = app.probe(self.source)
        self.settings = dict(qualityMode='web', encodingMode='software', hardwareBackend='nvenc', priority='fast',
                             container='mkv', resolution='original', fps='original', audio='copy',
                             mode='preserve', naming='custom', nameSuffix='optimized')
        app.WAKE.clear()
        app.STATE.update(files={self.item['id']: self.item}, jobs=[], queue_paused=False)

    def tearDown(self):
        app.WAKE.clear()
        app.STATE.update(self.saved)
        app.TEST_JOBS[:] = self.saved_tests
        app.TEST_FILES.clear()
        app.TEST_FILES.update(self.saved_test_files)
        self.tmp.cleanup()

    def analyzer(self):
        return Analyzer(app.STATE['ffmpeg'], app.STATE['ffprobe'], app.command_for, lambda: False, lambda _: None)

    def wait_job(self):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            job = app.STATE['jobs'][-1]
            if job['status'] not in ['queued', 'running']:
                return job
            time.sleep(.05)
        self.fail('Job timed out')

    def test_real_vmaf_search_and_final_output(self):
        original = self.source.read_bytes()
        app.enqueue([self.item['id']], self.settings, auto_start=True)
        job = self.wait_job()
        self.assertEqual(job['status'], 'completed', job['error'])
        self.assertTrue(job['qualityResult']['winner']['scores'])
        self.assertIn(app.probe(Path(job['output']))['codec'], ['h264', 'hevc', 'av1'])
        self.assertEqual(original, self.source.read_bytes())
        self.assertFalse(list(self.root.glob('.archiver-*')))

    def test_real_av1_candidate_search(self):
        if 'libsvtav1' not in app.STATE['encoders']:
            self.skipTest('SVT-AV1 unavailable')
        result = self.analyzer().analyze(self.item, self.settings, ['libsvtav1'])
        self.assertEqual(result['winner']['codec'], 'av1')
        self.assertTrue(passes(result['winner']['scores'], POLICIES['web']))

    def test_long_source_uses_fresh_validation_scenes(self):
        source = self.root / 'long.mp4'
        result = app.run([app.STATE['ffmpeg'], '-v', 'error', '-f', 'lavfi', '-i',
                          'testsrc2=size=320x180:rate=24', '-t', '20', '-c:v', 'libx264', '-crf', '0', str(source)])
        self.assertEqual(result.returncode, 0, result.stderr)
        item = app.probe(source)
        result = self.analyzer().analyze(item, self.settings, ['libx264'])
        self.assertTrue(result['winner']['freshValidation'])
        self.assertEqual(result['winner']['sampleCount'], 3)
        self.assertLessEqual(result['winner']['sampleSeconds'], 30)
        self.assertLessEqual(result['winner']['encodedSampleSeconds'], 33)

    def test_source_directory_selection_preserves_media_library(self):
        library = dict(app.STATE['files'])
        app.TEST_SCAN_STOP.clear()
        app.scan_test_sources(self.root, False)
        self.assertEqual(app.STATE['files'], library)
        self.assertTrue(any(f['path'] == str(self.source) for f in app.TEST_FILES.values()))
        self.assertFalse(app.TEST_SCAN['running'])

    def test_recursive_scans_skip_generated_test_folders(self):
        folder = self.root / ('Archiver-test-' + 'a' * 20)
        folder.mkdir()
        (folder / 'quality-candidate.mp4').write_bytes(b'not-a-library-source')
        app.TEST_SCAN_STOP.clear()
        app.scan_test_sources(self.root, True)
        self.assertTrue(app.TEST_FILES)
        self.assertFalse(any('quality-candidate' in item['path'] for item in app.TEST_FILES.values()))
        app.SCAN_STOP.clear()
        app.STATE['scan'] = {'running': True, 'done': 0, 'total': 0, 'errors': []}
        app.scan(str(self.root), True)
        self.assertFalse(any('quality-candidate' in item['path'] for item in app.STATE['files'].values()))

    def test_source_directory_is_default_and_method_is_validated(self):
        with self.assertRaisesRegex(ValueError, 'preference'):
            app.enqueue_tests([self.item['id']], {**self.settings, 'encodingMode': 'both'}, str(self.root))
        self.assertEqual(app.TEST_JOBS, [])
        app.TEST_PAUSED = True
        app.TEST_WAKE.clear()
        try:
            app.enqueue_tests([self.item['id']], self.settings)
            job = app.TEST_JOBS[-1]
            self.assertEqual(Path(job['directory']), self.source.parent)
            self.assertEqual(Path(job['outputDirectory']).parent, self.source.parent)
            self.assertEqual(job['settings']['priority'], 'balanced')
        finally:
            app.TEST_JOBS[-1]['status'] = 'cancelled'
            app.TEST_PAUSED = False

    def test_auto_xpsnr_creates_one_preset_and_invalidates_changed_source(self):
        settings = {**self.settings, 'qualityMode': 'auto', 'autoEngine':'ab-av1', 'abCodec':'h264', 'abTarget':'perceptual','xpsnrTarget':40}
        with patch.dict(app.STATE, encoders=['libx264'], vmaf=False, xpsnr=True):
            ids = app.enqueue_tests([self.item['id']], settings)
            job = next(j for j in app.TEST_JOBS if j['id'] == ids[0])
            deadline = time.monotonic() + 60
            while job['finished'] is None and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertEqual(job['status'], 'completed', job['error'])
            self.assertEqual(set(job['result']['profiles']), {'perceptual'})
            self.assertEqual(job['result']['metric'],'xpsnr')
            self.assertEqual(job['result']['targetScore'],40.0)
            self.assertEqual(job['result']['policy']['mean'],40.0)
            self.assertEqual(app.usable_profiles(job,{**settings,'xpsnrTarget':38}),[])
            self.assertEqual(set(app.usable_profiles(job, settings)), {'perceptual'})
            app.TEST_JOBS.remove(job)  # Clearing finished queue entries retains generated presets.
            self.assertIn(job, app.auto_reports())
            app.enqueue([self.item['id']], {**settings, 'autoPreset': 'perceptual', 'autoTestId': job['id']})
            self.assertEqual(app.STATE['jobs'][-1]['settings']['qualityMode'], 'perceptual')
            self.assertEqual(app.STATE['jobs'][-1]['settings']['xpsnrTarget'],40)
            self.assertEqual(app.STATE['jobs'][-1]['settings']['requestedQualityMode'], 'auto')
            self.assertFalse(app.usable_profiles(job, {**settings, 'encodingMode': 'hardware'}))
            with self.source.open('ab') as out:
                out.write(b'changed')
            self.assertEqual(app.usable_profiles(job, settings), [])

    def test_real_test_queue_uses_chosen_directory_and_reports_progress(self):
        work = self.root / 'chosen-test-directory'
        work.mkdir()
        events = []
        analyzer = Analyzer(app.STATE['ffmpeg'], app.STATE['ffprobe'], app.command_for,
                            lambda: False, lambda _: None, work_directory=work, telemetry=events.append)
        # A bounded real run verifies telemetry and sample placement without depending on GPU drivers.
        result = analyzer.analyze(self.item, self.settings, ['libx264'])
        self.assertTrue(any(e.get('stage') == 'encoding' for e in events))
        self.assertTrue(any(e.get('stage') == 'scoring' for e in events))
        self.assertTrue(any(e.get('trialsCompleted', 0) > 0 for e in events))
        self.assertEqual(list(work.iterdir()), [])
        with patch.object(app, 'quality_analysis', return_value=result) as analysis:
            ids = app.enqueue_tests([self.item['id']], self.settings, str(work))
            deadline = time.monotonic() + 30
            job = next(j for j in app.TEST_JOBS if j['id'] == ids[0])
            while job['finished'] is None and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertEqual(job['status'], 'completed', job['error'])
            self.assertEqual(job['percent'], 100)
            folder = Path(job['outputDirectory'])
            self.assertEqual(folder.parent, work)
            self.assertTrue((folder / 'results.json').is_file())
            self.assertTrue((folder / 'quality-candidate.mp4').is_file())
            self.assertEqual(analysis.call_args.kwargs['work_directory'], folder)
            self.assertFalse(list(folder.glob('archiver-quality-*')))

    def test_waiting_test_can_be_cancelled_and_pause_is_preserved(self):
        with app.MEDIA_LOCK:
            ids = app.enqueue_tests([self.item['id']], self.settings, str(self.root))
            job = next(j for j in app.TEST_JOBS if j['id'] == ids[0])
            deadline = time.monotonic() + 5
            while job['status'] == 'queued' and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertEqual(job['status'], 'waiting')
            job['cancel'] = True
            while job['finished'] is None and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertEqual(job['status'], 'cancelled')
        app.TEST_PAUSED = True
        app.TEST_WAKE.clear()
        app.enqueue_tests([self.item['id']], self.settings, str(self.root))
        self.assertTrue(app.TEST_PAUSED)
        self.assertFalse(app.TEST_WAKE.is_set())
        self.assertEqual(app.TEST_JOBS[-1]['status'], 'queued')
        app.TEST_JOBS[-1]['status'] = 'cancelled'
        app.TEST_PAUSED = False

    def test_original_is_byte_identical_and_retains_extension(self):
        app.enqueue([self.item['id']], {**self.settings, 'qualityMode': 'original', 'container': 'mp4'}, auto_start=True)
        job = self.wait_job()
        self.assertEqual(job['status'], 'completed', job['error'])
        self.assertEqual(Path(job['output']).suffix, '.mkv')
        self.assertEqual(Path(job['output']).read_bytes(), self.source.read_bytes())
        with self.assertRaisesRegex(ValueError, 'already preserves'):
            app.enqueue([self.item['id']], {**self.settings, 'qualityMode': 'original', 'mode': 'overwrite'})

    def test_final_verification_rejects_degraded_output(self):
        output = self.root / 'bad.mkv'
        result = app.run([app.STATE['ffmpeg'], '-v', 'error', '-i', str(self.source), '-vf', 'boxblur=12', '-c:v', 'libx264', str(output)])
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.assertRaisesRegex(ValueError, 'failed sampled quality'):
            self.analyzer().verify_output(self.item, output, POLICIES['perceptual'])

    def test_frame_mismatch_is_rejected(self):
        output = self.root / 'short.mkv'
        app.run([app.STATE['ffmpeg'], '-v', 'error', '-i', str(self.source), '-t', '1', '-c:v', 'libx264', str(output)])
        with self.assertRaisesRegex(ValueError, 'frame counts'):
            self.analyzer().score(self.source, output, self.root, 24, 0)

    def test_fingerprint_invalidates_source_and_policy_changes(self):
        first = fingerprint(self.item, self.settings, app.STATE['ffmpeg'], app.STATE['ffprobe'])
        changed = fingerprint(self.item, {**self.settings, 'qualityMode': 'small'}, app.STATE['ffmpeg'], app.STATE['ffprobe'])
        self.assertNotEqual(first, changed)
        with self.source.open('ab') as out:
            out.write(b'changed')
        self.assertNotEqual(first, fingerprint(self.item, self.settings, app.STATE['ffmpeg'], app.STATE['ffprobe']))

    def test_larger_quality_passing_output_is_published(self):
        if not app.STATE.get('xpsnr'):
            self.skipTest('XPSNR required')
        source=self.root/'compact-source.mkv'
        made=app.run([app.STATE['ffmpeg'],'-v','error','-i',str(self.source),'-c:v','libx264','-crf','40',str(source)])
        self.assertEqual(made.returncode,0,made.stderr)
        item=app.probe(source);app.STATE['files'][item['id']]=item
        result={'keepOriginal':False,'winner':dict(codec='h264',encoder='libx264',bitrate='crf',qualityValue=0,encoderPriority='balanced'),
                'policy':{'metric':'xpsnr','mean':38.0}}
        with patch.object(app,'quality_analysis',return_value=result):
            app.enqueue([item['id']],{**self.settings,'mode':'preserve','container':'mkv'},auto_start=True)
            job=self.wait_job()
        self.assertEqual(job['status'],'completed',job['error'])
        self.assertGreater(Path(job['output']).stat().st_size,source.stat().st_size)
        self.assertTrue(source.exists())

    def test_skip_and_failed_verification_do_not_replace_original(self):
        original = self.source.read_bytes()
        winner = dict(codec='h264', encoder='libx264', bitrate='crf', qualityValue=18, encoderPriority='fast')
        for result, verification, status in [({'keepOriginal': True, 'note': 'Insufficient savings'}, None, 'skipped'),
                                              ({'keepOriginal': False, 'winner': winner}, ValueError('verification failed'), 'failed')]:
            with patch.object(app, 'quality_analysis', return_value=result), patch.object(Analyzer, 'verify_output', side_effect=verification):
                app.enqueue([self.item['id']], {**self.settings, 'mode': 'overwrite', 'container': 'mkv'}, auto_start=True)
                job = self.wait_job()
                self.assertEqual(job['status'], status, job['error'])
                self.assertEqual(self.source.read_bytes(), original)
                self.assertFalse(list(self.root.glob('.archiver-*')))


if __name__ == '__main__':
    unittest.main()
