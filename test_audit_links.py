"""Independent synthetic risk/response/performance/version counterexamples. No inference."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from common import AuditError, digest
from unittest.mock import patch
from workspace import Workspace
from test_audit_workflow import CONTEXT, profile
from verify import synthetic_procedure
import audit_links as links

ROOT = Path(__file__).resolve().parent


class AuditLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='SYNTHETIC-audit-links-'); self.addCleanup(self.temp.cleanup)
        self.ws = Workspace(Path(self.temp.name)/'SYNTHETIC_ONLY', create=CONTEXT)
        self.ws.execute('원장·리드', ROOT/'samples/통합/통합_01_원장정상.xlsx')
        self.ws.execute('매출', ROOT/'samples/통합/통합업무_매출정상.xlsx')
        self.ws.save_workflow_profile(profile(('A04', 'F03')), 'SYNTHETIC ONLY 계획자')
        self.risk = {'id': 'RISK-SALES', 'title': '합성 매출 누락 위험', 'accounts': ['매출'],
                     'assertions': ['발생사실', '완전성'], 'procedure_ids': ['A04'], 'basis': self.ws.data_basis(),
                     'evidence_ids': list(self.ws.sources), 'nature': '증빙 대사', 'timing': '기말', 'extent': '합성 2건', 'assessment': '사람 합성 식별'}
        self.ws.save_workflow_risk(self.risk, 'SYNTHETIC ONLY 평가자')
        self.old_link = {'procedure_id': 'A04', 'risk_ids': ['RISK-SALES'], 'evidence_ids': list(self.ws.sources),
                         'basis': self.ws.data_basis(), 'nature': '증빙 대사', 'timing': '기말', 'extent': '합성 2건', 'plan': '합성 사람 계획'}
        self.ws.save_workflow_procedure(self.old_link, 'SYNTHETIC ONLY 계획자')

    def assessment(self, **changes):
        return {'risk_id': 'RISK-SALES', 'assertions': [{'category': '거래', 'assertion': s} for s in ('발생사실', '완전성')],
                'inherent_rating': '높음', 'inherent_reason': 'SYNTHETIC ONLY 독립 원장 누락 위험',
                'control_rating': '보통', 'control_reason': 'SYNTHETIC ONLY 운영 증거는 사람 검토',
                'significant_risk': False, 'significant_reason': 'SYNTHETIC ONLY 가상 사람 판단', **changes}

    def response(self, **changes):
        selections = [{'source_id': sid, 'company_code': CONTEXT['회사코드'], 'start_date': CONTEXT['시작일'],
                       'end_date': CONTEXT['기준일'], 'locator': 'SYNTHETIC ONLY 시트 2~3행', 'relevance': '합성 원장·매출의 발생 및 완전성 대사'} for sid in self.ws.sources]
        return {'id': 'RESPONSE-1', 'risk_id': 'RISK-SALES', 'procedure_id': 'A04',
                'assertions': self.assessment()['assertions'], 'nature': '원본 증빙·독립 원장 대사', 'timing': '2026년 기말',
                'extent': 'SYNTHETIC ONLY 모집단 2건', 'sources': selections, 'run_ids': list(self.ws.runs), **changes}

    def prepare(self):
        links.save_assessment(self.ws, self.assessment(), 'SYNTHETIC ONLY 사람')
        return links.save_response(self.ws, self.response(), 'SYNTHETIC ONLY 사람')

    def perform(self, **changes):
        return links.save_performance(self.ws, {'response_id': 'RESPONSE-1', 'performed': 'SYNTHETIC ONLY 사람이 모의 증빙 대사',
                    'performed_date': '2026-12-31', 'performer': 'SYNTHETIC ONLY 수행자',
                    'sufficiency': '충분', 'sufficiency_reason': 'SYNTHETIC ONLY 독립 검산·원본 관련성 수동 확인', **changes}, 'SYNTHETIC ONLY 기록자')

    def paper(self, pid='A04', review=False):
        self.ws.save_procedure(synthetic_procedure(pid, list(self.ws.sources)))
        if review:
            self.ws.request_review(pid); self.ws.review(pid, 'SYNTHETIC ONLY 별도 검토자', '합성 별도 내용 검토')

    def bind(self, **changes):
        return links.bind_workpaper(self.ws, 'RESPONSE-1', {'workpaper_id': 'A04', 'note_ids': [], 'f03_id': '', 'misstatement_ids': [], **changes}, 'SYNTHETIC ONLY 연결자')

    def codes(self):
        return {r['code'] for r in links.status(self.ws)['blockers']}

    def blocked(self, fn):
        head = self.ws.head
        with self.assertRaises(AuditError): fn()
        self.ws.refresh(); self.assertEqual(head, self.ws.head)

    def test_legacy_workspace_and_candidate_reads_never_activate_or_write(self):
        head, basis = self.ws.head, self.ws.basis()
        self.assertIsNone(links.basis(self.ws)); self.assertFalse(links.status(self.ws)['active'])
        links.candidates(self.ws); links.packet(self.ws, 'A04'); links.snapshot(self.ws)
        self.assertEqual((head, basis), (self.ws.head, self.ws.basis()))

    def test_blank_human_assessments_stay_pending_without_procedures_or_approvals(self):
        record = links.save_assessment(self.ws, self.assessment(inherent_rating='', inherent_reason='', control_rating='', control_reason='', significant_risk=None, significant_reason=''), 'SYNTHETIC ONLY 기록자')
        self.assertIsNone(record['significant_risk']); self.assertFalse(self.ws.procedures); self.assertFalse(self.ws.ai_approvals)
        self.assertTrue({'INHERENT_UNASSESSED', 'CONTROL_UNASSESSED', 'SIGNIFICANT_UNASSESSED'} <= self.codes())

    def test_assessment_mapping_and_each_assertion_response_checked(self):
        links.save_assessment(self.ws, self.assessment(assertions=[{'category': '거래', 'assertion': '발생사실'}]), '합성')
        self.assertIn('ASSERTION_UNCLASSIFIED', self.codes())
        self.prepare(); links.save_response(self.ws, self.response(assertions=[{'category': '거래', 'assertion': '발생사실'}]), '합성')
        self.assertIn('ASSERTION_RESPONSE_MISSING', self.codes())

    def test_actual_run_and_hash_match_never_marks_human_performance(self):
        response = self.prepare(); self.assertTrue(response['runs'])
        self.assertIn('NOT_PERFORMED', self.codes()); self.assertFalse(self.ws.procedures)

    def test_partial_source_scope_is_visible_and_blocks_actual_performance(self):
        self.prepare(); response = self.response(); response['sources'][0]['company_code'] = ''
        links.save_response(self.ws, response, '합성')
        self.assertIn('SOURCE_SCOPE_UNCONFIRMED', self.codes()); self.blocked(self.perform)

    def test_foreign_company_period_or_procedure_and_old_run_are_rejected(self):
        self.prepare()
        for field, value in (('company_code', 'JSBIO'), ('start_date', '2025-01-01'), ('end_date', '2025-12-31')):
            data = self.response(); data['sources'][0][field] = value
            self.blocked(lambda data=data: links.save_response(self.ws, data, '합성'))
        self.blocked(lambda: links.save_response(self.ws, self.response(procedure_id='F03'), '합성'))
        self.blocked(lambda: links.save_response(self.ws, self.response(run_ids=['foreign-run']), '합성'))

    def test_relevant_module_run_required_even_when_ledger_selected(self):
        self.prepare(); ledger = self.ws.latest()['원장·리드']['id']
        links.save_response(self.ws, self.response(run_ids=[ledger]), '합성')
        self.assertIn('PROCEDURE_RUN_UNSELECTED', self.codes()); self.blocked(self.perform)

    def test_no_self_stale_and_performance_change_invalidates_earlier_paper(self):
        before = self.ws.basis(); response = self.prepare()
        self.assertNotEqual(before, self.ws.basis()); self.assertNotIn('RESPONSE_STALE', self.codes())
        self.paper(); before_paper = deepcopy(self.ws.procedures['A04']); self.perform()
        self.assertEqual('자료변경·재검토', self.ws.procedure_state(before_paper))
        self.assertNotIn('PERFORMANCE_STALE', self.codes()); self.assertEqual(response['revision'], links.refresh(self.ws)['responses']['RESPONSE-1']['revision'])

    def test_positive_current_performance_paper_binding_review_reopen_is_readonly(self):
        self.prepare(); self.perform(); self.paper(review=True)
        basis = self.ws.basis(); self.bind(); self.assertEqual(basis, self.ws.basis())
        self.assertFalse(links.status(self.ws)['blockers'])
        head = self.ws.head; reopened = Workspace(self.ws.root)
        self.assertFalse(links.status(reopened)['blockers']); self.assertEqual(head, reopened.head)
        self.assertTrue(any(r['code'] == 'LINK_RECORDS_CURRENT' for r in links.snapshot(reopened)['rows']))

    def test_other_procedure_or_stale_workpaper_cannot_be_bound(self):
        self.prepare(); self.perform(); self.paper()
        self.blocked(lambda: self.bind(workpaper_id='F03'))
        self.ws.add_source(ROOT/'samples/통합/통합업무_매출정상.xlsx', '추가 합성')
        self.blocked(self.bind); self.assertIn('RESPONSE_STALE', self.codes())

    def test_text_edit_rebinding_and_review_pending_preserve_original_events(self):
        self.prepare(); self.perform(); self.paper(review=True); self.bind()
        events = deepcopy(self.ws.events); paper = dict(self.ws.procedures['A04']); paper['conclusion'] = 'SYNTHETIC ONLY 수정 결론'
        self.ws.save_procedure(paper)
        self.assertIn('WORKPAPER_CHANGED', self.codes()); self.bind()
        self.assertIn('WORKPAPER_REVIEW_PENDING', self.codes()); self.assertEqual(events, self.ws.events[:len(events)])

    def test_data_or_workflow_changes_stale_assessment_response_performance(self):
        self.prepare(); self.perform(); self.paper(review=True); self.bind()
        self.ws.save_workflow_risk({**self.risk, 'assessment': 'SYNTHETIC ONLY 위험 재평가'}, '합성 사람')
        self.assertTrue({'ASSESSMENT_STALE', 'RESPONSE_STALE', 'PERFORMANCE_STALE', 'WORKPAPER_CHANGED'} <= self.codes())

    def test_orphan_risk_retire_is_explicit_and_does_not_revive_old_basis(self):
        self.prepare(); before = self.ws.basis()
        self.ws.retire_workflow_risk('RISK-SALES', '합성 사람', '합성 범위 변경')
        self.assertTrue({'RISK_ORPHAN', 'RESPONSE_ORPHAN'} <= self.codes())
        links.retire(self.ws, 'responses', 'RESPONSE-1', '합성 사람', '합성 범위 변경')
        self.assertNotEqual(before, self.ws.basis())

    def test_sufficiency_pending_unresolved_note_and_f03_version_linked(self):
        self.prepare(); self.perform(sufficiency='추가절차필요'); self.paper(review=True); self.paper('F03')
        note = self.ws.add_note('SYNTHETIC ONLY 미해결', '추가 증빙 요청', '합성 사람')
        self.bind(note_ids=[note], f03_id='F03')
        self.assertTrue({'SUFFICIENCY_PENDING', 'NOTE_UNRESOLVED'} <= self.codes())
        p = dict(self.ws.procedures['F03']); p['conclusion'] = 'SYNTHETIC ONLY F03 수정'; self.ws.save_procedure(p)
        self.assertIn('F03_STALE', self.codes())

    def test_forged_assertion_unassessed_choices_xml_and_stale_head_rejected(self):
        for changes in ({'assertions': [{'category': '잔액', 'assertion': '발생사실'}]}, {'significant_risk': '예'}, {'inherent_reason': '\x0b'}, {'risk_id': 'FOREIGN'}):
            self.blocked(lambda changes=changes: links.save_assessment(self.ws, self.assessment(**changes), '합성'))
        head = self.ws.head; self.ws.add_note('합성 추가', '다른 창 입력', '합성')
        self.blocked(lambda: links.save_assessment(self.ws, self.assessment(), '합성', expected_head=head))

    def test_packet_contains_only_own_procedure_and_no_synthetic_approval(self):
        self.prepare(); self.perform(); self.paper(); self.bind()
        packet = links.packet(self.ws, 'A04'); before = self.ws.head
        self.assertEqual(4, len(packet['references'])); self.assertTrue(all(r['human_record_only'] for r in packet['references']))
        self.assertFalse(links.packet(self.ws, 'A12')['references']); self.assertEqual(before, self.ws.head)
        self.assertFalse(self.ws.ai_approvals); self.assertFalse(self.ws.workflow_locked)

    def test_source_bytes_change_blocks_reads_as_confirmed_and_all_new_saves(self):
        self.prepare(); source = next(iter(self.ws.sources.values()))
        (self.ws.root/source['file']).write_bytes(b'SYNTHETIC ONLY altered source')
        self.assertIn('SOURCE_INTEGRITY', self.codes())
        self.blocked(lambda: links.save_assessment(self.ws, self.assessment(), '합성 사람'))
        self.blocked(self.perform)

    def test_unrelated_module_run_and_stale_run_rejected(self):
        self.prepare(); self.ws.execute('금융상품', ROOT/'samples/통합/통합업무_금융정상.xlsx')
        self.risk['basis'] = self.ws.data_basis(); self.old_link['basis'] = self.ws.data_basis()
        self.ws.save_workflow_risk(self.risk, '합성'); self.ws.save_workflow_procedure(self.old_link, '합성')
        links.save_assessment(self.ws, self.assessment(), '합성')
        self.blocked(lambda: links.save_response(self.ws, self.response(), '합성'))
        old_run = self.ws.latest()['매출']['id']
        self.ws.execute('매출', ROOT/'samples/통합/통합업무_매출정상.xlsx')
        self.risk['basis'] = self.ws.data_basis(); self.old_link['basis'] = self.ws.data_basis()
        self.ws.save_workflow_risk(self.risk, '합성'); self.ws.save_workflow_procedure(self.old_link, '합성')
        links.save_assessment(self.ws, self.assessment(), '합성')
        self.blocked(lambda: links.save_response(self.ws, self.response(run_ids=[old_run]), '합성'))

    def test_compare_and_swap_race_does_not_overwrite_other_window(self):
        original = self.ws._append
        def racing(kind, data, expected_head=None):
            if kind == 'audit_link_assessment':
                Workspace(self.ws.root).add_note('SYNTHETIC ONLY 동시 입력', '다른 창 자료', '합성')
            return original(kind, data, expected_head=expected_head)
        with patch.object(self.ws, '_append', side_effect=racing):
            with self.assertRaises(AuditError):
                links.save_assessment(self.ws, self.assessment(), '합성')
        self.ws.refresh(); self.assertFalse(links.refresh(self.ws)['assessments'])
        self.assertEqual('SYNTHETIC ONLY 동시 입력', list(self.ws.notes.values())[-1]['title'])

    def test_lock_guard_blocks_new_api_events(self):
        self.prepare(); self.perform(); self.paper(); self.bind()
        # Explicit synthetic low-level fixture tests only the immutable lock guard;
        # it is not evidence of successful finalization or actual human approval.
        self.ws._append('workflow_finalize', {'id': 'SYNTHETIC ONLY LOCK GUARD FIXTURE'})
        self.ws.refresh(); self.assertTrue(self.ws.workflow_locked)
        for action in (lambda: links.save_assessment(self.ws, self.assessment(), '합성'),
                       lambda: links.save_response(self.ws, self.response(), '합성'), self.perform, self.bind,
                       lambda: links.retire(self.ws, 'responses', 'RESPONSE-1', '합성', '합성 사유')):
            self.blocked(action)

    def test_ai_approval_invalidates_on_new_assessment_but_binding_alone_does_not(self):
        from test_ai_workpapers import mock_response
        self.prepare(); self.perform()
        packet = self.ws.ai_packet('A04'); draft = self.ws.record_ai_draft(packet, mock_response(packet), 'SYNTHETIC ONLY 요청자')
        self.ws.apply_ai_draft(draft, 'SYNTHETIC ONLY 작성자')
        self.ws.approve_ai_content('A04', 'SYNTHETIC ONLY 내용 승인자', 'SYNTHETIC ONLY 실제 사람 승인 아님')
        self.assertTrue(self.ws.ai_status('A04')['approved']); self.bind()
        self.assertTrue(self.ws.ai_status('A04')['approved'])
        old_approval = deepcopy(self.ws.ai_approvals['A04'])
        links.save_assessment(self.ws, self.assessment(control_reason='SYNTHETIC ONLY 통제 재평가'), '합성')
        self.assertFalse(self.ws.ai_status('A04')['approved']); self.assertEqual(old_approval, self.ws.ai_approvals['A04'])


if __name__ == '__main__':
    unittest.main()
