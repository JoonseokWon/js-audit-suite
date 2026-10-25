"""Regression cases from the independent v1.9 UI review.

All windows remain withdrawn, focus_set is blocked, and every engagement is
synthetic and temporary. No inference, server, network, real archive selection,
real engagement or worker thread is used. Races are injected synchronously at
specific call boundaries instead of relying on sleeps or scheduling luck.
"""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import runtime
runtime.configure()
runtime.configure_tk_libraries()
import tkinter as tk
from tkinter import ttk

import ai_desktop
import workflow_desktop
from app import App
from audit_forms import load_registry
from common import AuditError, digest, dumps
from workspace import Workspace

ROOT = Path(__file__).resolve().parent
VERIFY = ROOT.parents[1] / '검증' / 'v1.9.0' / 'ui_review'
CONTEXT = {'회사코드': 'SYNTH01', '회사명': 'SYNTHETIC UI REVIEW ONLY',
           '시작일': '2026-01-01', '기준일': '2026-12-31', '회계체계': 'K-IFRS',
           '감사기준': '합성 검토', '작성자': '합성작성자', '더미업무': True}


class _NoRuntime:
    base_url = 'http://127.0.0.1:11437'

    def __init__(self, *args, **kwargs):
        pass

    def stop(self):
        pass


def _profile(reason='합성 사람이 선택한 기준', pids=('C01',)):
    return {'audit_framework': 'KSA_200_720', 'audit_framework_reason': reason,
            'form_framework': 'KIFRS',
            'materiality': {'benchmark_name': '합성 매출', 'benchmark_amount': 100000000,
                            'materiality_rate': '0.05', 'performance_rate': '0.75', 'trivial_rate': '0.01'},
            'scope': [{'procedure_id': pid, 'applicable': True, 'reason': '합성 사람이 선택한 범위'} for pid in pids]}


def _button(parent, label):
    for widget in parent.winfo_children():
        if isinstance(widget, ttk.Button) and widget.cget('text') == label:
            return widget
        try:
            return _button(widget, label)
        except LookupError:
            pass
    raise LookupError('Button not found: ' + label)


@unittest.skipUnless(sys.platform == 'win32', 'Windows-native UI regression tests')
class WorkflowUIReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        VERIFY.mkdir(parents=True, exist_ok=True)
        cls.class_temp = tempfile.TemporaryDirectory(prefix='hidden-root-', dir=VERIFY)
        cls.runtime_patch = patch.object(ai_desktop, 'LocalAIRuntime', _NoRuntime)
        cls.runtime_patch.start()
        cls.root = None
        cls.focus_patch = None
        try:
            try:
                cls.root = tk.Tk()
            except tk.TclError as exc:
                if sys.platform != 'win32' and ('no display name' in str(exc).lower()
                                               or "couldn't connect to display" in str(exc).lower()):
                    raise unittest.SkipTest('No native display') from exc
                raise
            cls.root.withdraw()
            cls.focus_patch = patch.object(cls.root, 'focus_set', return_value=None)
            cls.focus_patch.start()
            cls.app = App(cls.root, sector_home=Path(cls.class_temp.name) / 'synthetic-sectors')
            cls.root.update_idletasks()
            if cls.root.state() != 'withdrawn':
                raise AssertionError('The review test root must remain withdrawn')
        except BaseException:
            if cls.root is not None:
                cls.root.destroy()
            if cls.focus_patch is not None:
                cls.focus_patch.stop()
            cls.runtime_patch.stop()
            cls.class_temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.cancel.set()
            cls.app.shutdown_ai()
            cls.root.destroy()
        finally:
            cls.focus_patch.stop()
            cls.runtime_patch.stop()
            cls.class_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=VERIFY)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.errors = []
        self.error_patch = patch.object(workflow_desktop.messagebox, 'showerror',
                                       side_effect=lambda *args, **kwargs: self.errors.append(args))
        self.error_patch.start()
        self.addCleanup(self.error_patch.stop)
        self.confirm_patch = patch.object(workflow_desktop.messagebox, 'askokcancel', return_value=True)
        self.confirm_patch.start()
        self.addCleanup(self.confirm_patch.stop)
        self.app.busy = False
        self.app.closing = False
        self.ws = Workspace(self.base / 'A', create=CONTEXT)
        self.app.ws = self.ws
        self.app.reset_workspace_view()
        self.app.refresh()

    def tearDown(self):
        modal = getattr(self.app, 'wf_modal', None)
        if modal is not None and modal.win.winfo_exists():
            modal.close(force=True)
        self.assertEqual(self.root.state(), 'withdrawn')

    def test_01_dynamic_exception_and_reconciliation_scope_have_explicit_unmapped_form_rows(self):
        self.ws.execute('원장·리드', ROOT / 'samples/통합/통합_01_원장정상.xlsx')
        self.ws.execute('금융상품', ROOT / 'samples/통합/통합업무_금융정상.xlsx')
        latest = self.ws.latest()['금융상품']
        result = deepcopy(latest['result'])
        result['metrics']['원금'] -= 1
        result['issues'].append({'code': 'SYNTHETIC_UI_REVIEW', 'severity': '검토',
                                 'message': '합성 수동 확인', 'reference': 'SYNTHETIC ONLY'})
        self.ws._append('run', {**latest, 'id': 'synthetic-ui-review-run',
                                'result': result, 'result_hash': digest(result)})
        self.ws.refresh()
        selected = sorted(self.ws.required_procedures())
        dynamic = [pid for pid in selected if pid.startswith(('X-', 'B-'))]
        self.assertTrue(any(pid.startswith('X-') for pid in dynamic))
        self.assertTrue(any(pid.startswith('B-') for pid in dynamic))
        self.ws.save_workflow_profile(_profile(pids=selected), '합성계획자')
        self.app.refresh_workflow()
        rows = {row['절차ID']: row for row in self.app.wf_state['form_rows']}
        for pid in dynamic:
            with self.subTest(pid=pid):
                self.assertIn(pid, rows)
                self.assertEqual(rows[pid]['연결상태'].replace(' ', ''), '공식참고미지정')
                self.assertFalse(rows[pid].get('공식서식ID'))
                self.assertEqual(rows[pid]['서식계열'], 'KIFRS')
        self.assertEqual(len(self.app.wf_form_tree.get_children()), len(self.app.wf_state['form_rows']))

    def test_02_workspace_switch_clears_previous_detail_and_archive_cache(self):
        marker = '업무A에만있는합성위험·증거·ZIP'
        self.app.wf_detail.configure(state='normal')
        self.app.wf_detail.insert('1.0', marker)
        self.app.wf_detail.configure(state='disabled')
        self.app.wf_last_archive = {'path': str(self.base / '업무A.zip'), 'marker': marker}
        self.app.wf_state['old_business_marker'] = marker
        second = Workspace(self.base / 'B', create={**CONTEXT, '회사명': '합성 업무 B'})
        self.app.open_workspace(second.root)
        self.assertEqual(self.app.ws.engagement['회사명'], '합성 업무 B')
        self.assertEqual(self.app.wf_detail.get('1.0', 'end').strip(), '')
        self.assertEqual(self.app.wf_last_archive, {})
        self.assertNotIn(marker, dumps(self.app.wf_state))
        self.assertFalse(self.app.wf_form_tree.get_children())

    def _unsaved_inputs(self):
        source = self.base / 'synthetic-evidence.txt'
        source.write_text('SYNTHETIC ONLY / read-only UI verification fixture', encoding='utf-8')
        self.ws.add_source(source, '합성 증거')
        self.app.refresh()
        self.app.load_procedure('C01')
        self.app.proc_text['performed'].insert('1.0', '저장하지 않은 합성 수행 입력')
        self.app.request_vars['title'].set('저장하지 않은 합성 요청')
        self.app.request_evidence.selection_set(0)
        self.app.reviewer.set('저장하지 않은 합성 검토자')
        self.app.review_note.set('저장하지 않은 합성 검토내용')
        return (self.app.form_signature(), self.app.request_signature(),
                (self.app.reviewer.get(), self.app.review_note.get()))

    def _input_signatures(self):
        return (self.app.form_signature(), self.app.request_signature(),
                (self.app.reviewer.get(), self.app.review_note.get()))

    def test_03_verify_navigation_cancel_preserves_unsaved_inputs_and_does_not_start_job(self):
        original = self._unsaved_inputs()
        with patch.object(workflow_desktop.messagebox, 'askyesnocancel', return_value=None) as confirm, \
                patch.object(workflow_desktop.filedialog, 'askopenfilename') as chooser, \
                patch.object(self.app, '_wf_background') as background:
            self.app.workflow_verify_dialog()
        confirm.assert_called_once()
        chooser.assert_not_called()
        background.assert_not_called()
        self.assertEqual(self._input_signatures(), original)

    def test_04_verify_success_and_error_completion_preserve_all_unsaved_inputs(self):
        original = self._unsaved_inputs()
        self.assertTrue(self.app.dirty())
        self.app.finish_workflow_job('workflow_error', '합성 검증 오류')
        self.assertEqual(self._input_signatures(), original)
        self.assertTrue(self.app.dirty())
        self.app.finish_workflow_job('workflow_ok', {'valid': True, 'path': str(self.base / 'synthetic.zip'),
                                                    'mode': 'draft', 'source_count': 1})
        self.assertEqual(self._input_signatures(), original)
        self.assertTrue(self.app.dirty())
        self.assertFalse(self.ws.procedures)

    def test_05_ui_save_rejects_change_after_dialog_head_check_without_losing_input(self):
        self.ws.save_workflow_profile(_profile('기존 합성 계획'), '합성계획자')
        self.app.refresh()
        dialog = self.app.open_workflow_profile()
        field = dialog.fields['audit_framework_reason']
        field.delete('1.0', 'end')
        field.insert('1.0', '열어 둔 화면의 오래된 합성 계획')
        expected_head = dialog.head
        original_guard = self.ws.assert_writeable
        injected = False

        def concurrent_change(*args, **kwargs):
            nonlocal injected
            if not injected:
                injected = True
                other = Workspace(self.ws.root)
                other.save_workflow_profile(_profile('다른 작성자가 저장한 최신 합성 계획'), '다른 합성계획자')
            return original_guard(*args, **kwargs)

        with patch.object(self.ws, 'assert_writeable', side_effect=concurrent_change):
            _button(dialog.buttons, '계획 저장·중요성 계산').invoke()
        self.ws.refresh()
        self.assertTrue(injected)
        self.assertNotEqual(self.ws.head, expected_head)
        self.assertEqual(self.ws.workflow_profile['audit_framework_reason'], '다른 작성자가 저장한 최신 합성 계획')
        self.assertEqual(len([e for e in self.ws.events if e['kind'] == 'workflow_profile']), 2)
        self.assertEqual(len(self.errors), 1)
        self.assertTrue(dialog.win.winfo_exists())
        self.assertEqual(dialog.value('audit_framework_reason'), '열어 둔 화면의 오래된 합성 계획')

    def test_06_db_compare_and_swap_rejects_race_after_validation(self):
        self.ws.save_workflow_profile(_profile('기존 합성 계획'), '합성계획자')
        before = self.ws.head
        original_append = self.ws._append
        injected = False

        def competing_append(kind, data, expected_head=None):
            nonlocal injected
            if kind == 'workflow_profile' and not injected:
                injected = True
                other = Workspace(self.ws.root)
                other.save_workflow_profile(_profile('DB 경합의 최신 합성 계획'), '다른 합성계획자')
            return original_append(kind, data, expected_head=expected_head)

        with patch.object(self.ws, '_append', side_effect=competing_append):
            with self.assertRaises(AuditError):
                self.ws.save_workflow_profile(_profile('덮어쓰면 안 되는 오래된 계획'), '합성계획자', expected_head=before)
        self.ws.refresh()
        self.assertTrue(injected)
        self.assertEqual(self.ws.workflow_profile['audit_framework_reason'], 'DB 경합의 최신 합성 계획')
        self.assertEqual(len([e for e in self.ws.events if e['kind'] == 'workflow_profile']), 2)

    def test_07_all_54_procedures_are_plannable_before_runs_without_recording_performance(self):
        self.assertFalse(self.ws.runs)
        before = self.ws.head
        dialog = self.app.open_workflow_profile()
        ids = set(dialog.scope_tree.get_children())
        static_ids = {row['app_id'] for row in load_registry()['procedures']}
        self.assertEqual(len(static_ids), 54)
        self.assertTrue(static_ids <= ids)
        self.assertTrue({'G01', 'I01', 'H01'} <= ids)
        dialog.scope_tree.selection_set('G01')
        dialog.fields['scope_reason'].insert('1.0', '수행 전 사람이 선택한 합성 계획')
        _button(dialog.body, '선택 절차 적용').invoke()
        self.assertTrue(dialog.scope_records['G01']['applicable'])
        self.ws.refresh()
        self.assertEqual(self.ws.head, before)
        self.assertFalse(self.ws.runs)
        self.assertFalse(self.ws.workflow_procedure_links)
        self.assertFalse(self.ws.procedures)
        self.assertFalse(self.ws.ai_approvals)


if __name__ == '__main__':
    unittest.main()
