"""Shared GUI/actual packet policy. Hidden controls, fake adapter, zero model/network calls."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from common import AuditError, digest
from ai_provider import DEFAULT_MODEL
from desktop.ai.request_policy import (POLICY_VERSION, packet_options, build_packet,
                                       default_config, configuration_summary)


class RequestPolicyTests(unittest.TestCase):
    def test_defaults_match_real_integrated_validation_without_forcing_CPU(self):
        endpoint = 'http://127.0.0.1:11434'
        config = default_config(endpoint)
        self.assertEqual({'provider': 'ollama', 'model': DEFAULT_MODEL, 'endpoint': endpoint,
                          'num_ctx': 32768, 'timeout_seconds': 300}, config)
        self.assertNotIn('num_gpu', config); self.assertEqual('ai-request-policy-1', POLICY_VERSION)
        self.assertEqual({'max_chars': 24000, 'max_references': 70, 'rows_per_table': 3,
                          'max_tables': 8, 'cell_chars': 300}, packet_options())

    def test_explicit_local_and_OpenAI_choices_are_preserved_without_mutation(self):
        for chosen in ({'num_gpu': 0, 'num_ctx': 16384, 'timeout_seconds': 180},
                       {'provider': 'openai', 'model': 'SYNTHETIC_ONLY_CHOSEN_MODEL', 'num_ctx': 16384}):
            original = deepcopy(chosen); config = default_config('http://127.0.0.1:11434', chosen)
            self.assertTrue(all(config[key] == value for key, value in chosen.items()))
            config['timeout_seconds'] = 1; self.assertEqual(original, chosen)
        first = packet_options(); first['max_chars'] = 1
        self.assertEqual(24000, packet_options()['max_chars'])

    def test_settings_summary_explains_current_hardware_and_context(self):
        self.assertIn('하드웨어 자동 선택', configuration_summary(default_config('http://127.0.0.1:11434')))
        custom = default_config('http://127.0.0.1:11434', {'num_gpu': 0, 'num_ctx': 16384})
        text = configuration_summary(custom)
        self.assertIn('명시적 CPU 진단', text); self.assertIn('16,384', text)
        self.assertIn('명시한 사용자 설정은 유지', text)


@unittest.skipUnless(sys.platform == 'win32', 'Hidden native Windows UI')
class GUIRequestPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import runtime
        runtime.configure(); runtime.configure_tk_libraries()
        import tkinter as tk
        cls.tk = tk; cls.root = tk.Tk(); cls.root.withdraw()
        cls.temp = tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_GUI_POLICY_')
        from v25_demo import actual_case
        def check(ok, name):
            if not ok: raise AssertionError(name)
        cls.ws, _ = actual_case(Path(cls.temp.name)/'linked-case', check)
        cls.catalog = json.loads((runtime.configure()/'procedure_catalog.json').read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls):
        from window_capture import destroy_test_window
        destroy_test_window(cls.root); cls.temp.cleanup()

    def setUp(self):
        self.before = self.ws.head; self.sent = []; self.windows = []
        self.host = SimpleNamespace(ws=self.ws, current_pid='A04', ai_catalog=self.catalog,
            ai_runtime=SimpleNamespace(base_url='http://127.0.0.1:11434'),
            ai_config=default_config('http://127.0.0.1:11434'),
            ai_actor=lambda: 'SYNTHETIC ONLY GUI adapter requester', ai_clean_form=lambda: True,
            ai_api_key='', ai_openai_model='', guard=lambda: None, dirty=lambda: False)
        self.host.run_ai_generation = lambda ws, packet, actor, config: self.sent.append(
            {'ws': ws, 'packet': deepcopy(packet), 'actor': actor, 'config': deepcopy(config)})
        def window(_title):
            win = self.tk.Toplevel(self.root); win.withdraw(); self.windows.append(win); return win
        self.host.ai_window = window

    def tearDown(self):
        for win in reversed(self.windows):
            if win.winfo_exists(): win.destroy()
        self.ws.refresh(); self.assertEqual(self.before, self.ws.head)
        self.assertFalse(self.ws.ai_drafts); self.assertFalse(self.ws.ai_approvals)

    def test_preview_generation_and_actual_adapter_use_exact_same_linked_packet(self):
        from desktop.ai.evidence import open_current_evidence
        from desktop.ai.jobs import AIJobs
        with patch('ai_provider.generate_draft', side_effect=AssertionError('model invocation forbidden')) as provider:
            win = open_current_evidence(self.host)
            AIJobs.start_ai_generation(self.host)
            actual_adapter_packet = build_packet(self.ws, 'A04')
        self.assertEqual(0, provider.call_count); self.assertEqual(1, len(self.sent))
        generated = self.sent[0]['packet']
        self.assertEqual(packet_options(), generated['limits'])
        self.assertEqual(digest(win.packet), digest(generated))
        self.assertEqual(digest(actual_adapter_packet), digest(generated))
        self.assertEqual('withdrawn', win.state())
        self.assertEqual(32768, self.sent[0]['config']['num_ctx']); self.assertNotIn('num_gpu', self.sent[0]['config'])
        kinds = {ref['kind'] for ref in generated['references']}
        self.assertTrue({'misstatement_record', 'human_assertion_risk_assessment', 'human_risk_response',
                         'human_actual_performance', 'raw_xlsx_row', 'calculation_row'} <= kinds)
        self.assertEqual('user_recorded_unverified', generated['contract']['human_performance']['state'])

    def test_GUI_preserves_explicit_CPU_context_and_OpenAI_consent_path(self):
        from desktop.ai.jobs import AIJobs
        self.host.ai_config.update(num_gpu=0, num_ctx=16384, timeout_seconds=180)
        before = deepcopy(self.host.ai_config); AIJobs.start_ai_generation(self.host)
        self.assertEqual(before, self.host.ai_config)
        self.assertEqual(0, self.sent[-1]['config']['num_gpu']); self.assertEqual(16384, self.sent[-1]['config']['num_ctx'])
        self.host.ai_config['provider'] = 'openai'
        self.host.ai_api_key = 'SYNTHETIC_ONLY_FAKE_API_KEY'; self.host.ai_openai_model = 'SYNTHETIC_ONLY_CHOSEN_MODEL'
        consent = []
        self.host.open_external_consent = lambda packet, send: consent.append((packet, send))
        AIJobs.start_ai_generation(self.host)
        self.assertEqual(1, len(self.sent)); self.assertEqual(1, len(consent))
        consent[0][1]()
        self.assertEqual(2, len(self.sent)); config = self.sent[-1]['config']
        self.assertEqual('openai', config['provider']); self.assertTrue(config['external_consent'])
        self.assertNotIn('endpoint', config); self.assertIn('endpoint', self.host.ai_config)
        self.assertEqual('SYNTHETIC_ONLY_CHOSEN_MODEL', config['model'])

    def test_initialization_uses_new_defaults_and_does_not_overwrite_explicit_config(self):
        from desktop.ai.state import AIState
        runtime = SimpleNamespace(base_url='http://127.0.0.1:11434')
        with patch('desktop.ai.state.LocalAIRuntime', return_value=runtime):
            fresh = SimpleNamespace(); AIState.init_ai(fresh, self.catalog)
            self.assertEqual(default_config(runtime.base_url), fresh.ai_config)
            chosen = {'provider': 'ollama', 'model': DEFAULT_MODEL, 'num_gpu': 0, 'num_ctx': 16384, 'timeout_seconds': 180}
            previous = deepcopy(chosen); host = SimpleNamespace(ai_config=chosen); AIState.init_ai(host, self.catalog)
        self.assertTrue(all(host.ai_config[key] == value for key, value in chosen.items()))
        self.assertEqual(previous, chosen); self.assertIsNot(host.ai_config, chosen)


if __name__ == '__main__':
    unittest.main()
