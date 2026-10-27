"""Cross-module IDs remain own-procedure, current and explicitly pending when incomplete."""
import unittest
import test_audit_links
import misstatements


class RiskMisstatementLinksTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_audit_links.AuditLinkTests(); self.fixture.setUp(); self.ws = self.fixture.ws
        self.fixture.prepare(); self.fixture.perform()

    def tearDown(self):
        self.fixture.doCleanups()

    def record(self, pids=None):
        return misstatements.save_record(self.ws, {'description': 'SYNTHETIC ONLY 미확정 검토사항',
            'evidence_ids': list(self.ws.sources), 'procedure_ids': pids or ['A04', 'F03']}, 'SYNTHETIC ONLY 기록자')

    def papers(self):
        self.fixture.paper('A04', review=True); self.fixture.paper('F03', review=True)

    def test_linked_pending_register_not_promoted_to_sufficient_or_confirmed_error(self):
        record = self.record(); self.papers()
        self.fixture.bind(f03_id='F03', misstatement_ids=[record['id']])
        self.assertIn('MISSTATEMENT_PENDING', self.fixture.codes())
        self.assertEqual('', misstatements.get_record(self.ws, record['id'])['assessment'])
        changed = {'id': record['id'], 'description': 'SYNTHETIC ONLY 사람이 기록한 설명 수정',
                   'evidence_ids': list(self.ws.sources), 'procedure_ids': ['A04', 'F03']}
        misstatements.save_record(self.ws, changed, 'SYNTHETIC ONLY 사람')
        self.assertIn('MISSTATEMENT_STALE', self.fixture.codes())

    def test_foreign_procedure_and_missing_f03_or_record_are_rejected(self):
        record = self.record(['A12', 'F03']); self.papers()
        self.fixture.blocked(lambda: self.fixture.bind(f03_id='F03', misstatement_ids=[record['id']]))
        record2 = self.record(); self.papers()
        self.fixture.blocked(lambda: self.fixture.bind(misstatement_ids=[record2['id']]))
        self.fixture.blocked(lambda: self.fixture.bind(f03_id='F03', misstatement_ids=['MS-FOREIGN']))


if __name__ == '__main__':
    unittest.main()
