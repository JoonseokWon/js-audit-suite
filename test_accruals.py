from pathlib import Path
from datetime import date
from copy import deepcopy
import json,tempfile,unittest
import runtime
ROOT=runtime.configure()
import accruals,adapters,exporter
from common import *
from workspace import Workspace
from verify import check_book,synthetic_procedure
SPEC=json.loads((ROOT/'v13_specs.json').read_text(encoding='utf-8'))
def source(name='비용이연_01_정상'):
    b=next(b for b in SPEC['books'] if b['name']==name)
    return {k:[dict(zip(b['headers'][k],r))|{'_row':i+2,'_sheet':k} for i,r in enumerate(rows)] for k,rows in b['tables'].items()}
class AllocationTests(unittest.TestCase):
    def test_actual_previous_raw_data(self):
        r=accruals.analyze(source());self.assertEqual(r['metrics'],{'기말미지급비용':9000,'당기발생비용':9000,'기말선급비용':100000,'당기선급상각':20000});self.assertEqual(r['issues'],[])
    def test_leap_day_and_inclusive_boundaries(self):
        a,b=date(2024,2,1),date(2024,2,29)
        self.assertEqual(accruals.earned(2900,a,b,'일할',date(2024,1,31)),0)
        self.assertEqual(accruals.earned(2900,a,b,'일할',date(2024,2,1)),100)
        self.assertEqual(accruals.earned(2900,a,b,'일할',date(2024,2,29)),2900)
    def test_cumulative_rounding_has_no_opening_drift(self):
        a,b=date(2025,12,31),date(2026,1,2)
        opening=accruals.earned(100,a,b,'일할',date(2025,12,31));closing=accruals.earned(100,a,b,'일할',date(2026,1,2))
        self.assertEqual((opening,closing-opening,closing),(33,67,100))
    def test_one_day_and_half_won(self):
        self.assertEqual(accruals.earned(1,date(2026,12,31),date(2026,12,31),'일할',date(2026,12,31)),1)
        self.assertEqual(accruals.earned(1,date(2026,12,31),date(2027,1,1),'일할',date(2026,12,31)),1)
    def test_future_month_zero(self):self.assertEqual(accruals.earned(100,date(2027,1,1),date(2027,1,31),'월할',date(2026,12,31)),0)
    def test_partial_month_is_explicitly_rejected(self):
        with self.assertRaises(AuditError):accruals.period('2026-11-02','2027-10-31','월할')
    def test_subsequent_payment_not_deducted_at_yearend(self):
        r=accruals.analyze(source());self.assertEqual(r['metrics']['기말미지급비용'],9000);self.assertEqual(r['tables']['비용기간배분'][0]['후속지급'],9000)
    def test_unrecorded_liability_proposal_is_draft_only(self):
        r=accruals.analyze(source('비용이연_02_미기록부채'));p=r['tables']['수정분개검토'][0]
        self.assertEqual((p['차변계정'],p['대변계정'],p['금액'],p['상태']),('5701','2410',9000,'검토 초안'))
    def test_over_amortization_reverses_expense(self):
        p=accruals.analyze(source('비용이연_03_선급전액비용'))['tables']['수정분개검토'][0]
        self.assertEqual((p['차변계정'],p['대변계정'],p['금액']),('1450','5720',100000))
    def test_opening_difference_never_gets_blind_current_year_je(self):
        t=source();t['비용원장'][0].update(기초부채=1000,기말부채=10000)
        p=accruals.analyze(t)['tables']['수정분개검토'][0];self.assertIsNone(p['금액']);self.assertEqual(p['차변계정'],'')
    def test_equal_and_opposite_item_errors_do_not_disappear(self):
        r=accruals.analyze(source('비용이연_13_상계되는개별오류'));rows=r['tables']['비용원장대사']
        self.assertEqual(sum(x['차이'] for x in rows if x['지표']=='기말부채'),0);self.assertEqual(sum(x['지표']=='기말부채' and x['차이']!=0 for x in rows),2)
    def test_tolerance_does_not_erase_difference(self):
        r=accruals.analyze(source('비용이연_04_허용차이도검토'));self.assertTrue(any(x['상태']=='허용범위내차이' for x in r['tables']['비용원장대사']));self.assertTrue(r['issues'])
    def test_unknown_sources_cannot_auto_pass(self):
        self.assertIn('ACC_UNMATCHED_INVOICE',[x['code'] for x in accruals.analyze(source('비용이연_11_미연결송장'))['issues']])
        self.assertIn('ACC_UNMATCHED_PAYMENT',[x['code'] for x in accruals.analyze(source('비용이연_12_미연결후속지급'))['issues']])
    def test_prepaid_day_method_differs_from_approved_monthly_policy(self):
        t=source();t['용역계약'][1]['배분방법']='일할';r=accruals.analyze(t)
        self.assertEqual(r['metrics']['당기선급상각'],20055);self.assertEqual(r['metrics']['기말선급비용'],99945)
    def test_monthly_policy_full_12_months(self):self.assertEqual(accruals.earned(120000,date(2026,1,1),date(2026,12,31),'월할',date(2026,12,31)),120000)
    def test_unsupported_monthly_reporting_boundary(self):
        t=source();next(r for r in t['설정'] if r['항목']=='기준일')['값']='2026-12-30'
        with self.assertRaisesRegex(AuditError,'월초~월말'):accruals.analyze(t)
    def test_cancelled_calculation(self):
        import threading
        event=threading.Event();event.set()
        with self.assertRaises(AuditError):accruals.analyze(source(),event)

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.ws=Workspace(Path(self.temp.name)/'업무',create={'회사코드':'SYNTH01','회사명':'SYNTHETIC ONLY','시작일':'2026-01-01','기준일':'2026-12-31','회계체계':'합성','감사기준':'합성','작성자':'합성작성자','더미업무':True})
        self.ws.execute('원장·리드',ROOT/'samples/통합/통합_v1.3_원장_리드.xlsx');self.ws.execute(accruals.MODULE,ROOT/'samples/통합/비용이연_01_정상.xlsx')
    def test_tb_and_required_procedures(self):
        rows=[x for x in self.ws.cross_checks() if x['모듈']==accruals.MODULE];self.assertEqual(len(rows),4);self.assertTrue(all(x['상태']=='일치' for x in rows));self.assertTrue({'A08','A09'}<=self.ws.required_procedures())
    def test_both_workpapers_link_calculation_and_tb(self):
        for p in ('A08','A09'):self.assertEqual(len(self.ws.calculation_refs(p)['원장대사']),4)
    def test_review_requires_both_calculation_and_ledger_sources(self):
        latest=self.ws.latest();p=synthetic_procedure('A09',[latest[accruals.MODULE]['source_id']]);self.ws.save_procedure(p)
        with self.assertRaisesRegex(AuditError,'독립 원장'):self.ws.request_review('A09')
    def test_new_input_invalidates_review(self):
        self.ws.save_procedure(synthetic_procedure('A09',list(self.ws.sources)));self.ws.request_review('A09');self.ws.review('A09','합성검토자','SYNTHETIC ONLY')
        self.ws.execute(accruals.MODULE,ROOT/'samples/통합/비용이연_02_미기록부채.xlsx');self.assertEqual(self.ws.procedure_state(self.ws.procedures['A09']),'자료변경·재검토');self.assertTrue(any(p.startswith('X-') for p in self.ws.required_procedures()))
    def test_draft_proposals_never_post_to_general_ledger(self):
        before=self.ws.latest()['원장·리드']['result_hash'];self.ws.execute(accruals.MODULE,ROOT/'samples/통합/비용이연_02_미기록부채.xlsx');self.assertEqual(before,self.ws.latest()['원장·리드']['result_hash'])
    def test_misbound_scope_cannot_be_reviewed_as_complete(self):
        r=self.ws.latest()[accruals.MODULE];r=deepcopy(r);r['id']='scope-test';r['result']['detail']['대상계정']['당기발생비용']=['5700'];r['result_hash']=digest(r['result']);self.ws._append('run',r)
        self.assertIn('미확인',[x['상태'] for x in self.ws.cross_checks() if x['모듈']==accruals.MODULE])
        with self.assertRaises(AuditError):self.ws.snapshot(True)
    def test_readable_workpaper_has_calculations_and_links(self):
        self.ws.save_procedure(synthetic_procedure('A08',list(self.ws.sources)));self.ws.save_procedure(synthetic_procedure('A09',list(self.ws.sources)))
        path=Path(self.temp.name)/'조서.xlsx';cat=json.loads((ROOT/'procedure_catalog.json').read_text(encoding='utf-8'));exporter.export(self.ws,path,cat,False)
        import openpyxl
        w=openpyxl.load_workbook(path)
        try:
            for pid in ('A08','A09'):
                sh=w['조서_'+pid];self.assertTrue(any(str(row[0].value).startswith('계산값: ') for row in sh));self.assertTrue(any(row[1].hyperlink for row in sh))
        finally:w.close()

class FileCases(unittest.TestCase):pass
for b in SPEC['books']:
    if b['expected'].get('template'):continue
    def test(self,b=b):
        p=ROOT/'samples/통합'/(b['name']+'.xlsx');e=b['expected']
        if 'input_error' in e:
            with self.assertRaisesRegex(AuditError,e['input_error']):adapters.run(b['module'],p,SPEC['context'])
        else:check_book(b,p,SPEC['context'])
    setattr(FileCases,'test_'+b['name'],test)
if __name__=='__main__':unittest.main()
