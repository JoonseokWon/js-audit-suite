"""Bento routes and dirty-state guards. No real workspaces, keys or OS changes."""
from pathlib import Path
import ast
import hashlib
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parent

class DesktopStructureTests(unittest.TestCase):
    def test_app_entry_point_is_small_and_parseable(self):
        source=(SOURCE/'app.py').read_text(encoding='utf-8-sig')
        ast.parse(source)
        self.assertLessEqual(len(source.splitlines()),150)

    def test_views_and_actions_are_separate_modules(self):
        for folder in ('desktop/actions','desktop/views','desktop/widgets'):
            paths=list((SOURCE/folder).glob('*.py'))
            self.assertGreaterEqual(len(paths),3,folder)
            for path in paths:
                with self.subTest(path=path.name):ast.parse(path.read_text(encoding='utf-8-sig'))

    def test_all_ui_modules_stay_smaller_than_the_original_monolith(self):
        # These are preserved independent-tool domain copies, not UI modules.
        domain_copies={'desktop/tools/cashflow/engine.py','desktop/tools/cashflow/excel_io.py',
                       'desktop/tools/cashflow/samples.py'}
        for path in (SOURCE/'desktop').rglob('*.py'):
            if path.relative_to(SOURCE).as_posix() in domain_copies:
                continue
            with self.subTest(path=str(path.relative_to(SOURCE))):
                self.assertLessEqual(len(path.read_text(encoding='utf-8-sig').splitlines()),240)

@unittest.skipUnless(sys.platform=='win32','Native desktop integration requires Windows')
class BentoDesktopTests(unittest.TestCase):
    def setUp(self):
        import runtime
        runtime.configure();runtime.configure_tk_libraries()
        import tkinter as tk
        from app import App
        self.temp=tempfile.TemporaryDirectory();self.store=Path(self.temp.name)/'not-created-store'
        self.root=tk.Tk();self.root.withdraw();self.app=App(self.root,sector_home=self.store)

    def tearDown(self):
        self.app.shutdown_ai()
        from window_capture import destroy_test_window
        destroy_test_window(self.root);self.temp.cleanup()

    def test_root_remains_withdrawn(self):
        self.assertEqual(self.root.state(),'withdrawn')

    def test_default_home_and_nine_existing_workflows_remain_reachable(self):
        self.assertEqual(len(self.app.tabs),10)
        self.assertEqual(self.app.nb.select(),str(self.app.tabs['업무 요약']))
        for name,tab in self.app.tabs.items():
            self.assertTrue(self.app.navigate(name));self.assertEqual(self.app.nb.select(),str(tab))
            self.assertEqual(self.app.sidebar.active,name)

    def test_sidebar_contains_one_button_for_every_destination(self):
        self.assertEqual(set(self.app.tabs),set(self.app.sidebar.buttons))

    def test_module_routes_are_read_only_and_use_the_existing_module_names(self):
        from adapters import MODULES
        for module in MODULES:
            with self.subTest(module=module):
                self.assertTrue(self.app.route_module(module))
                self.assertEqual(self.app.module.get(),module)
                self.assertEqual(self.app.nb.select(),str(self.app.tabs['자료·검사']))
                self.assertIsNone(self.app.ws);self.assertFalse(self.store.exists())

    def test_navigation_obeys_unsaved_form_guard(self):
        current=self.app.nb.select()
        with patch.object(self.app,'check_navigation',return_value=False):
            self.assertFalse(self.app.navigate('절차·조서'))
        self.assertEqual(current,self.app.nb.select())

    def test_module_route_obeys_unsaved_form_guard_before_changing_module(self):
        from adapters import MODULES
        before=(self.app.module.get(),self.app.nb.select())
        with patch.object(self.app,'check_navigation',return_value=False):
            self.assertFalse(self.app.route_module(MODULES[-1]))
        self.assertEqual(before,(self.app.module.get(),self.app.nb.select()))

    def test_dashboard_refresh_does_not_create_an_engagement_or_data_folder(self):
        before=(self.app.ws,self.store.exists())
        self.app.refresh_dashboard();self.app.refresh_dashboard()
        self.assertEqual(before,(self.app.ws,self.store.exists()))

    def test_dashboard_contains_metric_and_module_cards(self):
        self.assertGreaterEqual(len(self.app.dashboard.grid.items),4)
        self.assertTrue({'sources','runs','cross','pending'}<=set(self.app.dashboard.values))
        from adapters import MODULES
        self.assertEqual(set(self.app.dashboard.module_states),set(MODULES))

    def test_scroll_containers_remain_available_at_high_text_zoom(self):
        self.assertEqual(len(self.app.tab_scrolls),9)
        for scale in (100,125,150,175):
            self.app.set_ui_zoom(scale)
            self.assertEqual(self.root.state(),'withdrawn')
            self.assertEqual(len(self.app.tab_scrolls),9)

if __name__=='__main__':unittest.main()
