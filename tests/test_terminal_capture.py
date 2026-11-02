import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import app
from terminal_screen import Screen


class ScreenTests(unittest.TestCase):
    def test_cursor_redraw_and_wrapped_json(self):
        screen=Screen(columns=30)
        self.assertIn(('stderr','old progress'),screen.feed('old progress'))
        output=screen.feed('\r\x1b[2Knew progress\r\n')
        self.assertIn(('stderr','new progress'),output)
        result='{"type":"crf-search-done","crf":23,"xpsnr":38}'
        events=[]
        for chunk in [result[:13],result[13:30],result[30:]]:events.extend(screen.feed(chunk))
        self.assertTrue(any(channel=='stdout' and 'crf-search-done' in text for channel,text in events))
        self.assertFalse(any(channel=='stdout' for channel,text in screen.feed('')))

    @unittest.skipUnless(os.name=='nt','Windows terminal required')
    def test_hidden_terminal_cancellation(self):
        try:
            from terminal_capture import run
        except ImportError:
            self.skipTest('pywinpty unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            start=time.monotonic()
            with self.assertRaises(InterruptedError):
                run([sys.executable,'-c','import time;time.sleep(60)'],tmp,os.environ.copy(),lambda:time.monotonic()-start>.4,lambda _:None)
            self.assertLess(time.monotonic()-start,10)
