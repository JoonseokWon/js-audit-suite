from pathlib import Path
import copy,json,tempfile,unittest
from account_cases import analyze
from common import AuditError
from workspace import Workspace
ROOT=Path(__file__).resolve().parent
CONTEXT={'회사코드':'SYNTH01','시작일':'2026-01-01','기준일':'2026-12-31'}

class AccountCaseTests(unittest.TestCase):
    def test_all_33_fixed_cases_300_expectations(self):
        cases=json.loads((ROOT/'worker_cases.json').read_text(encoding='utf-8'));count=0
        self.assertEqual(len(cases),33)
        for c in cases:
            with self.subTest(case=c['case_id']):
                out=analyze(ROOT/c['file'],CONTEXT)
                actual={r['검사ID']:r for r in out['tables']['계정별검사']}
                self.assertEqual(len(actual),len(c['expected']))
                for e in c['expected']:
                    got=actual[e['check_id']]
                    for a,b in [('상태','status'),('기대','expected_value'),('실제','actual_value'),('차이','difference')]:self.assertEqual(got[a],e[b],(c['case_id'],a))
                    count+=1
                self.assertFalse(out['detail']['현재원장연결'])
        self.assertEqual(count,300)
    def test_runtime_never_trusts_expected_results(self):
        original=ROOT/'samples/계정별증빙/cash_finance_CASH-01.json';data=json.loads(original.read_text(encoding='utf-8'))
        original_rows=analyze(original,CONTEXT)['tables']['계정별검사']
        data['case']['expected']=[{'status':'INPUT_BLOCKED','actual_value':9999999}]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'case.json';p.write_text(json.dumps(data),encoding='utf-8')
            self.assertEqual(analyze(p,CONTEXT)['tables']['계정별검사'],original_rows)
            next(x for x in data['case']['documents'] if x['document_type']=='bank_statement')['fields']['closing_balance']+=1
            p.write_text(json.dumps(data),encoding='utf-8');self.assertGreater(analyze(p,CONTEXT)['review'],0)
    def test_stored_trace_workpaper_draft_no_fake_tb(self):
        original=ROOT/'samples/계정별증빙/cash_finance_CASH-01.json'
        with tempfile.TemporaryDirectory() as d:
            ws=Workspace(Path(d)/'engagement',create={**CONTEXT,'회사명':'합성','회계체계':'K-IFRS','감사기준':'학습용','작성자':'합성작성자','더미업무':True})
            run=ws.execute('계정별증빙연습',original)
            self.assertEqual(run['result']['blocking'],0)
            self.assertIn('W01',ws.required_procedures())
            self.assertEqual(ws.cross_checks()[0]['상태'],'미확인')
            self.assertIsNone(run['result']['detail']['결론'])
            with self.assertRaises(AuditError):ws.snapshot(final=True)
            ws.save_procedure({'id':'W01','title':'연습 원천 검토','preparer':'합성작성자','evidence_ids':[run['source_id']]})
            self.assertEqual(ws.procedure_state(ws.procedures['W01']),'작성중')
    def test_duplicate_document_and_company_guard(self):
        c=json.loads((ROOT/'samples/계정별증빙/cash_finance_CASH-01.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'case.json';c['case']['documents'].append(copy.deepcopy(c['case']['documents'][0]));p.write_text(json.dumps(c),encoding='utf-8')
            with self.assertRaises(AuditError):analyze(p,CONTEXT)
            c['case']['documents'].pop();p.write_text(json.dumps(c),encoding='utf-8')
            with self.assertRaises(AuditError):analyze(p,{**CONTEXT,'회사코드':'OTHER'})
