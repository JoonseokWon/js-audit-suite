"""Review AI-01/02 counterexamples; no model calls or actual human approval."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from common import AuditError,dumps
from ai_contract import build_catalog,validate_response,CONTRACT_VERSION
from ai_contract.headers import response_context
from test_ai_provider import packet,draft
from test_review_ai_helpers import response_from_fields,sync_response
from test_ai_workpapers import CONTEXT,mock_response
from workspace import Workspace


def recorded_packet():
    p=packet()
    p['references']=[
        {'id':'REF001','kind':'ledger_reconciliation','company_code':'JS_ELEC',
            'data':{'모듈':'매출','지표':'순매출','상태':'미확인','차이':None}},
        {'id':'REF002','kind':'raw_xlsx_row','company_code':'JS_ELEC',
            'data':{'sheet':'deliveries','row':2,'values':{'delivered_qty':'10'}}},
        {'id':'REF003','kind':'calculation_row','company_code':'JS_ELEC',
            'data':{'table':'매출대사','row':{'순매출':'100000','status':'REVIEW','currency':'KRW'}}}]
    return p


def typed_response(p):
    value=draft(p)
    return {'context':response_context(p),'claims':build_catalog(p)['claims'],
        'proposals':value['fields'],'citations':value['citations']}


class TypedRecordedFactTests(unittest.TestCase):
    def test_recorded_human_input_remains_unverified_and_is_not_lost(self):
        from ai_contract import attach_contract
        p=packet();attach_contract(p,workflow_procedure={'performed':'사용자 수행기록',
            'performed_date':'2026-10-26','performer':'SYNTHETIC ONLY'})
        h=p['contract']['human_performance']
        self.assertEqual(h['state'],'user_recorded_unverified')
        self.assertEqual(h['records'][0]['source'],'workflow_procedure')
        self.assertFalse(h['physical_performance_verified'])

    def test_recorded_status_and_kind_are_exact_program_values(self):
        p=recorded_packet();parsed=typed_response(p);r=validate_response(p,parsed)
        self.assertEqual(r['acceptance_state'],'quarantined_proposal')
        self.assertIn('미확인',r['verified_fields']['performed'])
        self.assertIn('raw_xlsx_row',r['verified_fields']['performed'])
        self.assertIn('등록 원본 행 발췌',r['verified_fields']['performed'])

    def test_unconfirmed_reconciliation_cannot_become_blocked_control(self):
        p=recorded_packet();parsed=typed_response(p)
        claim=next(c for c in parsed['claims'] if c['reference_id']=='REF001')
        claim['status']['value']='차단'
        with self.assertRaisesRegex(AuditError,'종류·상태·값'):validate_response(p,parsed)

    def test_registered_delivery_row_cannot_become_physical_inventory(self):
        p=recorded_packet();parsed=typed_response(p)
        next(c for c in parsed['claims'] if c['reference_id']=='REF002')['reference_kind']='physical_inventory_inspection'
        with self.assertRaisesRegex(AuditError,'종류·상태·값'):validate_response(p,parsed)

    def test_same_number_in_another_reference_or_unit_is_not_substitutable(self):
        p=recorded_packet()
        for key,value in [('reference_id','REF002'),('value','100001'),('unit','USD'),('value_path',['wrong_field'])]:
            parsed=typed_response(p);claim=next(c for c in parsed['claims'] if c['reference_id']=='REF003');claim[key]=value
            with self.subTest(key=key),self.assertRaises(AuditError):validate_response(p,parsed)

    def test_boolean_and_integer_are_not_equal_typed_values(self):
        p=recorded_packet();p['references'][0]['data']['차이']=1
        parsed=typed_response(p);parsed['claims'][0]['value']=True
        with self.assertRaises(AuditError):validate_response(p,parsed)

    def test_required_exception_or_reconciliation_cannot_be_omitted(self):
        p=recorded_packet();parsed=typed_response(p)
        parsed['claims']=[c for c in parsed['claims'] if c['reference_id']!='REF001']
        with self.assertRaisesRegex(AuditError,'필수'):validate_response(p,parsed)

    def test_invalid_claim_identifier_types_raise_controlled_error(self):
        for ident in ({},[],None,True,1):
            p=recorded_packet();parsed=typed_response(p);parsed['claims'][0]['claim_id']=ident
            with self.subTest(ident=ident),self.assertRaises(AuditError):validate_response(p,parsed)

    def test_fixed_identity_and_human_state_cannot_be_forged(self):
        for key,value in [('identity',{'company_code':'OTHER'}),('human_performance',{'state':'performed','physical_performance_verified':True})]:
            p=recorded_packet();p['contract'][key]=value
            with self.subTest(key=key),self.assertRaises(AuditError):validate_response(p,typed_response(p))

    def test_catalog_limit_explicitly_counts_omitted_claims(self):
        p=packet()
        p['references']=[{'id':f'REF{i:03}','kind':'raw_xlsx_row','company_code':'JS_ELEC',
            'data':{'sheet':'orders','row':i}} for i in range(1,36)]
        c=build_catalog(p);self.assertEqual(len(c['claims']),24)
        self.assertEqual(c['scope']['omitted_claims'],11)
        self.assertIn('not the full table/row',c['scope']['scope'])


class QuarantinedProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.ws=Workspace(Path(self.temp.name)/'workspace',create=CONTEXT)

    def test_review_company_procedure_and_performance_probes_never_enter_facts(self):
        probes=[('scope','타사 새빛자동차의 매출 자료이다. 사람 검토가 필요하다.'),
            ('purpose','재고자산 실사 입회 절차에 관한 것이다.'),
            ('performed','감사인은 현장에서 재고를 실물과 대조하였다. 별도 검토가 필요하다.'),
            ('performed','금융기관 확인조회는 발송되었고 회신의 진위도 검증되었다. 사람 검토가 필요하다.'),
            ('scope','매출은 일백억원이다. 사람 검토가 필요하다.')]
        for index,(field,value) in enumerate(probes):
            ws=Workspace(Path(self.temp.name)/str(index),create=CONTEXT);p=ws.ai_packet('A04')
            r=mock_response(p);r['fields'][field]=value;sync_response(r);raw=r['raw_response']
            did=ws.record_ai_draft(p,r,'SYNTHETIC ONLY requester');d=ws.ai_drafts[did]
            self.assertEqual(d['acceptance_state'],'quarantined_proposal')
            self.assertEqual(d['raw_response'],raw)
            self.assertEqual(d['unverified_proposals'][field],value)
            ws.apply_ai_draft(did,'SYNTHETIC ONLY author')
            self.assertNotIn(value,'\n'.join(ws.procedures['A04'][k] for k in r['fields']))
            self.assertIn(CONTEXT['회사코드'],ws.procedures['A04']['purpose'])
            self.assertFalse(ws.ai_status('A04')['approved'])
            self.assertEqual(ws.procedures['A04']['performed_date'],'')
            self.assertEqual(ws.procedures['A04']['reviewer'],'')

    def test_program_fact_tampering_and_unknown_proposal_reference_are_blocked(self):
        p=self.ws.ai_packet('A04')
        for mode in ('program','citation'):
            r=mock_response(p)
            if mode=='program':r['verified_fields']['performed']='실제 수행을 확인했다'
            else:r['citations']['scope']=['REF999'];sync_response(r)
            before=self.ws.head
            with self.subTest(mode=mode),self.assertRaises(AuditError):self.ws.record_ai_draft(p,r,'SYNTHETIC ONLY')
            self.assertEqual(self.ws.head,before)

    def test_XML_noncharacter_in_proposal_is_preserved_and_never_auto_applied(self):
        p=self.ws.ai_packet('A04');r=mock_response(p)
        r['fields']['scope']='미검증 원문 \ufffe 제안. 사람 검토가 필요하다.';sync_response(r)
        raw=r['raw_response'];did=self.ws.record_ai_draft(p,r,'SYNTHETIC ONLY')
        self.assertEqual(self.ws.ai_drafts[did]['raw_response'],raw)
        self.ws.apply_ai_draft(did,'SYNTHETIC ONLY')
        self.assertNotIn('\ufffe',self.ws.procedures['A04']['scope'])

    def test_invalid_user_actor_cannot_partially_apply_a_saved_draft(self):
        self.ws.save_procedure({'id':'A04','title':'SYNTHETIC ONLY','preparer':'existing author'})
        p=self.ws.ai_packet('A04');did=self.ws.record_ai_draft(p,mock_response(p),'SYNTHETIC ONLY')
        before=(self.ws.head,deepcopy(self.ws.procedures),deepcopy(self.ws.ai_applications))
        with self.assertRaises(AuditError):self.ws.apply_ai_draft(did,'SYNTHETIC ONLY\x01')
        self.ws.refresh();self.assertEqual((self.ws.head,self.ws.procedures,self.ws.ai_applications),before)

    def test_invalid_request_or_approval_text_creates_no_event(self):
        p=self.ws.ai_packet('A04');r=mock_response(p);before=self.ws.head
        with self.assertRaises(AuditError):self.ws.record_ai_draft(p,r,'SYNTHETIC ONLY\x01')
        self.assertEqual(self.ws.head,before)
        did=self.ws.record_ai_draft(p,r,'SYNTHETIC ONLY');self.ws.apply_ai_draft(did,'SYNTHETIC ONLY')
        for actor,note in [('SYNTHETIC ONLY\x01','note'),('SYNTHETIC ONLY','note\x01')]:
            before=self.ws.head
            with self.assertRaises(AuditError):self.ws.approve_ai_content('A04',actor,note)
            self.assertEqual(self.ws.head,before)

    def test_strip_cannot_hide_leading_or_trailing_XML_forbidden_user_text(self):
        self.ws.save_procedure({'id':'A04','title':'SYNTHETIC ONLY','preparer':'existing author'})
        p=self.ws.ai_packet('A04');r=mock_response(p)
        did=self.ws.record_ai_draft(p,r,'SYNTHETIC ONLY')
        for char in ('\x0b','\x0c','\x1c','\x1f'):
            for actor in (char+'SYNTHETIC ONLY','SYNTHETIC ONLY'+char):
                before=(self.ws.head,deepcopy(self.ws.procedures),deepcopy(self.ws.ai_applications))
                with self.subTest(char=ord(char),side=actor.startswith(char)):
                    with self.assertRaises(AuditError):self.ws.record_ai_draft(p,r,actor)
                    with self.assertRaises(AuditError):self.ws.apply_ai_draft(did,actor)
                    self.ws.refresh()
                    self.assertEqual((self.ws.head,self.ws.procedures,self.ws.ai_applications),before)
        self.ws.apply_ai_draft(did,'SYNTHETIC ONLY')
        for char in ('\x0b','\x0c','\x1c','\x1f'):
            for invalid in (char+'SYNTHETIC ONLY','SYNTHETIC ONLY'+char):
                before=self.ws.head
                with self.assertRaises(AuditError):self.ws.approve_ai_content('A04',invalid,'valid note')
                with self.assertRaises(AuditError):self.ws.approve_ai_content('A04','SYNTHETIC ONLY',invalid)
                self.assertEqual(self.ws.head,before)

    def test_content_approval_uses_typed_citations_and_edit_invalidates_it(self):
        p=self.ws.ai_packet('A04');r=mock_response(p)
        did=self.ws.record_ai_draft(p,r,'SYNTHETIC ONLY');self.ws.apply_ai_draft(did,'SYNTHETIC ONLY')
        a=self.ws.approve_ai_content('A04','SYNTHETIC ONLY','Synthetic transition only, not real approval')
        self.assertEqual(a['contract_version'],CONTRACT_VERSION)
        self.assertEqual(a['citations'],self.ws.ai_drafts[did]['verified_citations'])
        self.assertFalse(a['model_proposals_automatically_applied'])
        changed=dict(self.ws.procedures['A04']);changed['conclusion']+=' 직접 수정';self.ws.save_procedure(changed)
        self.assertFalse(self.ws.ai_status('A04')['approved'])

    def test_legacy_text_and_approval_events_survive_but_cannot_be_reapplied_or_approved(self):
        p=self.ws.ai_packet('A04');legacy={'id':'legacy','procedure_id':'A04','packet':p,
            'basis':self.ws.basis(),'fields':{'purpose':'old text'},'raw_response':'old model raw'}
        self.ws._append('ai_draft',legacy);self.ws.refresh()
        self.ws.save_procedure({'id':'A04','title':'legacy','preparer':'SYNTHETIC ONLY'},_ai_draft_id='legacy')
        self.ws._append('ai_content_approval',{'procedure_id':'A04','draft_id':'legacy','note':'historical only'})
        self.ws.refresh();before=self.ws.head
        self.assertTrue(self.ws.ai_status('A04')['legacy']);self.assertFalse(self.ws.ai_status('A04')['approved'])
        for operation in (lambda:self.ws.apply_ai_draft('legacy','SYNTHETIC ONLY'),
                lambda:self.ws.approve_ai_content('A04','SYNTHETIC ONLY','legacy probe')):
            with self.assertRaises(AuditError):operation()
        self.assertEqual(self.ws.head,before)
        self.assertEqual(self.ws.ai_drafts['legacy']['raw_response'],'old model raw')
        self.assertEqual(self.ws.ai_status('A04')['historical_approval']['note'],'historical only')


if __name__=='__main__':unittest.main()
