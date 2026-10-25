"""Local-only release-policy mocks. No credentials, Git, API or EXE execution."""
from pathlib import Path
import copy
from contextlib import nullcontext
import importlib.util
import json
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT.parents[1] / '검증' / 'v1.9.0' / 'release-policy-tests'


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = load('_release_v19_test', 'github_release_v19.py')
package = load('_package_v19_test', 'package_v19.py')
previous = load('_package_v181_test', 'package_v181.py')


def proof():
    return {'schema': release.PROOF_SCHEMA, 'version': '1.9.0', 'status': 'passed',
            'unit': {'tests': 830, 'errors': 0, 'failures': 0, 'skipped': 0},
            'headless': {'source': {'ok': True, 'checks': ['MOCK-SYMBOLIC-ASSERTION-ONLY']},
                         'frozen': {'ok': True, 'checks': ['MOCK-SYMBOLIC-ASSERTION-ONLY']}},
            'source_frozen_observations_identical': True, 'portable_layout_verified': True,
            'icon_embedded_verified': True, 'unicode_roundtrip_verified': True,
            'current_actual_model_calls': 0,
            'ime': {'current_actual_key_test': False, 'baseline_version': '1.8.1',
                    'baseline_evidence_sha256': 'a' * 64,
                    'scope': 'MOCK ONLY / 기존 IME 재사용·현재 Unicode 왕복. 실제 키테스트 아님.'},
            'build_inputs': {name: 'b' * 64 for name in release.BUILD_REQUIRED},
            'exe': {'name': package.EXE_NAME, 'bytes': 100, 'sha256': 'c' * 64}}


class FakeAPI:
    def __init__(self):
        self.calls = []

    def inspect(self):
        return {'head': release.BASE_COMMIT, 'tag_exists': False, 'release': None,
                'repo_id': 1, 'previous_releases': {}}

    def call(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError('No real API call is permitted in this test')


class ReleasePolicyTests(unittest.TestCase):
    def setUp(self):
        QA.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=QA)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def baseline(self, force_mock=False):
        actual = package.PROJECT / '릴리스/js-audit-suite-v1.8.1-source.zip'
        if actual.is_file() and not force_mock:
            return actual, nullcontext()
        # Public CI has no packaged baseline ZIP. Exercise its exact public path
        # manifest with clearly labelled dummy bytes, without a download/skip.
        dummy = self.folder / 'MOCK-v181-source.zip'
        payloads = {name: ('MOCK BASELINE PATH ONLY / ' + name).encode('utf-8') for name in release.BASELINE_PATHS}
        previous.write_archive(dummy, payloads, package.SOURCE_PREFIX)
        return dummy, patch.object(package, 'BASELINE_SOURCE_SHA256', package.sha(dummy.read_bytes()))

    def windows(self, change=None):
        record = proof()
        exe = b'MZ' + bytes(98)
        record['exe'].update(bytes=len(exe), sha256=package.sha(exe))
        record.update(supported_scope=release.SUPPORTED_SCOPE,
                      source={'name': package.SOURCE_NAME, 'files': 1758, 'previous_public_paths_preserved': 1739,
                              'sha256': 'd' * 64})
        payloads = {'실행파일/' + package.EXE_NAME: exe,
                    '실행파일/portable-config.json': previous.json_bytes({'schema_version': 1, 'data_directory': '../데이터/회사별업무'}),
                    package.VALIDATION_NAME: previous.json_bytes(record), 'README.md': b'MOCK ONLY'}
        if change:
            change(payloads)
        payloads['파일목록_SHA256.json'] = previous.json_bytes([
            {'file': name, 'bytes': len(raw), 'sha256': package.sha(raw)} for name, raw in payloads.items()])
        path = self.folder / 'MOCK-Windows.zip'
        previous.write_archive(path, payloads, package.WINDOWS_PREFIX, empty_directories=('데이터/회사별업무/',))
        return record, {package.SOURCE_NAME: {'sha256': 'd' * 64}}, path

    def test_import_does_not_start_process_or_contact_api(self):
        with patch('subprocess.run', side_effect=AssertionError('process forbidden')):
            load('_import_only_release19', 'github_release_v19.py')
            load('_import_only_package19', 'package_v19.py')

    def test_version_baseline_and_four_previous_tags_are_pinned(self):
        self.assertEqual(release.BASE_COMMIT, 'd9d3c18459eddce6a01d51b9bafbce441782cc16')
        self.assertEqual(set(release.PREVIOUS_RELEASES), {'v1.7.0', 'v1.7.1', 'v1.8.0', 'v1.8.1'})
        self.assertEqual(len(release.OLD_WORKFLOW_PATHS), 4)
        self.assertEqual(release.TAG, 'v1.9.0')
        self.assertEqual(len(release.NEW_REQUIRED), 19)
        self.assertFalse(hasattr(release, 'revise'))

    def test_ci_bytes_and_new_headless_empty_output_contract(self):
        data = (ROOT / 'ci/audit-suite-v19.yml').read_bytes()
        self.assertEqual(data, release.DEFAULT_WORKFLOW.encode('utf-8'))
        self.assertIn(b"python-version: ['3.12', '3.14']", data)
        self.assertIn(b'tools/verify_headless_v19.py --directory', data)
        self.assertIn(b'${{ runner.temp }}', data)
        self.assertIn(b'tools/test_release_v19.py', data)
        self.assertNotIn(b'contents: write', data)

    def test_complete_mock_proof_has_explicit_zero_model_calls_and_prior_ime(self):
        release.validate_proof(proof())

    def test_missing_failed_or_skipped_local_proof_is_rejected(self):
        changes = [('status', 'pending'), ('unicode_roundtrip_verified', False),
                   ('source_frozen_observations_identical', False), ('portable_layout_verified', False),
                   ('icon_embedded_verified', False), ('current_actual_model_calls', 1)]
        for key, value in changes:
            with self.subTest(key=key):
                record = proof(); record[key] = value
                with self.assertRaises(RuntimeError): release.validate_proof(record)
        for key in ('errors', 'failures', 'skipped'):
            record = proof(); record['unit'][key] = 1
            with self.subTest(unit=key), self.assertRaises(RuntimeError): release.validate_proof(record)

    def test_different_symbolic_business_assertions_are_rejected(self):
        record = proof(); record['headless']['frozen']['checks'] = ['DIFFERENT-MOCK']
        with self.assertRaises(RuntimeError): release.validate_proof(record)

    def test_prior_ime_or_ai_cannot_be_relabelled_as_current_real_measurement(self):
        for key in ('actual_hardware_ime_test', 'actual_local_inference'):
            record = proof(); record[key] = True
            with self.subTest(key=key), self.assertRaises(RuntimeError): release.validate_proof(record)
        record = proof(); record['ime']['current_actual_key_test'] = True
        with self.assertRaises(RuntimeError): release.validate_proof(record)

    def test_build_manifest_requires_new_tools_registry_and_application(self):
        for name in ('app.py', 'audit_archive.py', 'form_registry.json', 'tools/package_v19.py', 'ci/audit-suite-v19.yml'):
            record = proof(); record['build_inputs'].pop(name)
            with self.subTest(name=name), self.assertRaises(RuntimeError): release.validate_proof(record)

    def test_public_policy_blocks_private_files_but_allows_new_metadata(self):
        for name in ('업무.sqlite3', '검증/final-validation.json', 'models/model.gguf',
                     'tools/credentials.json', '../outside.py', '.github/workflows/evil.yml',
                     '문서/원본기준서.pdf', '문서/원본기준서.pdf.zip'):
            with self.subTest(name=name), self.assertRaises(RuntimeError): release.allowed_public_path(name)
        for name in release.NEW_REQUIRED:
            release.allowed_public_path(name)
        release.allowed_public_path('.runtime/tcl_library/cookiejar/public_suffix_list.dat.gz')

    def test_actual_1739_file_baseline_is_retained_by_allowlist(self):
        baseline_path, context = self.baseline()
        with context:
            old = package.baseline_payloads(release, previous, baseline_path)
            self.assertEqual(len(old), 1739)
            self.assertEqual(set(old), release.BASELINE_PATHS)
            source = self.folder / 'mock-source'; source.mkdir()
            for name in release.NEW_REQUIRED | release.HISTORICAL_UPDATES:
                path = source / name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(release.DEFAULT_WORKFLOW.encode('utf-8') if name == 'ci/audit-suite-v19.yml' else b'MOCK NEW FILE ONLY')
            payloads, baseline = package.source_payloads(release, previous, baseline=baseline_path, source=source)
            self.assertEqual(set(payloads), set(old) | release.NEW_REQUIRED)
            self.assertEqual(len(payloads), 1758)
            for name in old:
                self.assertEqual(payloads[name], (source / name).read_bytes() if name in release.HISTORICAL_UPDATES else old[name])
            self.assertEqual(baseline, old)

    def test_previous_tools_and_dataset_bytes_are_immutable(self):
        source = self.folder / 'mock-source'; source.mkdir()
        for name in release.NEW_REQUIRED | release.HISTORICAL_UPDATES:
            path = source / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(release.DEFAULT_WORKFLOW.encode('utf-8') if name == 'ci/audit-suite-v19.yml' else b'MOCK NEW FILE ONLY')
        baseline_path, context = self.baseline()
        with context:
            for name in ('tools/package_v181.py', 'ci/audit-suite-v181.yml'):
                path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'forbidden mutation')
                with self.subTest(name=name), self.assertRaises(RuntimeError):
                    package.source_payloads(release, previous, baseline=baseline_path, source=source)
                path.unlink()

    def test_public_ci_mock_baseline_needs_no_download_or_skip(self):
        baseline_path, context = self.baseline(force_mock=True)
        with context, patch('subprocess.run', side_effect=AssertionError('process forbidden')):
            old = package.baseline_payloads(release, previous, baseline_path)
        self.assertEqual(set(old), release.BASELINE_PATHS)
        self.assertTrue(all(raw.startswith(b'MOCK BASELINE PATH ONLY') for raw in old.values()))

    def test_windows_zip_matches_current_exe_report_config_and_file_manifest(self):
        record, assets, path = self.windows()
        release.validate_current_evidence(record, assets, path)

    def test_windows_zip_rejects_original_pdf_or_business_db(self):
        for name in ('문서/공식원본.pdf', '데이터/회사별업무/업무.sqlite3'):
            with self.subTest(name=name):
                record, assets, path = self.windows(lambda payloads: payloads.__setitem__(name, b'forbidden'))
                with self.assertRaises(RuntimeError): release.validate_current_evidence(record, assets, path)
                path.unlink()

    def test_windows_zip_rejects_different_portable_data_location(self):
        record, assets, path = self.windows(lambda payloads: payloads.__setitem__(
            '실행파일/portable-config.json', previous.json_bytes({'schema_version': 1, 'data_directory': 'C:/outside'})))
        with self.assertRaises(RuntimeError): release.validate_current_evidence(record, assets, path)

    def test_existing_different_local_artifact_is_not_overwritten(self):
        target = self.folder / 'keep.zip'; target.write_bytes(b'old bytes')
        with self.assertRaises(RuntimeError):
            package.write_new_or_identical(previous, self.folder, target.name, b'new bytes')
        self.assertEqual(target.read_bytes(), b'old bytes')
        package.write_new_or_identical(previous, self.folder, target.name, b'old bytes')

    def test_packager_missing_final_validation_stops_before_outputs(self):
        with self.assertRaises(RuntimeError):
            package.current_checks(release, previous, source=self.folder, project=self.folder)
        self.assertFalse((self.folder / '릴리스').exists())
        self.assertFalse((self.folder / '배포').exists())

    def test_current_checks_pin_mock_exe_every_build_input_and_portable_config(self):
        source = self.folder / 'source'; source.mkdir()
        project = self.folder / 'project'; project.mkdir()
        record = proof()
        for name in record['build_inputs']:
            path = source / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'MOCK BUILD INPUT ONLY')
        config = previous.json_bytes({'schema_version': 1, 'data_directory': '../데이터/회사별업무'})
        (source / 'assets/portable-config.json').write_bytes(config)
        record['build_inputs'] = {name: package.sha((source / name).read_bytes()) for name in record['build_inputs']}
        exe = bytearray(100); exe[:2] = b'MZ'; struct.pack_into('<I', exe, 60, 64); exe[64:68] = b'PE\0\0'
        executable = project / '실행파일' / package.EXE_NAME; executable.parent.mkdir()
        executable.write_bytes(exe); (executable.parent / 'portable-config.json').write_bytes(config)
        record['exe'].update(bytes=len(exe), sha256=package.sha(exe))
        ime = project / '검증/실제한글입력.json'; ime.parent.mkdir()
        ime.write_bytes(previous.json_bytes({'status': 'passed', 'scope': 'MOCK ONLY / not a real measurement'}))
        record['ime']['baseline_evidence_sha256'] = package.sha(ime.read_bytes())
        final = project / '검증/v1.9.0/final-validation.json'; final.parent.mkdir()
        final.write_bytes(previous.json_bytes(record))
        result, data, settings = package.current_checks(release, previous, source=source, project=project)
        self.assertEqual(result, record); self.assertEqual(data, exe); self.assertEqual(settings, config)
        (source / 'audit_archive.py').write_bytes(b'changed after mock verification')
        with self.assertRaises(RuntimeError): package.current_checks(release, previous, source=source, project=project)

    def test_stage_invalid_evidence_makes_no_api_write_or_state(self):
        api = FakeAPI()
        state = self.folder / 'state.json'
        with patch.object(release, 'STATE', state), patch.object(release, 'CHECKOUT', self.folder / 'checkout'), \
             patch.object(release, 'local_artifacts', side_effect=RuntimeError('mock incomplete evidence')):
            with self.assertRaises(RuntimeError): release.stage(api, release.DEFAULT_WINDOWS_NAME)
        self.assertEqual(api.calls, [])
        self.assertFalse(state.exists())

    def test_publish_pending_ci_never_creates_tag_or_modifies_release(self):
        api = FakeAPI()
        with patch.object(release, 'load_state', return_value={'phase': 'STAGED'}), \
             patch.object(release, 'pinned_artifacts', return_value=({}, {})), \
             patch.object(release, 'status', return_value={'runs': []}):
            with self.assertRaises(RuntimeError): release.publish(api)
        self.assertEqual(api.calls, [])

    def test_single_child_commit_only_no_revision_chain(self):
        state = {'base': release.BASE_COMMIT, 'commit': '1' * 40, 'patch_commits': ['1' * 40]}
        self.assertEqual(release.patch_commits(state), ['1' * 40])
        state['patch_commits'] = ['2' * 40, '1' * 40]
        with self.assertRaises(RuntimeError): release.patch_commits(state)

    def test_ci_requires_both_versions_and_every_validation_step(self):
        def job(version):
            return {'name': 'Audit Suite Python ' + version, 'status': 'completed', 'conclusion': 'success',
                    'steps': [{'name': name, 'conclusion': 'success'} for name in ('Unit tests', 'Release policy mock tests', 'Headless integration')]}
        report = {'runs': [{'status': 'completed', 'conclusion': 'success', 'jobs': [job('3.12'), job('3.14')]}]}
        release.ci_gate(report)
        for name in ('Unit tests', 'Release policy mock tests', 'Headless integration'):
            changed = copy.deepcopy(report)
            next(step for step in changed['runs'][0]['jobs'][0]['steps'] if step['name'] == name)['conclusion'] = 'skipped'
            with self.subTest(name=name), self.assertRaises(RuntimeError): release.ci_gate(changed)
        changed = copy.deepcopy(report); changed['runs'][0]['jobs'][1]['name'] = 'Audit Suite Python 3.12'
        with self.assertRaises(RuntimeError): release.ci_gate(changed)

    def test_previous_release_fingerprint_includes_asset_hash_and_body(self):
        original = {'id': 1, 'body': 'keep', 'tag_name': 'v1.8.1', 'assets': [{'id': 2, 'name': 'old.zip', 'digest': 'sha256:old'}]}
        changed = copy.deepcopy(original); changed['assets'][0]['digest'] = 'sha256:changed'
        self.assertNotEqual(release.previous_release_fingerprint(original), release.previous_release_fingerprint(changed))
        changed = copy.deepcopy(original); changed['body'] = 'changed'
        self.assertNotEqual(release.previous_release_fingerprint(original), release.previous_release_fingerprint(changed))


if __name__ == '__main__':
    unittest.main(verbosity=2)
