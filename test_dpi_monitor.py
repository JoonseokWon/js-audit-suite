"""DPI transition and font tests. Physical monitor settings are never changed."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import ctypes
from ctypes import wintypes
import os
import sys
import unittest
import desktop_display as display
from dpi_support.windows_hook import WindowsDpiHook,WM_DPICHANGED,WM_NCDESTROY


class FakeNative:
    def __init__(self):
        self.positions,self.chained,self.removed=[],[],[]
        self.proc=lambda callback:callback
        self.ancestor=lambda handle,kind:handle
        self.thread=lambda:1
        self.install=lambda *args:True
    def owner(self,handle,process):
        ctypes.cast(process,ctypes.POINTER(wintypes.DWORD)).contents.value=os.getpid()
        return 1
    def next(self,*args):self.chained.append(args);return 73
    def position(self,*args):self.positions.append(args);return True
    def remove(self,*args):self.removed.append(args);return True


class NativeNotificationTests(unittest.TestCase):
    def test_pending_dpi_copies_rectangle_without_tk_or_keyboard_interception(self):
        api=FakeNative();hook=WindowsDpiHook(123,api)
        rect=wintypes.RECT(100,50,1900,1150)
        result=hook._message(123,WM_DPICHANGED,144 | (144<<16),ctypes.addressof(rect),0,0)
        rect.left=999
        self.assertEqual(result,73)
        self.assertEqual(hook.pop(),(144,(100,50,1900,1150)))
        self.assertIsNone(hook.pop())
        self.assertEqual(api.positions[0],(123,None,100,50,1800,1100,0x14))
        hook._message(123,0x010f,1,2,0,0)  # IME message passes through unchanged.
        self.assertEqual(api.chained[-1],(123,0x010f,1,2))
        hook.close();hook.close();self.assertEqual(len(api.removed),1)

    def test_destroy_removes_subclass_and_invalid_sizes_do_not_resize(self):
        api=FakeNative();hook=WindowsDpiHook(123,api)
        rect=wintypes.RECT(2,2,1,1)
        hook._message(123,WM_DPICHANGED,192,ctypes.addressof(rect),0,0)
        hook._message(123,WM_DPICHANGED,0,0,0,0)
        self.assertFalse(api.positions);self.assertIsNone(hook.pop())
        hook._message(123,WM_NCDESTROY,0,0,0,0)
        self.assertTrue(hook.closed);self.assertEqual(len(api.removed),1)
        self.assertEqual(hook.callback_errors,[])

    def test_other_process_or_thread_is_rejected(self):
        api=FakeNative();api.thread=lambda:2
        with self.assertRaises(OSError):WindowsDpiHook(123,api)

    def test_callback_failure_is_contained_and_native_chain_continues(self):
        api=FakeNative();hook=WindowsDpiHook(123,api)
        api.position=lambda *args:(_ for _ in ()).throw(OSError('synthetic failure'))
        rect=wintypes.RECT(0,0,600,400)
        self.assertEqual(hook._message(123,WM_DPICHANGED,120,ctypes.addressof(rect),0,0),73)
        self.assertEqual(len(hook.callback_errors),1)


class GeometryMatrixTests(unittest.TestCase):
    def test_1280_to_4k_with_100_125_150_200_percent_windows_dpi(self):
        for width,height in ((1280,720),(1366,768),(1920,1080),(2560,1440),(3840,2160)):
            for dpi in (96,120,144,192):
                for zoom in (100,125,150):
                    with self.subTest(resolution=(width,height),dpi=dpi,zoom=zoom):
                        area=(0,0,width,height-48)
                        values=display.window_geometry(area,dpi,zoom)
                        self.assertLessEqual(values['x']+values['width'],width)
                        self.assertLessEqual(values['y']+values['height'],height-48)
                        metrics=display.display_metrics(dpi,zoom)
                        self.assertGreaterEqual(metrics['row_height'],int(30*dpi/96*zoom/100))


class FontTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import runtime
        runtime.configure();runtime.configure_tk_libraries();display.enable_dpi_awareness()
        try:cls.root=display.tk.Tk();cls.root.withdraw()
        except display.tk.TclError as exc:
            if sys.platform!='win32' and ('no display' in str(exc).lower() or "couldn't connect" in str(exc).lower()):
                raise unittest.SkipTest('No display for native font tests') from exc
            raise
    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()
    def setUp(self):
        self.manager=display.DisplayManager(self.root,dpi=96,work_area_override=(0,0,3840,2100))
    def tearDown(self):
        self.manager.close()

    def test_custom_13_18_26pt_fonts_follow_dpi_and_zoom_without_changing_styles(self):
        self.manager.style.configure('DpiCustom.TLabel',foreground='#234567')
        for point in (11,13,18,26):
            font=display.tkfont.Font(root=self.root,size=point,family=self.manager.family,weight='bold')
            before=font.metrics('linespace')
            self.manager.update_dpi(192);self.root.update_idletasks()
            after=font.metrics('linespace')
            self.assertGreater(after,before*1.5)
            self.assertEqual(font.cget('size'),point);self.assertEqual(font.cget('weight'),'bold')
            self.manager.apply(125);self.root.update_idletasks()
            self.assertGreater(font.metrics('linespace'),after)
            self.manager.update_dpi(96);self.manager.apply(100)
        self.assertEqual(self.manager.style.lookup('DpiCustom.TLabel','foreground'),'#234567')

    def test_repeated_dpi_changes_do_not_accumulate_tree_scaling_or_reset_zoom(self):
        table=display.ttk.Treeview(self.root,columns=('amount',),show='headings')
        self.manager.register_tree(table,{'amount':160})
        self.manager.apply(125)
        for dpi in (120,144,192,96,192,96):
            self.manager.update_dpi(dpi)
            self.assertEqual(self.manager.percent,125)
            self.assertEqual(table.column('amount','width'),round(160*dpi/96*1.25))
        self.manager.apply(100);self.assertEqual(table.column('amount','width'),160)
        table.destroy()

    @unittest.skipUnless(sys.platform=='win32','Windows native editor')
    def test_native_editor_rebuilds_font_at_new_dpi_and_preserves_unicode(self):
        text=display.create_editable_text(self.root,height=3)
        value='계획·판단은 사람이 입력해요.\n한글 조서 123 가나다'
        text.insert('1.0',value)
        pixels=text._font_key[1]
        self.manager.update_dpi(192)
        self.assertGreaterEqual(text._font_key[1],pixels*1.9)
        self.assertEqual(text.get('1.0','end-1c'),value)
        self.manager.update_dpi(96)
        self.assertEqual(text._font_key[1],pixels)
        text.destroy()

    def test_invalid_dpi_preserves_current_metrics(self):
        before=dict(self.manager.metrics)
        with self.assertRaises(ValueError):self.manager.update_dpi(float('nan'))
        self.assertEqual(self.manager.metrics,before)

    def test_replacing_manager_keeps_named_font_owners_alive(self):
        import gc
        old=self.manager
        self.manager=display.DisplayManager(self.root,dpi=96,work_area_override=(0,0,3840,2100))
        del old
        gc.collect()
        self.manager.apply(150)
        self.assertIn(display.NORMAL_FONT,display.tkfont.names(self.root))
        self.assertGreater(self.manager.fonts[display.NORMAL_FONT].metrics('linespace'),0)

    @unittest.skipUnless(sys.platform=='win32','Windows native DPI notification')
    def test_real_own_window_tracker_is_hidden_and_disposes_native_hook(self):
        manager=display.DisplayManager(self.root)
        self.assertEqual(self.root.state(),'withdrawn')
        self.assertTrue(manager.tracker.status['native_hook'])
        tracker=manager.tracker
        timer=tracker.timer
        hook=tracker.hook
        manager.close()
        self.assertTrue(tracker.closed);self.assertTrue(hook.closed)
        self.assertNotIn(timer,self.root.tk.splitlist(self.root.tk.call('after','info')))


if __name__=='__main__':unittest.main()
