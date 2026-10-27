"""New synthetic integration checks, disjoint from actual-model release proofs."""
from pathlib import Path
import json
import tempfile
import unittest
from common import AuditError


class V25DemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_v25_'); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_user_inputs_do_not_create_human_records_and_old_manifest_still_loads(self):
        from v25_demo import create_demo, load_extension
        from demo_case import load_manifest, is_demo_workspace
        ws, manifest = create_demo(self.base/'user')
        self.assertTrue(is_demo_workspace(ws.root)); self.assertEqual(manifest['inputs'], load_manifest(ws.root)['inputs'])
        self.assertEqual(5, len(load_extension(ws.root)['steps']))
        self.assertFalse(ws.workflow_risks); self.assertFalse(ws.procedures); self.assertFalse(ws.ai_approvals)

    def test_supplementary_input_tamper_is_detected_without_changing_original_manifest(self):
        from v25_demo import create_demo, load_extension
        from demo_case import load_manifest
        ws, manifest = create_demo(self.base/'user'); extra = ws.root/manifest['v25']['inputs'][0]['path']
        extra.write_bytes(b'SYNTHETIC ONLY changed input')
        with self.assertRaises(AuditError): load_extension(ws.root)
        self.assertEqual(manifest['inputs'], load_manifest(ws.root)['inputs'])

    def test_complete_mock_integration_and_hidden_navigation_with_zero_model_calls(self):
        from v25_demo.verification import run_demo_verification
        result = run_demo_verification(self.base/'integration')
        self.assertTrue(result['ok']); self.assertFalse(result['actual_local_inference'])
        self.assertEqual(0, result['actual_model_calls']); self.assertEqual(0, result['actual_human_approvals'])
        self.assertEqual(1, result['synthetic_approval_events'])
        self.assertTrue(Path(result['flow']['export']).is_file()); self.assertEqual(3, len(result['flow']['stale_workspaces']))

    def test_existing_workspace_and_report_are_preserved(self):
        from v25_demo import create_demo
        from tools.verify_flow_v25 import self_test
        ws, _ = create_demo(self.base/'user'); head = ws.head
        with self.assertRaises(AuditError): create_demo(ws.root)
        self.assertEqual(head, ws.refresh().head)
        report = self.base/'old-report.json'; report.write_text('{"preserve":true}', encoding='utf-8')
        with self.assertRaises(ValueError): self_test(report)
        self.assertEqual({'preserve': True}, json.loads(report.read_text(encoding='utf-8')))


if __name__ == '__main__':
    unittest.main()
