from pathlib import Path
from copy import deepcopy
from decimal import Decimal
import json,tempfile,unittest,re
import runtime
ROOT=runtime.configure()
import inventory,payroll,adapters,exporter
from common import *
from workspace import Workspace
from verify import check_book,synthetic_procedure
SPEC=json.loads((ROOT/'v12_specs.json').read_text(encoding='utf-8'))
def source(name):
    b=next(x for x in SPEC['books'] if x['name']==name)
    return {k:[dict(zip(b['headers'][k],r))|{'_row':i+2,'_sheet':k} for i,r in enumerate(rows)] for k,rows in b['tables'].items()}
class InventoryTests(unittest.TestCase):
    def base(self):return source('재고평가_01_정상')
    def test_no_offset_of_losses_by_gain(self):
        r=inventory.analyze(self.base());self.assertEqual(r['metrics']['기말재고평가충당금'],15000)
        self.assertEqual([x['계산평가충당금'] for x in r['tables']['재고평가요약']],[15000,0])
    def test_reversal_never_increases_above_cost(self):
        t=self.base();t['NRV근거'][0]['예상판매단가']=1000000;r=inventory.analyze(t)
        self.assertEqual(r['metrics']['기말재고순액'],200000)
        self.assertEqual(r['metrics']['당기재고평가손실'],-18000)
    def test_fractional_unit_quantities_separate(self):
        r=inventory.analyze(source('재고평가_03_소수수량'));checks=r['tables']['원장통제']
        quantities=[x for x in checks if x['지표']=='기말수량합계' and x['자료'].startswith('재고명세')]
        self.assertEqual({x['자료'] for x in quantities},{'재고명세[EA]','재고명세[KG]'})
        self.assertEqual({Decimal(x['실제']) for x in quantities},{Decimal('10.5'),Decimal('5')})
    def test_blank_price_is_not_zero(self):
        t=self.base();t['NRV근거'][0]['예상판매단가']=None
        with self.assertRaises(AuditError):inventory.analyze(t)
    def test_negative_nrv_floor_has_review(self):
        t=source('재고평가_04_NRV음수');r=inventory.analyze(t)
        self.assertEqual(r['tables']['재고평가요약'][0]['계산재고순액'],0)
        self.assertIn('INV_NEGATIVE_NRV',[x['code'] for x in r['issues']])
    def test_half_won_rounding(self):
        t=self.base();t['재고명세'][0].update(기말수량='.5',원가단가=1)
        # Input grammar deliberately requires a leading zero.
        with self.assertRaises(AuditError):inventory.analyze(t)
        t['재고명세'][0]['기말수량']='0.5';r=inventory.analyze(t)
        self.assertEqual(r['tables']['재고평가요약'][0]['계산원가'],1)
    def test_tolerance_never_waives_quantity(self):
        t=self.base();next(x for x in t['설정'] if x['항목']=='허용오차')['값']='1000';t['재고원장'][0]['기말수량']=9
        self.assertIn('INV_QTY_UNIT',[x['code'] for x in inventory.analyze(t)['issues']])

class PayrollTests(unittest.TestCase):
    def base(self):return source('급여_01_정상')
    def test_midmonth_proration_and_dc(self):
        r=payroll.analyze(self.base());rows=r['tables']['월별급여계산'];self.assertEqual(rows[1]['재직일수'],16);self.assertEqual(rows[1]['계산기본급'],1500000);self.assertEqual(rows[0]['계산시간외'],150000)
        self.assertEqual(r['metrics']['당기DC비용'],500000)
    def test_after_cutoff_receipts_do_not_reduce_liability(self):
        r=payroll.analyze(self.base());self.assertEqual(r['metrics']['기말미지급급여'],1500000);self.assertEqual(r['metrics']['기말DC미지급'],200000)
        row=r['tables']['급여요약'][1];self.assertEqual(row['후속급여지급'],1350000);self.assertEqual(row['기말미지급급여'],1350000)
    def test_leave_is_additional_expected_cost_not_all_entitlement(self):
        r=payroll.analyze(self.base());self.assertEqual(r['tables']['연차계산'][1]['계산연차부채'],75000)
        self.assertEqual(r['metrics']['기말연차부채'],675000);self.assertEqual(r['metrics']['당기연차비용'],375000)
    def test_signed_leave_reversal(self):
        r=payroll.analyze(source('급여_17_연차환입'));self.assertEqual(r['metrics']['당기연차비용'],-225000)
    def test_expense_plus_allocated_equals_gross(self):
        r=payroll.analyze(source('급여_18_자산배부'));m=r['metrics'];self.assertEqual(m['당기급여비용']+m['당기급여배부원가'],5000000);self.assertEqual(m['당기DC비용']+m['당기DC배부원가'],500000)
    def test_leap_february_proration(self):
        t=self.base()
        for x in t['설정']:
            if x['항목'] in ('시작일','기준일','정산기한'):x['값']={'시작일':'2024-02-01','기준일':'2024-02-29','정산기한':'2025-02-28'}[x['항목']]
        t['인사명부'][0]['입사일']='2024-02-01';t['인사명부'][1]['입사일']='2024-02-16'
        for x in t['급여명세']:x['귀속월']='2024-02'
        for x in t['연차명세']:x['정산예정일']='2025-02-28'
        t['급여지급']=[];r=payroll.analyze(t);row=r['tables']['월별급여계산'][1]
        self.assertEqual(row['재직일수'],14);self.assertEqual(row['계산기본급'],1389655)
    def test_no_plan_requires_zero_contribution(self):
        t=self.base();t['인사명부'][0]['퇴직제도']='없음'
        with self.assertRaisesRegex(AuditError,'0 필수'):payroll.analyze(t)
    def test_shared_salary_account_requires_review(self):
        t=self.base();t['인사명부'][1]['급여계좌']='FAKE-SALARY-E01';t['급여지급'][1]['수취계좌']='FAKE-SALARY-E01'
        self.assertIn('PAY_SHARED_ACCOUNT',[x['code'] for x in payroll.analyze(t)['issues']])
    def test_missing_roster_rows_detected_by_independent_ids(self):
        t=self.base();t['인사명부'][1]['사번']='E99';t['연차명세'][1]['사번']='E99';t['급여잔액'][1]['사번']='E99';t['급여명세'][1]['사번']='E99'
        for x in t['급여지급']:
            if x['사번']=='E02':x['사번']='E99'
        r=payroll.analyze(t);self.assertGreater(r['blocking'],0)
    def test_dc_deadline_long_term_rejected(self):
        t=self.base();next(x for x in t['설정'] if x['항목']=='정산기한')['값']='2028-12-31'
        with self.assertRaisesRegex(AuditError,'365일'):payroll.analyze(t)

class V12WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ws=Workspace(Path(self.tmp.name)/'업무',create={'회사명':'SYNTHETIC ONLY','회사코드':'SYNTH01','시작일':'2026-01-01','기준일':'2026-12-31','작성자':'합성작성자','회계체계':'K-IFRS 예시','감사기준':'합성 검증','더미업무':True})
    def seed(self):
        for mod,name in [('원장·리드','통합업무_v1.2_원장정상'),('재고평가','재고평가_01_정상'),('종업원급여','급여_01_정상')]:self.ws.execute(mod,ROOT/'samples/통합'/(name+'.xlsx'))
    def test_tb_all_thirteen_new_metric_links(self):
        self.seed();rows=[x for x in self.ws.cross_checks() if x['모듈'] in ('재고평가','종업원급여')];self.assertEqual(len(rows),13);self.assertEqual({x['상태'] for x in rows},{'일치'})
        self.assertTrue({'A11','A16'}<=self.ws.required_procedures());self.assertIn('1490',next(x for x in rows if x['지표']=='기말재고순액')['사유'])
    def test_new_calculation_changes_prior_review(self):
        self.seed();self.ws.save_procedure(synthetic_procedure('A11',list(self.ws.sources)));self.ws.request_review('A11');self.ws.review('A11','합성검토자','SYNTHETIC ONLY')
        self.ws.execute('재고평가',ROOT/'samples/통합/재고평가_02_NRV원가초과.xlsx');self.assertEqual(self.ws.procedure_state(self.ws.procedures['A11']),'자료변경·재검토')
        self.assertTrue(any(x['상태']=='차이' for x in self.ws.cross_checks() if x['모듈']=='재고평가'))
    def test_unrelated_evidence_does_not_satisfy_payroll_workpaper(self):
        self.seed();self.ws.save_procedure(synthetic_procedure('A16',[self.ws.latest()['종업원급여']['source_id']]))
        with self.assertRaisesRegex(AuditError,'모두 연결'):self.ws.request_review('A16')
    def test_failed_latest_blocks_reviewed_export(self):
        self.seed();self.ws.execute('종업원급여',ROOT/'samples/통합/급여_06_DB모형.xlsx');self.assertGreater(self.ws.calculation_refs('A16')['차단'],0)
        with self.assertRaises(AuditError):self.ws.snapshot(True)
    def test_company_mismatch_blocks(self):
        self.ws.engagement['회사코드']='NOT-SYNTH'
        r=adapters.run('종업원급여',ROOT/'samples/통합/급여_01_정상.xlsx',{'회사코드':'NOT-SYNTH','시작일':'2026-01-01','기준일':'2026-12-31'})
        self.assertIn('ENGAGEMENT_SCOPE',[x['code'] for x in r['issues']])

class V12Fixtures(unittest.TestCase):pass
for b in SPEC['books']:
    if b['expected'].get('template'):continue
    def make(book):
        def test(self):
            p=ROOT/'samples/통합'/(book['name']+'.xlsx');before=sha(p)
            if 'input_error' in book['expected']:
                with self.assertRaisesRegex(AuditError,re.escape(book['expected']['input_error'])):adapters.run(book['module'],p,SPEC['context'])
            else:check_book(book,p,SPEC['context'])
            self.assertEqual(sha(p),before)
        return test
    setattr(V12Fixtures,'test_'+b['name'],make(b))
