"""Prevent the three original calculations bypassing workpaper evidence checks."""
import runtime
ROOT = runtime.configure()
import json
import tempfile
import unittest
from pathlib import Path
from common import AuditError
from procedures import task_definitions
from workspace import Workspace
from verify import synthetic_procedure

PAIRS = [('A02', '금융상품', '통합업무_금융정상.xlsx'),
         ('A04', '매출', '통합업무_매출정상.xlsx'),
         ('A12', '감가상각', '통합업무_감가상각정상.xlsx')]


class OriginalCalculationLinks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Workspace(Path(self.tmp.name)/'업무', create={
            '회사명': 'SYNTHETIC ONLY', '회사코드': 'SYNTH01',
            '시작일': '2026-01-01', '기준일': '2026-12-31',
            '작성자': '합성작성자', '회계체계': 'K-IFRS', '감사기준': '합성 검증', '더미업무': True})
        self.ws.execute('원장·리드', ROOT/'samples/통합/통합_01_원장정상.xlsx')
        for _, module, filename in PAIRS:
            self.ws.execute(module, ROOT/'samples/통합'/filename)

    def test_drafts_include_actual_calculation_and_ledger_evidence(self):
        tasks = {p['id']: p for p in task_definitions(self.ws, json.loads((ROOT/'procedure_catalog.json').read_text(encoding='utf-8')))}
        for pid, module, _ in PAIRS:
            with self.subTest(module=module):
                refs = self.ws.calculation_refs(pid)
                self.assertEqual(refs['모듈'], module)
                self.assertTrue(refs['계산표'])
                self.assertTrue(refs['원장대사'])
                self.assertIn('자동계산 연결: '+module, tasks[pid]['scope'])
                self.assertEqual(set(tasks[pid]['evidence_ids']), {
                    self.ws.latest()[module]['source_id'], self.ws.latest()['원장·리드']['source_id']})

    def test_one_side_evidence_cannot_pass_review_request(self):
        for pid, module, _ in PAIRS:
            for only in (module, '원장·리드'):
                with self.subTest(module=module, only=only):
                    self.ws.save_procedure(synthetic_procedure(pid, [self.ws.latest()[only]['source_id']]))
                    head = self.ws.head
                    with self.assertRaisesRegex(AuditError, '모두 연결'):
                        self.ws.request_review(pid)
                    self.assertEqual(self.ws.head, head)

    def test_current_evidence_pair_can_be_reviewed_and_new_run_reopens(self):
        for pid, module, _ in PAIRS:
            with self.subTest(module=module):
                evidence = [self.ws.latest()[module]['source_id'], self.ws.latest()['원장·리드']['source_id']]
                self.ws.save_procedure(synthetic_procedure(pid, evidence))
                self.ws.request_review(pid)
                self.ws.review(pid, '다른합성검토자', '합성자료 근거 연결 상태 시험')
                self.assertEqual(self.ws.procedure_state(self.ws.procedures[pid]), '검토기록완료')
        self.ws.execute('매출', ROOT/'samples/통합/통합업무_매출정상.xlsx')
        for pid, _, _ in PAIRS:
            self.assertEqual(self.ws.procedure_state(self.ws.procedures[pid]), '자료변경·재검토')


if __name__ == '__main__':
    unittest.main()
