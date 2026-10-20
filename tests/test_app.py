import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import subprocess
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import app


class ScanProgressTests(unittest.TestCase):
    def test_scan_reports_discovery_current_file_and_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.mp4').write_bytes(b'video')
            (root / 'b.mp4').write_bytes(b'bad')
            (root / 'notes.txt').write_text('ignore')
            nested = root / 'nested'
            nested.mkdir()
            (nested / 'c.mp4').write_bytes(b'video')
            def fake_probe(path, **kwargs):
                self.assertEqual(app.STATE['scan']['phase'], 'probing')
                self.assertIn(str(path), app.STATE['scan']['current'])
                if path.name == 'b.mp4':
                    raise ValueError('Unreadable')
                return {'id': path.name, 'name': path.name}
            app.SCAN_STOP.clear()
            app.STATE['scan'] = {'running': True, 'done': 0, 'total': 0, 'errors': []}
            with patch.object(app, 'probe', side_effect=fake_probe):
                app.scan(str(root), True, workers=4)
            status = app.STATE['scan']
            self.assertEqual(status['total'], 3)
            self.assertEqual(status['done'], 3)
            self.assertEqual(status['entries'], 4)
            self.assertEqual(status['folders'], 2)
            self.assertEqual(len(status['errors']), 1)
            self.assertFalse(status['running'])
            self.assertEqual(status['phase'], 'complete')
            self.assertGreaterEqual(status['finished'], status['started'])
            self.assertTrue(any('Skipped: b.mp4' in message for message in status['recent']))


class StopScanTests(unittest.TestCase):
    def test_stop_preserves_loaded_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ['a.mp4', 'b.mp4']:
                (root / name).write_bytes(b'video')
            app.SCAN_STOP.clear()
            app.STATE['scan'] = {'running': True, 'done': 0, 'total': 0, 'errors': []}
            def fake_probe(path, **kwargs):
                app.SCAN_STOP.set()
                return {'id': path.name, 'name': path.name}
            try:
                with patch.object(app, 'probe', side_effect=fake_probe):
                    app.scan(directory, False)
                self.assertEqual(app.STATE['scan']['phase'], 'stopped')
                self.assertEqual(app.STATE['scan']['done'], 1)
                self.assertEqual(len(app.STATE['files']), 1)
                self.assertEqual(app.STATE['scan']['errors'], [])
            finally:
                app.SCAN_STOP.clear()


class NamingTests(unittest.TestCase):
    def test_naming_modes(self):
        item = {'path': 'Clip.mov', 'width': 1280, 'height': 720, 'fps': 59.94}
        settings = dict(container='mkv', resolution='1080', fps='original', bitrate='auto')
        for naming, extra, expected in [
            ('default', {}, 'Clip.mkv'),
            ('custom', {'nameSuffix': 'archived'}, 'Clip_archived.mkv'),
            ('resolution', {}, 'Clip_1280x720.mkv'),
            ('framerate', {}, 'Clip_59.94fps.mkv'),
            ('quality', {}, 'Clip_source-bitrate.mkv'),
            ('settings', {}, 'Clip_1280x720_59.94fps_source-bitrate.mkv'),
            ('batch', {'batchName': 'Vacation'}, 'Vacation_002.mkv'),
        ]:
            with self.subTest(naming=naming):
                self.assertEqual(app.output_name(item, {**settings, 'naming': naming, **extra}, 2), expected)
        self.assertEqual(app.output_name(item, {**settings, 'mode': 'copy', 'naming': 'custom', 'nameSuffix': 'backup'}), 'Clip_backup.mov')
        self.assertEqual(app.output_name(item, {**settings, 'mode': 'overwrite', 'naming': 'batch'}), 'Clip.mov')

    def test_invalid_names(self):
        item = {'path': 'Clip.mp4'}
        for suffix in ['', '../elsewhere', 'bad:name', 'bad\\name']:
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                app.output_name(item, {'naming': 'custom', 'nameSuffix': suffix})
        with self.assertRaises(ValueError):
            app.output_name(item, {'naming': 'batch', 'batchName': 'CON'})


class ReplacementTests(unittest.TestCase):
    def test_recycle_failure_retains_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, encoded = root / 'video.mp4', root / 'encoded.mp4'
            original.write_bytes(b'original')
            encoded.write_bytes(b'encoded')
            with patch.object(app, 'recycle_file', side_effect=OSError('Recycle unavailable')):
                with self.assertRaisesRegex(OSError, 'Original retained'):
                    app.replace_original(encoded, original)
            self.assertEqual(original.read_bytes(), b'encoded')
            self.assertEqual(next(root.glob('.archiver-original-*/video.mp4')).read_bytes(), b'original')

    def test_publish_failure_restores_original(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / 'video.mp4'
            original.write_bytes(b'original')
            with self.assertRaises(OSError):
                app.replace_original(Path(directory) / 'missing.mp4', original)
            self.assertEqual(original.read_bytes(), b'original')

    @unittest.skipUnless(app.sys.platform == 'win32', 'Windows Recycle Bin required')
    def test_windows_recycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, encoded = root / 'disposable-recycle-test.txt', root / 'encoded.txt'
            original.write_bytes(b'disposable original for Archiver test')
            encoded.write_bytes(b'encoded')
            app.replace_original(encoded, original)
            self.assertEqual(original.read_bytes(), b'encoded')
            self.assertFalse(list(root.glob('.archiver-original-*')))


class FolderPickerTests(unittest.TestCase):
    def test_selection_and_cancellation(self):
        for directory in [str(Path.cwd()), '']:
            with self.subTest(directory=directory), patch.object(app.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps({'directory': directory}), '')) as launch:
                self.assertEqual(app.browse_directory(str(Path.cwd())), directory)
                self.assertEqual(launch.call_args.args[0][1], str(app.ROOT / 'folder_picker.py'))

    def test_unavailable_picker_has_manual_fallback(self):
        with patch.object(app.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'Tk unavailable')):
            with self.assertRaisesRegex(ValueError, 'paste the folder path'):
                app.browse_directory()
        self.assertFalse(app.BROWSE_LOCK.locked())


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg and FFprobe required')
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.configure(shutil.which('ffmpeg'), shutil.which('ffprobe'))
        threading.Thread(target=app.worker, daemon=True).start()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'sample.mp4'
        result = app.run([app.STATE['ffmpeg'], '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=24', '-t', '1', '-c:v', 'libx264', str(self.source)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.item = app.probe(self.source)
        with app.LOCK:
            app.WAKE.clear()
            app.STATE['queue_paused'] = False
            app.STATE['files'] = {self.item['id']: self.item}
            app.STATE['jobs'] = []
        self.settings = dict(codec='h264', encoder='libx264', resolution='720', fps='30', bitrate='1000k', container='mp4', audio='aac', mode='preserve', destination='', naming='custom', nameSuffix='encoded')

    def tearDown(self):
        self.tmp.cleanup()

    def wait_job(self):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            job = app.STATE['jobs'][-1]
            if job['status'] not in ['running', 'queued']:
                self.assertEqual(job['status'], 'completed', str(job['error']) + '\n' + '\n'.join(job['log']))
                return job
            time.sleep(.05)
        self.fail('Job timed out')

    def test_real_encode_and_metadata(self):
        original = self.source.read_bytes()
        self.assertEqual(self.item['width'], 160)
        self.assertAlmostEqual(self.item['fps'], 24)
        app.enqueue([self.item['id']], self.settings, auto_start=True)
        job = self.wait_job()
        self.assertEqual(job['source_size'], len(original))
        self.assertEqual(job['output_size'], Path(job['output']).stat().st_size)
        output = app.probe(Path(job['output']))
        self.assertEqual(output['codec'], 'h264')
        self.assertEqual(output['width'], 160)  # no upscaling
        self.assertAlmostEqual(output['fps'], 30)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(list(self.root.glob('.archiver-*')))
        with self.assertRaisesRegex(ValueError, 'already exists'):
            app.enqueue([self.item['id']], self.settings, auto_start=True)

    def test_manual_quality_and_custom_bitrate(self):
        for mode, extra in [('crf', {'qualityValue': '21'}), ('custom', {'customBitrate': '7.5'})]:
            output = self.root / (mode + '.mp4')
            command = app.command_for(self.source, output, {**self.settings, 'bitrate': mode, **extra})
            result = app.run(command)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.stat().st_size)
            self.assertIn('21' if mode == 'crf' else '7500k', command)
        for mode, extra in [('crf', {'qualityValue': '100'}), ('custom', {'customBitrate': 'nan'}), ('cqp', {'qualityValue': '20'})]:
            with self.assertRaises(ValueError):
                app.command_for(self.source, self.root / 'bad.mp4', {**self.settings, 'bitrate': mode, **extra})
        item = {**self.item, 'video_bitrate': 1000000}
        result = app.recommend_quality([item], self.settings)
        self.assertEqual(result['mode'], 'crf')
        self.assertGreater(result['value'], 0)
        with self.assertRaises(ValueError):
            app.recommend_quality([], self.settings)

    def test_automatic_source_bitrate_encode(self):
        original = self.source.read_bytes()
        self.settings.update(bitrate='auto', resolution='original', fps='original')
        app.enqueue([self.item['id']], self.settings, auto_start=True)
        job = self.wait_job()
        output = app.probe(Path(job['output']))
        self.assertEqual((output['width'], output['height']), (160, 90))
        self.assertAlmostEqual(output['fps'], 24)
        self.assertEqual(self.source.read_bytes(), original)

    def test_queue_waits_for_manual_start(self):
        app.enqueue([self.item['id']], self.settings)
        self.assertFalse(app.WAKE.is_set())
        self.assertEqual(app.STATE['jobs'][-1]['status'], 'queued')
        self.assertFalse((self.root / 'sample_encoded.mp4').exists())
        app.start_queue()
        self.wait_job()

    def test_permanent_delete_requires_confirmation(self):
        with self.assertRaisesRegex(ValueError, 'Confirm'):
            app.enqueue([self.item['id']], {**self.settings, 'mode': 'overwrite', 'deleteOriginal': True})
        self.assertEqual(app.STATE['jobs'], [])

    def test_pause_and_stop_queue(self):
        app.enqueue([self.item['id']], self.settings)
        app.pause_queue()
        self.assertTrue(app.STATE['queue_paused'])
        self.assertFalse(app.WAKE.is_set())
        self.assertEqual(app.STATE['jobs'][0]['status'], 'queued')
        app.start_queue()
        self.wait_job()
        with patch.object(app, 'PROCESS') as process:
            app.STATE['jobs'][0]['status'] = 'running'
            app.pause_queue(stop=True)
            self.assertTrue(app.STATE['jobs'][0]['cancel'])
            process.terminate.assert_called_once()
            app.STATE['jobs'][0]['status'] = 'cancelled'
        app.STATE['queue_paused'] = False

    def test_start_empty_queue(self):
        with self.assertRaisesRegex(ValueError, 'Add files'):
            app.start_queue()

    def test_audio_codecs_and_bitrates(self):
        source = self.root / 'audio-source.mkv'
        result = app.run([app.STATE['ffmpeg'], '-v', 'error', '-i', str(self.source), '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-c:v', 'copy', '-c:a', 'pcm_s16le', '-shortest', str(source)])
        self.assertEqual(result.returncode, 0, result.stderr)
        for codec, container, bitrate in [('aac', 'mp4', '128k'), ('mp3', 'mp4', '320k'), ('opus', 'mkv', '128k'), ('flac', 'mkv', '192k')]:
            with self.subTest(codec=codec):
                output = self.root / f'audio-{codec}.{container}'
                settings = {**self.settings, 'audio': codec, 'audioBitrate': bitrate}
                command = app.command_for(source, output, settings)
                result = app.run(command)
                self.assertEqual(result.returncode, 0, result.stderr)
                metadata = json.loads(app.run([app.STATE['ffprobe'], '-v', 'error', '-show_streams', '-of', 'json', str(output)]).stdout)
                audio = next(s for s in metadata['streams'] if s['codec_type'] == 'audio')
                self.assertEqual(audio['codec_name'], codec)
                if codec in ['aac', 'mp3']:
                    self.assertLess(abs(int(audio['bit_rate']) - int(bitrate[:-1])*1000), int(bitrate[:-1])*1000*.4)
        with self.assertRaisesRegex(ValueError, 'bitrate'):
            app.command_for(source, self.root / 'bad.mp4', {**self.settings, 'audioBitrate': 'invalid'})
        with self.assertRaisesRegex(ValueError, 'MKV'):
            app.command_for(source, self.root / 'bad.mp4', {**self.settings, 'audio': 'flac'})

    def test_automatic_metadata_modes(self):
        base = {**self.settings, 'bitrate': 'auto'}
        for rate_mode in ['vbr', 'cbr', '']:
            metadata = {'codec': 'h264', 'video_bitrate': 2345678, 'rate_mode': rate_mode}
            command = app.command_for(self.source, self.root / 'out.mp4', {**base, 'sourceMetadata': metadata})
            self.assertEqual(command[command.index('-b:v') + 1], '2345678')
            self.assertEqual('-maxrate' in command, rate_mode == 'cbr')
        command = app.command_for(self.source, self.root / 'out.mp4', {**base, 'sourceMetadata': {'codec': 'h264', 'rate_mode': 'crf', 'source_quality': 19}})
        self.assertEqual(command[command.index('-crf') + 1], '19')
        with self.assertRaisesRegex(ValueError, 'Automatic cannot find'):
            app.command_for(self.source, self.root / 'out.mp4', {**base, 'sourceMetadata': {'codec': 'h264'}})


    def test_overwrite_and_mismatched_container(self):
        self.settings.update(mode='overwrite', container='mkv', deleteOriginal=True, confirmDelete=True)
        with self.assertRaisesRegex(ValueError, 'container'):
            app.enqueue([self.item['id']], self.settings, auto_start=True)
        self.settings['container'] = 'mp4'
        app.enqueue([self.item['id']], self.settings, auto_start=True)
        self.wait_job()
        self.assertAlmostEqual(app.probe(self.source)['fps'], 30)

    def test_copy_and_move(self):
        destination = self.root / 'output'
        destination.mkdir()
        original = self.source.read_bytes()
        self.settings.update(mode='copy', destination=str(destination), naming='default')
        app.enqueue([self.item['id']], self.settings, auto_start=True)
        self.wait_job()
        self.assertEqual((destination / self.source.name).read_bytes(), original)
        self.assertTrue(self.source.exists())
        (destination / self.source.name).unlink()
        self.settings['mode'] = 'move'
        app.enqueue([self.item['id']], self.settings, auto_start=True)
        self.wait_job()
        self.assertFalse(self.source.exists())
        self.assertEqual((destination / self.source.name).read_bytes(), original)

    def test_failure_preserves_source(self):
        original = self.source.read_bytes()
        self.settings['mode'] = 'overwrite'
        with self.assertRaises(ValueError):
            app.enqueue([self.item['id']], {**self.settings, 'encoder': 'arbitrary-command'})
        build_command = app.command_for
        with patch.object(app, 'command_for', side_effect=lambda *args: build_command(*args)[:-1] + ['-nonexistent-option', str(args[1])]):
            app.enqueue([self.item['id']], self.settings, auto_start=True)
            deadline = time.monotonic() + 10
            while app.STATE['jobs'][-1]['status'] in ['queued', 'running'] and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertEqual(app.STATE['jobs'][-1]['status'], 'failed')
        self.assertEqual(self.source.read_bytes(), original)

    def test_cancel_preserves_source(self):
        original = self.source.read_bytes()
        self.settings['mode'] = 'overwrite'
        build_command = app.command_for
        def throttled(*args):
            command = build_command(*args)
            command.insert(command.index('-i'), '-re')
            return command
        with patch.object(app, 'command_for', side_effect=throttled):
            app.enqueue([self.item['id']], self.settings, auto_start=True)
            deadline = time.monotonic() + 10
            while app.PROCESS is None and time.monotonic() < deadline:
                time.sleep(.01)
            with app.LOCK:
                self.assertIsNotNone(app.PROCESS)
                app.STATE['jobs'][-1]['cancel'] = True
                app.PROCESS.terminate()
            while app.STATE['jobs'][-1]['status'] == 'running' and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertEqual(app.STATE['jobs'][-1]['status'], 'cancelled')
        self.assertEqual(self.source.read_bytes(), original)

    def test_http_and_preview(self):
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base) as response:
                self.assertIn(b'Archiver', response.read())
            with self.assertRaises(HTTPError) as denied:
                urlopen(base + '/api/state')
            self.assertEqual(denied.exception.code, 403)
            denied.exception.close()
            with urlopen(Request(base + '/api/state', headers={'X-Token': app.TOKEN})) as response:
                self.assertEqual(len(json.load(response)['files']), 1)
            with patch.object(app, 'browse_directory', return_value=str(self.root)):
                request = Request(base + '/api/browse', data=b'{"initial":""}', headers={'X-Token': app.TOKEN, 'Content-Type': 'application/json'})
                with urlopen(request) as response:
                    self.assertEqual(json.load(response)['directory'], str(self.root))
            with urlopen(base + f'/api/thumbnail?id={self.item["id"]}&token={app.TOKEN}') as response:
                self.assertEqual(response.headers['Content-Type'], 'image/jpeg')
                self.assertTrue(response.read().startswith(b'\xff\xd8'))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
