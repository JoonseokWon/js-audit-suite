"""Private withdrawn-window adapter tests. These do NOT test physical IME input.

No external HWND is searched, focused or changed. Native controls belong only to
each hidden test root. Actual Korean composition must be checked separately by
a person in the released application; Unicode programmatic input is not proof.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import unittest
from unittest.mock import patch

import windows_text as native


class TextContractTests(unittest.TestCase):
    def test_newlines_are_normalized_without_losing_actual_trailing_lines(self):
        self.assertEqual(native.normalize_newlines('가\r\n나\r다\n\n'), '가\n나\n다\n\n')

    def test_utf16_counts_supplementary_characters_and_hangul(self):
        self.assertEqual(native.utf16_length('가😀나'), 4)
        self.assertEqual(native._python_offset('가😀나', 3), 2)
        with self.assertRaises(native.NativeTextError):
            native._python_offset('가😀나', 2)

    def test_nul_and_unpaired_surrogates_are_rejected_explicitly(self):
        for text in ('가\0나', '\ud800', '\udfff'):
            with self.subTest(text=repr(text)), self.assertRaises(ValueError):
                native.validate_text(text)

    def test_limit_uses_utf16_units_and_allows_at_least_500k_emojis(self):
        self.assertGreaterEqual(native.MAX_TEXT_UTF16, 1_000_000)
        self.assertEqual(native.utf16_length(native.validate_text('😀' * 500_000)), 1_000_000)
        with patch.object(native, 'MAX_TEXT_UTF16', 3):
            self.assertEqual(native.validate_text('가😀'), '가😀')
            with self.assertRaises(ValueError):
                native.validate_text('😀😀')

    def test_nonwindows_factory_only_returns_none_and_does_not_create_widgets(self):
        with patch.object(native.sys, 'platform', 'linux'), patch.object(native, 'WindowsText') as constructor:
            self.assertIsNone(native.build_windows_text(object()))
            constructor.assert_not_called()

    def test_windows_factory_does_not_hide_initialization_failures(self):
        with patch.object(native.sys, 'platform', 'win32'), patch.object(native, 'WindowsText', side_effect=native.NativeTextError('명시적 실패')):
            with self.assertRaisesRegex(native.NativeTextError, '명시적 실패'):
                native.build_windows_text(object())


@unittest.skipUnless(sys.platform == 'win32', 'Windows-only native control')
class NativeControlTests(unittest.TestCase):
    def setUp(self):
        import runtime
        runtime.configure()
        runtime.configure_tk_libraries()
        self.root = native.tk.Tk()
        self.root.withdraw()  # no mapping/activation/SetFocus or foreign-window access
        self.text = native.WindowsText(self.root, height=4, width=45, wrap='word')
        self.text.pack(fill='both', expand=True)
        self.root.update_idletasks()

    def tearDown(self):
        self.root.destroy()

    def test_private_unicode_plain_text_control_loaded_from_absolute_system_path(self):
        self.assertTrue(self.text.audit_native_text)
        self.assertIs(self.text.audit_container, self.text)
        self.assertTrue(self.text._api.is_window(self.text.native_handle))
        self.assertTrue(self.text._api.dll_path.lower().endswith('\\system32\\msftedit.dll'))
        name = ctypes.create_unicode_buffer(256)
        get_class = self.text._api.user.GetClassNameW
        get_class.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        get_class.restype = ctypes.c_int
        self.assertGreater(get_class(self.text.native_handle, name, len(name)), 0)
        self.assertEqual(name.value.upper(), native.NATIVE_CLASS.upper())
        self.assertEqual(self.text._send(native.EM_GETTEXTMODE) & native.TM_PLAINTEXT, native.TM_PLAINTEXT)

    def test_empty_document_has_exactly_tk_implicit_newline(self):
        self.assertEqual(self.text.get('1.0', 'end'), '\n')
        self.assertEqual(self.text.get('1.0', 'end-1c'), '')

    def test_unicode_english_multiline_and_actual_final_newlines_roundtrip(self):
        for source in ('검토', '검토😀 JS전자', '첫째\n둘째', '첫째\r\n둘째\r셋째',
                       '끝\n', '끝\n\n', '\n', '\n\n', '검토 100,000원\t대사 완료'):
            with self.subTest(source=repr(source)):
                self.text.delete('1.0', 'end')
                self.text.insert('1.0', source)
                expected = native.normalize_newlines(source)
                self.assertEqual(self.text.get('1.0', 'end'), expected + '\n')
                self.assertEqual(self.text.get('1.0', 'end-1c'), expected)

    def test_append_and_middle_insert_or_delete_never_split_emoji(self):
        self.text.insert('1.0', '가😀나\n원장')
        self.text.insert('1.2', '중간')
        self.text.insert('end', '\n끝😀')
        self.assertEqual(self.text.get('1.0', 'end-1c'), '가😀중간나\n원장\n끝😀')
        self.text.delete('1.1', '1.2')
        self.assertEqual(self.text.get('1.0', 'end-1c'), '가중간나\n원장\n끝😀')
        self.assertEqual(self.text.get('2.0', '2.2'), '원장')

    def test_line_indexes_do_not_treat_non_lf_unicode_separators_as_tk_lines(self):
        body = '가\v나\u0085다\u2028라\n둘째'
        # The index contract can be checked independently of a native control's
        # normalization policy for exotic control characters.
        self.assertEqual(self.text._offset('2.0', body), len('가\v나\u0085다\u2028라\n'))
        self.assertEqual(self.text._offset('1.999', body), len('가\v나\u0085다\u2028라'))

    def test_initial_document_load_positions_caret_at_first_line_without_focus(self):
        self.text.insert('1.0', '첫째\n둘째😀')
        self.assertEqual(self.text.get('insert'), '첫')
        self.text.insert('end', '끝')
        self.assertEqual(self.text.get('insert'), '\n')

    def test_disabled_ignores_programmatic_load_and_can_be_reenabled(self):
        self.text.insert('1.0', '보존할 기존 조서😀')
        self.text.configure(state='disabled')
        self.assertEqual(self.text.cget('state'), 'disabled')
        self.text.delete('1.0', 'end')
        self.text.insert('end', '변경 금지')
        self.assertEqual(self.text.get('1.0', 'end-1c'), '보존할 기존 조서😀')
        self.text.configure(state='normal')
        self.text.insert('end', ' 수정')
        self.assertEqual(self.text.get('1.0', 'end-1c'), '보존할 기존 조서😀 수정')

    def test_get_preserves_native_selection_and_reading_is_not_a_rewrite(self):
        self.text.insert('1.0', '가😀나 원장')
        self.text._send(native.EM_SETSEL, 1, 3)
        self.assertEqual(self.text.get('1.0', 'end-1c'), '가😀나 원장')
        start, end = wintypes.DWORD(), wintypes.DWORD()
        self.text._send(native.EM_GETSEL, ctypes.addressof(start), ctypes.addressof(end))
        self.assertEqual((start.value, end.value), (1, 3))

    def test_font_zoom_changes_native_font_without_rewriting_or_losing_selection(self):
        self.text.insert('1.0', '재무제표\n본문😀')
        self.text._send(native.EM_SETSEL, 1, 3)
        original = self.text.get('1.0', 'end-1c')
        old = self.text._font_handle
        self.text.refresh_font()
        self.assertEqual(self.text._font_handle, old)
        self.root.tk.call('tk', 'scaling', float(self.root.tk.call('tk', 'scaling')) * 1.25)
        self.text.refresh_font()
        self.assertNotEqual(self.text._font_handle, old)
        self.assertEqual(self.text.get('1.0', 'end-1c'), original)
        start, end = wintypes.DWORD(), wintypes.DWORD()
        self.text._send(native.EM_GETSEL, ctypes.addressof(start), ctypes.addressof(end))
        self.assertEqual((start.value, end.value), (1, 3))

    def test_private_control_parent_is_clipping_wrapper(self):
        get_parent = self.text._api.user.GetParent
        get_parent.argtypes = [wintypes.HWND]
        get_parent.restype = wintypes.HWND
        self.assertEqual(int(get_parent(self.text.native_handle)), self.text.winfo_id())

    def test_large_document_over_500k_characters_roundtrips_without_silent_64k_limit(self):
        original = '한글😀 abc\n' * 65_000
        self.assertGreater(len(original), 500_000)
        self.text.insert('1.0', original)
        self.assertEqual(self.text.get('1.0', 'end-1c'), original)
        self.text.insert('end', '끝😀')
        self.assertEqual(self.text.get('1.0', 'end-1c'), original + '끝😀')

    def test_rejected_write_preserves_existing_document(self):
        self.text.insert('1.0', '기존😀')
        for value in ('\0', '\ud800', 'x' * (native.MAX_TEXT_UTF16 + 1)):
            with self.subTest(kind=repr(value[:10])), self.assertRaises(ValueError):
                self.text.insert('end', value)
            self.assertEqual(self.text.get('1.0', 'end-1c'), '기존😀')

    def test_destroy_releases_private_native_window_and_font_and_is_idempotent(self):
        handle, font = self.text.native_handle, self.text._font_handle
        api = self.text._api
        self.text.destroy()
        self.assertFalse(api.is_window(handle))
        self.assertIsNone(self.text.native_handle)
        self.assertIsNone(self.text._font_handle)
        self.text._close_native()
        with self.assertRaises(native.NativeTextError):
            self.text.get('1.0', 'end')


if __name__ == '__main__':
    unittest.main()
