import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import notification_history as history
class NotificationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.file=Path(self.temp.name)/'history.json';self.mock=patch.object(history,'path',return_value=self.file);self.mock.start()
 def tearDown(self):self.mock.stop();self.temp.cleanup()
 def test_persistence_read_clear(self):
  item=history.add('Saved','My preset','success');self.assertEqual(history.snapshot()['items'][0]['id'],item['id']);self.assertEqual(history.snapshot()['unread'],1)
  self.assertEqual(history.change('read')['unread'],0);self.assertEqual(history.change('clear')['items'],[])
 def test_terminal_queue_events_and_deduplication(self):
  job={'id':'one','name':'A video.mp4','status':'running'};self.assertIsNone(history.queue_result(job,'encoding'))
  job['status']='completed';first=history.queue_result(job,'encoding');again=history.queue_result(job,'encoding');self.assertEqual(first['id'],again['id']);self.assertEqual(len(history.snapshot()['items']),1)
  job.update(status='failed',error='Encoder unavailable');error=history.queue_result(job,'encoding');self.assertEqual(error['level'],'error');self.assertIn('Encoder unavailable',error['message'])
  job.update(id='test',status='completed',queueError='Destination missing');self.assertEqual(history.queue_result(job,'test')['level'],'error')
  job.update(id='cancelled',status='cancelled',queueError='');self.assertEqual(history.queue_result(job,'test')['level'],'info')
 def test_bounded_history_and_parallel_writes(self):
  with patch.object(history,'LIMIT',10),ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda i:history.add(str(i)),range(25)))
  self.assertEqual(len(history.snapshot()['items']),10)
 def test_corruption_and_invalid_events_do_not_destroy_history(self):
  history.add('Saved');original=self.file.read_bytes()
  for args in [('',),('x'*201,),('Valid','x','bad')]:
   with self.assertRaises(ValueError):history.add(*args)
  self.assertEqual(self.file.read_bytes(),original)
  self.file.write_text('{bad')
  with self.assertRaises(ValueError):history.add('Do not overwrite')
  self.assertEqual(self.file.read_text(),'{bad')
 def test_history_write_error_cannot_fail_media_job(self):
  import app
  with patch.object(history,'queue_result',side_effect=OSError('disk full')):app.notify_queue_result({'status':'completed'},'encoding')
 def test_unchanged_history_avoids_retransmitting_entries(self):
  first=history.snapshot();self.assertTrue(history.snapshot(first['revision'])['unchanged'])
  history.add('New item');changed=history.snapshot(first['revision']);self.assertEqual(len(changed['items']),1)
  self.assertTrue(history.snapshot(changed['revision'])['unchanged'])
if __name__=='__main__':unittest.main()
