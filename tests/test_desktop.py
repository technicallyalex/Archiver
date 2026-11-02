import ctypes as ct
from ctypes import wintypes as wt
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch


@unittest.skipUnless(sys.platform == 'win32', 'Native Windows tray required')
class DesktopTests(unittest.TestCase):
    def test_single_instance_lock_releases(self):
        from windows_tray import InstanceLock
        name = 'unit-test-' + str(time.monotonic_ns())
        first, second = InstanceLock(name), InstanceLock(name)
        try:
            self.assertFalse(first.existing)
            self.assertTrue(second.existing)
        finally:
            first.close()
            second.close()
        third = InstanceLock(name)
        try:
            self.assertFalse(third.existing)
        finally:
            third.close()

    def test_shutdown_cancels_waiting_work_and_stops_server(self):
        import app
        server = Mock()
        encode = {'status': 'queued', 'cancel': False}
        test = {'status': 'queued', 'cancel': False}
        try:
            with patch.dict(app.STATE, jobs=[encode], scan={'running': False}, queue_paused=False), patch.object(app, 'TEST_JOBS', [test]), patch.object(app, 'TEST_SCAN', {'running': False}), patch.object(app, 'PROCESS', None):
                app.stop_application(server)
                self.assertEqual(encode['status'], 'cancelled')
                self.assertEqual(test['status'], 'cancelled')
                self.assertTrue(encode['cancel'] and test['cancel'])
                self.assertTrue(app.SHUTTING_DOWN.is_set())
                server.shutdown.assert_called_once()
        finally:
            app.SHUTTING_DOWN.clear()
            app.SCAN_STOP.clear()
            app.TEST_SCAN_STOP.clear()

    def test_native_tray_opens_and_quits_without_a_visible_window(self):
        from windows_tray import Tray, _bind
        opened, finished = threading.Event(), threading.Event()
        errors = []
        tray = Tray('Archiver native test', [('Open', lambda: True, opened.set)], lambda: 'Idle', lambda force=False: True)
        def run():
            try:
                tray.run()
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        post = _bind(tray.user, 'PostMessageW', wt.BOOL, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
        try:
            deadline = time.monotonic() + 5
            while (not tray.hwnd or not hasattr(tray, 'data')) and not finished.is_set() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertFalse(errors, str(errors))
            self.assertTrue(tray.hwnd)
            self.assertFalse(_bind(tray.user, 'IsWindowVisible', wt.BOOL, wt.HWND)(tray.hwnd))
            self.assertTrue(tray.notify(1, ct.byref(tray.data)))
            self.assertEqual(ct.sizeof(tray.data), 976 if ct.sizeof(ct.c_void_p) == 8 else 956)
            post(tray.hwnd, tray.CALLBACK, 0, 0x202)
            self.assertTrue(opened.wait(3))
            post(tray.hwnd, 0x10, 0, 0)
            self.assertTrue(finished.wait(5), 'Tray did not exit')
            self.assertFalse(errors, str(errors))
        finally:
            if tray.hwnd:
                post(tray.hwnd, 0x10, 0, 0)
            thread.join(5)
