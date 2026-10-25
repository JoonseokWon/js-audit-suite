"""Regression tests for unsaved review text, hidden callbacks and native fonts."""
from pathlib import Path
import gc
import sys
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(sys.platform == 'win32', 'Native desktop tests require Windows')
class BentoPreservationTests(unittest.TestCase):
    def setUp(self):
        import runtime
        runtime.configure()
        runtime.configure_tk_libraries()
        from app import App, tk
        from workspace import Workspace
        from verify import synthetic_procedure
        self.temp = tempfile.TemporaryDirectory(prefix='audit-bento-preservation-')
        base = Path(self.temp.name)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = App(self.root, sector_home=base / 'synthetic-store')
        self.ws = Workspace(base / 'work', create={
            '회사코드': 'SYNTH01', '회사명': '합성 입력보존 검증',
            '시작일': '2026-01-01', '기준일': '2026-12-31',
            '회계체계': 'K-IFRS', '감사기준': '합성 검증용',
            '작성자': '합성작성자', '더미업무': True,
        })
        raw = base / 'synthetic.txt'
        raw.write_text('SYNTHETIC ONLY / not real audit evidence', encoding='utf-8')
        sid = self.ws.add_source(raw, '합성 증거')
        self.ws.save_procedure(synthetic_procedure('C01', [sid]))
        self.app.open_workspace(self.ws.root)
        self.app.load_procedure('C01')
        self.head = self.app.ws.head

    def tearDown(self):
        try:
            self.assertEqual(self.root.state(), 'withdrawn')
            self.app.shutdown_ai()
            from window_capture import destroy_test_window
            destroy_test_window(self.root)
        finally:
            self.temp.cleanup()

    def review_input(self):
        value = ('미저장합성검토자', '임시 합성 검토메모 / 실제 검토 아님')
        self.app.reviewer.set(value[0])
        self.app.review_note.set(value[1])
        return value

    def assert_review_text(self, value):
        self.assertEqual((self.app.reviewer.get(), self.app.review_note.get()), value)
        self.assertNotEqual(self.app.review_saved, value)

    def test_hidden_action_row_waits_for_configure_without_polling(self):
        from desktop.widgets.flow import FlowFrame
        row = FlowFrame(self.root)
        self.root.update_idletasks()
        self.assertLess(row.winfo_width(), 100)
        before = self.root.tk.call('after', 'info')
        row.reflow()
        self.assertIsNone(row.pending)
        self.assertEqual(self.root.tk.call('after', 'info'), before)
        row.destroy()
        row.schedule()
        self.assertIsNone(row.pending)

    def test_review_only_dirty_cancel_keeps_procedure_text_and_selection(self):
        from tkinter import messagebox
        pending = self.review_input()
        index = next(str(i) for i, task in enumerate(self.app.tasks) if task['id'] == 'C02')
        self.app.proc_tree.selection_set(index)
        with patch.object(messagebox, 'askokcancel', return_value=False) as confirm:
            self.app.on_procedure_select()
        confirm.assert_called_once()
        self.assertEqual(self.app.current_pid, 'C01')
        selected = int(self.app.proc_tree.selection()[0])
        self.assertEqual(self.app.tasks[selected]['id'], 'C01')
        self.assert_review_text(pending)
        self.assertEqual(self.app.ws.head, self.head)

    def test_save_keeps_unsaved_review_text_without_saving_review(self):
        pending = self.review_input()
        self.app.proc_text['purpose'].insert('end', ' 합성 수정')
        self.app.save_procedure()
        self.assert_review_text(pending)
        record = self.app.ws.procedures['C01']
        self.assertEqual(record['state'], '작성중')
        self.assertEqual((record['reviewer'], record['review_note']), ('', ''))

    def test_request_keeps_unsaved_review_text_without_approval(self):
        pending = self.review_input()
        self.app.request_review()
        self.assert_review_text(pending)
        record = self.app.ws.procedures['C01']
        self.assertEqual(record['state'], '검토요청')
        self.assertEqual((record['reviewer'], record['review_note']), ('', ''))
        self.assertFalse(self.app.ws.ai_approvals)

    def test_workpaper_quick_action_obeys_navigation_guard(self):
        before = self.app.nb.select()
        with patch.object(self.app, 'check_navigation', return_value=False) as guard:
            self.assertFalse(self.app.open_workpaper_draft())
        guard.assert_called_once()
        self.assertEqual(self.app.nb.select(), before)
        self.assertEqual(self.app.ws.head, self.head)

    def test_candidate_quick_actions_preserve_context_when_cancelled(self):
        before = (self.app.request_signature(), self.app.nb.select())
        candidate = {'후보키': 'synthetic', '조서ID': 'C02'}
        with patch.object(self.app, 'selected_risk', return_value=candidate), \
                patch.object(self.app, 'check_navigation', return_value=False):
            self.assertFalse(self.app.risk_request())
            self.app.risk_workpaper()
        self.assertEqual((self.app.request_signature(), self.app.nb.select()), before)
        self.assertEqual(self.app.current_pid, 'C01')
        self.assertEqual(self.app.ws.head, self.head)

    def test_issue_quick_action_cannot_skip_navigation_guard(self):
        self.app.issue_tree.insert('', 'end', iid='0', values=('합성',))
        self.app.issue_tree.selection_set('0')
        with patch.object(self.app, 'check_navigation', return_value=False) as guard:
            self.app.select_issue()
        guard.assert_called_once()
        self.assertEqual(self.app.current_pid, 'C01')
        self.assertEqual(self.app.ws.head, self.head)

    def test_design_named_fonts_keep_native_names_and_sizes_after_gc(self):
        from tkinter import font
        gc.collect()
        expected = {'AuditTitle': 24, 'AuditMetric': 27, 'AuditSection': 15, 'AuditBrand': 17}
        owners = self.root._audit_design_fonts
        for name, size in expected.items():
            with self.subTest(name=name):
                self.assertIn(name, owners)
                self.assertIn(name, font.names(self.root))
                self.assertEqual(font.nametofont(name, root=self.root).cget('size'), size)
                self.assertEqual(str(owners[name]), name)

    def test_adjacent_keyboard_navigation_uses_guard_and_notebook_is_not_focusable(self):
        self.assertFalse(self.root.tk.getboolean(self.app.nb.cget('takefocus')))
        before = self.app.nb.select()
        with patch.object(self.app, 'check_navigation', return_value=False) as guard:
            self.assertEqual(self.app.navigate_adjacent(1), 'break')
            self.assertEqual(self.app.navigate_adjacent(-1), 'break')
        self.assertEqual(guard.call_count, 2)
        self.assertEqual(self.app.nb.select(), before)
        self.assertEqual(self.app.ws.head, self.head)


if __name__ == '__main__':
    unittest.main()
