"""Independent hand oracles, real ledger gates and structured-input abuse cases."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import threading
import unittest

from common import AuditError, read_xlsx
import financial_bridge as bridge
import ledger

ROOT = Path(__file__).resolve().parent
CONTEXT = {'회사코드':'SYNTH01','시작일':'2026-01-01','기준일':'2026-12-31','통화':'KRW','연결구분':'별도'}


class FinancialBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        cls.inputs, cls.source = read_xlsx(ROOT/'samples/통합/통합_v1.3_원장_리드.xlsx', ledger.SCHEMA)
        cls.ledger = ledger.analyze(deepcopy(cls.inputs))
        cls.ledger['source'] = cls.source
        cls.normal = bridge.build_sample(cls.folder/'normal', cls.ledger)
        cls.json = json.loads(cls.normal.read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def run_source(self, source, ledger_result=None, context=None):
        p = self.folder/'test_input.json'
        p.write_text(json.dumps(source,ensure_ascii=False),encoding='utf-8')
        return bridge.analyze(p,context or CONTEXT,self.ledger if ledger_result is None else ledger_result)

    def assert_blocked(self, result, code='FS_INPUT'):
        self.assertGreater(result['blocking'],0,result)
        self.assertIn(code,[x['code'] for x in result['issues']])
        for rows in result['tables'].values(): self.assertEqual(rows,[])
        self.assertFalse(result['detail']['posting_allowed'])
        self.assertEqual(result['detail']['검토상태'],'미검토 초안')

    def test_normal_real_ledger_and_hand_oracles(self):
        result=bridge.analyze(self.normal,CONTEXT,self.ledger)
        self.assertEqual((result['blocking'],result['review']),(0,0),result['issues'])
        self.assertEqual(result['metrics']['매핑계정수'],59)
        self.assertEqual(result['metrics']['필수주석수'],8)
        self.assertEqual(result['metrics']['대사항목수'],94)
        amounts={x['항목ID']:x['보고금액'] for x in result['tables']['재무제표대사'] if x['코드']=='FS_TB'}
        self.assertEqual(amounts['A_CURRENT'],4002752)
        self.assertEqual(amounts['A_NONCURRENT'],1435817)
        self.assertEqual(amounts['ASSETS'],5438569)
        self.assertEqual(amounts['LIABILITIES'],5283551)
        self.assertEqual(amounts['EQUITY'],155018)
        self.assertEqual(amounts['REVENUE'],146400)
        self.assertEqual(amounts['EXPENSE'],6730382)
        self.assertEqual(amounts['PROFIT'],-6583982)
        self.assertEqual(amounts['ASSETS'],amounts['LIABILITIES']+amounts['EQUITY'])
        self.assertEqual(len(result['tables']['원장리드연결']),59)
        self.assertTrue(all(x['원장조정전']==x['사용잔액'] for x in result['tables']['원장리드연결']))
        self.assertTrue(all(x['차이']==0 for x in result['tables']['원장리드연결']))
        self.assertTrue(all('시산표!' in x['원본행'] for x in result['tables']['TB본문매핑']))
        self.assertTrue(result['detail']['원장입력SHA256'])
        self.assertEqual(result['detail']['원장원천']['sha256'],self.source['sha256'])
        self.assertTrue(all(x['검토상태']=='미검토' for x in result['tables']['재무제표대사']))

    def test_all_generated_cases(self):
        manifest=json.loads((self.normal.parent/'financial_cases/cases.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['cases']),13)
        for case in manifest['cases']:
            with self.subTest(case=case['name']):
                result=bridge.analyze(self.normal.parent/'financial_cases'/case['file'],CONTEXT,self.ledger)
                self.assertEqual(result['blocking'],case['blocking'],result['issues'])
                if 'review' in case:self.assertEqual(result['review'],case['review'])
                if 'required_code' in case:self.assertIn(case['required_code'],[x['code'] for x in result['issues']])

    def test_ledger_unavailable_no_financial_comparison(self):
        self.assert_blocked(bridge.analyze(self.normal,CONTEXT), 'FS_LEDGER_UNAVAILABLE')

    def test_wrong_module(self):
        fake=deepcopy(self.ledger);fake['module']='금융상품'
        self.assert_blocked(self.run_source(self.json,fake),'FS_LEDGER_UNAVAILABLE')

    def test_blocked_ledger(self):
        fake=deepcopy(self.ledger);fake['blocking']=1
        self.assert_blocked(self.run_source(self.json,fake),'FS_LEDGER_BLOCKED')

    def test_hidden_blocking_issue(self):
        fake=deepcopy(self.ledger);fake['issues'].append({'severity':'차단','code':'X'})
        self.assert_blocked(self.run_source(self.json,fake),'FS_LEDGER_BLOCKED')

    def test_blocking_bool_not_zero(self):
        fake=deepcopy(self.ledger);fake['blocking']=False
        self.assert_blocked(self.run_source(self.json,fake),'FS_LEDGER_BLOCKED')

    def test_ledger_inputs_required(self):
        fake=deepcopy(self.ledger);del fake['tables']['입력_총계정원장']
        self.assert_blocked(self.run_source(self.json,fake),'FS_LEDGER_INPUT')

    def test_actual_ledger_gap_recomputed_even_when_supplied_status_zero(self):
        fake=deepcopy(self.ledger);fake['tables']['입력_총계정원장'].pop()
        self.assert_blocked(self.run_source(self.json,fake),'FS_LEDGER_BLOCKED')

    def test_stale_lead_rejected(self):
        fake=deepcopy(self.ledger);fake['tables']['리드스케줄'][0]['조정전']+=1
        self.assert_blocked(self.run_source(self.json,fake),'FS_LEDGER_STALE')

    def test_stale_control_rejected(self):
        fake=deepcopy(self.ledger);fake['tables']['원장통제'][0]['실제']+=1
        self.assert_blocked(self.run_source(self.json,fake),'FS_LEDGER_STALE')

    def test_json_declared_tb_context_cannot_override_real_context(self):
        fake=deepcopy(self.json)
        for k in ('설정','TB문맥'):fake[k]['회사코드']='OTHER'
        for r in fake['문서']:r['회사코드']='OTHER'
        self.assert_blocked(self.run_source(fake))

    def test_actual_engagement_mismatch(self):
        c=CONTEXT|{'회사코드':'OTHER'}
        self.assert_blocked(bridge.analyze(self.normal,c,self.ledger),'FS_LEDGER_CONTEXT')

    def test_nonzero_pl_opening_is_not_current_period_income(self):
        inputs=deepcopy(self.inputs)
        for code,delta in [('4000',1),('3000',-1)]:
            for role in ('시산표','독립통제'):
                row=next(x for x in inputs[role] if x['계정코드']==code)
                row['기초잔액']+=delta;row['기말잔액']+=delta
        changed=ledger.analyze(inputs)
        self.assertEqual(changed['blocking'],0,changed['issues'])
        self.assert_blocked(self.run_source(self.json,changed))

    def test_result_context_mismatch(self):
        fake=deepcopy(self.ledger);fake['context']['기준일']='2025-12-31'
        self.assert_blocked(self.run_source(self.json,fake),'FS_LEDGER_CONTEXT')

    def test_consolidated_engagement_rejected(self):
        self.assert_blocked(bridge.analyze(self.normal,CONTEXT|{'연결구분':'연결'},self.ledger),'FS_CONTEXT')

    def test_approved_aje_not_used_in_unadjusted_comparison(self):
        inputs=deepcopy(self.inputs)
        for i,(code,d,c) in enumerate([('1500',1000,0),('3000',0,1000)],2):
            inputs['감사조정'].append({'조정ID':'APPROVED_SYNTH','행ID':str(i),'계정코드':code,'차변':d,'대변':c,'근거':'합성 승인조정','상태':'승인','_row':i,'_sheet':'감사조정'})
        changed=ledger.analyze(inputs)
        result=self.run_source(self.json,changed)
        self.assertEqual(result['blocking'],0,result['issues'])
        self.assertEqual(result['metrics']['차이항목수'],0)
        self.assertIn('FS_PRE_ADJUSTMENT',[x['code'] for x in result['issues']])
        row=next(x for x in result['tables']['원장리드연결'] if x['계정코드']=='1500')
        self.assertEqual((row['원장조정전'],row['원장조정후'],row['사용잔액']),(1200000,1201000,1200000))

    def test_sign_reversal_does_not_abs(self):
        v=deepcopy(self.json);next(r for r in v['계정매핑'] if r['계정코드']=='1390')['계수']=-1
        r=self.run_source(v)
        row=next(x for x in r['tables']['재무제표대사'] if x['코드']=='FS_TB' and x['항목ID']=='B_1390')
        self.assertEqual(row['차이'],-21296)

    def test_coherent_totals_notes_equation_still_tb_mismatch(self):
        p=self.normal.parent/'financial_cases/13_합계는맞지만TB불일치.json'
        r=bridge.analyze(p,CONTEXT,self.ledger)
        self.assertEqual({x['code'] for x in r['issues']},{'FS_TB'})
        self.assertEqual(sum(x['상태']!='일치' for x in r['tables']['재무제표대사'] if x['코드'] in ('FS_SUM','FS_NOTE','FS_BALANCE')),0)

    def test_null_bool_and_float_are_not_zero(self):
        for amount in (None,True,1.0):
            v=deepcopy(self.json);v['항목'][0]['금액']=amount
            with self.subTest(amount=amount):self.assert_blocked(self.run_source(v))

    def test_repeated_nested_leaf_rejected(self):
        v=deepcopy(self.json)
        v['합계관계'].append({'관계ID':'DUP_LEAF','문서ID':'FS','합계항목':'ASSETS','구성항목':'B_1000','계수':1})
        self.assert_blocked(self.run_source(v))

    def test_zero_balance_account_mapping_missing_rejected(self):
        v=deepcopy(self.json);v['계정매핑']=[r for r in v['계정매핑'] if r['계정코드']!='2210']
        self.assert_blocked(self.run_source(v))

    def test_nonzero_tolerance_stays_open(self):
        r=bridge.analyze(self.normal.parent/'financial_cases/10_허용범위내차이.json',CONTEXT,self.ledger)
        self.assertEqual(r['blocking'],0)
        self.assertGreater(r['review'],0)
        self.assertTrue(all(x['상태']=='허용범위내차이' for x in r['tables']['재무제표대사'] if x['차이']))

    def test_duplicate_json_key(self):
        p=self.folder/'duplicate.json';p.write_text('{"schema_version":"1.1","schema_version":"1.1"}',encoding='utf-8')
        self.assert_blocked(bridge.analyze(p,CONTEXT,self.ledger))

    def test_nan_literal(self):
        p=self.folder/'nan.json';p.write_text('{"x":NaN}',encoding='utf-8')
        self.assert_blocked(bridge.analyze(p,CONTEXT,self.ledger))

    def test_source_hash_exact_and_no_mutation(self):
        before=self.normal.read_bytes();r=bridge.analyze(self.normal,CONTEXT,self.ledger)
        self.assertEqual(self.normal.read_bytes(),before)
        self.assertEqual(r['source']['sha256'],hashlib.sha256(before).hexdigest())
        self.assertTrue(all(x['SHA256']==r['source']['sha256'] for x in r['tables']['원천위치']))

    def test_cancel_propagates_without_result(self):
        event=threading.Event();event.set()
        with self.assertRaisesRegex(AuditError,'취소'):bridge.analyze(self.normal,CONTEXT,self.ledger,event)

    def test_original_vendor_byte_identical(self):
        meta=json.loads((ROOT/'financial_bridge/PROVENANCE.json').read_text(encoding='utf-8'))
        vendor=ROOT/'financial_bridge/vendor/financial.py'
        self.assertEqual(hashlib.sha256(vendor.read_bytes()).hexdigest(),meta['original_sha256'])

    def test_sample_builder_unknown_account_not_guessed(self):
        r=deepcopy(self.ledger)
        # A controlled replacement account may be a valid GL but has no explicit sample presentation policy.
        for table in ('입력_시산표','입력_총계정원장','입력_계정매핑','입력_독립통제','입력_모듈연결'):
            for row in r['tables'][table]:
                if row['계정코드']=='1000':row['계정코드']='UNKNOWN'
        setting=next(x for x in r['tables']['입력_설정'] if x['항목']=='추출범위');setting['값']=setting['값'].replace('1000','UNKNOWN')
        inputs={role:r['tables']['입력_'+role] for role in ledger.SCHEMA}
        changed=ledger.analyze(inputs)
        with self.assertRaisesRegex(AuditError,'명시한 기존'):bridge.build_sample(self.folder/'unknown',changed)


if __name__=='__main__':unittest.main(verbosity=2)
