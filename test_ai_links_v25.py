"""AI packet hooks preserve provenance and do not turn human input into facts."""
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from common import AuditError,digest
from ai_contract import attach_contract,build_catalog,validate_response
from ai_contract.generation import generation_plan
from ai_contract.linked_records import add_references,HUMAN_KINDS
from ai_contract.headers import response_context
from test_ai_provider import packet


class LinkedHumanRecordsTests(unittest.TestCase):
    def setup_packet(self,limit=70):
        p=packet();p['limitations']=[]
        ws=SimpleNamespace(context={'회사코드':'JS_ELEC','시작일':'2026-01-01','기준일':'2026-12-31'})
        def ref(kind,data,**links):
            if len(p['references'])>=limit:return None
            rid=f"REF{len(p['references'])+1:03}"
            p['references'].append({'id':rid,'kind':kind,'company_code':'JS_ELEC','data':deepcopy(data),**links})
            return rid
        return ws,p,ref

    def test_no_linked_records_preserves_existing_packet(self):
        ws,p,ref=self.setup_packet();before=deepcopy(p)
        with patch('audit_links.packet',return_value={'references':[]}),patch('misstatements.packet',return_value={'references':[]}):
            self.assertEqual(add_references(ws,'A04',p,ref),{})
        self.assertEqual(p,before)

    def test_exact_human_record_kinds_and_unverified_performance_are_preserved(self):
        ws,p,ref=self.setup_packet()
        risk=[]
        for index,kind in enumerate(HUMAN_KINDS[:-1]):
            data={'id':str(index),'pin':{'context':dict(ws.context)}}
            if kind=='human_actual_performance':data.update(performed='SYNTHETIC ONLY 직접 입력 모사',performed_date='2026-12-31',performer='SYNTHETIC ONLY')
            risk.append({'kind':kind,'procedure_id':'A04','human_record_only':True,'data':data})
        ms={'kind':'misstatement_record','record_id':'MS01','data':{'id':'MS01','company_code':'JS_ELEC',
            'start_date':'2026-01-01','cutoff_date':'2026-12-31','procedure_ids':['A04'],
            'amount':7,'current':True,'verification_state':'미확인','assessment':'사람 검토 중'}}
        with patch('audit_links.packet',return_value={'references':risk,'rows':[],'scope':'사람 입력·미검증'}),patch('misstatements.packet',return_value={'references':[ms],'inventory':{'available':1,'included':1,'omitted':0}}):
            add_references(ws,'A04',p,ref)
        attach_contract(p)
        self.assertEqual(p['contract']['human_performance']['state'],'user_recorded_unverified')
        self.assertFalse(p['contract']['human_performance']['physical_performance_verified'])
        claims=build_catalog(p)['program_copy_claims']
        self.assertTrue(set(HUMAN_KINDS).issubset({c['reference_kind'] for c in claims}))
        plan=generation_plan(p)
        parsed={'context':response_context(p),'claims':claims,
            'proposals':{f:'사람이 추가 확인할 미검증 제안이다.' for f in plan['citations']},'citations':plan['citations']}
        derived=validate_response(p,parsed)
        text=derived['verified_fields']['performed']
        self.assertIn('사람 입력 수행기록·실제 수행 미검증',text)
        self.assertIn('사람 입력 왜곡표시 기록·회계적 관련성 미검증',text)
        self.assertIn('사용자의 수행기록이 있으나 실제 수행은 프로그램이 검증하지 않았습니다',text)
        self.assertEqual(derived['acceptance_state'],'quarantined_proposal')

    def test_field_scope_and_company_guards_reject_foreign_records(self):
        for value in ('foreign_company','foreign_period','foreign_procedure','unlinked_procedure'):
            ws,p,ref=self.setup_packet()
            data={'company_code':'JS_ELEC','start_date':'2026-01-01','cutoff_date':'2026-12-31','procedure_ids':['A04']}
            item={'kind':'misstatement_record','data':data}
            if value=='foreign_company':data['company_code']='JS_AUTO'
            elif value=='foreign_period':data['cutoff_date']='2025-12-31'
            elif value=='foreign_procedure':item['procedure_id']='A08'
            else:data['procedure_ids']=['A08']
            with self.subTest(value=value),patch('audit_links.packet',return_value={'references':[]}),patch('misstatements.packet',return_value={'references':[item]}):
                with self.assertRaises(AuditError):add_references(ws,'A04',p,ref)

    def test_limited_reference_and_status_coverage_is_explicit_and_hashed(self):
        ws,p,ref=self.setup_packet(limit=3)
        items=[{'kind':'misstatement_record','record_id':str(i),'data':{'procedure_ids':['A04'],'amount':i}} for i in range(5)]
        info={'references':items,'scope':'발췌','inventory':{'available':9,'included':5,'omitted':4,'manifest_hash':'a'*64},
            'rows':[{'status':str(i)} for i in range(12)]}
        with patch('audit_links.packet',return_value={'references':[]}),patch('misstatements.packet',return_value=info):
            add_references(ws,'A04',p,ref)
        section=p['linked_human_records']['misstatements']
        self.assertEqual(section['available_references'],5);self.assertEqual(section['included_references'],2)
        self.assertEqual(section['omitted_references'],3)
        self.assertEqual(section['source_inventory']['omitted'],4)
        self.assertEqual(section['full_reference_manifest_hash'],digest(items))
        self.assertEqual(section['status_included'],4);self.assertEqual(section['status_omitted'],8)
        self.assertEqual(sum(row[-1] for row in section['all_status_codes']),12)

    def test_real_JS_electronics_human_records_reach_bounded_packet_without_actual_AI(self):
        import audit_links,misstatements
        from ai_quality.case_v25 import create_case
        from test_audit_workflow import profile
        with tempfile.TemporaryDirectory() as tmp:
            ws,_=create_case(Path(tmp),lambda ok,name:self.assertTrue(ok,name))
            ws.save_workflow_profile(profile(('A04','F03')),'SYNTHETIC ONLY')
            ws.save_workflow_risk({'id':'R25','title':'SYNTHETIC ONLY 매출 금액 차이',
                'accounts':['매출'],'assertions':['정확성'],'procedure_ids':['A04'],
                'basis':ws.data_basis(),'evidence_ids':list(ws.sources),'nature':'증빙 대사',
                'timing':'기말','extent':'합성 송장 1건','assessment':'SYNTHETIC ONLY 판단 입력 모사'},'SYNTHETIC ONLY')
            ws.save_workflow_procedure({'procedure_id':'A04','risk_ids':['R25'],
                'evidence_ids':list(ws.sources),'basis':ws.data_basis(),'nature':'자료 대사',
                'timing':'기말','extent':'합성 1건','plan':'SYNTHETIC ONLY 직접 계획'},'SYNTHETIC ONLY')
            audit_links.save_assessment(ws,{'risk_id':'R25','assertions':[{'category':'거래','assertion':'정확성'}],
                'inherent_rating':'높음','inherent_reason':'합성 금액 차이','control_rating':'',
                'control_reason':'','significant_risk':None,'significant_reason':''},'SYNTHETIC ONLY')
            selected=[{'source_id':sid,'company_code':ws.context['회사코드'],
                'start_date':ws.context['시작일'],'end_date':ws.context['기준일'],
                'locator':'SYNTHETIC ONLY 원문 발췌','relevance':'SYNTHETIC ONLY 합성 금액 대사'}
                for sid in (run['source_id'] for run in ws.latest().values())]
            audit_links.save_response(ws,{'id':'RESP25','risk_id':'R25','procedure_id':'A04',
                'assertions':[{'category':'거래','assertion':'정확성'}],'nature':'자료 대사','timing':'기말',
                'extent':'합성 송장 1건','sources':selected,'run_ids':[r['id'] for r in ws.latest().values()]},'SYNTHETIC ONLY')
            misstatements.save_record(ws,{'description':'SYNTHETIC ONLY 7원 차이 조사 대기',
                'evidence_ids':list(ws.sources),'procedure_ids':['A04','F03']},'SYNTHETIC ONLY')
            packet=ws.ai_packet('A04',limits={'max_chars':24000})
            kinds={r['kind'] for r in packet['references']}
            self.assertTrue({'raw_xlsx_row','calculation_row','human_assertion_risk_assessment','human_risk_response','misstatement_record'}<=kinds)
            self.assertEqual(packet['contract']['human_performance']['state'],'not_recorded')
            self.assertEqual(packet['linked_human_records']['misstatements']['included_references'],1)
            self.assertFalse(ws.ai_drafts);self.assertFalse(ws.ai_approvals)


if __name__=='__main__':unittest.main()
