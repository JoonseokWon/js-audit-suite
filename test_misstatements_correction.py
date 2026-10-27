"""Actual GL movement, company acceptance and stale proofs are different states."""
from common import AuditError
import misstatements as ms
from test_misstatements_support import Case, ACTOR, ledger


class CorrectionTests(Case):
    def test_acceptance_without_actual_gl_change_is_not_reflected(self):
        record=ms.save_record(self.ws,self.record_value(correction_state='수정',company_position='수용'),ACTOR)
        check=ms.verify_correction(self.ws,self.check_value(record),ACTOR)
        self.assertFalse(check['reflected'])
        self.assertEqual(ms.record_status(self.ws,record['id'])['verification_state'],'선택GL변동불일치·미반영')
        self.assertIn('실제 GL 수정 반영 대사',ms.record_status(self.ws,record['id'])['missing'])

    def test_approved_adjustment_overlay_is_not_actual_gl_posting(self):
        record=ms.save_record(self.ws,self.record_value(correction_state='수정',company_position='수용'),ACTOR)
        run=self.ws.execute('원장·리드',ledger(self.base/'조정표시만.xlsx',overlay=True))
        self.assertEqual(run['result']['tables']['리드스케줄'][0]['승인조정'],100)
        ms.reconfirm_record(self.ws,record['id'],ACTOR,'SYNTHETIC ONLY 수정 수용·원장 사본 확인')
        check=ms.verify_correction(self.ws,self.check_value(record),ACTOR)
        self.assertFalse(check['reflected']);self.assertEqual(check['after_rows'],[])

    def test_changed_ledger_needs_reconfirmation_then_actual_balanced_posting_matches(self):
        record=ms.save_record(self.ws,self.record_value(correction_state='수정',company_position='수용'),ACTOR)
        new=self.ws.execute('원장·리드',ledger(self.base/'실제수정전표.xlsx',corrected=True))
        self.assertEqual(new['result']['blocking'],0)
        head=self.ws.head
        with self.assertRaisesRegex(AuditError,'재확인'):ms.verify_correction(self.ws,self.check_value(record),ACTOR)
        self.assertEqual(head,self.ws.head)
        ms.reconfirm_record(self.ws,record['id'],ACTOR,'SYNTHETIC ONLY 변경 원장과 원기록 확인')
        check=ms.verify_correction(self.ws,self.check_value(record),ACTOR)
        self.assertTrue(check['reflected']);self.assertEqual([r['actual_movement'] for r in check['comparisons']],[100,-100])
        self.assertEqual(ms.record_status(self.ws,record['id'])['verification_state'],'선택GL변동일치')
        self.assertEqual(len(check['after_rows']),2)
        self.assertFalse(self.ws.ai_approvals)
        self.ws.execute('원장·리드',self.base/'실제수정전표.xlsx')
        self.assertEqual(ms.record_status(self.ws,record['id'])['verification_state'],'자료·기록변경·재확인필요')

    def test_record_edit_invalidates_prior_correction_even_if_amount_unchanged(self):
        record=ms.save_record(self.ws,self.record_value(correction_state='수정',company_position='수용'),ACTOR)
        self.ws.execute('원장·리드',ledger(self.base/'실제수정.xlsx',corrected=True))
        ms.reconfirm_record(self.ws,record['id'],ACTOR,'SYNTHETIC ONLY 재확인')
        ms.verify_correction(self.ws,self.check_value(record),ACTOR)
        ms.save_record(self.ws,{**self.record_value(correction_state='수정',company_position='수용'),'id':record['id']},ACTOR)
        self.assertEqual(ms.record_status(self.ws,record['id'])['verification_state'],'자료·기록변경·재확인필요')

    def test_unknown_account_or_unbalanced_expected_vector_never_passes(self):
        record=ms.save_record(self.ws,self.record_value(correction_state='수정',company_position='수용'),ACTOR)
        for checks in ([{'account_code':'1100','expected_movement':100}],
                       [{'account_code':'9999','expected_movement':100},{'account_code':'4000','expected_movement':-100}]):
            value={**self.check_value(record),'account_checks':checks};head=self.ws.head
            with self.assertRaises(AuditError):ms.verify_correction(self.ws,value,ACTOR)
            self.assertEqual(self.ws.head,head)

    def test_unmodified_sources_and_full_baseline_proof_are_required(self):
        record=ms.save_record(self.ws,self.record_value(correction_state='수정',company_position='수용'),ACTOR)
        self.ws.execute('원장·리드',ledger(self.base/'실제수정.xlsx',corrected=True))
        ms.reconfirm_record(self.ws,record['id'],ACTOR,'SYNTHETIC ONLY 재확인')
        value=self.check_value(record);value['evidence_ids']=[self.ws.latest()['원장·리드']['source_id']]
        with self.assertRaisesRegex(AuditError,'함께 연결'):ms.verify_correction(self.ws,value,ACTOR)
        original=self.ws.root/self.ws.sources[self.run['source_id']]['file'];original.write_bytes(b'changed')
        with self.assertRaisesRegex(AuditError,'변경/누락'):ms.verify_correction(self.ws,self.check_value(record),ACTOR)
