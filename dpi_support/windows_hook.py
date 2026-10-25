"""DPI notification subclass for an HWND created by this process and UI thread.

No keyboard or IME messages are intercepted. The callback performs only Win32
layout and records a pending DPI; Tk work is deferred to its normal event loop.
"""
import ctypes
from ctypes import wintypes
import os

WM_DPICHANGED = 0x02E0
WM_NCDESTROY = 0x0082


class _API:
    def __init__(self):
        self.user = ctypes.WinDLL('user32.dll', use_last_error=True, winmode=0x800)
        self.common = ctypes.WinDLL('comctl32.dll', use_last_error=True, winmode=0x800)
        self.kernel = ctypes.WinDLL('kernel32.dll', use_last_error=True, winmode=0x800)
        self.proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                      ctypes.c_size_t, ctypes.c_ssize_t,
                                      ctypes.c_size_t, ctypes.c_size_t)
        self.ancestor = self.user.GetAncestor
        self.ancestor.argtypes, self.ancestor.restype = [wintypes.HWND, wintypes.UINT], wintypes.HWND
        self.owner = self.user.GetWindowThreadProcessId
        self.owner.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.owner.restype = wintypes.DWORD
        self.thread = self.kernel.GetCurrentThreadId
        self.thread.argtypes, self.thread.restype = [], wintypes.DWORD
        self.install = self.common.SetWindowSubclass
        self.install.argtypes = [wintypes.HWND, self.proc, ctypes.c_size_t, ctypes.c_size_t]
        self.install.restype = wintypes.BOOL
        self.remove = self.common.RemoveWindowSubclass
        self.remove.argtypes = [wintypes.HWND, self.proc, ctypes.c_size_t]
        self.remove.restype = wintypes.BOOL
        self.next = self.common.DefSubclassProc
        self.next.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
        self.next.restype = ctypes.c_ssize_t
        self.position = self.user.SetWindowPos
        self.position.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.position.restype = wintypes.BOOL


class WindowsDpiHook:
    def __init__(self, handle, api=None):
        self.api = api or _API()
        self.hwnd = self.api.ancestor(handle, 2) or handle  # GA_ROOT
        process = wintypes.DWORD()
        thread = self.api.owner(self.hwnd, ctypes.byref(process))
        if process.value != os.getpid() or thread != self.api.thread():
            raise OSError('DPI 처리는 현재 앱의 UI 스레드 창에만 연결할 수 있습니다.')
        self.closed, self.pending, self.notifications = False, None, 0
        self.callback_errors, self.resize_failures = [], 0
        self.identifier = id(self)
        self.callback = self.api.proc(self._message)
        if not self.api.install(self.hwnd, self.callback, self.identifier, 0):
            raise OSError('앱 DPI 알림을 연결하지 못했습니다: '+str(ctypes.get_last_error()))

    def _message(self, hwnd, message, wparam, lparam, identifier, data):
        try:
            if message == WM_DPICHANGED and not self.closed:
                dpi = int(wparam) & 0xffff
                if 48 <= dpi <= 768 and lparam:
                    rect = ctypes.cast(lparam, ctypes.POINTER(wintypes.RECT)).contents
                    values = (rect.left, rect.top, rect.right, rect.bottom)
                    if 0 < rect.right-rect.left <= 65536 and 0 < rect.bottom-rect.top <= 65536:
                        self.pending = (dpi, values)
                        self.notifications += 1
                        # SWP_NOZORDER | SWP_NOACTIVATE: preserve focus and stacking.
                        if not self.api.position(hwnd, None, rect.left, rect.top,
                                                  rect.right-rect.left, rect.bottom-rect.top, 0x14):
                            self.resize_failures += 1
            elif message == WM_NCDESTROY:
                self.close()
        except BaseException as error:
            # Never allow a Python exception to escape into a native WndProc.
            self.callback_errors.append(type(error).__name__+': '+str(error))
        return self.api.next(hwnd, message, wparam, lparam)

    def pop(self):
        value, self.pending = self.pending, None
        return value

    def close(self):
        if not self.closed:
            self.closed = True
            self.api.remove(self.hwnd, self.callback, self.identifier)
