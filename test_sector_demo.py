"""Black-box sector provider controls; resources and older releases are readonly."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import patch
import json
import os
import shutil
import tempfile
import unittest

from common import AuditError
from workspace import Workspace
import sector_demo
import exporter
from tools.verify_sectors_headless import COMPANIES, PARENT_PROCEDURES, fingerprint, validate_workspace, validate_data_folder, balanced_omission, exercise_saved_history

ROOT = Path(__file__).resolve().parent
RESOURCES = ROOT/'sector_resources'


class SectorDemoTests(unittest.TestCase):
    def setUp(self):
        area = ROOT/'sector_verification'
        area.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='unit-sector-', dir=area)
        self.folder = Path(self.temp.name).resolve()
        if not self.folder.is_relative_to(area.resolve()):
            raise AssertionError('격리 테스트 폴더 경로 오류')
        self.store = self.folder/'store'

    def tearDown(self):
        self.temp.cleanup()

    def open(self, code='JS_ELEC', **kwargs):
        return sector_demo.open_company(code, self.store, kwargs.pop('resources', RESOURCES), **kwargs)

    def resource_copy(self):
        target = self.folder/'resources-copy'
        shutil.copytree(RESOURCES, target)
        return target

    def company_xlsx(self, root, code='JS_ELEC'):
        files = [p for p in root.rglob('*.xlsx') if code in p.relative_to(root).parts or code in p.name]
        self.assertTrue(files, '회사별 원본 XLSX를 찾지 못했습니다.')
        return sorted(files)[0]

    def test_registered_five_company_choices(self):
        entries = sector_demo.list_companies(RESOURCES)
        self.assertEqual({r['code'] for r in entries}, set(COMPANIES))
        self.assertEqual(len(entries), 5)

    def test_default_storage_is_absolute_without_profile_environment(self):
        missing = {'LOCALAPPDATA', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH'}
        environment = {key: value for key, value in os.environ.items() if key.upper() not in missing}
        with patch.dict(os.environ, environment, clear=True):
            self.assertFalse(any(os.environ.get(key) for key in missing))
            path = sector_demo.default_storage_root()
        self.assertTrue(path.is_absolute())
        self.assertEqual(path.parts[-3:], ('JSAudit', 'sector-demos', 'v1.7'))

    def test_manifest_path_escape_is_rejected_without_outside_write(self):
        resources = self.resource_copy()
        outside = self.folder/'outside-user-document.txt'
        outside.write_text('사용자 원문 보존', encoding='utf-8')
        before = outside.read_bytes()
        manifest = resources/'manifest.json'
        for path in ('../outside-user-document.txt', '/absolute.xlsx', 'C:/absolute.xlsx', 'companies/JS/../escape.xlsx', 'companies\\JS\\escape.xlsx'):
            data = json.loads((RESOURCES/'manifest.json').read_text(encoding='utf-8'))
            data['files'][0]['path'] = path
            manifest.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            with self.subTest(path=path), self.assertRaises(AuditError):
                self.open(resources=resources)
        self.assertEqual(outside.read_bytes(), before)
        self.assertFalse(self.store.exists())

    def test_manifest_duplicate_file_entry_is_rejected(self):
        resources = self.resource_copy()
        manifest = resources/'manifest.json'
        data = json.loads(manifest.read_text(encoding='utf-8'))
        data['files'].append(dict(data['files'][0]))
        manifest.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        with self.assertRaises(AuditError):
            self.open(resources=resources)

    def test_manifest_cross_company_input_reference_is_rejected(self):
        resources = self.resource_copy()
        manifest = resources/'manifest.json'
        data = json.loads(manifest.read_text(encoding='utf-8'))
        target = next(c for c in data['companies'] if c['code'] == 'JS_ELEC')
        other = next(c for c in data['companies'] if c['code'] == 'JS_AUTO')
        target['inputs'][0] = dict(other['inputs'][0])
        manifest.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        with self.assertRaises(AuditError):
            self.open(resources=resources)

    def test_normal_company_has_exact_current_ledger_and_drafts(self):
        result = self.open()
        self.assertFalse(result['reused'])
        ws = Workspace(result['folder'])
        checks = []
        record = validate_workspace(ws, 'JS_ELEC', checks)
        self.assertEqual((record['modules'], record['current_ledger_links']), (15, 35))
        self.assertTrue(result['workspace_id'])
        self.assertTrue(ws.root.is_relative_to(self.store.resolve()))

    def test_reselection_preserves_user_procedure_and_request_after_switch(self):
        first = self.open()
        ws = Workspace(first['folder'])
        sid = next(iter(ws.sources))
        ws.save_procedure({'id': 'USER-KEEP', 'title': '사용자 추가 확인 메모', 'preparer': '합성검토담당',
                           'scope': '재선택 후 남아야 하는 사용자 기록', 'evidence_ids': [sid]})
        request = ws.save_request({'title': '사용자 요청', 'requested_from': '합성 담당자', 'note': '전환 뒤 보존',
                                   'due_date': '2027-01-15', 'state': '요청', 'source_ids': []})
        old_head, before = ws.head, fingerprint(ws.root)
        other_result = self.open('JS_AUTO')
        other = Workspace(other_result['folder'])
        self.assertEqual(other.context['회사코드'], 'JS_AUTO')
        self.assertNotIn('USER-KEEP', other.procedures)
        self.assertNotIn(request['id'], other.requests)
        self.assertFalse(set(ws.sources) & set(other.sources))
        again = self.open()
        returned = Workspace(again['folder'])
        self.assertTrue(again['reused'])
        self.assertEqual(again['workspace_id'], first['workspace_id'])
        self.assertEqual(returned.head, old_head)
        self.assertEqual(fingerprint(returned.root), before)
        self.assertIn('USER-KEEP', returned.procedures)
        self.assertIn(request['id'], returned.requests)

    def test_fresh_creates_new_uuid_and_preserves_completed_workspace(self):
        first = self.open('JS')
        before = fingerprint(first['folder'])
        second = self.open('JS', fresh=True)
        self.assertFalse(second['reused'])
        self.assertNotEqual(first['workspace_id'], second['workspace_id'])
        self.assertNotEqual(Path(first['folder']), Path(second['folder']))
        self.assertEqual(fingerprint(first['folder']), before)
        self.assertEqual(self.open('JS')['workspace_id'], second['workspace_id'])

    def test_parent_has_only_cash_investments_capital_and_five_drafts(self):
        result = self.open('JS')
        ws = Workspace(result['folder'])
        checks = []
        record = validate_workspace(ws, 'JS', checks)
        self.assertEqual((record['modules'], record['current_ledger_links']), (1, 0))
        self.assertEqual(set(ws.procedures), PARENT_PROCEDURES)
        self.assertEqual(result['company_kind'], 'parent')
        view = validate_data_folder(ws, 'JS', checks)
        self.assertEqual((view['input_files'], view['extracted_workbooks']), (1, 0))

    def test_balanced_journal_omission_fails_independent_controls(self):
        outcome = balanced_omission(RESOURCES)
        self.assertEqual(outcome['remaining_debit_minus_credit'], 0)
        self.assertTrue(outcome['blocked_by_independent_controls'])
        self.assertGreater(outcome['independent_control_failures'], 0)

    def test_current_raw_data_view_exact_pack_bytes_without_new_evidence(self):
        result = self.open()
        ws = Workspace(result['folder'])
        before = fingerprint(ws.root)
        record = validate_data_folder(ws, 'JS_ELEC', [])
        self.assertEqual((record['input_files'], record['extracted_workbooks']), (15, 16))
        self.assertEqual(fingerprint(ws.root), before)
        self.assertEqual(result['company_kind'], 'subsidiary')

    def test_readable_raw_workbook_tamper_blocks_view_and_reopening(self):
        result = self.open()
        ws = Workspace(result['folder'])
        copied = sorted((Path(result['folder']).parent/'원천엑셀').rglob('*.xlsx'))[0]
        copied.write_bytes(copied.read_bytes()+b'TAMPER')
        before = fingerprint(ws.root.parent)
        with self.assertRaises(AuditError):
            sector_demo.data_folder(ws)
        with self.assertRaises(AuditError):
            self.open()
        self.assertEqual(fingerprint(ws.root.parent), before)

    def test_readable_raw_workbook_missing_blocks_without_regeneration(self):
        result = self.open()
        ws = Workspace(result['folder'])
        copied = sorted((Path(result['folder']).parent/'원천엑셀').rglob('*.xlsx'))[0]
        copied.unlink()
        before = fingerprint(ws.root.parent)
        with self.assertRaises(AuditError):
            sector_demo.data_folder(ws)
        with self.assertRaises(AuditError):
            self.open()
        self.assertEqual(fingerprint(ws.root.parent), before)

    def test_explicit_save_request_and_workpaper_review_history_survives_switch(self):
        first = self.open()
        ws = Workspace(first['folder'])
        record = exercise_saved_history(ws, [])
        self.assertEqual((record['events_added'], record['request_versions'], record['procedure_versions']), (6, 3, 3))
        before = fingerprint(ws.root)
        self.open('JS_AUTO')
        again = self.open()
        self.assertEqual(fingerprint(again['folder']), before)
        returned = Workspace(again['folder'])
        self.assertEqual(returned.procedures['C02']['state'], '검토기록완료')
        self.assertEqual(returned.procedures['C02']['reviewer'], '합성 검토담당')

    def test_event_history_schema_tamper_blocks_without_repair(self):
        import sqlite3
        first = self.open('JS')
        ws = Workspace(first['folder'])
        db = sqlite3.connect(ws.dbpath)
        try:
            db.execute('DROP TRIGGER no_event_update')
            db.commit()
        finally:
            db.close()
        before = fingerprint(ws.root)
        with self.assertRaises(AuditError):
            self.open('JS')
        self.assertEqual(fingerprint(ws.root), before)

    def test_resource_tamper_blocks_new_session_and_preserves_previous(self):
        resources = self.resource_copy()
        first = self.open(resources=resources)
        before = fingerprint(first['folder'])
        path = self.company_xlsx(resources)
        path.write_bytes(path.read_bytes()+b'TAMPER')
        with self.assertRaises(AuditError):
            self.open(resources=resources, fresh=True)
        self.assertEqual(fingerprint(first['folder']), before)

    def test_missing_resource_is_rejected(self):
        resources = self.resource_copy()
        self.company_xlsx(resources).unlink()
        with self.assertRaises(AuditError):
            self.open(resources=resources)

    def test_unknown_and_path_shaped_company_codes_rejected(self):
        for code in ('UNKNOWN', '../JS', 'JS/JS_AUTO', 'JS_ELEC ', 'C:\\JS'):
            with self.subTest(code=code), self.assertRaises(AuditError):
                self.open(code)

    def test_resource_folder_cannot_be_used_as_storage(self):
        resources = self.resource_copy()
        before = fingerprint(resources)
        for storage in (resources, resources/'new-workspaces'):
            with self.subTest(storage=storage), self.assertRaises(AuditError):
                sector_demo.open_company('JS_ELEC', storage, resources)
        self.assertEqual(fingerprint(resources), before)

    def test_shared_folder_user_file_is_preserved(self):
        self.store.mkdir()
        user_file = self.store/'사용자자료.txt'
        user_file.write_text('원문은 덮어쓰거나 삭제하면 안 됩니다.', encoding='utf-8')
        before = user_file.read_bytes()
        try:
            result = self.open()
        except AuditError:
            pass  # Refusal is an acceptable safe response for unmanaged stores.
        else:
            self.assertNotEqual(Path(result['folder']).resolve(), self.store.resolve())
            self.assertTrue(Path(result['folder']).resolve().is_relative_to(self.store.resolve()))
        self.assertEqual(user_file.read_bytes(), before)

    def test_precancelled_creation_does_not_change_resources(self):
        before = fingerprint(RESOURCES)
        event = Event(); event.set()
        with self.assertRaises(AuditError):
            self.open(event=event)
        self.assertEqual(fingerprint(RESOURCES), before)

    def test_mid_create_failure_preserves_registry_and_previous_work(self):
        first = self.open()
        before = fingerprint(first['folder'])
        seen = []
        def fail(message):
            self.assertIsInstance(message, str)
            seen.append(message)
            if len(seen) == 4:
                raise RuntimeError('의도한 생성 중간 실패')
        with self.assertRaises((AuditError, RuntimeError)):
            self.open(fresh=True, progress=fail)
        self.assertGreaterEqual(len(seen), 4)
        self.assertEqual(fingerprint(first['folder']), before)
        selected = self.open()
        self.assertTrue(selected['reused'])
        self.assertEqual(selected['workspace_id'], first['workspace_id'])

    def test_mid_create_cancellation_preserves_previous(self):
        first = self.open()
        before = fingerprint(first['folder'])
        event = Event(); seen = []
        def cancel(message):
            seen.append(message)
            if len(seen) == 3:
                event.set()
        with self.assertRaises(AuditError):
            self.open(fresh=True, event=event, progress=cancel)
        self.assertGreaterEqual(len(seen), 3)
        self.assertEqual(fingerprint(first['folder']), before)
        self.assertEqual(self.open()['workspace_id'], first['workspace_id'])

    def test_registered_source_tamper_is_blocked_without_regeneration(self):
        first = self.open()
        ws = Workspace(first['folder'])
        source = next(iter(ws.sources.values()))
        file = ws.root/source['file']
        file.write_bytes(file.read_bytes()+b'TAMPER')
        after_tamper = fingerprint(ws.root)
        with self.assertRaises(AuditError):
            self.open()
        self.assertEqual(fingerprint(ws.root), after_tamper)

    def test_registered_source_missing_is_blocked(self):
        first = self.open()
        ws = Workspace(first['folder'])
        source = next(iter(ws.sources.values()))
        (ws.root/source['file']).unlink()
        after = fingerprint(ws.root)
        with self.assertRaises(AuditError):
            self.open()
        self.assertEqual(fingerprint(ws.root), after)

    def test_registered_store_missing_is_blocked_without_regeneration(self):
        first = self.open()
        registry = self.store/sector_demo.STORE_FILE
        registry.unlink()
        after = fingerprint(self.store)
        with self.assertRaises(AuditError):
            self.open()
        self.assertEqual(fingerprint(self.store), after)
        self.assertTrue(Path(first['folder']).is_dir())

    def test_registered_store_path_escape_is_blocked(self):
        first = self.open()
        registry = self.store/sector_demo.STORE_FILE
        data = json.loads(registry.read_text(encoding='utf-8'))
        data['companies']['JS_ELEC']['folder'] = '../outside/업무'
        registry.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        before = fingerprint(first['folder'])
        with self.assertRaises(AuditError):
            self.open()
        self.assertEqual(fingerprint(first['folder']), before)

    def test_session_owner_mismatch_is_blocked(self):
        first = self.open()
        marker = Path(first['folder']).parent/'session.json'
        data = json.loads(marker.read_text(encoding='utf-8'))
        data['store_id'] = '0'*32
        marker.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        before = fingerprint(first['folder'])
        with self.assertRaises(AuditError):
            self.open()
        self.assertEqual(fingerprint(first['folder']), before)

    def test_session_failed_state_is_not_reopened_as_complete(self):
        first = self.open()
        marker = Path(first['folder']).parent/'session.json'
        data = json.loads(marker.read_text(encoding='utf-8'))
        data['state'] = 'failed'
        marker.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        before = fingerprint(first['folder'])
        with self.assertRaises(AuditError):
            self.open()
        self.assertEqual(fingerprint(first['folder']), before)

    def test_foreign_company_database_is_not_silently_opened(self):
        first, other = self.open('JS_ELEC'), self.open('JS_AUTO')
        left, right = Workspace(first['folder']), Workspace(other['folder'])
        shutil.copyfile(right.dbpath, left.dbpath)
        shutil.copyfile(right.anchor, left.anchor)
        after = fingerprint(left.root)
        with self.assertRaises(AuditError):
            self.open('JS_ELEC')
        self.assertEqual(fingerprint(left.root), after)

    def test_unreviewed_final_export_is_blocked_without_file(self):
        outcome = self.open()
        ws = Workspace(outcome['folder'])
        path = self.folder/'검토완료로위장.xlsx'
        catalog = json.loads((ROOT/'procedure_catalog.json').read_text(encoding='utf-8'))
        with self.assertRaises(AuditError):
            exporter.export(ws, path, catalog, final=True)
        self.assertFalse(path.exists())

    def test_concurrent_same_company_cannot_create_two_active_sessions(self):
        def run():
            try:
                return self.open()
            except AuditError as exc:
                return exc
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run(), range(2)))
        success = [r for r in results if isinstance(r, dict)]
        self.assertTrue(success)
        self.assertEqual(len({r['workspace_id'] for r in success}), 1)
        self.assertEqual(sum(not r['reused'] for r in success), 1)


if __name__ == '__main__':
    unittest.main()
