"""Original-file hash/physical-row preservation, with only isolated temporary copies."""
from copy import deepcopy
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import unittest
from common import AuditError, digest, sha
from onboarding.demo import CONTEXT, ledger_result
from onboarding.erp import analyze, sample
from onboarding.erp.input_io import read_original, stage_original
from test_onboarding_erp import confirm

ROOT=Path(__file__).parent
SOURCE=ROOT/'samples/통합/통합_v1.3_원장_리드.xlsx'


class ERPOriginalTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.path=Path(self.temp.name)/'가상_가져오기.xlsx'
        copyfile(SOURCE,self.path)
        self.tables,self.metadata=read_original(self.path)

    def tearDown(self):self.temp.cleanup()

    def stage(self):
        p=sample(CONTEXT)
        return stage_original(p,self.path,self.tables,self.metadata,'총계정원장',
            {'journal_id':'전표ID'},p['config'])

    def test_exact_file_hash_and_physical_rows_without_approval(self):
        p=self.stage();r=p['source_rows'][0]
        self.assertEqual(r['source_sha256'],sha(self.path))
        self.assertEqual((r['source_file'],r['source_sheet'],r['source_row']),('가상_가져오기.xlsx','총계정원장',2))
        self.assertEqual(r['전표ID'],self.tables['총계정원장'][0]['전표ID'])
        self.assertEqual(p['config']['source_rows_sha256'],digest(p['source_rows']))
        self.assertEqual(p['approval'],{})

    def test_file_changed_after_read_is_rejected(self):
        with self.path.open('ab') as f:f.write(b'SYNTHETIC-CHANGED')
        with self.assertRaisesRegex(AuditError,'바뀌었습니다'):self.stage()

    def test_reapproving_edited_rows_cannot_reuse_imported_byte_provenance(self):
        p=self.stage();p['source_rows'][0]['차변']+=1
        r=analyze(confirm(p),CONTEXT,ledger_result(CONTEXT))
        self.assertGreater(r['blocking'],0)
        self.assertIn('원본 파일·행 해시',r['issues'][-1]['message'])

    def test_same_filename_is_not_file_identity(self):
        p=self.stage();p['source_rows'][0]['source_sha256']='0'*64
        r=analyze(confirm(p),CONTEXT,ledger_result(CONTEXT))
        self.assertIn('ERP_INPUT',{i['code'] for i in r['issues']})

    def test_formula_and_external_connection_cannot_be_cached_evidence(self):
        from xml.etree import ElementTree as ET
        with ZipFile(self.path) as z:archive={name:z.read(name) for name in z.namelist()}
        sheet=next(name for name in archive if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'))
        root=ET.fromstring(archive[sheet]);ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        cell=root.find('.//x:c',ns)
        for child in list(cell):cell.remove(child)
        cell.attrib.pop('t',None)
        ET.SubElement(cell,'{'+ns['x']+'}f').text='1=1'
        ET.SubElement(cell,'{'+ns['x']+'}v').text='1'
        archive[sheet]=ET.tostring(root)
        bad=Path(self.temp.name)/'수식캐시_가상.xlsx'
        with ZipFile(bad,'w') as z:
            for name,data in archive.items():z.writestr(name,data)
        with self.assertRaisesRegex(AuditError,'수식'):read_original(bad)
        external=Path(self.temp.name)/'외부연결_가상.xlsx'
        with ZipFile(external,'w') as z:
            for name,data in archive.items():z.writestr(name,data)
            z.writestr('xl/externalLinks/externalLink1.xml','<externalLink/>')
        with self.assertRaisesRegex(AuditError,'외부연결'):read_original(external)


if __name__=='__main__':unittest.main()
