"""Actual workbook roundtrip plus hostile/corrupted import boundaries."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED, ZIP_BZIP2
import hashlib
import json
import stat
import unittest
import warnings

from common import AuditError
from raw_sources import build_pack, load_pack, _json, _path, _workbook

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'testdata' / 'raw_source_baseline'
CONTEXT = {'회사코드': 'SYNTH01', '시작일': '2026-01-01', '기준일': '2026-12-31', '통화': 'KRW', '연결구분': '별도'}


def encode(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


class SourcePackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory(prefix='auditpack-tests-')
        cls.tmp_path = Path(cls.tmp.name)
        cls.links = {'schema_version': 'raw-links-1', 'context': CONTEXT, 'populations': [], 'allocations': []}
        cls.pack = build_pack(cls.tmp_path / 'baseline.auditpack', SOURCE, cls.links)
        cls.binary = cls.pack.read_bytes()
        with ZipFile(BytesIO(cls.binary)) as z:
            cls.members = {i.filename: z.read(i) for i in z.infolist()}
        cls.actual = load_pack(cls.pack, CONTEXT)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def mutate(self, change=None, refresh=True, extras=(), compression=ZIP_DEFLATED):
        members = dict(self.members)
        if change:
            change(members)
        if refresh:
            manifest = json.loads(members['manifest.json'])
            manifest['files'] = [{'path': k, 'sha256': digest(v), 'bytes': len(v)} for k, v in sorted(members.items()) if k != 'manifest.json']
            members['manifest.json'] = encode(manifest)
        buf = BytesIO()
        with ZipFile(buf, 'w', compression=compression) as z:
            for name, binary in members.items():
                z.writestr(name, binary)
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                for name, binary in extras:
                    z.writestr(name, binary)
        path = self.tmp_path / (self._testMethodName + '.auditpack')
        path.write_bytes(buf.getvalue())
        return path

    def json_change(self, member, change):
        def mutate(members):
            data = json.loads(members[member])
            change(data)
            members[member] = encode(data)
        return mutate

    def assertBlocked(self, path, text=None, context=CONTEXT):
        with self.assertRaises(AuditError) as caught:
            load_pack(path, context)
        if text:
            self.assertIn(text, str(caught.exception))

    def test_actual_16_workbooks_114_tables_98_existing_ids(self):
        catalog = self.actual['catalog']
        self.assertEqual(len(catalog['tables']), 114)
        ids = [t['dataset_id'] for t in catalog['tables']]
        self.assertEqual({f'D{n:03}' for n in range(1, 99)}, {i for i in ids if i.startswith('D')})
        self.assertEqual(len(set(t['source_file'] for t in catalog['tables'])), 16)
        self.assertTrue(all('/CSV/' not in t['source_file'] and '오류' not in t['source_file'] for t in catalog['tables']))
        self.assertEqual(self.actual['source'], {'filename': 'baseline.auditpack', 'bytes': len(self.binary), 'sha256': digest(self.binary)})

    def test_original_xlsx_bytes_preserved(self):
        for t in self.actual['catalog']['tables']:
            name = t['source_file']
            self.assertEqual(self.members[name], (SOURCE / '배포' / name.removeprefix('sources/')).read_bytes())

    def test_quoted_timestamp_records_original_and_transform(self):
        transforms = [t for t in self.actual['catalog']['transformations'] if t['kind'] == 'quoted_iso_timestamp']
        self.assertEqual(len(transforms), 282)
        rec = transforms[0]
        self.assertEqual(rec['original'], "'2027-01-05T09:00:00+09:00")
        self.assertEqual(rec['normalized'], '2027-01-05T09:00:00+09:00')
        self.assertEqual(rec['row'], 2)

    def test_all_null_formatted_rows_recorded_but_not_business_rows(self):
        records = [t for t in self.actual['catalog']['transformations'] if t['kind'] == 'all_null_formatted_row']
        self.assertEqual(len(records), 3)
        adjustment = next(t for t in self.actual['catalog']['tables'] if t['dataset_id'] == 'D057')
        self.assertEqual(adjustment['rows'], [])
        self.assertTrue(any(t['dataset_id'] == 'D057' and t['row'] == 2 and all(v is None for v in t['original']) for t in records))

    def test_null_and_zero_remain_distinct(self):
        values = [v for t in self.actual['catalog']['tables'] for r in t['rows'] for v in r['values']]
        self.assertIn(None, values)
        self.assertTrue(any(type(v) is int and v == 0 for v in values))

    def test_deterministic_identical_bytes(self):
        second = build_pack(self.tmp_path / 'second.auditpack', SOURCE, self.links)
        self.assertEqual(second.read_bytes(), self.binary)

    def test_default_build_links_is_delegated(self):
        with patch('raw_accounts.build_links', return_value=self.links) as fn:
            p = build_pack(self.tmp_path / 'default.auditpack', SOURCE)
            self.assertTrue(p.is_file())
            self.assertEqual(len(fn.call_args.args[0]['tables']), 114)

    def test_path_traversal_absolute_drive_backslash_and_control(self):
        for name in ('../bad.xlsx', '/bad.xlsx', 'sources/../bad.xlsx', 'C:/bad.xlsx', 'sources\\bad.xlsx', 'sources//bad.xlsx', 'sources/./bad.xlsx', 'sources/a\n.xlsx', 'sources/a./x.xlsx'):
            with self.subTest(name=name), self.assertRaises(AuditError):
                _path(name)

    def test_duplicate_archive_member_blocked(self):
        self.assertBlocked(self.mutate(extras=[('catalog.json', b'{}')]), '중복')

    def test_casefold_duplicate_archive_member_blocked(self):
        self.assertBlocked(self.mutate(extras=[('CATALOG.JSON', b'{}')]), '중복')

    def test_symlink_archive_member_blocked(self):
        info = ZipInfo('sources/symlink.xlsx')
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.assertBlocked(self.mutate(extras=[(info, b'../outside')]), 'symlink')

    def test_unsupported_compression_blocked(self):
        self.assertBlocked(self.mutate(compression=ZIP_BZIP2), '압축 방식')

    def test_zip_bomb_ratio_blocked(self):
        self.assertBlocked(self.mutate(extras=[('sources/bomb.xlsx', b'0' * 500000)]), '압축률')

    def test_member_count_limit(self):
        self.assertBlocked(self.mutate(extras=[(f'sources/{i}.xlsx', b'a') for i in range(150)]), '개수')

    def test_overall_size_limit_before_zip_parse(self):
        with patch('raw_sources.PACK_LIMIT', 100):
            self.assertBlocked(self.pack, '40MB')

    def test_missing_required_file(self):
        self.assertBlocked(self.mutate(lambda m: m.pop('catalog.json')), '필수 파일')

    def test_unregistered_file_blocked(self):
        self.assertBlocked(self.mutate(refresh=False, extras=[('sources/unregistered.xlsx', b'x')]), '미등록')

    def test_registered_but_unselected_xlsx_blocked(self):
        self.assertBlocked(self.mutate(lambda m: m.update({'sources/extra.xlsx': b'x'})), '선택 불일치')

    def test_unsupported_executable_member(self):
        self.assertBlocked(self.mutate(extras=[('sources/instruction.exe', b'x')]), '미지원')

    def test_sha_tamper_detected(self):
        self.assertBlocked(self.mutate(lambda m: m.update({'catalog.json': m['catalog.json'] + b' '}), refresh=False), 'SHA256')

    def test_manifest_bytes_bool_is_not_integer(self):
        p = self.mutate(self.json_change('manifest.json', lambda m: m['files'][0].update(bytes=True)), refresh=False)
        self.assertBlocked(p, '크기')

    def test_duplicate_json_keys_rejected_even_after_rehash(self):
        p = self.mutate(lambda m: m.update({'links.json': b'{"schema_version":"raw-links-1","schema_version":"raw-links-1"}'}))
        self.assertBlocked(p, '중복 키')

    def test_json_nonfinite_and_depth_limits(self):
        for data in (b'{"x":NaN}', b'{"x":1e999}', b'[' * 30 + b'0' + b']' * 30):
            with self.assertRaises(AuditError):
                _json(data, 'test')

    def test_catalog_value_tamper_rehashed_still_blocked(self):
        p = self.mutate(self.json_change('catalog.json', lambda c: c['tables'][1]['rows'][0]['values'].__setitem__(3, 999999)))
        self.assertBlocked(p, '원본 XLSX')

    def test_catalog_bool_to_integer_type_tamper(self):
        p = self.mutate(self.json_change('catalog.json', lambda c: c['tables'][1]['rows'][0]['values'].__setitem__(3, True)))
        self.assertBlocked(p, '원본 XLSX')

    def test_catalog_row_number_tamper_rehashed_blocked(self):
        p = self.mutate(self.json_change('catalog.json', lambda c: c['tables'][1]['rows'][0].update(row=999)))
        self.assertBlocked(p, '원본 XLSX')

    def test_catalog_missing_zero_row_rehashed_blocked(self):
        p = self.mutate(self.json_change('catalog.json', lambda c: c['tables'][1]['rows'].pop()))
        self.assertBlocked(p, '원본 XLSX')

    def test_catalog_header_tamper_rehashed_blocked(self):
        p = self.mutate(self.json_change('catalog.json', lambda c: c['tables'][1]['headers'].__setitem__(0, '가짜회사')))
        self.assertBlocked(p, '원본 XLSX')

    def test_catalog_sheet_source_and_duplicate_id_tamper(self):
        for key, value in (('sheet', '존재안함'), ('source_file', 'sources/fake.xlsx'), ('dataset_id', 'D001')):
            p = self.mutate(self.json_change('catalog.json', lambda c: c['tables'][0].update({key: value})))
            self.assertBlocked(p, '원본 XLSX')

    def test_transform_record_removal_blocked(self):
        p = self.mutate(self.json_change('catalog.json', lambda c: c['transformations'].pop()))
        self.assertBlocked(p, '원본 XLSX')

    def test_context_company_period_currency_consolidation_block(self):
        for key, value in (('회사코드', 'OTHER'), ('기준일', '2025-12-31'), ('통화', 'USD'), ('연결구분', '연결')):
            self.assertBlocked(self.pack, context=CONTEXT | {key: value})

    def test_links_context_and_schema_mismatch(self):
        for change in (lambda l: l.update(schema_version='wrong'), lambda l: l['context'].update(회사코드='OTHER'), lambda l: l.update(populations={})):
            self.assertBlocked(self.mutate(self.json_change('links.json', change)), 'links')

    def test_cancelled_import(self):
        event = Event()
        event.set()
        with self.assertRaisesRegex(AuditError, '취소'):
            load_pack(self.pack, CONTEXT, event)

    def test_invalid_non_zip_and_extension(self):
        path = self.tmp_path / 'notzip.auditpack'
        path.write_bytes(b'not a ZIP')
        self.assertBlocked(path, 'ZIP')
        p2 = self.tmp_path / 'notzip.zip'
        p2.write_bytes(self.binary)
        self.assertBlocked(p2, '.auditpack')

    def test_nested_xlsx_formula_and_error_values_blocked(self):
        original = next(v for k, v in self.members.items() if k.endswith('01_원장_리드_합성자료.xlsx'))
        for replacement in ('<c r="A2"><f>1+1</f><v>2</v></c>', '<c r="A2" t="e"><v>#REF!</v></c>'):
            with ZipFile(BytesIO(original)) as z:
                nested = {i.filename: z.read(i) for i in z.infolist()}
            xml = nested['xl/worksheets/sheet1.xml'].decode('utf-8')
            import re
            replacement = re.sub(r'<(/?)(c|f|v)(\b)', r'<\1x:\2\3', replacement)
            xml, count = re.subn(r'<x:c\b[^>]*r="A2"[^>]*>.*?</x:c>', replacement, xml, count=1)
            self.assertEqual(count, 1)
            nested['xl/worksheets/sheet1.xml'] = xml.encode('utf-8')
            buf = BytesIO()
            with ZipFile(buf, 'w', compression=ZIP_DEFLATED) as z:
                for name, binary in nested.items():
                    z.writestr(name, binary)
            with self.assertRaisesRegex(AuditError, '수식·오류'):
                _workbook(buf.getvalue(), 'test.xlsx')

    def test_nested_xlsx_external_relationship_blocked(self):
        original = next(v for k, v in self.members.items() if k.endswith('01_원장_리드_합성자료.xlsx'))
        buf = BytesIO()
        with ZipFile(BytesIO(original)) as src, ZipFile(buf, 'w', compression=ZIP_DEFLATED) as target:
            for info in src.infolist():
                target.writestr(info.filename, src.read(info))
            target.writestr('xl/worksheets/_rels/sheet1.xml.rels', b'<Relationships><Relationship TargetMode="External" Target="https://example.invalid"/></Relationships>')
        with self.assertRaisesRegex(AuditError, '외부 참조'):
            _workbook(buf.getvalue(), 'test.xlsx')


if __name__ == '__main__':
    unittest.main(verbosity=2)
