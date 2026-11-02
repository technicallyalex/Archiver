import copy
from pathlib import Path
import shutil
import tempfile
import unittest

import app


class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise unittest.SkipTest('FFmpeg tools required')

    def setUp(self):
        self.old = copy.deepcopy(app.STATE)
        app.configure(shutil.which('ffmpeg'), shutil.which('ffprobe'))
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root/'source.mkv'
        result=app.run([app.STATE['ffmpeg'],'-v','error','-f','lavfi','-i','testsrc2=size=96x64:rate=12:duration=1',
                        '-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','ffv1','-c:a','pcm_s16le',str(self.source)])
        self.assertEqual(result.returncode,0,result.stderr)
        self.item=app.probe(self.source)
        app.STATE['files']={self.item['id']:self.item};app.STATE['jobs']=[]

    def tearDown(self):
        app.STATE.clear();app.STATE.update(self.old)
        self.tmp.cleanup()

    def settings(self, profile):
        return dict(qualityMode='archive',archiveProfile=profile,mode='preserve',naming='custom',nameSuffix='archive')

    def test_profiles_resolve_container_and_keep_originals(self):
        for profile,extension in [('prores','.mov')]:
            app.STATE['jobs']=[]
            app.enqueue([self.item['id']],self.settings(profile))
            job=app.STATE['jobs'][0]
            self.assertEqual(Path(job['output']).suffix,extension)
            self.assertEqual(job['settings']['sourceMetadata']['fps'],12)
            self.assertNotEqual(job['output'],str(self.source))
        with self.assertRaises(ValueError):
            app.enqueue([self.item['id']],{**self.settings('ffv1'),'mode':'overwrite'})

    def test_removed_archival_outputs_are_rejected(self):
        for profile in ['ffv1', 'copy']:
            with self.assertRaises(ValueError):
                app.enqueue([self.item['id']], self.settings(profile))

    def test_prores_hq_uses_10bit_422_pcm_and_verifies(self):
        app.enqueue([self.item['id']],self.settings('prores'))
        job=app.STATE['jobs'][0];target=Path(job['output'])
        result=app.run(app.command_for(self.source,target,job['settings']))
        self.assertEqual(result.returncode,0,result.stderr)
        info=app.probe(target)
        self.assertEqual(info['codec'],'prores')
        self.assertEqual(info['pixel_format'],'yuv422p10le')
        self.assertEqual(info['audio'],'pcm_s24le')
        app.verify_archive(job,target)
        bad={**job['settings'],'sourceMetadata':{**self.item,'color_transfer':'smpte2084'}}
        with self.assertRaises(ValueError):
            app.command_for(self.source,target,bad)
