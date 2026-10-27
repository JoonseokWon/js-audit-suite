"""Hidden Tk/native controls only; no physical IME, DPI or Office automation."""
from pathlib import Path
from types import SimpleNamespace
import sys
import tkinter as tk
from unittest.mock import patch
import unittest
from common import AuditError
import test_audit_links
import audit_links


@unittest.skipUnless(sys.platform == 'win32', 'Windows native editor')
class AuditLinksDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import runtime
        runtime.configure(); runtime.configure_tk_libraries()
        cls.root = tk.Tk(); cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        from window_capture import destroy_test_window
        destroy_test_window(cls.root)

    def setUp(self):
        self.fixture = test_audit_links.AuditLinkTests(); self.fixture.setUp(); self.ws = self.fixture.ws
        self.host = SimpleNamespace(root=self.root, ws=self.ws, display=SimpleNamespace(refresh_widgets=lambda: None),
                                    status=tk.StringVar(self.root), guard=lambda: None, check_navigation=lambda: True,
                                    refresh=lambda: None, call=lambda fn: fn())
        self.opened = []

    def tearDown(self):
        for child in list(self.root.winfo_children()):
            try: child.destroy()
            except tk.TclError: pass
        self.fixture.doCleanups()

    def test_readonly_dialog_is_hidden_head_pinned_and_does_not_activate(self):
        from desktop.audit_links import open_dialog
        head = self.ws.head; d = open_dialog(self.host)
        self.assertEqual('withdrawn', d.win.state()); self.assertEqual(head, d.head)
        self.assertFalse(d.win.audit_links_state['active']); self.assertEqual(head, self.ws.head)
        self.assertEqual('', d.value('risk_id')); self.assertEqual('', d.value('response_id'))
        self.assertTrue(hasattr(d.win, 'audit_links_tree')); d.close(force=True)

    def test_risk_and_actual_performance_choices_start_blank(self):
        from desktop.audit_links.forms import assessment_form, performance_form
        d = assessment_form(self.host, 'RISK-SALES')
        for key in ('actor', 'inherent_rating', 'inherent_reason', 'control_rating', 'control_reason', 'significant', 'significant_reason'):
            self.assertEqual('', d.value(key), key)
        d.close(force=True); self.fixture.prepare(); head = self.ws.head
        d = performance_form(self.host, 'RESPONSE-1')
        for key in ('actor', 'performed', 'performed_date', 'performer', 'sufficiency', 'sufficiency_reason'):
            self.assertEqual('', d.value(key), key)
        self.assertEqual(head, self.ws.head); d.close(force=True)

    def test_original_xml_control_is_rejected_before_whitespace_trim(self):
        from desktop.audit_links.forms import assessment_form
        d = assessment_form(self.host, 'RISK-SALES'); head = self.ws.head
        d.fields['actor'].set('\x0bSYNTHETIC ONLY')
        with self.assertRaises(AuditError) as error:
            d.value('actor')
        self.assertIn('U+000B', str(error.exception)); self.assertEqual(head, self.ws.head)
        d.close(force=True)

    def test_dirty_close_cancel_and_workspace_head_change_preserve_input(self):
        from desktop.audit_links.forms import assessment_form
        d = assessment_form(self.host, 'RISK-SALES'); d.fields['actor'].set('SYNTHETIC ONLY 직접 입력')
        with patch('desktop.workflow.shared.messagebox.askokcancel', return_value=False):
            self.assertFalse(d.close()); self.assertTrue(d.win.winfo_exists())
        self.ws.add_note('합성 다른창', '중간 변경', '합성')
        with patch('desktop.workflow.shared.messagebox.showerror'):
            self.assertIsNone(d.save(lambda: self.fail('old-head write must not run'), 'saved'))
        self.assertIn('이력이 변경', self.host.status.get()); self.assertTrue(d.win.winfo_exists())
        d.close(force=True)

    def test_source_attestation_and_run_selection_not_prefilled(self):
        from desktop.audit_links.forms import response_form
        self.fixture.prepare(); d = response_form(self.host, 'RISK-SALES')
        for key in ('pid', 'company_code', 'start_date', 'end_date', 'locator', 'relevance', 'actor'):
            self.assertEqual('', d.value(key), key)
        self.assertEqual([], d.value('sources')); self.assertEqual([], d.value('runs')); d.close(force=True)


if __name__ == '__main__':
    unittest.main()
