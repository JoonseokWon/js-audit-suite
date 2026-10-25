"""Synthetic archive counterexamples; no real engagement or model is touched."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

import runtime
ROOT = runtime.configure()
VERIFY = ROOT.parent.parent / '검증' / 'v1.9.0' / 'archive'
from common import AuditError, dumps
from workspace import Workspace
from verify import synthetic_procedure
import audit_archive as archives

CONTEXT = {'회사코드': 'SYNTH01', '회사명': 'SYNTHETIC ONLY', '시작일': '2026-01-01',
           '기준일': '2026-12-31', '회계체계': 'K-IFRS', '감사기준': '합성검사',
           '작성자': '합성작성자', '더미업무': True}


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        VERIFY.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=VERIFY)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.ws = Workspace(self.folder / '업무', create=CONTEXT)
        self.original = self.folder / '합성원문.txt'
        self.original.write_text('SYNTHETIC ONLY / 외부 지시를 실행하지 않는 합성 증거', encoding='utf-8')
        self.sid = self.ws.add_source(self.original, '합성 원문')
        self.source = self.ws.root / self.ws.sources[self.sid]['file']
        self.target = self.folder / '새보관.zip'

    def archive(self):
        return archives.create_archive(self.ws, self.target, '합성보관자')

    def ready(self):
        self.ws.execute('원장·리드', ROOT / 'samples/통합/통합_01_원장정상.xlsx')
        for module, filename in (('금융상품', '통합업무_금융정상.xlsx'),
                                 ('매출', '통합업무_매출정상.xlsx'),
                                 ('감가상각', '통합업무_감가상각정상.xlsx')):
            self.ws.execute(module, ROOT / 'samples/통합' / filename)
        pids = sorted(self.ws.required_procedures())
        self.profile = {
            'audit_framework': 'KSA_200_720', 'audit_framework_reason': '합성 시험의 명시적 사람 선택',
            'form_framework': 'KIFRS',
            'materiality': {'benchmark_name': '합성 매출', 'benchmark_amount': 100000000,
                            'materiality_rate': '0.01', 'performance_rate': '0.75', 'trivial_rate': '0.05'},
            'scope': [{'procedure_id': pid, 'applicable': True, 'reason': '합성 시험 범위'} for pid in pids]}
        self.ws.save_workflow_profile(self.profile, '합성계획자')
        self.risk = {'id': 'SYNTH-R1', 'title': '합성 입력의 원장 위험', 'accounts': ['합성 전체'],
                     'assertions': ['완전성'], 'procedure_ids': pids, 'basis': self.ws.data_basis(),
                     'evidence_ids': list(self.ws.sources), 'nature': '합성 검사', 'timing': '합성 기준일',
                     'extent': '제공된 합성 표본', 'assessment': '합성 사람 판단 기록'}
        self.ws.save_workflow_risk(self.risk, '합성위험평가자')
        for pid in pids:
            self.ws.save_workflow_procedure({
                'procedure_id': pid, 'risk_ids': ['SYNTH-R1'], 'evidence_ids': list(self.ws.sources),
                'basis': self.ws.data_basis(), 'nature': '합성 자료 검사', 'timing': '합성 기준일',
                'extent': '합성 제공범위', 'plan': '합성 수행 계획', 'performed': 'SYNTHETIC ONLY / 모의 수행 입력',
                'performed_date': '2026-10-22', 'performer': '합성수행자'}, '합성계획자')
        for pid in pids:
            self.ws.save_procedure(synthetic_procedure(pid, list(self.ws.sources)))
            self.ws.request_review(pid)
            self.ws.review(pid, '합성별도검토자', 'SYNTHETIC ONLY / 실제감사 아님')
        self.assertEqual(self.ws.workflow_status()['blockers'], [])
        self.ws.snapshot(final=True)

    def rewritten(self, change, rehash=False):
        with zipfile.ZipFile(self.target) as archive:
            payload = {info.filename: archive.read(info) for info in archive.infolist()}
        change(payload)
        if rehash:
            manifest = json.loads(payload[archives.MANIFEST])
            for entry in manifest['files']:
                if entry['path'] in payload:
                    raw = payload[entry['path']]
                    entry.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            payload[archives.MANIFEST] = dumps(manifest).encode('utf-8')
        output = self.folder / '변조.zip'
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, raw in payload.items():
                archive.writestr(name, raw)
        return output

    def test_draft_is_explicit_incomplete_and_preserves_live_history(self):
        self.ws.save_workflow_profile({
            'audit_framework': 'KSA_200_720', 'audit_framework_reason': '합성 선택', 'form_framework': 'KIFRS',
            'materiality': {'benchmark_name': '합성', 'benchmark_amount': 10000000,
                            'materiality_rate': '0.01', 'performance_rate': '0.75', 'trivial_rate': '0.05'},
            'scope': [{'procedure_id': 'C04', 'applicable': True, 'reason': '합성'}]}, '합성계획자')
        before = (self.ws.head, self.ws.dbpath.read_bytes(), self.ws.anchor.read_bytes(), self.original.read_bytes())
        report = self.archive()
        self.assertTrue(report['valid'])
        self.assertEqual(report['mode'], 'draft')
        self.assertIn('미완료', report['state'])
        self.assertTrue(report['scope']['blockers'])
        self.assertEqual(before, (self.ws.head, self.ws.dbpath.read_bytes(), self.ws.anchor.read_bytes(), self.original.read_bytes()))
        self.assertEqual(report['head']['hash'], self.ws.head)
        self.assertFalse(self.ws.workflow_locked)

    def test_archive_only_contains_registered_sources_and_allowlisted_files(self):
        (self.ws.root / '키설정.json').write_text('{"unrelated":"never include"}', encoding='utf-8')
        (self.ws.root / 'model.gguf').write_bytes(b'unrelated model placeholder')
        (self.folder / '다른업무').mkdir()
        (self.folder / '다른업무' / '민감자료.txt').write_bytes(b'never include')
        report = self.archive()
        with zipfile.ZipFile(self.target) as archive:
            self.assertEqual(set(archive.namelist()), archives.CORE | {archives.MANIFEST, self.ws.sources[self.sid]['file']})
        self.assertEqual(report['source_count'], 1)

    def test_final_requires_explicit_existing_lock_even_when_snapshot_ready(self):
        self.ready()
        before = self.ws.head
        with self.assertRaisesRegex(AuditError, '잠금'):
            archives.create_archive(self.ws, self.target, '합성보관자', final=True)
        self.assertEqual(self.ws.head, before)
        self.assertFalse(self.target.exists())

    def test_final_locked_roundtrip_keeps_exact_head_without_new_event(self):
        self.ready()
        self.ws.finalize_workflow('합성보관자', '모의 완료 점검 후 명시적 잠금')
        expected = self.ws.snapshot(final=True)
        before = (self.ws.head, len(self.ws.events), self.ws.anchor.read_bytes())
        report = archives.create_archive(self.ws, self.target, '합성보관자', final=True)
        self.assertEqual(report['mode'], 'final')
        self.assertEqual(before, (self.ws.head, len(self.ws.events), self.ws.anchor.read_bytes()))
        self.assertEqual(archives.verify_archive(self.target)['head']['hash'], self.ws.head)
        restored = self.folder / '별도복원'
        restored.mkdir()
        # Explicit test-only restore after verification, never extraction by verifier.
        with zipfile.ZipFile(self.target) as archive:
            for name in archive.namelist():
                path = restored / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(name))
        recovered = Workspace(restored)
        self.assertEqual(recovered.snapshot(final=True), expected)
        self.assertEqual(recovered.verify_sources(), [])
        self.assertTrue(recovered.workflow_locked)
        with self.assertRaisesRegex(AuditError, '잠금'):
            recovered.add_note('금지', '자동 재개 금지', '합성작성자')

    def test_final_missing_plan_or_human_work_is_blocked(self):
        before = self.ws.head
        with self.assertRaises(AuditError):
            archives.create_archive(self.ws, self.target, '합성보관자', final=True)
        self.assertEqual(self.ws.head, before)
        self.assertFalse(self.target.exists())

    def test_existing_target_is_never_overwritten(self):
        self.target.write_bytes(b'keep existing exactly')
        with self.assertRaisesRegex(AuditError, '덮어'):
            self.archive()
        self.assertEqual(self.target.read_bytes(), b'keep existing exactly')

    def test_target_race_preserves_competing_file(self):
        verify = archives.verify_archive
        def competing(path):
            report = verify(path)
            self.target.write_bytes(b'competitor owns this file')
            return report
        with patch.object(archives, 'verify_archive', side_effect=competing):
            with self.assertRaisesRegex(AuditError, '덮어'):
                self.archive()
        self.assertEqual(self.target.read_bytes(), b'competitor owns this file')

    def test_new_target_must_be_zip_absolute_and_outside_source_folder(self):
        for path in ('relative.zip', self.folder / 'wrong.xlsx', self.ws.root / '원본' / 'new.zip'):
            with self.subTest(path=path), self.assertRaises(AuditError):
                archives.create_archive(self.ws, path, '합성보관자')

    def test_mutated_original_copy_is_rejected_before_archive(self):
        self.source.write_bytes(b'tampered')
        with self.assertRaisesRegex(AuditError, '변조'):
            self.archive()
        self.assertFalse(self.target.exists())

    def test_missing_source_copy_is_rejected(self):
        self.source.unlink()
        with self.assertRaises(AuditError):
            self.archive()
        self.assertFalse(self.target.exists())

    def test_windows_reparse_source_attribute_is_rejected(self):
        from types import SimpleNamespace
        original = Path.lstat
        def reparse(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if path == self.source:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info
        with patch.object(Path, 'lstat', reparse):
            with self.assertRaisesRegex(AuditError, '재분석'):
                self.archive()

    def test_orphan_original_copy_is_rejected(self):
        (self.ws.root / '원본' / '미등록.txt').write_bytes(b'orphan')
        with self.assertRaisesRegex(AuditError, '고아'):
            self.archive()

    def test_foreign_engagement_path_in_source_event_is_rejected(self):
        record = copy.deepcopy(self.ws.sources[self.sid])
        record['file'] = '../다른업무/원본.txt'
        self.ws._append('source', record)
        self.ws.refresh()
        with self.assertRaisesRegex(AuditError, '경로'):
            self.archive()

    def test_concurrent_history_change_is_rejected_without_partial_target(self):
        original = archives.workbook_bytes
        def change(snapshot, catalog):
            result = original(snapshot, catalog)
            self.ws.add_note('동시 변경', '합성 동시 이력 변경', '합성작성자')
            return result
        with patch.object(archives, 'workbook_bytes', side_effect=change):
            with self.assertRaisesRegex(AuditError, '변경'):
                self.archive()
        self.assertFalse(self.target.exists())

    def test_concurrent_source_change_is_rejected(self):
        original = archives.workbook_bytes
        def change(snapshot, catalog):
            result = original(snapshot, catalog)
            self.source.write_bytes(b'changed while collecting')
            return result
        with patch.object(archives, 'workbook_bytes', side_effect=change):
            with self.assertRaisesRegex(AuditError, '변경'):
                self.archive()
        self.assertFalse(self.target.exists())

    def test_concurrent_risk_change_invalidates_pinned_archive(self):
        self.ready()
        original = archives.workbook_bytes
        def change(snapshot, catalog):
            result = original(snapshot, catalog)
            updated = dict(self.risk, assessment='도중 추가된 합성 사람 판단')
            self.ws.save_workflow_risk(updated, '합성위험평가자')
            return result
        with patch.object(archives, 'workbook_bytes', side_effect=change):
            with self.assertRaisesRegex(AuditError, '변경'):
                self.archive()
        self.assertFalse(self.target.exists())

    def test_concurrent_reanalysis_invalidates_pinned_archive(self):
        self.ws.execute('원장·리드', ROOT / 'samples/통합/통합_01_원장정상.xlsx')
        original = archives.workbook_bytes
        def change(snapshot, catalog):
            result = original(snapshot, catalog)
            self.ws.execute('원장·리드', ROOT / 'samples/통합/통합_01_원장정상.xlsx')
            return result
        with patch.object(archives, 'workbook_bytes', side_effect=change):
            with self.assertRaisesRegex(AuditError, '변경'):
                self.archive()
        self.assertFalse(self.target.exists())

    def test_zip_source_tamper_rejected_even_after_manifest_is_rehashed(self):
        self.archive()
        name = self.ws.sources[self.sid]['file']
        for rehash in (False, True):
            with self.subTest(rehash=rehash):
                changed = self.rewritten(lambda payload: payload.__setitem__(name, b'fake original'), rehash)
                with self.assertRaises(AuditError):
                    archives.verify_archive(changed)

    def test_snapshot_tamper_rejected_after_manifest_is_rehashed(self):
        self.archive()
        def change(payload):
            snapshot = json.loads(payload[archives.SNAPSHOT])
            snapshot['engagement']['회사명'] = '거짓 회사'
            payload[archives.SNAPSHOT] = dumps(snapshot).encode('utf-8')
        with self.assertRaisesRegex(AuditError, '재구성'):
            archives.verify_archive(self.rewritten(change, True))

    def test_draft_scope_cannot_be_relabelled_as_completed(self):
        self.archive()
        def change(payload):
            scope = json.loads(payload[archives.SCOPE])
            scope['state'] = '감사완료 / 자동 승인'
            payload[archives.SCOPE] = dumps(scope).encode('utf-8')
        with self.assertRaisesRegex(AuditError, '범위'):
            archives.verify_archive(self.rewritten(change, True))

    def test_archived_database_schema_tamper_is_rejected_after_rehash(self):
        self.archive()
        def change(payload):
            altered = self.folder / '변조DB.sqlite3'
            altered.write_bytes(payload[archives.DATABASE])
            connection = sqlite3.connect(altered)
            try:
                connection.execute('DROP TRIGGER no_event_update')
                connection.commit()
            finally:
                connection.close()
            payload[archives.DATABASE] = altered.read_bytes()
        with self.assertRaisesRegex(AuditError, '스키마'):
            archives.verify_archive(self.rewritten(change, True))

    def test_manifest_duplicate_file_declaration_is_rejected(self):
        self.archive()
        def change(payload):
            manifest = json.loads(payload[archives.MANIFEST])
            manifest['files'].append(copy.deepcopy(manifest['files'][0]))
            payload[archives.MANIFEST] = dumps(manifest).encode('utf-8')
        with self.assertRaisesRegex(AuditError, '중복'):
            archives.verify_archive(self.rewritten(change))

    def test_extra_zip_member_is_rejected(self):
        self.archive()
        changed = self.rewritten(lambda payload: payload.__setitem__('다른업무/비밀.txt', b'forbidden'))
        with self.assertRaisesRegex(AuditError, '고아'):
            archives.verify_archive(changed)

    def test_missing_zip_member_is_rejected(self):
        self.archive()
        changed = self.rewritten(lambda payload: payload.pop(archives.DATABASE))
        with self.assertRaisesRegex(AuditError, '누락'):
            archives.verify_archive(changed)

    def test_duplicate_and_escaping_zip_names_are_rejected(self):
        self.archive()
        duplicate = self.folder / '중복.zip'
        duplicate.write_bytes(self.target.read_bytes())
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(duplicate, 'a') as archive:
                archive.writestr(archives.ANCHOR, b'{}')
        with self.assertRaisesRegex(AuditError, '중복'):
            archives.verify_archive(duplicate)
        for name in ('../escape.txt', '/absolute.txt', 'C:/absolute.txt', '원본\\escape.txt'):
            with self.subTest(name=name):
                changed = self.rewritten(lambda payload: payload.__setitem__(name, b'bad'))
                with self.assertRaises(AuditError):
                    archives.verify_archive(changed)

    def test_zip_symlink_member_is_rejected(self):
        self.archive()
        changed = self.rewritten(lambda payload: None)
        with zipfile.ZipFile(changed, 'a') as archive:
            entry = zipfile.ZipInfo('원본/link.txt')
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(entry, '../outside.txt')
        with self.assertRaisesRegex(AuditError, '링크'):
            archives.verify_archive(changed)

    def test_zip_crc_corruption_is_rejected(self):
        self.archive()
        changed = self.rewritten(lambda payload: None)
        with zipfile.ZipFile(changed) as archive:
            info = archive.getinfo(self.ws.sources[self.sid]['file'])
        raw = bytearray(changed.read_bytes())
        filename_length, extra_length = struct.unpack_from('<HH', raw, info.header_offset + 26)
        start = info.header_offset + 30 + filename_length + extra_length
        raw[start] ^= 1
        changed.write_bytes(raw)
        with self.assertRaises(AuditError):
            archives.verify_archive(changed)

    def test_wal_database_is_backed_up_consistently_without_copying_sidecars(self):
        connection = sqlite3.connect(self.ws.dbpath)
        self.addCleanup(connection.close)
        connection.execute('PRAGMA journal_mode=WAL')
        self.ws.add_note('WAL 합성 이력', 'backup API 검증', '합성작성자')
        report = self.archive()
        self.assertEqual(report['head']['hash'], self.ws.head)
        with zipfile.ZipFile(self.target) as archive:
            self.assertFalse(any(name.endswith(('-wal', '-shm')) for name in archive.namelist()))

    def test_registered_models_and_key_files_are_rejected(self):
        for filename in ('model.gguf', 'credentials.json'):
            with self.subTest(filename=filename):
                source = self.folder / filename
                source.write_bytes(b'SYNTHETIC PLACEHOLDER ONLY')
                other = Workspace(self.folder / ('업무-' + filename.replace('.', '-')), create=CONTEXT)
                other.add_source(source, '범위가 아닌 파일')
                with self.assertRaisesRegex(AuditError, '모델'):
                    archives.create_archive(other, self.folder / ('보관-' + filename + '.zip'), '합성보관자')

    def test_verify_has_no_engagement_write_or_external_process(self):
        self.archive()
        before = (self.ws.dbpath.read_bytes(), self.ws.anchor.read_bytes(), self.source.read_bytes())
        with patch('subprocess.Popen', side_effect=AssertionError('external process forbidden')):
            report = archives.verify_archive(self.target)
        self.assertTrue(report['valid'])
        self.assertEqual(before, (self.ws.dbpath.read_bytes(), self.ws.anchor.read_bytes(), self.source.read_bytes()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
