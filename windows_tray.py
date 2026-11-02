"""Native Windows notification-area icon, using only the standard library."""
import ctypes as ct
from ctypes import wintypes as wt
import logging
import os
from pathlib import Path
import time


def _bind(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype, function.argtypes = result, arguments
    return function


class InstanceLock:
    def __init__(self, port):
        self.kernel = ct.WinDLL('kernel32', use_last_error=True)
        create = _bind(self.kernel, 'CreateMutexW', wt.HANDLE, ct.c_void_p, wt.BOOL, wt.LPCWSTR)
        self.handle = create(None, False, f'Local\\Archiver-port-{port}')
        if not self.handle:
            raise ct.WinError(ct.get_last_error())
        self.existing = ct.get_last_error() == 183

    def close(self):
        if self.handle:
            _bind(self.kernel, 'CloseHandle', wt.BOOL, wt.HANDLE)(self.handle)
            self.handle = None


class Tray:
    CALLBACK = 0x8001

    def __init__(self, title, actions, status, on_quit):
        self.title, self.actions, self.status, self.on_quit = title, actions, status, on_quit
        self.user = ct.WinDLL('user32', use_last_error=True)
        self.shell = ct.WinDLL('shell32', use_last_error=True)
        self.kernel = ct.WinDLL('kernel32', use_last_error=True)
        self.hwnd = None
        self.last_open = -10.
        self.callback_error = None
        self.proc_type = ct.WINFUNCTYPE(ct.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

        class WindowClass(ct.Structure):
            _fields_ = [('style', wt.UINT), ('proc', self.proc_type), ('classExtra', ct.c_int),
                        ('windowExtra', ct.c_int), ('instance', wt.HINSTANCE), ('icon', wt.HICON),
                        ('cursor', wt.HANDLE), ('background', wt.HBRUSH), ('menu', wt.LPCWSTR), ('name', wt.LPCWSTR)]

        class Guid(ct.Structure):
            _fields_ = [('a', wt.DWORD), ('b', wt.WORD), ('c', wt.WORD), ('d', ct.c_ubyte * 8)]

        class IconData(ct.Structure):
            _fields_ = [('size', wt.DWORD), ('window', wt.HWND), ('id', wt.UINT), ('flags', wt.UINT),
                        ('message', wt.UINT), ('icon', wt.HICON), ('tip', wt.WCHAR * 128),
                        ('state', wt.DWORD), ('stateMask', wt.DWORD), ('info', wt.WCHAR * 256),
                        ('version', wt.UINT), ('infoTitle', wt.WCHAR * 64), ('infoFlags', wt.DWORD),
                        ('guid', Guid), ('balloonIcon', wt.HICON)]

        self.window_class_type, self.icon_type = WindowClass, IconData
        self.notify = _bind(self.shell, 'Shell_NotifyIconW', wt.BOOL, wt.DWORD, ct.POINTER(IconData))
        self.default_proc = _bind(self.user, 'DefWindowProcW', ct.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
        self.destroy_window = _bind(self.user, 'DestroyWindow', wt.BOOL, wt.HWND)
        self.callback = self.proc_type(self._message)
        self.instance = _bind(self.kernel, 'GetModuleHandleW', wt.HINSTANCE, wt.LPCWSTR)(None)
        self.class_name = f'ArchiverTray_{os.getpid()}_{id(self)}'
        self.taskbar_created = _bind(self.user, 'RegisterWindowMessageW', wt.UINT, wt.LPCWSTR)('TaskbarCreated')

    def _icon(self):
        # Load the same A-r artwork used for the browser and executable.
        artwork = Path(__file__).resolve().parent / 'web/assets/archiver.ico'
        if artwork.is_file():
            load = _bind(self.user, 'LoadImageW', wt.HANDLE, wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ct.c_int, ct.c_int, wt.UINT)
            icon = load(None, str(artwork), 1, 32, 32, 0x10)
            if icon:
                return icon
        pixels = bytearray()
        for y in range(32):
            for x in range(32):
                left, right = 16 - (y - 7) * .48, 16 + (y - 7) * .48
                letter = 7 <= y <= 25 and (abs(x - left) <= 1.4 or abs(x - right) <= 1.4 or (18 <= y <= 20 and left <= x <= right))
                pixels.extend((132, 237, 192, 255) if letter else (28, 32, 24, 255))
        mask = (ct.c_ubyte * 128)()
        color = (ct.c_ubyte * len(pixels)).from_buffer_copy(pixels)
        create = _bind(self.user, 'CreateIcon', wt.HICON, wt.HINSTANCE, ct.c_int, ct.c_int, wt.BYTE, wt.BYTE, ct.c_void_p, ct.c_void_p)
        icon = create(self.instance, 32, 32, 1, 32, mask, color)
        if not icon:
            raise ct.WinError(ct.get_last_error())
        return icon

    def _open(self):
        if time.monotonic() - self.last_open > .6:
            self.last_open = time.monotonic()
            self.actions[0][2]()

    def _menu(self):
        menu = _bind(self.user, 'CreatePopupMenu', wt.HMENU)()
        if not menu:
            raise ct.WinError(ct.get_last_error())
        append = _bind(self.user, 'AppendMenuW', wt.BOOL, wt.HMENU, wt.UINT, ct.c_size_t, wt.LPCWSTR)
        try:
            append(menu, 2, 0, self.status())
            append(menu, 0x800, 0, None)
            for index, (label, enabled, _) in enumerate(self.actions, 100):
                append(menu, 0 if enabled() else 2, index, label)
            append(menu, 0x800, 0, None)
            append(menu, 0, 200, 'Quit Archiver')
            point = wt.POINT()
            _bind(self.user, 'GetCursorPos', wt.BOOL, ct.POINTER(wt.POINT))(ct.byref(point))
            _bind(self.user, 'SetForegroundWindow', wt.BOOL, wt.HWND)(self.hwnd)
            chosen = _bind(self.user, 'TrackPopupMenu', wt.UINT, wt.HMENU, wt.UINT, ct.c_int, ct.c_int, ct.c_int, wt.HWND, ct.c_void_p)(menu, 0x102, point.x, point.y, 0, self.hwnd, None)
            _bind(self.user, 'PostMessageW', wt.BOOL, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)(self.hwnd, 0, 0, 0)
            if chosen == 200:
                self._quit()
            elif 100 <= chosen < 100 + len(self.actions):
                self.actions[chosen - 100][2]()
        finally:
            _bind(self.user, 'DestroyMenu', wt.BOOL, wt.HMENU)(menu)

    def _quit(self, force=False):
        if self.on_quit(force):
            self.destroy_window(self.hwnd)

    def _message(self, hwnd, message, wparam, lparam):
        try:
            if message == self.CALLBACK:
                if lparam == 0x202:
                    self._open()
                elif lparam in [0x205, 0x7B]:
                    self._menu()
                return 0
            if message == self.taskbar_created:
                self.notify(0, ct.byref(self.data))
                return 0
            if message == 0x113:  # WM_TIMER: app job status only; no system telemetry.
                self.data.tip = (self.title + ' — ' + self.status())[:127]
                self.notify(1, ct.byref(self.data))
                return 0
            if message == 0x10:
                self._quit()
                return 0
            if message == 0x11:
                return 1
            if message == 0x16 and wparam:
                self._quit(force=True)
                return 0
            if message == 2:
                self.notify(2, ct.byref(self.data))
                _bind(self.user, 'PostQuitMessage', None, ct.c_int)(0)
                return 0
            return self.default_proc(hwnd, message, wparam, lparam)
        except Exception:
            logging.exception('Tray action failed')
            _bind(self.user, 'MessageBoxW', ct.c_int, wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.UINT)(hwnd, 'Archiver could not complete this action. See archiver-desktop.log in the application folder.', 'Archiver', 0x10)
            return 0

    def run(self):
        definition = self.window_class_type()
        definition.proc, definition.instance, definition.name = self.callback, self.instance, self.class_name
        register = _bind(self.user, 'RegisterClassW', wt.ATOM, ct.POINTER(self.window_class_type))
        if not register(ct.byref(definition)):
            raise ct.WinError(ct.get_last_error())
        icon = None
        try:
            icon = self._icon()
            create = _bind(self.user, 'CreateWindowExW', wt.HWND, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                           ct.c_int, ct.c_int, ct.c_int, ct.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, ct.c_void_p)
            self.hwnd = create(0, self.class_name, self.title, 0, 0, 0, 0, 0, None, None, self.instance, None)
            if not self.hwnd:
                raise ct.WinError(ct.get_last_error())
            self.data = self.icon_type()
            self.data.size, self.data.window, self.data.id = ct.sizeof(self.data), self.hwnd, 1
            self.data.flags, self.data.message, self.data.icon, self.data.tip = 7, self.CALLBACK, icon, self.title[:127]
            if not self.notify(0, ct.byref(self.data)):
                raise RuntimeError('Windows could not add the Archiver tray icon')
            _bind(self.user, 'SetTimer', ct.c_size_t, wt.HWND, ct.c_size_t, wt.UINT, ct.c_void_p)(self.hwnd, 1, 2000, None)
            message = wt.MSG()
            get = _bind(self.user, 'GetMessageW', ct.c_int, ct.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT)
            translate = _bind(self.user, 'TranslateMessage', wt.BOOL, ct.POINTER(wt.MSG))
            dispatch = _bind(self.user, 'DispatchMessageW', ct.c_ssize_t, ct.POINTER(wt.MSG))
            while True:
                result = get(ct.byref(message), None, 0, 0)
                if result == -1:
                    raise ct.WinError(ct.get_last_error())
                if not result:
                    break
                translate(ct.byref(message))
                dispatch(ct.byref(message))
        finally:
            if self.hwnd:
                if hasattr(self, 'data'):
                    self.notify(2, ct.byref(self.data))
                self.destroy_window(self.hwnd)
                self.hwnd = None
            if icon:
                _bind(self.user, 'DestroyIcon', wt.BOOL, wt.HICON)(icon)
            _bind(self.user, 'UnregisterClassW', wt.BOOL, wt.LPCWSTR, wt.HINSTANCE)(self.class_name, self.instance)
