import collections
import copy
from concurrent.futures import ThreadPoolExecutor
import errno
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import app
import exclusion_preferences
import output_names


class OutputNamesTests(unittest.TestCase):
    def test_existing_and_reserved_names_get_next_available_number(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);base=root/'Take.mp4';base.write_bytes(b'original');(root/'Take_002.mp4').mkdir()
            names=output_names.Names([root/'Take_003.mp4'])
            self.assertEqual(names.reserve(base).name,'Take_004.mp4')
            self.assertEqual(names.reserve(base).name,'Take_005.mp4')
            self.assertEqual(base.read_bytes(),b'original')

    def test_large_batch_enumerates_each_folder_once_and_caps_name_length(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);names=output_names.Names()
            with patch.object(output_names.os,'scandir',wraps=os.scandir) as scan:
                result=[names.reserve(root/'Clip.mov') for _ in range(1000)]
                self.assertEqual(scan.call_count,1)
            self.assertEqual(len(set(result)),1000);self.assertEqual(result[-1].name,'Clip_1000.mov')
            long=root/('a'*251+'.mp4');names=output_names.Names([long])
            self.assertEqual(len(names.reserve(long).name),255)

    def test_publication_handles_late_collisions_and_copy_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);base=root/'Clip.mp4';base.write_bytes(b'keep');temp=root/'temporary';temp.write_bytes(b'new')
            job={'outputBase':str(base),'output':str(base),'status':'running','log':collections.deque()}
            with patch.dict(app.STATE,jobs=[job]),patch.object(app.os,'link',side_effect=OSError(errno.EXDEV,'cross-device')):
                actual=app.publish_unique(job,temp,base)
            self.assertEqual(actual.name,'Clip_002.mp4');self.assertEqual(base.read_bytes(),b'keep');self.assertEqual(actual.read_bytes(),b'new')

    def test_simultaneous_publication_reserves_distinct_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);base=root/'Clip.mp4';base.write_bytes(b'keep')
            jobs=[];temps=[]
            for i in range(2):
                planned=root/f'Clip_{i+2:03d}.mp4';planned.write_bytes(b'external')
                temp=root/f'temp{i}';temp.write_bytes(bytes([i]));temps.append(temp)
                jobs.append(dict(outputBase=str(base),output=str(planned),status='running',log=collections.deque()))
            with patch.dict(app.STATE,jobs=jobs),ThreadPoolExecutor(max_workers=2) as pool:
                outputs=list(pool.map(lambda pair:app.publish_unique(pair[0],pair[1],Path(pair[0]['output'])),zip(jobs,temps)))
            self.assertEqual(len(set(outputs)),2)
            self.assertEqual({p.name for p in outputs},{'Clip_004.mp4','Clip_005.mp4'})
            self.assertEqual((root/'Clip_002.mp4').read_bytes(),b'external')

    def test_old_exclusion_preference_cannot_reenable_name_skipping(self):
        self.assertNotIn('skipParentCopies',exclusion_preferences.validate({'skipParentCopies':True}))


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Video tools required')
class CollisionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.old=copy.deepcopy(app.STATE);app.configure(shutil.which('ffmpeg'),shutil.which('ffprobe'))
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.source=self.root/'source.mp4'
        r=app.run([app.STATE['ffmpeg'],'-v','error','-f','lavfi','-i','testsrc2=s=96x64:r=10:d=1','-c:v','libx264',str(self.source)])
        self.assertEqual(r.returncode,0,r.stderr)
        self.item=app.probe(self.source);app.STATE['files']={self.item['id']:self.item};app.STATE['jobs']=[]
        self.settings=dict(qualityMode='custom',codec='h264',encoder='libx264',container='mp4',audio='copy',bitrate='custom',customBitrate=1,mode='preserve',naming='custom',nameSuffix='archiver')
    def tearDown(self):app.STATE.clear();app.STATE.update(self.old);self.tmp.cleanup()

    def test_late_collision_keeps_both_files_and_does_not_reencode(self):
        original=self.source.read_bytes();app.enqueue([self.item['id']],self.settings)
        job=app.STATE['jobs'][0];planned=Path(job['output']);command=app.command_for
        def raced(*args,**kwargs):planned.write_bytes(b'created after queueing');return command(*args,**kwargs)
        with patch.object(app,'command_for',side_effect=raced) as encode:app.execute_job(job)
        self.assertEqual(encode.call_count,1);self.assertEqual(job['status'],'completed',job['error'])
        self.assertEqual(Path(job['output']).name,planned.stem+'_002.mp4')
        self.assertEqual(planned.read_bytes(),b'created after queueing');self.assertEqual(self.source.read_bytes(),original)
        self.assertEqual(app.probe(Path(job['output']))['codec'],'h264')

    def test_batch_and_separate_queue_requests_share_name_reservations(self):
        folder=self.root/'sub';folder.mkdir();other=folder/self.source.name;shutil.copyfile(self.source,other)
        second=app.probe(other);app.STATE['files'][second['id']]=second
        target=self.root/'outputs';target.mkdir();(target/'source.mp4').write_bytes(b'existing')
        settings={**self.settings,'mode':'directory','destination':str(target),'naming':'template','filenameTemplate':'{original}'}
        app.enqueue([self.item['id']],settings,dry_run=True);self.assertEqual(app.STATE['jobs'],[])
        app.enqueue([self.item['id']],settings);app.enqueue([second['id']],settings)
        self.assertEqual([Path(j['output']).name for j in app.STATE['jobs']],['source_002.mp4','source_003.mp4'])
        self.assertEqual((target/'source.mp4').read_bytes(),b'existing')
