from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import json
from copy import deepcopy
import runtime
runtime.configure()
import adapters,review_support,exporter
from workspace import Workspace
from common import AuditError
from app import ANALYTIC_DEMO_FILES,CATALOG
ROOT=Path(__file__).resolve().parent
C={'회사코드':'SYNTH01','회사명':'합성','시작일':'2026-01-01','기준일':'2026-12-31','회계체계':'합성','감사기준':'합성','작성자':'합성작성자','더미업무':True}
class AnalyticsIntegrationTests(TestCase):
    def setUp(self):self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ws=Workspace(Path(self.tmp.name)/'업무',create=C)
    def normal(self):
        for module,name in ANALYTIC_DEMO_FILES:self.ws.execute(module,ROOT/'samples/통합'/name)
    def test_fifteen_modules_35_connections_and_strict_human_draft(self):
        self.normal();self.assertEqual(len(self.ws.latest()),15);self.assertEqual(len(self.ws.cross_checks()),35)
        self.assertTrue(all(r['상태']=='일치' for r in self.ws.cross_checks()));self.assertTrue({'G01','I01','H01'}<=self.ws.required_procedures())
        for module in ('GLA','FIA','현금분석'):
            r=self.ws.latest()[module]['result'];self.assertEqual(r['blocking'],0,r['issues']);self.assertTrue(r['detail']['현재원장연결']);self.assertEqual(len(r['tables']['현재원장연결']),141)
        with self.assertRaises(AuditError):self.ws.snapshot(True)
    def test_missing_actual_ledger_blocks_each_analyzer(self):
        for m in ('GLA','FIA','현금분석'):
            r=adapters.run(m,ROOT/'samples/통합'/('통합_v1.5_'+m+'.xlsx'),{k:C[k] for k in ('회사코드','시작일','기준일')})
            self.assertGreater(r['blocking'],0);self.assertFalse(r['detail']['현재원장연결'])
    def test_cross_window_rerun_invalidates_candidates_and_request(self):
        self.ws.execute('원장·리드',ROOT/'samples/통합/통합_v1.3_원장_리드.xlsx');self.ws.execute('GLA',ROOT/'samples/통합/통합_v1.5_GLA.xlsx')
        row=self.ws.risk_register()[0];other=Workspace(self.ws.root);other.execute('원장·리드',ROOT/'samples/통합/통합_v1.3_원장_리드.xlsx')
        self.assertTrue(all(r['연결상태']=='차단·재실행 필요' for r in self.ws.risk_register()))
        with self.assertRaises(AuditError):self.ws.candidate_request_draft(row['후보키'])
    def test_request_draft_is_unsaved_and_evidence_pinned(self):
        self.normal();r=self.ws.risk_register()[0];d=self.ws.candidate_request_draft(r['후보키'])
        self.assertEqual(self.ws.requests,{});self.assertFalse(d['requested_from']);self.assertEqual(d['source_ids'],[r['자료ID']])
        saved=self.ws.save_request({**d,'requested_from':'합성 담당'});self.assertEqual(self.ws.requests[saved['id']]['state'],'요청')
    def test_context_preserves_originals_and_accurately_labels_analytics(self):
        self.normal();p=Path(self.tmp.name)/'review.json';review_support.save_context(self.ws,p);data=json.loads(p.read_text(encoding='utf-8'))
        self.assertFalse(data['uses_ai_inference']);self.assertTrue(data['candidates'])
        source=self.ws.sources[self.ws.latest()['재무제표·주석']['source_id']];original=Path(source['original']);before=original.read_bytes()
        for target in (self.ws.anchor,self.ws.root/source['file'],original):
            with self.assertRaises(AuditError):review_support.save_context(self.ws,target)
        self.assertEqual(original.read_bytes(),before)
    def test_stale_analysis_cannot_be_resaved_and_reviewed(self):
        self.normal();self.ws.execute('원장·리드',ROOT/'samples/통합/통합_v1.3_원장_리드.xlsx')
        for pid,module in [('G01','GLA'),('I01','FIA'),('H01','현금분석')]:
            self.ws.save_procedure({'id':pid,'title':module,'preparer':'가상작성자','purpose':'합성','risk':'합성','scope':'합성','performed':'합성 상태검사','conclusion':'합성 상태검사','performed_date':'2026-12-31','evidence_ids':[self.ws.latest()[module]['source_id'],self.ws.latest()['원장·리드']['source_id']]})
            with self.assertRaises(AuditError):self.ws.request_review(pid)
    def test_modified_source_prevents_context_and_new_analysis(self):
        self.normal();r=self.ws.risk_register()[0];source=self.ws.sources[r['자료ID']];(self.ws.root/source['file']).write_bytes(b'changed')
        with self.assertRaises(AuditError):self.ws.candidate_request_draft(r['후보키'])
        with self.assertRaises(AuditError):review_support.save_context(self.ws,Path(self.tmp.name)/'bad.json')
        with self.assertRaises(AuditError):self.ws.execute('FIA',ROOT/'samples/통합/통합_v1.5_FIA.xlsx')
