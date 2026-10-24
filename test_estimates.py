"""Independent values, input rejection, estimate-to-GL and workpaper regression tests."""
from pathlib import Path
from copy import deepcopy
import json,tempfile,unittest
from datetime import date
from decimal import Decimal
import runtime
ROOT=runtime.configure()
import leases,ecl,adapters,ledger,exporter
from workspace import Workspace
from common import *
from verify import check_book,synthetic_procedure
SPEC=json.loads((ROOT/'new_specs.json').read_text(encoding='utf-8'))

def tables(index):
    b=SPEC['books'][index]
    return {k:[dict(zip(b['headers'][k],row))|{'_row':i+2,'_sheet':k} for i,row in enumerate(rows)] for k,rows in b['tables'].items()}
def lease_contract(**kw):return tables(0)['리스계약'][0]|kw
class LeaseTests(unittest.TestCase):
    def test_closed_form_reference(self):
        initial,rows=leases.schedule(lease_contract())
        self.assertEqual(initial['최초리스부채'],212434);self.assertEqual(rows[11]['기말부채'],112551)
        self.assertEqual(sum(r['이자비용'] for r in rows),27566)
        self.assertEqual(rows[-1]['기말부채'],0);self.assertEqual(rows[-1]['기말사용권'],0)
    def test_zero_rate_advance_single_payment(self):
        initial,rows=leases.schedule(lease_contract(개월수=1,내용월수=1,할인율=0,지급시점='월초선급'))
        self.assertEqual(initial['최초리스부채'],0);self.assertEqual(initial['최초사용권자산'],10000)
        self.assertEqual(rows[0]['현금지급'],0);self.assertEqual(rows[0]['이자비용'],0)
    def test_annual_effective_conversion(self):
        # (1.01 ** 12)-1 exactly expressed, without float conversion.
        _,monthly=leases.schedule(lease_contract())
        _,annual=leases.schedule(lease_contract(할인율종류='연유효',할인율=str(Decimal('1.01')**12-1)))
        self.assertEqual([(r['기말부채'],r['이자비용']) for r in monthly],[(r['기말부채'],r['이자비용']) for r in annual])
    def test_every_month_rolls_and_cash_sum(self):
        for advance in ('월말후급','월초선급'):
            init,rows=leases.schedule(lease_contract(지급시점=advance,월지급액=13,개월수=61,내용월수=48,선급금=3))
            for row in rows:
                self.assertEqual(row['기초부채']+row['이자비용']-row['현금지급'],row['기말부채'])
                self.assertEqual(row['기초사용권']-row['상각비'],row['기말사용권'])
            self.assertEqual(sum(r['상각비'] for r in rows),init['최초사용권자산'])
            self.assertEqual(init['개시일선급지급']+sum(r['현금지급'] for r in rows),61*13)
    def test_opening_carry_and_partial_year(self):
        t=tables(0);next(r for r in t['설정'] if r['항목']=='시작일')['값']='2026-07-01'
        r=leases.analyze(t);s=r['tables']['리스요약'][0]
        self.assertEqual(s['당기신규부채'],0);self.assertGreater(s['기초리스부채'],0)
        self.assertEqual(s['기초리스부채']+s['당기리스이자']-s['당기현금지급'],s['기말리스부채'])
    def test_prior_expired_contract_is_zero(self):
        t=tables(0);t['리스계약'][0]['개시일']='2023-01-01'
        r=leases.analyze(t);self.assertEqual(set(r['metrics'].values()),{0})
    def test_missing_zero_is_rejected(self):
        for field in ('선급금','할인율','월지급액'):
            with self.subTest(field=field),self.assertRaises(AuditError):leases.schedule(lease_contract(**{field:None}))
    def test_period_monthend_guard(self):
        t=tables(0);next(r for r in t['설정'] if r['항목']=='기준일')['값']='2026-12-30'
        with self.assertRaisesRegex(AuditError,'월말'):leases.analyze(t)
    def test_independent_control_missing(self):
        t=tables(0);t['독립통제'].pop()
        with self.assertRaisesRegex(AuditError,'필수 지표'):leases.analyze(t)
    def test_long_high_rate_stays_stable(self):
        init,rows=leases.schedule(lease_contract(할인율=1,개월수=600,내용월수=600))
        self.assertEqual(rows[-1]['기말부채'],0)
        self.assertEqual(init['최초리스부채']+sum(r['이자비용']-r['현금지급'] for r in rows),0)
    def test_tolerance_cannot_waive_population(self):
        t=tables(0);t['리스계약'][0]['월지급액']+=1;next(r for r in t['설정'] if r['항목']=='허용오차')['값']='1000'
        self.assertGreater(leases.analyze(t)['blocking'],0)

class ECLTests(unittest.TestCase):
    def base(self):return tables(16)
    def test_weighting_and_individual_exclusion(self):
        r=ecl.analyze(self.base());d=r['tables']['채권별ECL']
        self.assertEqual([x['계산충당금'] for x in d],[5200,5000]);self.assertEqual(d[0]['가중손실률'],'0.052')
    def test_maturity_boundaries(self):
        from datetime import timedelta
        for days,loss in [(0,1300),(30,1300),(31,5200),(90,5200),(91,26000)]:
            t=self.base();t['채권'][0]['만기일']=(date(2026,12,31)-timedelta(days=days)).isoformat()
            self.assertEqual(ecl.analyze(t)['tables']['채권별ECL'][0]['계산충당금'],loss)
    def test_round_per_receivable_and_zero_amount(self):
        t=self.base();t['채권'][0]['채권잔액']=0;t['채권'][1]['채권잔액']=1
        r=ecl.analyze(t);self.assertEqual(r['metrics']['기말대손충당금'],1)
    def test_no_allowance_exceeds_exposure(self):
        t=self.base();t['채권'][1]['개별손실률']='1'
        r=ecl.analyze(t)
        for x in r['tables']['채권별ECL']:self.assertTrue(0<=x['계산충당금']<=x['채권잔액'])
    def test_nonexpense_movements_are_not_expense(self):
        r=ecl.analyze(self.base());s=r['tables']['충당금요약'][0]
        self.assertEqual(s['기초충당금']+s['비용외증감']+s['당기대손상각비'],10200)
        t=self.base();t['충당금변동'].clear();t['독립통제']=[x for x in t['독립통제']]
        r=ecl.analyze(t);self.assertIn('ECL_MOVEMENT',[x['code'] for x in r['issues']])
    def test_identity_control_not_only_total(self):
        t=self.base();t['채권'][0]['채권ID']='AR_NEW'
        r=ecl.analyze(t);self.assertGreater(r['blocking'],0)
    def test_unsupported_framework_and_naive_time(self):
        t=self.base();next(x for x in t['설정'] if x['항목']=='모형')['값']='은행3단계'
        with self.assertRaisesRegex(AuditError,'미지원'):ecl.analyze(t)
        t=self.base();t['독립통제'][0]['추출일시']='2027-01-01T00:00:00'
        with self.assertRaisesRegex(AuditError,'시간대'):ecl.analyze(t)

class EstimateWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ws=Workspace(Path(self.tmp.name)/'업무',create={'회사명':'SYNTHETIC ONLY','회사코드':'SYNTH01','시작일':'2026-01-01','기준일':'2026-12-31','작성자':'합성작성자','회계체계':'K-IFRS 예시','감사기준':'합성 검증','더미업무':True})
    def seed(self):
        for mod,name in [('원장·리드','통합업무_v1.1_원장정상'),('리스','리스_01_정상'),('대손충당금','대손_01_정상')]:self.ws.execute(mod,ROOT/'samples/통합'/(name+'.xlsx'))
    def test_tb_signs_and_multiaccount_binding(self):
        self.seed();rows=[r for r in self.ws.cross_checks() if r['모듈'] in ('리스','대손충당금')]
        self.assertEqual(len(rows),7);self.assertEqual({r['상태'] for r in rows},{'일치'})
        self.assertIn('2210',next(r for r in rows if r['지표']=='기말리스부채')['사유'])
        self.assertTrue({'A15','A07'}<=self.ws.required_procedures())
    def test_failed_latest_cannot_reuse_old_calculation(self):
        self.seed();self.ws.execute('리스',ROOT/'samples/통합/리스_07_원장누락.xlsx')
        self.assertGreater(self.ws.latest()['리스']['result']['blocking'],0)
        self.assertGreater(self.ws.calculation_refs('A15')['차단'],0)
        with self.assertRaises(AuditError):self.ws.snapshot(True)
    def test_estimate_recalculation_invalidates_review(self):
        self.seed();p=synthetic_procedure('A15',list(self.ws.sources));self.ws.save_procedure(p);self.ws.request_review('A15');self.ws.review('A15','합성검토자','SYNTHETIC ONLY')
        self.ws.execute('리스',ROOT/'samples/통합/리스_03_선급.xlsx')
        self.assertEqual(self.ws.procedure_state(self.ws.procedures['A15']),'자료변경·재검토')
        self.assertTrue(any(r['상태']=='차이' for r in self.ws.cross_checks() if r['모듈']=='리스'))
    def test_new_workpapers_mandatory(self):
        self.seed()
        for pid in self.ws.required_procedures()-{'A15'}:
            self.ws.save_procedure(synthetic_procedure(pid,list(self.ws.sources)));self.ws.request_review(pid);self.ws.review(pid,'합성검토자','SYNTHETIC ONLY')
        with self.assertRaises(AuditError):self.ws.snapshot(True)
    def test_unrelated_evidence_cannot_review_estimate(self):
        self.seed();p=synthetic_procedure('A15',[self.ws.latest()['리스']['source_id']]);self.ws.save_procedure(p)
        with self.assertRaisesRegex(AuditError,'모두 연결'):self.ws.request_review('A15')
    def test_independent_id_csv_order_invariant_and_duplicate(self):
        from estimate_controls import independent_ids
        p=Path(self.tmp.name)/'독립.csv';p.write_text('채권ID\nAR02\nAR01\n',encoding='utf-8-sig')
        self.assertEqual(independent_ids(p,'채권ID'),{'행수':2,'ID해시':digest(['AR01','AR02'])})
        p.write_text('채권ID\nAR01\nAR01\n',encoding='utf-8-sig')
        with self.assertRaisesRegex(AuditError,'중복'):independent_ids(p,'채권ID')
    def test_v10_workspaces_still_open(self):
        # Schema stays audit-suite-1; v1.0 modules retain their original expectations.
        self.ws.execute('원장·리드',ROOT/'samples/통합/통합_01_원장정상.xlsx')
        reopened=Workspace(self.ws.root);self.assertEqual(reopened.latest()['원장·리드']['result']['blocking'],0)
        self.assertNotIn('A15',reopened.required_procedures())

class EstimateFixtureTests(unittest.TestCase):pass
for b in SPEC['books']:
    if b['expected'].get('template'):continue
    def make(book):
        def test(self):
            path=ROOT/'samples/통합'/(book['name']+'.xlsx');before=sha(path)
            if 'input_error' in book['expected']:
                with self.assertRaisesRegex(AuditError,re.escape(book['expected']['input_error'])):adapters.run(book['module'],path,SPEC['context'])
            else:check_book(book,path,SPEC['context'])
            self.assertEqual(sha(path),before)
        return test
    setattr(EstimateFixtureTests,'test_'+b['name'],make(b))
