"""Registry integrity and read-only official-reference verification."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audit_forms as forms

ROOT = Path(__file__).resolve().parent
LOCAL_REFERENCE = ROOT.parents[1] / '참고자료' / '2026_기준서와_예시조서' / forms.REFERENCE_FILENAME


class FormRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = forms.load_registry()

    def changed(self, mutate):
        registry = copy.deepcopy(self.registry)
        mutate(registry)
        return registry

    def assert_invalid(self, mutate):
        with self.assertRaises(forms.FormRegistryError):
            forms.validate_registry(self.changed(mutate))

    def test_exact_inventory_116_files_82_workbooks_435_sheets(self):
        registry = self.registry
        self.assertEqual(len(registry['forms']), 116)
        self.assertEqual(Counter(f['framework'] for f in registry['forms']),
                         {'KIFRS': 52, '일반기업': 42, '소규모기업': 22})
        self.assertEqual(Counter(f['extension'] for f in registry['forms']), registry['source']['file_types'])
        self.assertEqual(sum(bool(f['sheet_names']) for f in registry['forms']), 82)
        self.assertEqual(sum(len(f['sheet_names']) for f in registry['forms']), 435)
        self.assertEqual(sum(f['macro_container'] for f in registry['forms']), 2)
        self.assertEqual(sum(f['vba_present'] for f in registry['forms']), 2)
        self.assertEqual(registry['source']['sha256'], forms.REFERENCE_SHA256)

    def test_all_54_procedures_have_three_explicit_profile_states(self):
        registry = self.registry
        self.assertEqual(len(registry['procedures']), 54)
        self.assertEqual(len(registry['crosswalk']), 162)
        self.assertEqual(Counter(m['mapping_status'] for m in registry['crosswalk']),
                         {'설계상참고': 93, '수동판단': 60, '미연결': 9})
        self.assertEqual(sum(len(m['references']) for m in registry['crosswalk']), 228)
        for procedure in registry['procedures']:
            for framework in forms.FRAMEWORKS:
                with self.subTest(pid=procedure['app_id'], framework=framework):
                    rows = forms.registry_rows(framework, [procedure['app_id']])
                    self.assertTrue(rows)
                    self.assertTrue(all(row['서식계열'] == framework for row in rows))
                    self.assertTrue(all(row['연결상태'] in forms.MAPPING_STATUSES for row in rows))
                    self.assertTrue(all(row['제외범위'] and row['주의'] for row in rows))

    def test_catalog_and_supplemental_namespace_are_distinct(self):
        catalog = json.loads((ROOT / 'procedure_catalog.json').read_text(encoding='utf-8'))
        result = forms.procedure_ids_validation(catalog)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['registry_only'], [])
        self.assertEqual(set(result['supplemental_ids']), forms.SUPPLEMENTAL_IDS)
        catalog['modules'].append(copy.deepcopy(catalog['modules'][0]))
        self.assertFalse(forms.procedure_ids_validation(catalog)['ok'])
        catalog['modules'][-1]['id'] = 'MISSING'
        self.assertEqual(forms.procedure_ids_validation(catalog)['catalog_only'], ['MISSING'])
        catalog['modules'].pop(0)
        self.assertIn('C01', forms.procedure_ids_validation(catalog)['registry_only'])

    def test_fs01_reference_is_not_subsequent_event_f01(self):
        for framework in ('KIFRS', '일반기업'):
            linked = forms.forms_for_procedure('FS01', framework)
            self.assertEqual({r['form_code'] for r in linked}, {'3650', '8400'})
            self.assertTrue(all(r['linked_sheets'] == [r['form_code']] for r in linked))
            self.assertTrue(all('재무제표' in row['scope'] for row in linked))
            later = forms.forms_for_procedure('F01', framework)
            self.assertEqual({r['form_code'] for r in later}, {'8100~8700'})
            self.assertTrue(all(row['mapping_status'] == '수동판단' for row in later))
        small = forms.forms_for_procedure('FS01', '소규모기업')
        self.assertEqual({row['form_code'] for row in small}, {'8400'})
        self.assertEqual(small[0]['linked_sheets'], ['8400'])

    def test_exact_linked_sheet_does_not_mean_all_inventory_sheets(self):
        linked = forms.forms_for_procedure('A01', 'KIFRS')
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0]['linked_sheets'], ['A'])
        self.assertGreater(len(linked[0]['sheet_names']), 30)
        self.assertEqual(linked[0]['mapping_status'], '설계상참고')
        self.assertEqual(forms.registry_rows('KIFRS', ['A01'])[0]['시트'], 'A')
        fs_rows = forms.registry_rows('KIFRS', ['FS01'])
        self.assertTrue(all(row['참고단위'] == '시트명' and row['시트'] == row['서식번호'] for row in fs_rows))
        later = forms.registry_rows('KIFRS', ['F01'])
        self.assertTrue(all(row['참고단위'] == '파일' and row['시트'] == '' for row in later))

    def test_framework_aliases_and_no_cross_profile_fallback(self):
        self.assertEqual(forms.forms_for_procedure('A01', 'K-IFRS'), forms.forms_for_procedure('A01', 'KIFRS'))
        self.assertEqual(forms.forms_for_procedure('A01', '일반기업회계기준'), forms.forms_for_procedure('A01', '일반기업'))
        for framework in forms.FRAMEWORKS:
            for row in forms.forms_for_procedure('P01', framework):
                self.assertEqual(row['framework'], framework)
                self.assertFalse(row['macro_container'])
        self.assertFalse(any(r['form_code'] == '2302' for r in forms.forms_for_procedure('P01', '소규모기업')))
        with self.assertRaises(forms.FormRegistryError):
            forms.forms_for_procedure('A01', '알 수 없는 기준')

    def test_form_family_label_does_not_assert_accounting_or_audit_framework(self):
        for family in forms.FRAMEWORKS:
            rows = forms.registry_rows(family, ['FS01'])
            self.assertTrue(all(row['서식계열'] == family for row in rows))
            self.assertTrue(all('회계체계' not in row and '감사기준' not in row for row in rows))
        with self.assertRaisesRegex(forms.FormRegistryError, '서식계열'):
            forms.normalize_framework('KSA_1200')

    def test_explicit_unlinked_rows_and_unknown_ids(self):
        for pid in ('C06', 'C07', 'A21'):
            self.assertEqual(forms.forms_for_procedure(pid), [])
            row = forms.registry_rows('일반기업', [pid])[0]
            self.assertEqual(row['연결상태'], '미연결')
            self.assertEqual(row['공식서식ID'], '')
        for pid in ('UNKNOWN', 'X-run-1', 'B-digest'):
            with self.assertRaises(forms.FormRegistryError):
                forms.forms_for_procedure(pid)
        with self.assertRaises(forms.FormRegistryError):
            forms.registry_rows('일반기업', ['A01', 'A01'])

    def test_no_mutable_result_leaks_into_later_reads(self):
        first = forms.forms_for_procedure('A01')
        first[0]['linked_sheets'].append('invented')
        first[0]['sheet_names'].clear()
        self.assertEqual(forms.forms_for_procedure('A01')[0]['linked_sheets'], ['A'])
        fresh = forms.load_registry()
        fresh['forms'].clear()
        self.assertEqual(len(forms.load_registry()['forms']), 116)

    def test_duplicate_official_and_app_ids_rejected(self):
        self.assert_invalid(lambda r: r['forms'][1].update(official_id=r['forms'][0]['official_id']))
        self.assert_invalid(lambda r: r['procedures'][1].update(app_id=r['procedures'][0]['app_id']))
        self.assert_invalid(lambda r: r['forms'][0].update(official_id='app.procedure:A01'))
        self.assert_invalid(lambda r: r['procedures'][0].update(namespace='official.example.2026'))

    def test_orphan_crosswalk_ids_and_sheets_rejected(self):
        self.assert_invalid(lambda r: r['crosswalk'][0].update(app_id='ORPHAN'))
        self.assert_invalid(lambda r: r['crosswalk'][0]['references'][0].update(official_id='official.example.2026:KIFRS:MISSING'))
        self.assert_invalid(lambda r: r['crosswalk'][0]['references'][0].update(linked_sheets=['없는시트']))
        self.assert_invalid(lambda r: r['crosswalk'].pop())
        self.assert_invalid(lambda r: r['crosswalk'].append(copy.deepcopy(r['crosswalk'][0])))

    def test_cross_framework_reference_and_path_rejected(self):
        general_id = next(f['official_id'] for f in self.registry['forms'] if f['framework'] == '일반기업')
        self.assert_invalid(lambda r: r['crosswalk'][0]['references'][0].update(official_id=general_id))
        self.assert_invalid(lambda r: r['forms'][0].update(framework='일반기업'))
        self.assert_invalid(lambda r: r['forms'][0].update(member='../unsafe.xlsx'))

    def test_unsupported_claims_and_embedded_content_rejected(self):
        self.assert_invalid(lambda r: r['crosswalk'][0].update(mapping_status='공식적합성인증'))
        self.assert_invalid(lambda r: r['forms'][0].update(full_text='본문을 넣을 수 없음'))
        self.assert_invalid(lambda r: r['source']['inspection'].update(macros_executed=True))
        self.assert_invalid(lambda r: r['source'].update(sha256='0' * 64))
        self.assert_invalid(lambda r: r['forms'][0].update(sha256='not-a-hash'))
        self.assert_invalid(lambda r: r['crosswalk'][0].update(mapping_status='미연결'))
        self.assert_invalid(lambda r: r['crosswalk'][0].update(exclusions=[]))

    def test_duplicate_json_keys_nonfinite_and_unknown_fields_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'registry.json'
            for content in ('{"schema_version":1,"schema_version":2}', '{"bad":NaN}', '[]', '{"unknown":true}'):
                with self.subTest(content=content):
                    path.write_text(content, encoding='utf-8')
                    with self.assertRaises(forms.FormRegistryError):
                        forms.load_registry(path)

    def test_missing_and_invalid_zip_stop_without_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / forms.REFERENCE_FILENAME
            with patch.object(forms.zipfile, 'ZipFile', side_effect=AssertionError('must not parse')):
                self.assertFalse(forms.verify_local_reference_zip(source)['ok'])
                source.write_bytes(b'not a zip')
                result = forms.verify_local_reference_zip(source)
                self.assertFalse(result['ok'])
                self.assertEqual(result['member_hashes_verified'], 0)
                source.write_bytes(b'0' * forms.REFERENCE_BYTES)
                result = forms.verify_local_reference_zip(source)
                self.assertFalse(result['ok'])
                self.assertNotEqual(result['sha256'], forms.REFERENCE_SHA256)
                self.assertEqual(result['member_hashes_verified'], 0)

    @unittest.skipUnless(LOCAL_REFERENCE.is_file(), '공식 원본 ZIP은 공개 소스에 포함하지 않음; 로컬 원본 확인 시 실행')
    def test_actual_zip_all_member_hashes_and_all_workbook_sheet_names_read_only(self):
        before = hashlib.sha256(LOCAL_REFERENCE.read_bytes()).hexdigest()
        result = forms.verify_local_reference_zip(LOCAL_REFERENCE)
        after = hashlib.sha256(LOCAL_REFERENCE.read_bytes()).hexdigest()
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['member_hashes_verified'], 116)
        self.assertEqual(result['workbooks_verified'], 82)
        self.assertEqual(result['sheets_verified'], 435)
        self.assertEqual(result['counts']['entries'], 119)
        self.assertEqual(result['counts']['directories'], 3)
        self.assertEqual(result['counts']['files'], 116)
        self.assertEqual(before, after)
        self.assertEqual(before, forms.REFERENCE_SHA256)
        self.assertFalse(result['formulas_evaluated'])
        self.assertFalse(result['macros_executed'])
        self.assertFalse(result['external_links_refreshed'])

    def test_frozen_resource_root(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'form_registry.json'
            path.write_bytes((ROOT / 'form_registry.json').read_bytes())
            with patch.object(forms.sys, '_MEIPASS', directory, create=True):
                self.assertEqual(len(forms.load_registry()['forms']), 116)


if __name__ == '__main__':
    unittest.main()
