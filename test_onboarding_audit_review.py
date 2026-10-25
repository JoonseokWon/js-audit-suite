"""Independent adversarial review: reconfirmation must not hide omitted amounts.

All records and confirmations here are SYNTHETIC ONLY. No user workspace,
external request, inference provider, UI operation or actual approval is used.
"""
from copy import deepcopy
import unittest
from onboarding import substantive, erp
from onboarding.confirmation import confirm_input
from onboarding.demo import CONTEXT, ledger_result


def confirmed(module,payload):
    return confirm_input(module,payload,'SYNTHETIC ONLY 독립검사자',
        'SYNTHETIC ONLY 재확인 뒤에도 원장 차이·누락을 차단하는 회귀검사')


def sub(module,payload):
    return substantive.analyze(module,confirmed(module,payload),CONTEXT,ledger_result(CONTEXT))


def raw(payload):
    return erp.analyze(confirmed('실무자료·원장',payload),CONTEXT,ledger_result(CONTEXT))


class IndependentOnboardingAuditReview(unittest.TestCase):
    def test_mixed_sign_net_population_cannot_remove_high_and_negative_strata(self):
        p=substantive.sample('감사표본선정',CONTEXT)
        receipt=next(r for r in p['population'] if r['gl_refs']==['J01/L1'])
        payment=next(r for r in p['population'] if r['gl_refs']==['J04/L2'])
        receipt['gl_refs']+=payment['gl_refs'];receipt['amount']+=payment['amount']
        p['population'].remove(payment)
        r=sub('감사표본선정',p)
        self.assertGreater(r['blocking'],0,
            '100,000 고액행과 -80,000 음수행을 20,000 순액으로 묶어 전수검사층에서 지울 수 없어야 합니다.')
        self.assertFalse(r['detail']['현재원장연결'])

    def test_whole_cip_account_cannot_disappear_when_transfer_renamed_acquisition(self):
        p=substantive.sample('유형자산증감',CONTEXT)
        p['assets']=[r for r in p['assets'] if r['asset_type']=='PPE']
        p['asset_movements']=[r for r in p['asset_movements'] if r['asset_id']=='PPE1']
        next(r for r in p['asset_movements'] if r['kind']=='transfer_in').update(kind='acquisition',pair_id='')
        r=sub('유형자산증감',p)
        self.assertGreater(r['blocking'],0,
            '원장1600 기말20,000과 취득·대체·취소를 입력에서 통째로 지운 범위축소는 차단해야 합니다.')

    def test_gl_line_amount_changed_then_reconfirmed_still_fails(self):
        p=erp.sample(CONTEXT);p['source_rows'][0]['차변금액']+=1
        r=raw(p)
        self.assertGreater(r['blocking'],0)
        self.assertFalse(r['detail']['현재원장연결'])

    def test_balanced_gl_journal_omission_does_not_pass_on_debit_credit_balance(self):
        p=erp.sample(CONTEXT)
        p['source_rows']=[r for r in p['source_rows'] if r['전표번호']!='J01']
        r=raw(p)
        self.assertGreater(r['blocking'],0)
        self.assertFalse(r['detail']['현재원장연결'])

    def test_reported_amount_changed_and_reconfirmed_still_fails(self):
        p=erp.sample(CONTEXT);p['presentation_values'][0]['amount']+=1
        self.assertGreater(raw(p)['blocking'],0)

    def test_opposite_differences_in_different_groups_remain_errors(self):
        p=erp.sample(CONTEXT)
        for code,delta in (('1500',1000),('1600',-1000)):
            next(r for r in p['presentation_mapping'] if r['statement']=='BS' and r['account_code']==code).update(
                validation_group='separate-'+code,group_policy='net',group_basis='SYNTHETIC ONLY 개별 그룹')
            next(r for r in p['presentation_values'] if r['statement']=='BS' and r['line_id']==code)['amount']+=delta
        self.assertGreater(raw(p)['blocking'],0)

    def test_current_ledger_recomputed_not_trusted_from_cached_pass_flag(self):
        p=erp.sample(CONTEXT);l=ledger_result(CONTEXT)
        l['tables']['리드스케줄'][0]['조정후']+=1
        r=erp.analyze(confirmed('실무자료·원장',p),CONTEXT,l)
        self.assertGreater(r['blocking'],0)

    def test_joint_map_and_value_edit_cannot_mix_pre_post_adjustment_body(self):
        import ledger
        p=erp.sample(CONTEXT)
        p['adjustments']=[{'adjustment_id':'SYNTH','line_id':'L'+str(i),'account_code':code,
            'debit':debit,'credit':credit,'evidence':'SYNTHETIC ONLY 이자 발생','status':'승인'}
            for i,(code,debit,credit) in enumerate((('5200',100,0),('2300',0,100)),1)]
        p=confirm_input('실무자료·원장',p,'SYNTHETIC ONLY','SYNTHETIC ONLY 조정 회귀',confirm_adjustments=True)
        current=ledger.analyze(erp.prepare_ledger(p,CONTEXT))
        next(r for r in p['presentation_mapping'] if r['statement']=='PL' and r['account_code']=='5200')['basis']='post_adjustment'
        value=next(r for r in p['presentation_values'] if r['statement']=='PL' and r['line_id']=='5200')
        value['basis']='post_adjustment';value['amount']+=100
        r=erp.analyze(confirmed('실무자료·원장',p),CONTEXT,current)
        self.assertGreater(r['blocking'],0,
            '이자비용4,100은 조정후이고 미지급이자1,000은 조정전인 혼재 본문을 통과시키면 안 됩니다.')

    def test_nonexistent_financial_account_scope_cannot_make_gl_connection_vacuous(self):
        p=substantive.sample('금융기관조회',CONTEXT)
        p['institution_sources']=[r for r in p['institution_sources'] if r['source_type']!='current']
        targets={r['institution_id'] for r in p['institution_sources']}
        p['requests']=[r for r in p['requests'] if r['institution_id'] in targets]
        p['policy']['financial_account_codes']='NONEXISTENT'
        r=sub('금융기관조회',p)
        self.assertGreater(r['blocking'],0,
            '없는 정책계정 때문에 원장대사0행이 되어도 현재원장연결=True를 표시하면 안 됩니다.')
        self.assertFalse(r['detail']['현재원장연결'])

    def test_note_movement_omission_is_not_silently_net_zero(self):
        p=substantive.sample('주석구성대사',CONTEXT)
        p['note_movements']=[r for r in p['note_movements'] if 'J20' not in r['record_id']]
        self.assertGreater(sub('주석구성대사',p)['blocking'],0)

    def test_unknown_classification_evidence_stays_unknown_without_automatic_judgment(self):
        p=substantive.sample('분류검토',CONTEXT)
        p['classification_evidence'][0]['status']='unknown'
        r=sub('분류검토',p);row=r['tables']['분류AsIsToBe검토'][0]
        self.assertEqual(row['검토상태'],'미확인')
        self.assertTrue(row['미확인항목'])
        self.assertFalse(row['프로그램적정판정'])
        self.assertFalse(r['detail']['분류자동확정'])
        self.assertFalse(r['detail']['실제감사수행완료'])

    def test_confirmation_unverified_reply_remains_followup_and_never_sent(self):
        p=substantive.sample('금융기관조회',CONTEXT)
        request=p['requests'][0]
        p['responses']=[{'record_id':'RESP','source_ref':'SYNTHETIC ONLY/response',
            'gl_refs':[],'institution_id':request['institution_id'],'request_id':request['request_id'],
            'field':'deposits','amount':1068000,'as_of':CONTEXT['기준일'],
            'details':'SYNTHETIC ONLY 미검증 회신','authenticity':'unverified','reviewer':'','reason':''}]
        r=sub('금융기관조회',p)
        self.assertTrue(any('진위 미확인' in row['후속요청사유'] for row in r['tables']['후속요청초안']))
        self.assertFalse(r['detail']['실제발송'])
        self.assertFalse(r['detail']['회신진위자동확인'])

    def test_reconfirmed_sampling_wrong_amount_keeps_difference(self):
        p=substantive.sample('감사표본선정',CONTEXT);p['population'][0]['amount']+=1
        self.assertGreater(sub('감사표본선정',p)['blocking'],0)

    def test_qualitative_conflict_not_cleared_by_input_confirmation(self):
        p=substantive.sample('분류검토',CONTEXT);p['classification_evidence'][3]['status']='contradicted'
        r=sub('분류검토',p);row=r['tables']['분류AsIsToBe검토'][0]
        self.assertEqual(row['검토상태'],'상충')
        self.assertFalse(row['프로그램적정판정'])
        self.assertGreater(r['review'],0)


if __name__=='__main__':unittest.main()
