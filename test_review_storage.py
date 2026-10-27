"""Human-write text safety and narrow legacy ERP input compatibility."""
from pathlib import Path
import tempfile
import unittest
from openpyxl import load_workbook
from common import AuditError,digest
from workspace import Workspace
from verify import synthetic_procedure
from onboarding.demo import CONTEXT
from onboarding.erp import sample,analyze,prepare_ledger
from onboarding.workbook_schema import descriptors
from onboarding.workbooks import load_input,save_input,META

ENGAGEMENT={**CONTEXT,'회사명':'SYNTHETIC ONLY','회계체계':'K-IFRS',
    '감사기준':'합성 검증','작성자':'SYNTHETIC ONLY 가상작성자','더미업무':True}


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_forbidden_controls_are_rejected_before_any_human_event(self):
        ws=Workspace(self.root/'업무',create=ENGAGEMENT);head=ws.head
        for cp in (1,11,12,31,0xD800,0xFFFE):
            bad='첫줄\n둘'+chr(cp)+'끝'
            p=synthetic_procedure('A04',[]);p['conclusion']=bad
            entry={'title':'자료요청','requested_from':'가상회사','note':bad,
                   'due_date':'2026-10-29','state':'요청','source_ids':[]}
            for call in (lambda:ws.save_procedure(p),lambda:ws.add_note('검토',bad,'가상인'),
                         lambda:ws.save_request(entry)):
                with self.subTest(code=cp,call=call):
                    with self.assertRaisesRegex(AuditError,'U\\+[0-9A-F]{4}'):call()
                    self.assertEqual(ws.refresh().head,head)

    def test_legal_hangul_and_whitespace_survive_new_save_and_reopen(self):
        ws=Workspace(self.root/'업무',create=ENGAGEMENT)
        body='검토\t받침 수정\n가상확인\r\n재검토'
        nid=ws.add_note('가상검토',body,'SYNTHETIC ONLY')
        self.assertEqual(Workspace(ws.root).notes[nid]['body'],body)

    def test_controls_at_edges_are_rejected_before_strip_can_erase_them(self):
        ws=Workspace(self.root/'업무',create=ENGAGEMENT);head=ws.head
        for cp in (11,12,28,31):
            for body in ('BODY'+chr(cp),chr(cp)+'BODY'):
                with self.subTest(code=cp,body=repr(body)):
                    with self.assertRaisesRegex(AuditError,f'U\\+{cp:04X}'):
                        ws.add_note('가상 검토',body,'SYNTHETIC ONLY')
                    with self.assertRaisesRegex(AuditError,f'U\\+{cp:04X}'):
                        ws.save_procedure({**synthetic_procedure('A04',[]),'preparer':body})
                    with self.assertRaisesRegex(AuditError,f'U\\+{cp:04X}'):
                        ws.save_request({'title':body,'requested_from':'합성회사','note':'합성요청',
                            'due_date':'2026-10-29','state':'요청','source_ids':[]})
                    self.assertEqual(ws.refresh().head,head)

    def test_bad_new_engagement_does_not_create_partial_database(self):
        target=self.root/'실패업무'
        with self.assertRaises(AuditError):Workspace(target,create={**ENGAGEMENT,'회사명':'잘못\x01회사'})
        self.assertFalse(target.exists())

    def test_legacy_erp_without_company_mapping_is_readable_but_never_assumed(self):
        payload=sample(CONTEXT)
        payload.pop('company_mapping');payload['column_mapping']=[r for r in payload['column_mapping'] if r['target']!='company_id']
        for row in payload['source_rows']:row.pop('회사코드',None)
        path=self.root/'구형입력.xlsx';save_input('실무자료·원장',payload,path)
        restored=load_input('실무자료·원장',path,CONTEXT)
        self.assertEqual(restored['company_mapping'],[]);self.assertEqual(restored['approval'],{})
        # Mapping is unconfirmed, even if an old workbook carried current context.
        r=analyze(restored,CONTEXT,None)
        self.assertIn('ERP_COMPANY_UNVERIFIED',{i['code'] for i in r['issues']})
        self.assertFalse(r['detail']['현재원장연결'])
        with self.assertRaises(AuditError):prepare_ledger(restored,CONTEXT)

    def test_partial_missing_company_sheet_stays_a_structural_error(self):
        payload=sample(CONTEXT);path=self.root/'부분누락.xlsx';save_input('실무자료·원장',payload,path)
        sheet=next(d['sheet'] for d in descriptors('실무자료·원장',payload) if d['key']=='company_mapping')
        book=load_workbook(path);del book[sheet];book.save(path);book.close()
        with self.assertRaises(AuditError):load_input('실무자료·원장',path,CONTEXT)


if __name__=='__main__':unittest.main()
