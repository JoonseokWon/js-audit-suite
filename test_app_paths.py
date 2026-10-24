"""Isolated portable-location policy checks; no UI or live company data access."""
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import app_paths
from common import AuditError


class PortablePathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '통합감사 프로그램'
        self.exe_dir = self.root / '실행파일'
        self.exe_dir.mkdir(parents=True)
        self.exe = self.exe_dir / '통합 회계감사.exe'
        self.exe.write_bytes(b'not an executable; path fixture only')
        self.config = self.exe_dir / app_paths.CONFIG_FILE

    def write(self, directory='../데이터/회사별업무', **overrides):
        config = {'schema_version': 1, 'data_directory': directory, **overrides}
        self.config.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')

    def resolve(self):
        return app_paths.portable_storage_root(executable=self.exe, frozen=True)

    def test_missing_config_keeps_legacy_policy_without_write_probe(self):
        with patch.object(app_paths.tempfile, 'TemporaryFile') as probe:
            self.assertIsNone(self.resolve())
        probe.assert_not_called()

    def test_source_ignores_config_including_invalid_config(self):
        self.config.write_text('invalid json', encoding='utf-8')
        with patch.object(app_paths.tempfile, 'TemporaryFile') as probe:
            self.assertIsNone(app_paths.portable_storage_root(executable=self.exe, frozen=False))
        probe.assert_not_called()

    def test_supported_sibling_path_and_no_store_creation(self):
        self.write()
        expected = self.root / '데이터/회사별업무'
        self.assertEqual(self.resolve(), expected.resolve())
        self.assertFalse(expected.exists())
        self.assertEqual(sorted(p.name for p in self.exe_dir.iterdir()), sorted([self.exe.name, self.config.name]))

    def test_child_path_stays_within_application_root(self):
        self.write('자료/회사별업무')
        self.assertEqual(self.resolve(), (self.exe_dir / '자료/회사별업무').resolve())

    def test_current_working_directory_does_not_select_config_or_data(self):
        self.write()
        unrelated = Path(self.temp.name) / '다른 현재 폴더'
        unrelated.mkdir()
        (unrelated / app_paths.CONFIG_FILE).write_text('invalid unrelated config', encoding='utf-8')
        before = Path.cwd()
        try:
            os.chdir(unrelated)
            self.assertEqual(self.resolve(), (self.root / '데이터/회사별업무').resolve())
        finally:
            os.chdir(before)

    def test_production_arguments_use_frozen_and_executable_not_source_directory(self):
        self.write()
        with patch.object(app_paths.sys, 'frozen', True, create=True), patch.object(app_paths.sys, 'executable', str(self.exe)):
            self.assertEqual(app_paths.portable_storage_root(), (self.root / '데이터/회사별업무').resolve())

    def test_schema_rejects_missing_extra_bool_and_unknown_versions(self):
        bad = [[], None, {}, {'schema_version': 1}, {'data_directory': '자료'},
               {'schema_version': True, 'data_directory': '자료'},
               {'schema_version': '1', 'data_directory': '자료'},
               {'schema_version': 2, 'data_directory': '자료'},
               {'schema_version': 1, 'data_directory': '자료', 'unknown': 'ignored?'}]
        for config in bad:
            with self.subTest(config=config):
                self.config.write_text(json.dumps(config), encoding='utf-8')
                with self.assertRaises(AuditError):
                    self.resolve()

    def test_duplicate_keys_and_invalid_json_are_errors_not_fallbacks(self):
        for raw in ('', '{', '{"schema_version":1,"data_directory":"자료","data_directory":"다른자료"}', '\ufeff{bad json}'):
            with self.subTest(raw=raw):
                self.config.write_text(raw, encoding='utf-8')
                with self.assertRaises(AuditError):
                    self.resolve()

    def test_optional_utf8_bom_is_accepted(self):
        self.config.write_text('\ufeff'+json.dumps({'schema_version':1,'data_directory':'../데이터/회사별업무'}, ensure_ascii=False), encoding='utf-8')
        self.assertEqual(self.resolve(), (self.root / '데이터/회사별업무').resolve())

    def test_path_policy_blocks_absolute_drives_escapes_and_ambiguous_components(self):
        bad = ['C:/Users/data', 'C:data', '//server/share', '/tmp/data', '\\server\\share',
               '../../outside', '../..', '자료/../밖', '../자료/../밖', '..', '.',
               '자료//업무', './자료', '../자료/', '../자료.', '../자료 ', '', None, 42,
               '../자료\x00', '../자료\n업무', '..\\자료']
        for directory in bad:
            with self.subTest(directory=directory):
                self.write(directory)
                with self.assertRaises(AuditError):
                    self.resolve()

    def test_existing_file_is_not_a_data_directory(self):
        file = self.root / '자료파일'
        file.write_bytes(b'preserve')
        self.write('../자료파일')
        with self.assertRaises(AuditError):
            self.resolve()
        self.assertEqual(file.read_bytes(), b'preserve')

    def test_existing_directory_is_not_modified(self):
        folder = self.root / '데이터/회사별업무'
        folder.mkdir(parents=True)
        marker = folder / 'store.json'
        marker.write_text('existing-store-preserved', encoding='utf-8')
        self.write()
        self.assertEqual(self.resolve(), folder.resolve())
        self.assertEqual(marker.read_text(encoding='utf-8'), 'existing-store-preserved')

    def test_readonly_execution_directory_is_a_clear_error(self):
        self.write()
        with patch.object(app_paths.tempfile, 'TemporaryFile', side_effect=PermissionError('owned test fixture')):
            with self.assertRaisesRegex(AuditError, '쓰기 권한'):
                self.resolve()

    def test_oversize_config_is_rejected_before_json_parse(self):
        self.config.write_bytes(b' ' * (app_paths.MAX_CONFIG_BYTES + 1))
        with self.assertRaises(AuditError):
            self.resolve()

    def test_directory_named_config_is_not_a_configuration_file(self):
        self.config.mkdir()
        with self.assertRaises(AuditError):
            self.resolve()

    def test_config_cannot_redirect_to_program_root_or_execution_directory(self):
        for relative in ('../실행파일', '../데이터/../', '資料/..'):
            with self.subTest(relative=relative):
                self.write(relative)
                with self.assertRaises(AuditError):
                    self.resolve()


if __name__ == '__main__':
    unittest.main(verbosity=2)
