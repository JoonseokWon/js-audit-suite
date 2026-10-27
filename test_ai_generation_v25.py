"""Generation grammar and rejection regressions; no actual model calls."""
from copy import deepcopy
import json
import re
import unittest
from unittest.mock import patch
import ai_provider as ai
from ai_contract import build_catalog
from ai_contract.generation import generation_plan
from test_ai_provider import packet,draft,wire,ollama_response


def four_exception_packet():
    p=packet();p['references']=[
        {'id':'REF001','kind':'engagement','company_code':'JS_ELEC','data':p['engagement']},
        {'id':'REF002','kind':'procedure_definition','company_code':'JS_ELEC','data':{'id':'A04'}},
        {'id':'REF003','kind':'calculation_row','company_code':'JS_ELEC','data':{'row':{'billed_supply_amount':90007}}},
        {'id':'REF004','kind':'raw_xlsx_row','company_code':'JS_ELEC','data':{'values':{'supply_amount':90000}}}]
    for i,code in enumerate(('CONTRACT_AMOUNT_MISMATCH','SUPPLY_AMOUNT_MISMATCH',
                              'TOTAL_AMOUNT_MISMATCH','LEDGER_AMOUNT_MISMATCH'),5):
        p['references'].append({'id':f'REF{i:03}','kind':'exception','company_code':'JS_ELEC',
            'data':{'code':code,'severity':'검토','expected':90000,'actual':90007,'difference':7}})
    p['references'].append({'id':'REF009','kind':'run_summary','company_code':'JS_ELEC',
        'data':{'metrics':{'순매출':100000},'review':4,'blocking':0}})
    p['references'].append({'id':'REF010','kind':'ledger_reconciliation','company_code':'JS_ELEC',
        'data':{'차이':0,'상태':'일치'}})
    return p


def constrained_wire(p):
    v=wire(draft(p));plan=generation_plan(p)
    v['citations']=deepcopy(plan['citations'])
    v['proposals']={f:'현재 등록된 근거의 발췌 범위에 대한 사람의 추가 검토가 필요한 미검증 초안이다.' for f in ai.FIELDS}
    for f,prefix in plan['prefixes'].items():v['proposals'][f]=prefix+v['proposals'][f]
    v['proposals']['scope']='현재 자동검사 실행요약의 순매출 100000원 자료를 한정한 미검증 초안이다.'
    return v


class LocalGenerationV25Tests(unittest.TestCase):
    def test_typed_branch_also_constrains_all_exception_codes_and_refs(self):
        p=four_exception_packet();before=deepcopy(p);public=ai.response_schema(p);old=deepcopy(public)
        schema=ai._ollama_response_schema(p,public);plan=generation_plan(p)
        self.assertEqual(schema['properties']['claims']['enum'],[build_catalog(p)['program_copy_claims']])
        for field in ('performed','conclusion'):
            pattern=schema['properties']['proposals']['properties'][field]['pattern']
            valid=json.dumps(plan['prefixes'][field]+'추가 확인을 위한 원문 대사 범위의 미검증 제안만 작성한다.',ensure_ascii=False)[1:-1]
            self.assertIsNotNone(re.fullmatch(pattern,valid))
            self.assertIsNone(re.fullmatch(pattern,'누락된 예외 목록을 대신한 일반적인 검토 제안이다.'))
        ids=schema['properties']['citations']['properties']['performed']['enum'][0]
        self.assertTrue(set(f'REF{i:03}' for i in range(5,9)).issubset(ids))
        self.assertEqual(public,old);self.assertEqual(p,before)

    def test_correct_100000_has_run_summary_source_in_scope_not_all_fields(self):
        p=four_exception_packet();plan=generation_plan(p)
        self.assertIn('REF009',plan['citations']['scope'])
        self.assertNotIn('REF009',plan['citations']['purpose'])
        self.assertNotIn('REF009',plan['citations']['risk'])
        v=constrained_wire(p)
        self.assertTrue(ai.validate_draft_response(p,v['proposals'],v['citations']))
        v['citations']['scope']=['REF002']
        with self.assertRaisesRegex(ai.AIProviderError,'수치'):
            ai.validate_draft_response(p,v['proposals'],v['citations'])

    def test_missing_exception_code_or_citation_is_still_rejected_not_repaired(self):
        p=four_exception_packet()
        for mode in ('code','reference'):
            v=constrained_wire(p)
            if mode=='code':v['proposals']['performed']=v['proposals']['performed'].replace('SUPPLY_AMOUNT_MISMATCH','누락')
            else:v['citations']['performed'].remove('REF006')
            response=ollama_response();response['message']['content']=json.dumps(v,ensure_ascii=False)
            raw=response['message']['content']
            with self.subTest(mode=mode),patch.object(ai,'_post_json',return_value=response) as post:
                with self.assertRaisesRegex(ai.AIProviderError,'예외 코드|본문과'):
                    ai.generate_draft(p,{})
                self.assertEqual(post.call_count,1);self.assertEqual(response['message']['content'],raw)

    def test_generation_request_and_original_response_stay_separate(self):
        p=four_exception_packet();v=constrained_wire(p);response=ollama_response()
        response['message']['content']=json.dumps(v,ensure_ascii=False);raw=response['message']['content']
        def respond(_target,payload,*_args):
            plan=json.loads(payload['messages'][1]['content'])['local_generation_plan']
            self.assertEqual(plan,generation_plan(p))
            self.assertEqual(payload['format']['properties']['citations']['properties']['scope']['enum'],[plan['citations']['scope']])
            self.assertNotIn('num_gpu',payload['options'])
            return response
        with patch.object(ai,'_post_json',side_effect=respond):result=ai.generate_draft(p,{})
        self.assertEqual(result['raw_response'],raw)
        self.assertEqual(result['fields'],v['proposals'])
        self.assertEqual(result['acceptance_state'],'quarantined_proposal')
        self.assertNotEqual(result['fields'],result['verified_fields'])

    def test_quotes_backslashes_and_duplicate_exception_codes_remain_exact(self):
        p=four_exception_packet();code=r'RISK("Q")+\BOUND[1].*?'
        p['references'][4]['data']['code']=code;p['references'][5]['data']['code']=code
        plan=generation_plan(p);pattern=ai._ollama_response_schema(p,ai.response_schema(p))['properties']['proposals']['properties']['performed']['pattern']
        text=plan['prefixes']['performed']+'사람의 추가 확인이 필요한 등록 원문 발췌와 자동계산 대사 범위이다.'
        self.assertIsNotNone(re.fullmatch(pattern,json.dumps(text,ensure_ascii=False)[1:-1]))
        self.assertIn(code+' [REF005]',text);self.assertIn(code+' [REF006]',text)

    def test_no_exception_keeps_free_proposal_but_fixed_source_arrays(self):
        p=packet();local=ai._ollama_response_schema(p,ai.response_schema(p))
        self.assertNotIn('pattern',local['properties']['proposals']['properties']['performed'])
        self.assertEqual(local['properties']['citations']['properties']['scope']['enum'],[['REF001']])


if __name__=='__main__':unittest.main()
