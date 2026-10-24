"""DPI/zoom metrics and native helper contracts; no OS display setting changes."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys,unittest,xml.etree.ElementTree as ET
import desktop_display as display

def native_root():
    import runtime
    runtime.configure()
    runtime.configure_tk_libraries()
    display.enable_dpi_awareness()
    try:return display.tk.Tk()
    except display.tk.TclError as exc:
        # A missing display can be expected on Unix headless runners. Invalid
        # Tcl/Tk scripts, and every Windows initialization error, must fail.
        message=str(exc).lower()
        if sys.platform!='win32' and ('no display name' in message or "couldn't connect to display" in message):
            raise unittest.SkipTest('No native display: '+str(exc)) from exc
        raise

class Call:
    def __init__(self,result):self.result=result;self.calls=[]
    def __call__(self,*args):self.calls.append(args);return self.result

class DisplayMetricTests(unittest.TestCase):
    def test_native_init_never_skips_windows_or_library_errors(self):
        import runtime
        for platform,message,expected in (
            ('win32','no display name and no $DISPLAY environment variable',display.tk.TclError),
            ('win32',"Can't find a usable init.tcl",display.tk.TclError),
            ('linux',"Can't find a usable init.tcl",display.tk.TclError),
            ('linux','no display name and no $DISPLAY environment variable',unittest.SkipTest),
        ):
            with self.subTest(platform=platform,message=message),patch.object(runtime,'configure'),patch.object(runtime,'configure_tk_libraries'),patch.object(display,'enable_dpi_awareness'),patch.object(sys,'platform',platform),patch.object(display.tk,'Tk',side_effect=display.tk.TclError(message)),self.assertRaises(expected):
                native_root()

    def test_supported_scale_values(self):
        self.assertEqual(display.SCALE_OPTIONS,(90,100,110,125,150,175))
        for value in display.SCALE_OPTIONS:
            self.assertEqual(display.normalize_scale(value),value)
            self.assertEqual(display.normalize_scale(str(value)+'%'),value)

    def test_unknown_or_nonfinite_scale_is_rejected(self):
        for value in (0,50,101,200,None,True,'nan','inf','not a scale'):
            with self.subTest(value=value),self.assertRaises(ValueError):display.normalize_scale(value)

    def test_metrics_for_96_144_192_dpi_and_native_zoom_choices(self):
        for dpi in (96,144,192):
            for scale in (100,125,150):
                with self.subTest(dpi=dpi,scale=scale):
                    m=display.display_metrics(dpi,scale)
                    self.assertAlmostEqual(m['factor'],dpi/96*scale/100)
                    self.assertAlmostEqual(m['tk_scaling'],dpi/72*scale/100)
                    self.assertEqual((m['normal_points'],m['small_points']),(11,10))
                    self.assertEqual(m['column_width'],round(170*m['factor']))
                    self.assertGreaterEqual(m['row_height'],round(30*m['factor']))

    def test_large_actual_font_linespace_never_clips_tree_row(self):
        m=display.display_metrics(144,150,linespace=70)
        self.assertGreaterEqual(m['row_height'],70+round(8*m['factor']))

    def test_invalid_dpi_rejected(self):
        for dpi in (0,-96,1000,float('nan'),float('inf')):
            with self.subTest(dpi=dpi),self.assertRaises(ValueError):display.display_metrics(dpi)

    def test_metrics_do_not_accumulate_scaling(self):
        original=display.display_metrics(144,100)
        display.display_metrics(144,150)
        self.assertEqual(original,display.display_metrics(144,100))

    def test_window_fits_large_and_small_work_areas_at_all_scales(self):
        for area in ((0,0,2560,1392),(0,0,1366,728),(-1920,0,0,1040)):
            for dpi in (96,144,192):
                for scale in display.SCALE_OPTIONS:
                    with self.subTest(area=area,dpi=dpi,scale=scale):
                        g=display.window_geometry(area,dpi,scale)
                        self.assertGreater(g['width'],0);self.assertGreater(g['height'],0)
                        self.assertGreaterEqual(g['x'],area[0]);self.assertGreaterEqual(g['y'],area[1])
                        self.assertLessEqual(g['x']+g['width'],area[2]);self.assertLessEqual(g['y']+g['height'],area[3])
                        self.assertLessEqual(g['min_width'],g['width']);self.assertLessEqual(g['min_height'],g['height'])

    def test_initial_2560_window_is_wider_than_legacy(self):
        g=display.window_geometry((0,0,2560,1392),96,100)
        self.assertEqual(g['width'],1680);self.assertGreater(g['width'],1320)

    def test_window_minimum_does_not_grow_with_dpi_or_app_zoom(self):
        for dpi in (96,144,192):
            for scale in display.SCALE_OPTIONS:
                g=display.window_geometry((0,0,3840,2088),dpi,scale)
                self.assertEqual((g['min_width'],g['min_height']),(960,640))

    def test_invalid_work_area_rejected(self):
        for area in ((0,0,20,20),(0,0,1),()):
            with self.subTest(area=area),self.assertRaises(ValueError):display.window_geometry(area)

    def test_manifest_system_awareness_is_explicit_and_unprivileged(self):
        root=ET.parse(Path(__file__).with_name('windows.manifest')).getroot()
        values={n.tag.split('}')[-1]:n for n in root.iter()}
        self.assertEqual(values['dpiAware'].text,'true')
        self.assertEqual(values['dpiAwareness'].text,'system')
        self.assertEqual(values['requestedExecutionLevel'].attrib,{'level':'asInvoker','uiAccess':'false'})

    def test_source_api_requests_system_awareness(self):
        api=Call(True);user=SimpleNamespace(SetProcessDpiAwarenessContext=api)
        state=display._enable_windows(user)
        self.assertEqual(state['mode'],'system');self.assertTrue(state['enabled'])
        self.assertEqual(api.calls[0][0].value,display.ctypes.c_void_p(-2).value)

    def test_manifest_or_host_awareness_is_not_forced_again(self):
        user=SimpleNamespace(SetProcessDpiAwarenessContext=Call(False),GetThreadDpiAwarenessContext=Call(1),GetAwarenessFromDpiAwarenessContext=Call(2))
        fallback=SimpleNamespace(SetProcessDpiAwareness=Call(0))
        with patch.object(display.ctypes,'get_last_error',return_value=5,create=True):state=display._enable_windows(user,fallback)
        self.assertEqual(state['status'],'already_configured');self.assertEqual(state['mode'],'per_monitor')
        self.assertFalse(fallback.SetProcessDpiAwareness.calls)

    def test_old_windows_api_fallback(self):
        fallback=SimpleNamespace(SetProcessDpiAwareness=Call(0))
        state=display._enable_windows(SimpleNamespace(),fallback)
        self.assertEqual(state['method'],'SetProcessDpiAwareness');self.assertEqual(fallback.SetProcessDpiAwareness.calls,[(1,)])

    def test_legacy_windows_api_fallback(self):
        user=SimpleNamespace(SetProcessDPIAware=Call(True))
        self.assertEqual(display._enable_windows(user)['method'],'SetProcessDPIAware')

    def test_non_windows_is_safe_and_cached(self):
        with patch.object(display,'_awareness',None),patch.object(display.sys,'platform','linux'):
            first=display.enable_dpi_awareness();first['status']='caller changed'
            self.assertEqual(display.enable_dpi_awareness()['status'],'not_windows')

class DisplayNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=native_root();cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):cls.root.destroy()

    def setUp(self):
        self.manager=display.DisplayManager(self.root,scale=100,dpi=96,work_area_override=(0,0,1920,1040))
        self.panel=display.ttk.Frame(self.root);self.panel.pack(fill='both',expand=True)

    def tearDown(self):self.panel.destroy();self.root.update_idletasks()

    def test_named_normal_text_small_heading_fonts(self):
        for name,point in [(display.NORMAL_FONT,11),(display.TEXT_FONT,11),(display.SMALL_FONT,10),(display.HEADING_FONT,11)]:
            self.assertEqual(display.tkfont.nametofont(name,self.root).cget('size'),point)
        self.assertEqual(display.tkfont.nametofont(display.HEADING_FONT,self.root).cget('weight'),'bold')

    def test_native_100_125_150_scaling_and_font_linespace(self):
        observed=[]
        for value in (100,125,150):
            m=self.manager.apply(value);self.root.update_idletasks()
            line=self.manager.fonts[display.TEXT_FONT].metrics('linespace')
            self.assertGreaterEqual(m['row_height'],line+self.manager.px(8))
            self.assertAlmostEqual(float(self.root.tk.call('tk','scaling')),96/72*value/100,delta=.02)
            observed.append(line)
        self.assertLess(observed[0],observed[1]);self.assertLess(observed[1],observed[2])

    def test_tree_columns_restore_and_accept_new_dynamic_columns(self):
        tree=display.ttk.Treeview(self.panel,columns=('a',),show='headings');tree.column('a',width=170)
        self.manager.register_tree(tree,{'a':170});self.manager.apply(150)
        self.assertEqual(tree.column('a','width'),255)
        tree.configure(columns=('a','b'));tree.column('b',width=220)
        self.manager.register_tree(tree)
        self.assertEqual(tree.column('b','width'),330)
        self.manager.apply(100)
        self.assertEqual(tree.column('a','width'),170);self.assertEqual(tree.column('b','width'),220)
        self.manager.register_tree(tree,{'a':240})
        self.assertEqual(tree.column('a','width'),240)

    def test_apply_preserves_custom_button_style(self):
        self.manager.style.configure('Primary.TButton',foreground='#123456')
        self.manager.apply(125)
        self.assertEqual(self.manager.style.lookup('Primary.TButton','foreground'),'#123456')

    def test_text_helper_is_text_and_exposes_layout_container(self):
        text=display.create_scrolled_text(self.panel,height=4);text.audit_container.pack(fill='both',expand=True)
        self.assertIsInstance(text,display.tk.Text)
        self.assertTrue(text.cget('yscrollcommand'));self.assertEqual(str(text.cget('font')),display.TEXT_FONT)
        text.insert('end','조서 본문\n'*100);self.root.update_idletasks();text.yview_moveto(1)
        self.assertGreater(text.yview()[0],0)

    def test_refresh_updates_legacy_text_font(self):
        text=display.tk.Text(self.panel,font=('맑은 고딕',10))
        self.manager.refresh_widgets();self.assertEqual(str(text.cget('font')),display.TEXT_FONT)

    def test_scrollable_form_reaches_bottom_and_cleans_bindings(self):
        form=display.ScrollableFrame(self.panel);form.pack(fill='both',expand=True)
        for i in range(70):display.ttk.Label(form.inner,text='조서 수행·검토 입력 '+str(i)).pack()
        self.root.update_idletasks();form.refresh();form.canvas.yview_moveto(1)
        self.assertGreater(form.canvas.yview()[0],0)
        tag=form._wheel_tag;form.destroy()
        self.assertFalse(self.root.tk.call('bind',tag,'<MouseWheel>'))

    def test_scroll_timer_and_class_bindings_have_the_root_as_owner(self):
        form=display.ScrollableFrame(self.panel)
        command=self.root.tk.call('after','info',form._pending)[0]
        self.assertIn(command,self.root._tclCommands)
        self.assertNotIn(command,form._tclCommands or [])
        for wheel in form._wheel_commands:
            self.assertIn(wheel,self.root._tclCommands)
            self.assertNotIn(wheel,form._tclCommands or [])
        self.root.after_cancel(form._pending)
        form.destroy()
        for widget in (self.root,self.panel):
            self.assertTrue(all(self.root.tk.call('info','commands',name) for name in widget._tclCommands or []))

    def test_manual_refresh_cancels_superseded_timer_before_frame_destroy(self):
        errors=[];old=self.root.report_callback_exception
        self.root.report_callback_exception=lambda kind,value,trace:errors.append(value)
        try:
            form=display.ScrollableFrame(self.panel);timer=form._pending
            form.refresh()
            self.assertNotIn(timer,self.root.tk.splitlist(self.root.tk.call('after','info')))
            form.destroy();self.root.update()
            self.assertEqual(errors,[])
        finally:self.root.report_callback_exception=old

    def test_apply_posts_display_changed_event(self):
        events=[];binding=self.root.bind('<<AuditDisplayChanged>>',lambda event:events.append(True),add='+')
        self.manager.apply(125);self.root.update()
        self.root.unbind('<<AuditDisplayChanged>>',binding)
        self.assertTrue(events)

class WholeAppTeardownTests(unittest.TestCase):
    def test_multiple_scroll_tabs_zoom_reflow_then_cancel_all_and_destroy(self):
        """Cover the actual app plus window_capture's next-interpreter cleanup."""
        from app import App
        root=native_root()
        errors=[];root.report_callback_exception=lambda kind,value,trace:errors.append(value)
        try:
            from window_capture import destroy_test_window
            app=App(root)
            self.assertEqual(len(app.tab_scrolls),7);self.assertIsInstance(app.proc_scroll,display.ScrollableFrame)
            for _ in range(3):root.update()
            for scale in (100,125,150):
                app.set_ui_zoom(scale);root.update_idletasks()
            # Reflow can leave non-idle timers. All must have valid ownership
            # when the test helper cancels them via root before root.destroy().
            for timer in root.tk.splitlist(root.tk.call('after','info')):root.after_cancel(timer)
            missing=[]
            def inspect(widget):
                for command in widget._tclCommands or []:
                    if not root.tk.call('info','commands',command):missing.append((type(widget).__name__,command))
                for child in widget.winfo_children():inspect(child)
            inspect(root)
            self.assertEqual(missing,[])
            destroy_test_window(root)
            self.assertEqual(errors,[])
        finally:
            try:
                if root.winfo_exists():
                    for timer in root.tk.splitlist(root.tk.call('after','info')):root.after_cancel(timer)
                    root.destroy()
            except display.tk.TclError:pass

if __name__=='__main__':unittest.main()
