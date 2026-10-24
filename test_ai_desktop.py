"""Actual Tk click paths with mocked inference/runtime; zero model/network I/O."""
import copy
import json
import queue
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import runtime
runtime.configure()
runtime.configure_tk_libraries()
import tkinter as tk
from tkinter import ttk
import ai_desktop
import ai_provider
from app import App
from common import AuditError, digest, dumps
from workspace import Workspace


def mock_response(packet):
    """Explicit fixed unit fixture; never used as a production fallback."""
    ref = packet['references'][0]['id']
    fields = {
        'purpose': f'고정 모의 응답이며 모델 호출은 없다. 합성 자료 검토 초안이다. [{ref}]',
        'risk': f'입력 누락과 추출 신뢰성에 대한 사람의 판단이 필요하다. [{ref}]',
        'scope': f'현재 회사와 기간의 발췌 자료이며 생략된 범위는 미확인이다. [{ref}]',
        'performed': f'자동검사 자료를 기록할 초안이다. 실사·조회·수령 확인은 미수행이다. [{ref}]',
        'conclusion': f'사람 검토 전 초안이며 예외·미수행 범위의 추가 확인과 판단이 필요하다. [{ref}]',
    }
    citations = {field: [ref] for field in fields}
    exceptions = [item for item in packet['references'] if item['kind'] == 'exception']
    if exceptions:
        fields['performed'] += ' 선택 예외 코드: ' + ', '.join(dict.fromkeys(item['data']['code'] for item in exceptions)) + '.'
        citations['performed'] = list(dict.fromkeys([ref] + [item['id'] for item in exceptions]))
        fields['conclusion'] += ' 선택된 예외·누락은 사람이 추가조사와 추가확인을 해야 한다.'
    context = {'company_code': packet['engagement']['company_code'],
               'procedure_id': packet['procedure']['id'], 'basis': packet['basis']}
    return {'fields': fields, 'citations': citations, **context,
            'provider': 'ollama', 'model': 'unit-fixture-no-inference',
            'prompt_version': ai_provider.PROMPT_VERSION, 'packet_hash': digest(packet),
            'raw_response': dumps({'fields': fields, 'citations': citations, 'context': context})}


class MockRuntime:
    """No process start, download, HTTP or model loading even if UI calls it."""
    base_url = 'http://127.0.0.1:11437'

    def __init__(self, root=None):
        self.root = Path(root or tempfile.gettempdir()) / ('mock-local-ai' if root is None else '')
        self.stop_calls = 0
        self.ensure_calls = 0
        self.status_calls = 0
        self.setup_calls = 0

    def stop(self):
        self.stop_calls += 1

    def ensure_server(self, **_):
        self.ensure_calls += 1
        return {'ready': True, 'mock': True}

    def status(self):
        self.status_calls += 1
        return {'ready': False, 'mock': True, 'downloaded': False}

    def setup(self, **_):
        self.setup_calls += 1
        return {'ready': True, 'mock': True, 'downloaded': False}


class AIDesktopNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime_patch = patch.object(ai_desktop, 'LocalAIRuntime', MockRuntime)
        cls.runtime_patch.start()
        cls.temp_class = tempfile.TemporaryDirectory()
        try:
            try:
                cls.root = tk.Tk()
            except tk.TclError as exc:
                if sys.platform != 'win32' and ('no display name' in str(exc).lower() or "couldn't connect to display" in str(exc).lower()):
                    raise unittest.SkipTest('No native display') from exc
                raise
            cls.root.withdraw()
            cls.app = App(cls.root, sector_home=Path(cls.temp_class.name) / 'sectors')
            cls.root.update_idletasks()
        except BaseException:
            cls.runtime_patch.stop()
            cls.temp_class.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.cancel.set()
            cls.app.shutdown_ai()
            cls.root.destroy()
        finally:
            cls.runtime_patch.stop()
            cls.temp_class.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.errors = []
        self.sent = []
        self.blocker = threading.Event()
        self.addCleanup(self.blocker.set)
        self.error_patch = patch.object(ai_desktop.messagebox, 'showerror', side_effect=lambda *a, **k: self.errors.append(a))
        self.error_patch.start()
        self.addCleanup(self.error_patch.stop)
        self.ask_patch = patch.object(ai_desktop.messagebox, 'askyesnocancel', return_value=False)
        self.ask_mock = self.ask_patch.start()
        self.addCleanup(self.ask_patch.stop)
        self.confirm_patch = patch.object(ai_desktop.messagebox, 'askokcancel', return_value=True)
        self.confirm_patch.start()
        self.addCleanup(self.confirm_patch.stop)
        self.model_patch = patch.object(ai_desktop, 'generate_draft', side_effect=self.provider)
        self.model = self.model_patch.start()
        self.addCleanup(self.model_patch.stop)
        self.app.cancel.clear()
        self.app.closing = False
        self.app.ai_runtime = MockRuntime(self.base / 'runtime')
        self.app.ai_config = {'provider': 'ollama', 'model': ai_provider.DEFAULT_MODEL,
                              'endpoint': MockRuntime.base_url, 'num_gpu': 0,
                              'num_ctx': 16384, 'timeout_seconds': 300}
        self.app.ai_api_key = ''
        self.app.ai_openai_model = ''
        self.ws = self.open_workspace('JS_TEST', '업무A')

    def tearDown(self):
        self.blocker.set()
        self.app.cancel.set()
        deadline = time.monotonic() + 3
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        if self.app.busy:
            self.app.set_busy(False)
        for widget in list(self.root.winfo_children()):
            if isinstance(widget, tk.Toplevel):
                widget.destroy()
        self.app.ai_api_key = ''
        self.app.ai_openai_model = ''
        self.root.update_idletasks()

    def provider(self, packet, config, event):
        # Check the real fixed-endpoint guard without making any HTTP request.
        ai_provider._endpoint(config['provider'], config.get('endpoint'))
        self.sent.append({'packet': copy.deepcopy(packet), 'config': dict(config)})
        response = mock_response(packet)
        response['provider'] = config['provider']
        return response

    def open_workspace(self, code, name):
        folder = self.base / name
        Workspace(folder, create={'회사코드': code, '회사명': name + ' SYNTHETIC ONLY',
                  '시작일': '2026-01-01', '기준일': '2026-12-31', '회계체계': 'K-IFRS',
                  '감사기준': '합성 단위검사', '작성자': '합성작성자', '더미업무': True})
        self.app.open_workspace(folder)
        self.app.load_procedure('A04')
        self.root.update_idletasks()
        return self.app.ws

    def pump(self, until=None):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.root.update()
            if (until() if until else not self.app.busy):
                return
            time.sleep(.01)
        self.fail('Mock UI job did not finish within five seconds')

    def install_applied_draft(self):
        packet = self.ws.ai_packet('A04', self.app.ai_catalog)
        did = self.ws.record_ai_draft(packet, mock_response(packet), '모의요청자')
        self.ws.apply_ai_draft(did, '사람작성자')
        self.app.refresh()
        self.app.load_procedure('A04')
        return did

    def approval_window(self):
        self.app.ai_approve_button.invoke()
        win = self.app.ai_approval_win
        win.confirmed.set(True)
        win.actor.set('사람승인자')
        win.note.insert('1.0', '모의 초안의 실제 표시 내용과 근거·한계를 사람이 확인한 단위검사')
        return win

    def open_openai_consent(self):
        self.app.ai_config['provider'] = 'openai'
        self.app.ai_openai_model = 'explicit-unit-test-model'
        self.app.ai_api_key = 'unit_fixture_key_' + 'x' * 32
        self.app.ai_generate_button.invoke()
        self.assertTrue(self.app.ai_consent_win.winfo_exists())
        return self.app.ai_consent_win

    def test_native_local_generate_preview_apply_approval_click_path(self):
        self.assertEqual(self.app.ai_generate_button.cget('text'), 'AI 초안 생성')
        self.app.ai_generate_button.invoke()
        self.pump()
        self.assertFalse(self.errors)
        self.assertEqual(len(self.ws.ai_drafts), 1)
        self.assertNotIn('A04', self.ws.procedures)
        sent = self.sent[0]
        self.assertEqual(sent['config']['model'], ai_provider.DEFAULT_MODEL)
        self.assertLessEqual(len(dumps(sent['packet'])), 12000)
        self.app.ai_preview_win.apply_button.invoke()
        self.assertFalse(self.errors)
        self.assertEqual(self.ws.ai_status('A04')['state'], 'AI 최종내용 미승인')
        win = self.approval_window()
        win.approve_button.invoke()
        self.assertFalse(self.errors)
        self.assertTrue(self.ws.ai_status('A04')['approved'])

    def test_negative_sales_mock_draft_preserves_selected_exception_codes_and_citations(self):
        source = runtime.configure() / 'samples/기존/매출 자동화/v2_02_청구는있고원장누락.xlsx'
        self.ws.execute('매출', source)
        self.app.refresh()
        self.app.load_procedure('A04')
        self.app.ai_generate_button.invoke()
        self.pump()
        self.assertFalse(self.errors)
        self.assertEqual(len(self.ws.ai_drafts), 1)
        saved = next(iter(self.ws.ai_drafts.values()))
        exceptions = [ref for ref in saved['packet']['references'] if ref['kind'] == 'exception']
        self.assertTrue(exceptions)
        for ref in exceptions:
            self.assertIn(ref['data']['code'], saved['fields']['performed'])
            self.assertIn(ref['id'], saved['citations']['performed'])
        self.assertIn('추가조사', saved['fields']['conclusion'])

    def test_openai_requires_this_request_consent_before_mock_transmission(self):
        win = self.open_openai_consent()
        win.send_button.invoke()
        self.assertFalse(self.app.busy)
        self.assertFalse(self.model.called)
        self.assertTrue(self.errors)
        self.errors.clear()
        win.confirmed.set(True)
        win.send_button.invoke()
        self.pump()
        self.assertFalse(self.errors)
        self.assertEqual(self.sent[0]['config']['provider'], 'openai')
        self.assertTrue(self.sent[0]['config']['external_consent'])
        self.assertNotIn('endpoint', self.sent[0]['config'])
        self.assertEqual(len(self.ws.ai_drafts), 1)

    def test_settings_key_masked_memory_only_not_packet_database_or_response(self):
        self.app.ai_settings_button.invoke()
        win = self.app.ai_settings_win
        key = 'unit_fixture_key_' + 'x' * 32
        self.assertTrue(win.key_entry.cget('show'))
        win.provider.set('OpenAI API')
        win.model.set('explicit-unit-test-model')
        win.key.set(key)
        win.save_button.invoke()
        self.assertEqual(win.key.get(), '')
        self.assertEqual(self.app.ai_api_key, key)
        self.app.ai_generate_button.invoke()
        consent = self.app.ai_consent_win
        consent.confirmed.set(True)
        consent.send_button.invoke()
        self.pump()
        self.assertFalse(self.errors)
        self.assertNotIn(key, dumps(self.sent[0]['packet']))
        self.assertNotIn(key, dumps(list(self.ws.ai_drafts.values())))
        for file in self.ws.root.rglob('*'):
            if file.is_file():
                self.assertNotIn(key.encode(), file.read_bytes())

    def test_cancel_during_pending_inference_discards_late_mock_result(self):
        entered = threading.Event()
        def blocked(packet, config, event):
            entered.set()
            self.blocker.wait(2)
            return mock_response(packet)
        self.model.side_effect = blocked
        start = time.monotonic()
        self.app.ai_generate_button.invoke()
        self.assertLess(time.monotonic() - start, 1)
        self.assertTrue(entered.wait(1))
        self.assertTrue(self.app.busy)
        self.app.sector_cancel.invoke()
        self.blocker.set()
        self.pump()
        self.assertFalse(self.ws.ai_drafts)
        self.assertFalse(self.ws.ai_approvals)
        self.assertIn('취소', self.app.status.get())

    def test_cancel_after_response_queued_before_ui_commit(self):
        self.app.ai_generate_button.invoke()
        deadline = time.monotonic() + 2
        while self.app.queue.empty() and time.monotonic() < deadline:
            time.sleep(.01)
        self.app.cancel.set()
        self.pump()
        self.assertFalse(self.ws.ai_drafts)
        self.assertFalse(self.ws.ai_approvals)

    def test_workspace_switch_is_blocked_while_worker_pending(self):
        self.model.side_effect = lambda packet, config, event: (self.blocker.wait(2), mock_response(packet))[1]
        self.app.ai_generate_button.invoke()
        with self.assertRaises(AuditError):
            self.app.open_workspace(self.ws.root)
        self.assertIs(self.app.ws, self.ws)
        self.app.cancel.set()
        self.blocker.set()
        self.pump()

    def test_cancel_unsaved_form_prompt_prevents_generation(self):
        self.app.proc_text['purpose'].insert('end', ' 아직 저장하지 않은 사람 수정')
        self.ask_mock.return_value = None
        self.app.ai_generate_button.invoke()
        self.assertFalse(self.app.busy)
        self.assertFalse(self.model.called)
        self.assertTrue(self.app.dirty())

    def test_approval_rejects_content_saved_after_dialog_open(self):
        self.install_applied_draft()
        win = self.approval_window()
        self.app.proc_text['conclusion'].insert('end', '\n승인창에 표시되지 않은 새 판단')
        self.app.save_workpaper_button.invoke()
        self.assertFalse(self.app.dirty())
        win.approve_button.invoke()
        self.assertFalse(self.ws.ai_status('A04')['approved'])
        self.assertTrue(self.errors)

    def test_approval_rejects_edit_then_restore_new_revision(self):
        self.install_applied_draft()
        win = self.approval_window()
        original = self.app.proc_text['conclusion'].get('1.0', 'end').strip()
        self.app.proc_text['conclusion'].insert('end', '\n임시 수정')
        self.app.save_workpaper_button.invoke()
        self.app.proc_text['conclusion'].delete('1.0', 'end')
        self.app.proc_text['conclusion'].insert('1.0', original)
        self.app.save_workpaper_button.invoke()
        win.approve_button.invoke()
        self.assertFalse(self.ws.ai_status('A04')['approved'])
        self.assertTrue(self.errors)

    def test_approval_rejects_workspace_changed_behind_old_dialog(self):
        self.install_applied_draft()
        win = self.approval_window()
        other = self.open_workspace('JS_OTHER', '업무B')
        win.approve_button.invoke()
        self.assertFalse(self.ws.ai_approvals)
        self.assertFalse(other.ai_approvals)
        self.assertTrue(self.errors)

    def test_approval_rejects_click_during_another_busy_job(self):
        self.install_applied_draft()
        win = self.approval_window()
        self.app.set_busy(True)
        try:
            win.approve_button.invoke()
        finally:
            self.app.set_busy(False)
        self.assertFalse(self.ws.ai_status('A04')['approved'])
        self.assertTrue(self.errors)

    def test_existing_settings_dialog_cannot_replace_runtime_while_busy(self):
        self.app.ai_settings_button.invoke()
        win = self.app.ai_settings_win
        old = self.app.ai_runtime
        win.runtime_root.set(str(self.base / 'different-runtime'))
        self.app.set_busy(True)
        try:
            win.check_button.invoke()
            win.setup_button.invoke()
        finally:
            self.app.set_busy(False)
        self.assertIs(self.app.ai_runtime, old)
        self.assertEqual(old.stop_calls, 0)
        self.assertEqual(old.status_calls, 0)
        self.assertEqual(old.setup_calls, 0)
        self.assertEqual(len(self.errors), 2)

    def test_old_consent_cannot_send_after_workspace_switch(self):
        win = self.open_openai_consent()
        self.open_workspace('JS_OTHER', '업무B')
        win.confirmed.set(True)
        win.send_button.invoke()
        if self.app.busy:
            self.pump()
        self.assertFalse(self.model.called)
        self.assertFalse(self.ws.ai_drafts)
        self.assertTrue(self.errors)

    def test_old_consent_cannot_send_after_procedure_switch(self):
        win = self.open_openai_consent()
        self.app.load_procedure('P01')
        win.confirmed.set(True)
        win.send_button.invoke()
        if self.app.busy:
            self.pump()
        self.assertFalse(self.model.called)
        self.assertFalse(self.ws.ai_drafts)
        self.assertTrue(self.errors)

    def test_old_consent_cannot_send_after_basis_change(self):
        win = self.open_openai_consent()
        source = self.base / '추가 합성증빙.txt'
        source.write_text('SYNTHETIC ONLY', encoding='utf-8')
        self.ws.add_source(source, '새 합성 근거')
        self.app.refresh()
        win.confirmed.set(True)
        win.send_button.invoke()
        if self.app.busy:
            self.pump()
        self.assertFalse(self.model.called)
        self.assertFalse(self.ws.ai_drafts)
        self.assertTrue(self.errors)

    def test_old_preview_cannot_apply_to_copied_workspace_with_same_draft_id(self):
        packet = self.ws.ai_packet('A04', self.app.ai_catalog)
        did = self.ws.record_ai_draft(packet, mock_response(packet), '모의요청자')
        self.app.ai_preview_button.invoke()
        win = self.app.ai_preview_win
        copied = self.base / '복제 업무B'
        shutil.copytree(self.ws.root, copied)
        self.app.open_workspace(copied)
        self.app.load_procedure('A04')
        other = self.app.ws
        self.assertIn(did, other.ai_drafts)
        win.apply_button.invoke()
        self.assertNotIn('A04', other.procedures)
        self.assertNotIn('A04', self.ws.procedures)
        self.assertTrue(self.errors)

    def test_generic_worker_exception_never_echoes_memory_key(self):
        key = 'unit_fixture_key_' + 'x' * 32
        self.model.side_effect = RuntimeError(key)
        self.app.ai_generate_button.invoke()
        self.pump()
        self.assertFalse(self.ws.ai_drafts)
        self.assertNotIn(key, self.app.status.get())
        self.assertNotIn(key, dumps(self.errors))

    def test_settings_status_button_only_uses_mock_runtime(self):
        self.app.ai_settings_button.invoke()
        win = self.app.ai_settings_win
        win.check_button.invoke()
        self.pump()
        self.assertEqual(self.app.ai_runtime.status_calls, 1)
        self.assertEqual(self.app.ai_runtime.setup_calls, 0)
        self.assertIn('"mock": true', win.runtime_status.get())
        self.assertFalse(self.model.called)


if __name__ == '__main__':
    unittest.main(verbosity=2)
