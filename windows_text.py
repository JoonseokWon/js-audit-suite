"""Small, plain-text Windows Rich Edit adapter for Korean audit narratives.

The Windows control owns IME composition, editing, selection and undo. This
module never intercepts IME/keyboard messages, changes an input method or reads
another application's windows. Tk owns only the layout frame. No native editor
is silently substituted on Windows after an initialization error.

Supported Tk Text subset: get/insert/delete using line.column, end, end-1c and
insert; state/font/height/width/wrap; focus_set. get includes Tk's implicit final
newline. The native document contains only the user's actual text. Limits are
2,000,000 UTF-16 code units (at least 500,000 supplementary characters), and
programmatic writes are checked for truncation. Embedded NUL and unpaired UTF-16
surrogates are rejected instead of changing evidence text silently.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import re
import sys
import tkinter as tk

MAX_TEXT_UTF16 = 2_000_000
NATIVE_CLASS = 'RICHEDIT50W'
WM_USER = 0x0400
WM_SETFONT = 0x0030
WM_SETTEXT = 0x000C
EM_SETSEL = 0x00B1
EM_GETSEL = 0x00B0
EM_REPLACESEL = 0x00C2
EM_SCROLLCARET = 0x00B7
EM_SETREADONLY = 0x00CF
EM_EXLIMITTEXT = WM_USER + 53
EM_SETTEXTMODE = WM_USER + 89
EM_GETTEXTMODE = WM_USER + 90
EM_GETTEXTEX = WM_USER + 94
EM_GETTEXTLENGTHEX = WM_USER + 95
TM_PLAINTEXT = 1
TM_MULTILEVELUNDO = 8
TM_MULTICODEPAGE = 32


class NativeTextError(RuntimeError):
    """An explicit native-editor failure; callers must show it to the user."""


def normalize_newlines(value):
    return str(value).replace('\r\n', '\n').replace('\r', '\n')


def utf16_length(value):
    return len(value.encode('utf-16-le')) // 2


def validate_text(value):
    text = normalize_newlines(value)
    from export_support.text import require_xml_text
    require_xml_text(text,'본문')
    try:
        size = utf16_length(text)
    except UnicodeEncodeError as exc:
        raise ValueError('본문에 완성되지 않은 UTF-16 문자가 있습니다.') from exc
    if size > MAX_TEXT_UTF16:
        raise ValueError(f'본문은 UTF-16 {MAX_TEXT_UTF16:,} 단위까지 입력할 수 있습니다. 자료를 나누어 작성하세요.')
    return text


def _python_offset(text, units):
    """Convert a native UTF-16 caret offset, rejecting a split surrogate pair."""
    raw = text.encode('utf-16-le')
    units = min(max(0, int(units)), len(raw) // 2)
    try:
        return len(raw[:units * 2].decode('utf-16-le'))
    except UnicodeDecodeError as exc:
        raise NativeTextError('Windows 편집기 커서가 Unicode 문자 중간에 있습니다.') from exc


class _TextLength(ctypes.Structure):
    _fields_ = [('flags', wintypes.DWORD), ('codepage', wintypes.UINT)]


class _GetText(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('flags', wintypes.DWORD),
                ('codepage', wintypes.UINT), ('default_char', ctypes.c_void_p),
                ('used_default_char', ctypes.c_void_p)]


class _WinAPI:
    def __init__(self):
        # SEARCH_SYSTEM32 prevents a project/working-directory DLL from being
        # loaded. GetSystemDirectoryW supplies an absolute path for every DLL.
        kernel = ctypes.WinDLL('kernel32.dll', use_last_error=True, winmode=0x800)
        get_dir = kernel.GetSystemDirectoryW
        get_dir.argtypes = [wintypes.LPWSTR, wintypes.UINT]
        get_dir.restype = wintypes.UINT
        buf = ctypes.create_unicode_buffer(32768)
        count = get_dir(buf, len(buf))
        if not count or count >= len(buf):
            raise NativeTextError('Windows System32 경로를 확인하지 못했습니다.')
        directory = buf.value.rstrip('\\')
        self.dll_path = directory + '\\Msftedit.dll'
        self.rich = ctypes.WinDLL(self.dll_path, use_last_error=True, winmode=0x800)
        self.user = ctypes.WinDLL(directory + '\\user32.dll', use_last_error=True, winmode=0x800)
        self.gdi = ctypes.WinDLL(directory + '\\gdi32.dll', use_last_error=True, winmode=0x800)

        self.create = self.user.CreateWindowExW
        self.create.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
        self.create.restype = wintypes.HWND
        self.send = self.user.SendMessageW
        self.send.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
        self.send.restype = ctypes.c_ssize_t
        self.move = self.user.MoveWindow
        self.move.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.BOOL]
        self.move.restype = wintypes.BOOL
        self.is_window = self.user.IsWindow
        self.is_window.argtypes = [wintypes.HWND]
        self.is_window.restype = wintypes.BOOL
        self.destroy = self.user.DestroyWindow
        self.destroy.argtypes = [wintypes.HWND]
        self.destroy.restype = wintypes.BOOL
        self.set_focus = self.user.SetFocus
        self.set_focus.argtypes = [wintypes.HWND]
        self.set_focus.restype = wintypes.HWND
        self.create_font = self.gdi.CreateFontW
        self.create_font.argtypes = [ctypes.c_int] * 5 + [wintypes.DWORD] * 8 + [wintypes.LPCWSTR]
        self.create_font.restype = wintypes.HFONT
        self.delete_object = self.gdi.DeleteObject
        self.delete_object.argtypes = [wintypes.HGDIOBJ]
        self.delete_object.restype = wintypes.BOOL


_api = None


def _win_api():
    global _api
    if sys.platform != 'win32':
        raise NativeTextError('Windows 한글 편집기는 Windows에서만 사용할 수 있습니다.')
    if _api is None:
        try:
            _api = _WinAPI()
        except (OSError, AttributeError) as exc:
            raise NativeTextError('Windows 한글 편집기 초기화 실패: ' + str(exc)) from exc
    return _api


class WindowsText(tk.Frame):
    """A layout frame containing one private, standard Unicode Rich Edit HWND."""
    audit_native_text = True

    def __init__(self, parent, **options):
        self._api = _win_api()
        self._hwnd = None
        self._font_handle = None
        self._font_key = None
        self._closed = False
        self._text_state = str(options.pop('state', 'normal'))
        self._text_font = str(options.pop('font', 'TkTextFont'))
        self._text_height = int(options.pop('height', 10))
        self._text_width = int(options.pop('width', 80))
        self._text_wrap = str(options.pop('wrap', 'word'))
        if self._text_state not in ('normal', 'disabled'):
            raise tk.TclError('state는 normal 또는 disabled여야 합니다.')
        if self._text_wrap != 'word':
            raise tk.TclError('Windows 한글 편집기는 wrap=word만 지원합니다.')
        if options:
            raise tk.TclError('Windows 한글 편집기에서 지원하지 않는 옵션: ' + ', '.join(options))
        super().__init__(parent, borderwidth=0, highlightthickness=0, takefocus=1)
        self.audit_container = self
        self.frame = self
        self._audit_scroll_frame = self
        try:
            # WS_CHILD | WS_VISIBLE | WS_VSCROLL | WS_CLIPSIBLINGS | WS_TABSTOP,
            # ES_MULTILINE | ES_AUTOVSCROLL | ES_WANTRETURN. The HWND parent is
            # this Tk frame, so canvas scrolling and unmapping clip it normally.
            style = 0x40000000 | 0x10000000 | 0x00200000 | 0x04000000 | 0x00010000 | 4 | 0x40 | 0x1000
            self._hwnd = self._api.create(0x200, NATIVE_CLASS, '', style, 0, 0, 1, 1,
                                            self.winfo_id(), None, None, None)
            if not self._hwnd:
                raise NativeTextError('Windows 한글 편집기 창 생성 실패: ' + str(ctypes.get_last_error()))
            if self._send(EM_SETTEXTMODE, TM_PLAINTEXT | TM_MULTILEVELUNDO | TM_MULTICODEPAGE, 0) != 0:
                raise NativeTextError('Windows 한글 편집기를 Unicode 일반 텍스트 모드로 설정하지 못했습니다.')
            self._send(EM_EXLIMITTEXT, 0, MAX_TEXT_UTF16)
            self._send(EM_SETREADONLY, int(self._text_state == 'disabled'), 0)
            self.refresh_font()
            self.bind('<Configure>', self._resize, add='+')
            self.bind('<FocusIn>', self._focus_native, add='+')
            self.bind('<Destroy>', self._on_destroy, add='+')
        except BaseException:
            self._close_native()
            super().destroy()
            raise

    @property
    def native_handle(self):
        return self._hwnd

    def _send(self, message, wparam=0, lparam=0):
        if self._closed or not self._hwnd or not self._api.is_window(self._hwnd):
            raise NativeTextError('이미 닫힌 Windows 한글 편집기입니다.')
        return int(self._api.send(self._hwnd, message, wparam, lparam))

    def _body(self):
        length_arg = _TextLength(2 | 8, 1200)  # GTL_PRECISE | GTL_NUMCHARS
        units = self._send(EM_GETTEXTLENGTHEX, ctypes.addressof(length_arg), 0)
        if not 0 <= units <= MAX_TEXT_UTF16:
            raise NativeTextError('Windows 한글 편집기 본문 길이를 확인하지 못했습니다.')
        buffer = ctypes.create_string_buffer((units + 1) * 2)
        arg = _GetText(len(buffer), 0, 1200, None, None)
        copied = self._send(EM_GETTEXTEX, ctypes.addressof(arg), ctypes.addressof(buffer))
        if copied < 0 or copied != units:
            raise NativeTextError('Windows 한글 편집기 본문이 일부만 읽혔습니다.')
        try:
            return normalize_newlines(buffer.raw[:copied * 2].decode('utf-16-le'))
        except UnicodeDecodeError as exc:
            raise NativeTextError('Windows 한글 편집기의 Unicode 본문을 읽지 못했습니다.') from exc

    def _offset(self, index, body):
        index = str(index).strip()
        if index == 'end':
            return len(body) + 1
        if index in ('end-1c', 'end - 1c'):
            return len(body)
        if index == 'insert':
            start, end = wintypes.DWORD(), wintypes.DWORD()
            self._send(EM_GETSEL, ctypes.addressof(start), ctypes.addressof(end))
            return _python_offset(body, end.value)
        match = re.fullmatch(r'([1-9]\d*)\.(\d+)', index)
        if not match:
            raise tk.TclError('지원하지 않는 Text 인덱스: ' + index)
        line, column = map(int, match.groups())
        # Tk Text recognizes LF as a line boundary; str.splitlines would also
        # treat vertical tabs, NEL and Unicode separators as separate lines.
        lines = [value + '\n' for value in body.split('\n')]
        if line > len(lines):
            return len(body) + 1
        prefix = sum(len(v) for v in lines[:line - 1])
        return min(prefix + column, prefix + len(lines[line - 1]) - 1)

    def get(self, index1='1.0', index2=None):
        body = validate_text(self._body())
        doc = body + '\n'
        start = self._offset(index1, body)
        end = start + 1 if index2 is None else self._offset(index2, body)
        return doc[start:max(start, end)]

    def _replace(self, body, start, end, replacement):
        expected = validate_text(body[:start] + replacement + body[end:])
        self._send(EM_SETSEL, utf16_length(body[:start]), utf16_length(body[:end]))
        text_buffer = ctypes.create_unicode_buffer(replacement.replace('\n', '\r'))
        self._send(EM_REPLACESEL, 1, ctypes.addressof(text_buffer))
        if self._body() != expected:
            # Roll back rather than silently accepting truncation or alteration.
            original = ctypes.create_unicode_buffer(body.replace('\n', '\r'))
            self._send(WM_SETTEXT, 0, ctypes.addressof(original))
            raise NativeTextError('Windows 한글 편집기에 본문 전체가 반영되지 않아 이전 내용을 복원했습니다.')

    def insert(self, index, chars, *tags):
        if self._text_state == 'disabled':
            return
        if tags:
            raise tk.TclError('Windows 일반 텍스트 편집기는 태그를 지원하지 않습니다.')
        replacement = validate_text(chars)
        body = self._body()
        start = min(self._offset(index, body), len(body))
        self._replace(body, start, start, replacement)
        if not body and str(index).strip() == '1.0':
            # Workpaper loading starts at the first line, even when a long
            # replacement made Rich Edit move its caret to the document end.
            self._send(EM_SETSEL, 0, 0)
            self._send(EM_SCROLLCARET, 0, 0)

    def delete(self, index1, index2=None):
        if self._text_state == 'disabled':
            return
        body = self._body()
        start = min(self._offset(index1, body), len(body))
        end = start + 1 if index2 is None else self._offset(index2, body)
        self._replace(body, start, min(max(start, end), len(body)), '')

    def cget(self, key):
        values = {'state': self._text_state, 'font': self._text_font,
                  'height': self._text_height, 'width': self._text_width,
                  'wrap': self._text_wrap}
        return values[key] if key in values else super().cget(key)

    def configure(self, cnf=None, **options):
        if isinstance(cnf, str) and not options:
            return self.cget(cnf)
        if cnf:
            options = {**cnf, **options}
        if not options:
            return {key: self.cget(key) for key in ('state', 'font', 'height', 'width', 'wrap')}
        if 'state' in options:
            state = str(options.pop('state'))
            if state not in ('normal', 'disabled'):
                raise tk.TclError('state는 normal 또는 disabled여야 합니다.')
            self._send(EM_SETREADONLY, int(state == 'disabled'), 0)
            self._text_state = state
        resized = False
        for key in ('font', 'height', 'width'):
            if key in options:
                value = options.pop(key)
                setattr(self, '_text_' + key, str(value) if key == 'font' else int(value))
                resized = True
        if 'wrap' in options:
            if str(options.pop('wrap')) != self._text_wrap:
                raise tk.TclError('Windows 한글 편집기는 wrap=word만 지원합니다.')
        if options:
            super().configure(**options)
        if resized:
            self.refresh_font()

    config = configure

    def refresh_font(self):
        if self._closed or not self._hwnd:
            return
        spec = self._text_font
        family = str(self.tk.call('font', 'actual', spec, '-family'))
        points = int(self.tk.call('font', 'actual', spec, '-size'))
        scale = float(self.tk.call('tk', 'scaling'))
        pixels = max(1, round(points * scale if points > 0 else -points))
        weight = 700 if str(self.tk.call('font', 'actual', spec, '-weight')) == 'bold' else 400
        italic = int(str(self.tk.call('font', 'actual', spec, '-slant')) == 'italic')
        key = (family, pixels, weight, italic)
        if key != self._font_key:
            font = self._api.create_font(-pixels, 0, 0, 0, weight, italic, 0, 0, 1, 0, 0, 5, 0, family)
            if not font:
                raise NativeTextError('Windows 한글 편집기의 글꼴을 만들지 못했습니다.')
            self._send(WM_SETFONT, int(font), 1)
            old = self._font_handle
            self._font_handle = font
            self._font_key = key
            if old:
                self._api.delete_object(old)
        line = int(self.tk.call('font', 'metrics', spec, '-linespace'))
        char = int(self.tk.call('font', 'measure', spec, '0'))
        super().configure(height=max(1, self._text_height) * line + 8,
                          width=max(1, self._text_width) * char + 8)
        self._resize()

    def _resize(self, event=None):
        if not self._closed and self._hwnd and self._api.is_window(self._hwnd):
            self._api.move(self._hwnd, 0, 0, max(1, self.winfo_width()), max(1, self.winfo_height()), True)

    def _focus_native(self, event=None):
        if not self._closed and self._hwnd and self._api.is_window(self._hwnd):
            self._api.set_focus(self._hwnd)

    def focus_set(self):
        super().focus_set()
        self._focus_native()

    def _close_native(self):
        if self._closed:
            return
        self._closed = True
        handle, font = self._hwnd, self._font_handle
        self._hwnd = self._font_handle = None
        if handle and self._api.is_window(handle):
            self._api.destroy(handle)
        if font:
            self._api.delete_object(font)

    def _on_destroy(self, event):
        if event.widget is self:
            self._close_native()

    def destroy(self):
        self._close_native()
        super().destroy()


def build_windows_text(parent, **options):
    """Return None only on other platforms, never hide a Windows failure."""
    if sys.platform != 'win32':
        return None
    return WindowsText(parent, **options)
