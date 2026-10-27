"""ACC-01 independent company identity counterexamples; no real person approval."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from common import AuditError,digest
from onboarding.demo import CONTEXT,ledger_result
from onboarding.erp import sample,analyze,prepare_ledger
from onboarding.erp.schema import APPROVAL_FIELDS
from onboarding.erp.input_io import read_original,stage_original
from onboarding.confirmation import confirm_input
from openpyxl import Workbook


def confirm(payload):
    payload['approval']={'actor':'SYNTHETIC ONLY','reason':'가상 입력확인 상태전이·실제 승인 아님',
        'input_hash':digest({key:payload.get(key) for key in APPROVAL_FIELDS})}
    return payload


class ReviewCompanyTests(unittest.TestCase):
    def setUp(self):
        self.context=dict(CONTEXT);self.base=sample(self.context);self.current=ledger_result(self.context)

    def run_case(self,payload):return analyze(confirm(payload),self.context,self.current)

    def test_declared_company_column_and_mapping_match_with_original_trace(self):
        r=self.run_case(deepcopy(self.base))
        self.assertEqual(r['blocking'],0);self.assertTrue(r['detail']['회사식별확인'])
        self.assertTrue(r['detail']['현재원장연결'])
        row=r['tables']['원본부호변환'][0]
        self.assertEqual(row['원본회사코드'],self.context['회사코드'])
        self.assertEqual(row['매핑회사코드'],self.context['회사코드'])

    def test_other_company_is_not_relabelled_even_with_identical_amounts(self):
        p=deepcopy(self.base)
        for row in p['source_rows']:row['법인코드']='OTHER'
        r=self.run_case(p)
        self.assertIn('ERP_COMPANY_MISMATCH',{i['code'] for i in r['issues']})
        self.assertFalse(r['detail']['현재원장연결'])
        self.assertTrue(all(x['원본회사코드']=='OTHER' and x['매핑회사코드']=='OTHER'
            for x in r['tables']['원본부호변환']))

    def test_missing_company_column_stays_unverified_and_initial_gl_is_rejected(self):
        for remove_column in (False,True):
            p=deepcopy(self.base);p['column_mapping']=[r for r in p['column_mapping'] if r['target']!='company_id']
            p['company_mapping']=[]  # Narrow legacy-workbook compatibility never invents a company.
            if remove_column:
                for row in p['source_rows']:row.pop('법인코드')
            r=self.run_case(p)
            self.assertEqual(r['blocking'],0);self.assertGreater(r['review'],0)
            self.assertFalse(r['detail']['현재원장연결'])
            self.assertTrue(all(x['매핑회사코드']=='' for x in r['tables']['원본부호변환']))
            with self.assertRaisesRegex(AuditError,'회사'):prepare_ledger(confirm(p),self.context)

    def test_mixed_and_blank_companies_are_blocked_without_dropping_rows(self):
        for value,code in [('OTHER','ERP_COMPANY_MIXED'),('  ','ERP_COMPANY_EMPTY'),(True,'ERP_COMPANY_EMPTY')]:
            p=deepcopy(self.base);p['source_rows'][0]['법인코드']=value
            r=self.run_case(p)
            with self.subTest(value=value):
                self.assertIn(code,{i['code'] for i in r['issues']})
                self.assertGreater(r['blocking'],0);self.assertEqual(r['metrics']['원본행수'],44)

    def test_whitespace_is_trimmed_only_for_comparison_and_raw_value_is_preserved(self):
        p=deepcopy(self.base)
        for row in p['source_rows']:row['법인코드']=' '+self.context['회사코드']+' '
        r=self.run_case(p)
        self.assertEqual(r['blocking'],0);self.assertTrue(r['detail']['회사식별확인'])
        self.assertEqual(r['tables']['원본부호변환'][0]['원본회사코드'],' '+self.context['회사코드']+' ')

    def test_numeric_source_identifier_requires_explicit_mapping_to_text_code(self):
        p=deepcopy(self.base)
        for row in p['source_rows']:row['법인코드']=1
        r=self.run_case(p);self.assertGreater(r['blocking'],0)
        p['company_mapping']=[{'source_company':1,'company_code':self.context['회사코드']}]
        r=self.run_case(p);self.assertEqual(r['blocking'],0);self.assertTrue(r['detail']['회사식별확인'])
        p['company_mapping']=[{'source_company':'01','company_code':self.context['회사코드']}]
        self.assertGreater(self.run_case(p)['blocking'],0)

    def test_two_source_company_aliases_are_not_merged_silently(self):
        p=deepcopy(self.base);p['source_rows'][0]['법인코드']='ALIAS'
        p['company_mapping'].append({'source_company':'ALIAS','company_code':self.context['회사코드']})
        self.assertIn('ERP_COMPANY_MIXED',{i['code'] for i in self.run_case(p)['issues']})

    def test_company_mapping_change_requires_fresh_confirmation(self):
        p=confirm(deepcopy(self.base));p['company_mapping'][0]['company_code']='OTHER'
        r=analyze(p,self.context,self.current)
        self.assertIn('ONB_APPROVAL_REQUIRED',{i['code'] for i in r['issues']})

    def test_excel_origin_hash_and_row_hash_survive_company_mapping(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'ERP.xlsx';book=Workbook();sheet=book.active;sheet.title='원본'
            headers=list(self.base['source_rows'][0]);headers=[x for x in headers if not x.startswith('source_')]
            sheet.append(headers)
            for row in self.base['source_rows']:sheet.append([row[k] for k in headers])
            book.save(path);book.close()
            tables,meta=read_original(path)
            mapping={r['target']:r['source'] for r in self.base['column_mapping']}
            p=stage_original(self.base,path,tables,meta,'원본',mapping,self.base['config'])
            before=digest(p['source_rows'])
            p=confirm_input('실무자료·원장',p,'SYNTHETIC ONLY','가상 상태전이')
            r=analyze(p,self.context,self.current)
            self.assertEqual(r['blocking'],0);self.assertTrue(r['detail']['회사식별확인'])
            self.assertEqual(before,digest(p['source_rows']))
            self.assertTrue(all(x['원본SHA256']==meta['sha256'] for x in r['tables']['원본부호변환']))


if __name__=='__main__':unittest.main()
