"""Evidence follow-up and proposed disclosures remain separate from judgment."""
from copy import deepcopy
import unittest
from onboarding.substantive import sample, negative_cases
from onboarding.substantive.samples import row
from test_onboarding_substantive import Fixture


class ConfirmationTests(Fixture):
    AREA = '금융기관조회'
    def test_union_includes_prior_closed_zero_guarantee_and_collateral_sources(self):
        result=self.run_case(self.AREA)
        targets={r['기관ID']:r for r in result['tables']['조회대상합집합']}
        self.assertEqual(set(targets), {'BANK-A','BANK-B','BANK-CLOSED','BANK-ZERO','BANK-GUARANTEE'})
        self.assertTrue({'prior','closed'} <= set(targets['BANK-CLOSED']['근거유형']))
        self.assertEqual(result['metrics']['후속요청항목'],25)
        self.assertFalse(result['detail']['실제발송'])
        self.assertFalse(result['detail']['회신진위자동확인'])

    def test_missing_zero_bank_request_is_blocked(self):
        payload=negative_cases(self.AREA,self.context)['0잔액기관누락']
        self.assertIn('CONFIRM_TARGET_UNION',self.codes(self.run_case(self.AREA,payload)))

    def test_prior_year_balance_is_scope_evidence_not_current_balance(self):
        payload=sample(self.AREA,self.context)
        next(r for r in payload['institution_sources'] if r['record_id']=='PRIOR')['book_amount']=500000
        result=self.run_case(self.AREA,payload)
        row=next(r for r in result['tables']['회신항목대사']
                 if r['기관ID']=='BANK-CLOSED' and r['항목']=='deposits')
        self.assertEqual(row['장부근거금액'],0)

    def test_partial_other_date_and_unverified_response_create_followup(self):
        cases=negative_cases(self.AREA,self.context)
        partial=self.run_case(self.AREA,cases['부분회신'])
        self.assertGreater(partial['review'],0)
        rows=partial['tables']['후속요청초안']
        self.assertTrue(any('미회신/부분회신' in r['후속요청사유'] for r in rows))
        self.assertTrue(any('진위 미확인' in r['후속요청사유'] for r in rows))
        other=self.run_case(self.AREA,cases['다른기준일'])
        self.assertTrue(any('다른 기준일' in r['후속요청사유'] for r in other['tables']['후속요청초안']))

    def test_complete_entered_responses_still_do_not_verify_authenticity_or_finish_audit(self):
        payload=sample(self.AREA,self.context); balances={}
        for source in payload['institution_sources']:
            key=(source['institution_id'],source['field'])
            balances[key]=balances.get(key,0)+source['book_amount']
        for request in payload['requests']:
            for field in request['requested_fields']:
                payload['responses'].append(row(request['record_id']+'-'+field,(),
                    institution_id=request['institution_id'],request_id=request['request_id'],field=field,
                    amount=balances[request['institution_id'],field],as_of=self.context['기준일'],
                    details='SYNTHETIC ONLY 입력 예시',authenticity='person_claimed',
                    reviewer='SYNTHETIC ONLY',reason='가상 진위확인 입력·실제 감사 아님'))
        result=self.run_case(self.AREA,payload)
        self.assertEqual(result['metrics']['후속요청항목'],0)
        self.assertFalse(result['detail']['회신진위자동확인'])
        self.assertFalse(result['detail']['실제감사수행완료'])

    def test_duplicate_current_account_or_missing_collateral_request_field(self):
        payload=sample(self.AREA,self.context)
        payload['institution_sources'].append(dict(payload['institution_sources'][0],record_id='DUP'))
        self.assertIn('CONFIRM_CURRENT_DUP',self.codes(self.run_case(self.AREA,payload)))
        payload=sample(self.AREA,self.context);payload['requests'][0]['requested_fields'].remove('collateral')
        self.assertIn('CONFIRM_REQUEST_FIELDS',self.codes(self.run_case(self.AREA,payload)))

    def test_deleted_current_sources_or_nonexistent_declared_accounts_cannot_vacuously_pass(self):
        for fake_scope in (False,True):
            payload=sample(self.AREA,self.context)
            payload['institution_sources']=[r for r in payload['institution_sources'] if r['source_type']!='current']
            if fake_scope:payload['policy']['financial_account_codes']='NONEXISTENT'
            result=self.run_case(self.AREA,payload)
            self.assertGreater(result['blocking'],0)
            self.assertIn('CONFIRM_DECLARED_SCOPE',self.codes(result))
            if fake_scope:self.assertIn('CONFIRM_SCOPE_TB',self.codes(result))
            self.assertFalse(result['detail']['현재원장연결'])

    def test_inactive_current_account_links_to_unchanged_tb_without_inventing_gl_rows(self):
        from collections import defaultdict
        from onboarding.demo import ledger_tables
        from onboarding.contracts import ledger_basis
        import ledger
        tables=ledger_tables(self.context)
        tables['총계정원장']=[r for r in tables['총계정원장'] if r['전표ID']!='J17']
        totals=defaultdict(lambda:[0,0,0])
        for r in tables['총계정원장']:
            item=totals[r['계정코드']];item[0]+=1;item[1]+=r['차변'];item[2]+=r['대변']
        for r in tables['시산표']:
            count,debit,credit=totals[r['계정코드']]
            r.update(당기차변=debit,당기대변=credit,기말잔액=r['기초잔액']+debit-credit)
        tb={r['계정코드']:r for r in tables['시산표']}
        for r in tables['독립통제']:
            count,debit,credit=totals[r['계정코드']]
            r.update(원장행수=count,차변합계=debit,대변합계=credit,기말잔액=tb[r['계정코드']]['기말잔액'])
        self.ledger=ledger.analyze(tables);self.ledger['context']=dict(self.context)
        self.assertEqual(self.ledger['blocking'],0)
        payload=sample(self.AREA,self.context)
        payload['policy']['ledger_basis_hash']=ledger_basis(self.ledger)
        for r in payload['institution_sources']:
            if r['source_type']=='current':
                r['book_amount']=tb[r['account_code']]['기말잔액']*r['factor']
                r['gl_refs']=[g['전표ID']+'/'+g['행ID'] for g in tables['총계정원장'] if g['계정코드']==r['account_code']]
        inactive=next(r for r in payload['institution_sources'] if r['account_code']=='1010')
        self.assertEqual(inactive['gl_refs'],[])
        self.assertEqual(inactive['book_amount'],0)
        result=self.run_case(self.AREA,payload)
        self.assertEqual(result['blocking'],0,result['issues'])
        self.assertTrue(result['detail']['현재원장연결'])
        self.assertEqual(len(result['tables']['조회장부잔액대사']),4)


class NoteTests(Fixture):
    AREA = '주석구성대사'
    def test_loan_and_collateral_amounts_have_separate_meanings(self):
        result=self.run_case(self.AREA)
        self.assertEqual(result['metrics']['차입구성합계'],350000)
        self.assertEqual(result['metrics']['담보근거금액'],60000)
        self.assertEqual(result['blocking'],0)
        self.assertFalse(result['detail']['원본주석수정'])

    def test_original_note_is_preserved_and_tobe_comes_from_controlled_bridge(self):
        payload=negative_cases(self.AREA,self.context)['주석현재잔액차이']; before=deepcopy(payload)
        result=self.run_case(self.AREA,payload)
        target=next(r for r in result['tables']['주석AsIsToBe'] if r['계정코드']=='1500')
        self.assertEqual((target['현재기말AsIs'],target['근거기말ToBe'],target['수정제안차이']), (89999,90000,1))
        self.assertEqual(payload['note_balances'],before['note_balances'])
        self.assertGreater(result['blocking'],0)

    def test_missing_noncash_reclassification_and_collateral_link_are_detected(self):
        for name,payload in negative_cases(self.AREA,self.context).items():
            with self.subTest(name=name):self.assertGreater(self.run_case(self.AREA,payload)['blocking'],0)

    def test_cash_borrowing_cannot_be_called_noncash_by_omitting_cash_reference(self):
        payload=sample(self.AREA,self.context)
        movement=next(r for r in payload['note_movements'] if r['record_id']=='NM-2100-J09-L2')
        movement['kind']='noncash';movement['gl_refs']=['J09/L2']
        self.assertIn('NOTE_NONCASH_CLASS',self.codes(self.run_case(self.AREA,payload)))

    def test_loan_component_cannot_refer_only_to_an_unrelated_account(self):
        payload=sample(self.AREA,self.context);payload['note_components'][0]['gl_refs']=['J17/L1']
        self.assertIn('NOTE_COMPONENT_ACCOUNT',self.codes(self.run_case(self.AREA,payload)))


class ClassificationTests(Fixture):
    AREA = '분류검토'
    def test_short_maturity_and_all_supported_inputs_never_approve_classification(self):
        result=self.run_case(self.AREA)
        item=result['tables']['분류AsIsToBe검토'][0]
        self.assertTrue(item['원래만기3개월이내참고'])
        self.assertEqual(item['검토상태'],'근거입력완비·사람판단필요')
        self.assertFalse(item['프로그램적정판정'])
        self.assertFalse(result['detail']['분류자동확정'])

    def test_missing_qualitative_evidence_is_unresolved_even_with_short_dates(self):
        payload=negative_cases(self.AREA,self.context)['정성근거누락']
        result=self.run_case(self.AREA,payload)
        self.assertEqual(result['metrics']['미확인대상'],1)
        self.assertEqual(result['tables']['분류AsIsToBe검토'][0]['누락항목'],['contract_terms'])

    def test_restrictions_or_long_original_maturity_create_conflict(self):
        cases=negative_cases(self.AREA,self.context)
        for name in ('제한증거상충','장기상품잔존3개월'):
            with self.subTest(name=name):self.assertEqual(self.run_case(self.AREA,cases[name])['metrics']['상충대상'],1)

    def test_amount_or_ledger_scope_mismatch_is_blocked(self):
        payload=negative_cases(self.AREA,self.context)['금액원장차이']
        self.assertGreater(self.run_case(self.AREA,payload)['blocking'],0)
        payload=sample(self.AREA,self.context);payload['classification_items'][0]['gl_refs']=['J01/L1']
        self.assertIn('CLASSIFICATION_LEDGER_SCOPE',self.codes(self.run_case(self.AREA,payload)))


if __name__=='__main__':unittest.main()
