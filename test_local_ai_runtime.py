"""Portable AI setup tests: all HTTP/process activity is mocked, no live server."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

import local_ai_runtime as ai


class Response(io.BytesIO):
    status = 200

    def __init__(self, data=b'', url='https://github.com/ollama/ollama/releases/download/v0.40.7/test.zip', headers=None):
        super().__init__(data)
        self.url = url
        self.headers = headers or {}

    def geturl(self):
        return self.url


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'private-ai'
        self.ai = ai.LocalAIRuntime(self.root)
        self.http = patch.object(ai.http.client, 'HTTPConnection', side_effect=AssertionError('Unexpected live HTTP')).start()
        self.addCleanup(patch.stopall)
        self.popen = patch.object(ai.subprocess, 'Popen', side_effect=AssertionError('Unexpected process')).start()
        self.ai._json_api = Mock(side_effect=OSError('offline'))

    def tiny_zip(self, name='regular.zip', files=None):
        self.root.mkdir(exist_ok=True)
        p = self.root / name
        with zipfile.ZipFile(p, 'w', zipfile.ZIP_DEFLATED) as z:
            for path, data in (files or {'ollama.exe': b'portable runtime', 'lib/test.dll': b'library'}).items():
                z.writestr(path, data)
        return p

    def installed(self):
        z = self.tiny_zip()
        self.ai.runtime.mkdir()
        records = self.ai._archive_records([z], stage=self.ai.runtime)
        self.ai._write_install(records, [z])
        return z

    def tags(self, **overrides):
        row = {'name': ai.MODEL, 'model': ai.MODEL, 'digest': 'sha256:' + ai.MODEL_DIGEST, 'size': ai.MODEL_BLOB_BYTES}
        row.update(overrides)
        return {'models': [row]}

    def online(self, tags=None):
        self.ai._json_api = Mock(side_effect=lambda path, *a, **k: {'version': ai.VERSION} if path == '/api/version' else (tags or self.tags()))

    def info(self, data=b'archive data'):
        return {'name': 'test.zip', 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

    def download_response(self, data, **kwargs):
        opener = Mock()
        opener.open.return_value = Response(data, **kwargs)
        patch.object(ai, 'build_opener', return_value=opener).start()
        return opener

    def pull_response(self, items):
        data = b''.join((json.dumps(x).encode() + b'\n') if not isinstance(x, bytes) else x for x in items)
        conn = Mock()
        conn.getresponse.return_value = Response(data)
        conn.sock = None
        self.http.side_effect = None
        self.http.return_value = conn
        self.ai.status = Mock(return_value={'model': True})
        return conn

    def test_constructor_no_side_effects(self):
        self.assertFalse(self.root.exists())
        self.http.assert_not_called()
        self.popen.assert_not_called()
        self.assertEqual(self.ai.base_url, 'http://127.0.0.1:11437')
        self.assertEqual(self.ai.model, 'qwen3:4b-instruct-2507-q4_K_M')

    def test_source_default_root(self):
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(ai.default_root(), Path(ai.__file__).resolve().parent / '배포' / '로컬AI')

    def test_frozen_default_root(self):
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(Path(self.temp.name) / 'app.exe')):
            self.assertEqual(ai.default_root(), Path(self.temp.name).resolve() / '로컬AI')

    def test_drive_root_rejected(self):
        with self.assertRaises(ai.LocalAIError):
            ai.LocalAIRuntime(Path(self.temp.name).anchor)

    def test_status_missing_runtime(self):
        state = self.ai.status()
        self.assertFalse(state['ready'])
        self.assertFalse(state['runtime'])
        self.popen.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_status_ready_requires_three_layers(self):
        self.installed()
        self.online()
        self.assertTrue(self.ai.status()['ready'])
        self.assertFalse(self.ai.status()['owned_server'])

    def test_model_mismatch_cases(self):
        self.installed()
        for changes in ({'digest': '0' * 64}, {'name': 'qwen3:8b'}, {'model': 'qwen3:8b'}, {'size': True}, {'size': 0}, {'size': 5 * 1024**3}):
            with self.subTest(changes=changes):
                self.online(self.tags(**changes))
                self.assertFalse(self.ai.status()['model'])
                self.assertFalse(self.ai.status()['ready'])

    def test_manifest_tamper_and_missing_file(self):
        self.installed()
        self.assertTrue(self.ai._runtime_ok())
        self.ai.exe.write_bytes(b'changed runtime!')
        self.assertFalse(self.ai._runtime_ok())
        self.ai.exe.unlink()
        self.assertFalse(self.ai._runtime_ok())

    def test_malformed_manifest_not_ready(self):
        self.installed()
        for data in (b'[]', b'null', b'{broken', b'{"schema":"bad"}'):
            self.ai.manifest.write_bytes(data)
            self.assertFalse(self.ai._runtime_ok())

    def test_manifest_path_escape_rejected(self):
        self.installed()
        m = json.loads(self.ai.manifest.read_bytes())
        m['files'][0]['path'] = '../outside.exe'
        self.ai.manifest.write_text(json.dumps(m))
        self.assertFalse(self.ai._runtime_ok())

    def test_archive_path_rejection(self):
        for name in ('../outside', '/absolute', 'C:/outside', 'a\\b', 'a/./b', 'a//b', 'CON.txt', 'name.', 'name ', 'a\x00b'):
            with self.subTest(name=name), self.assertRaises(ai.LocalAIError):
                ai._safe(self.root, name)

    def test_archive_symlink_rejected(self):
        z = self.root / 'link.zip'
        self.root.mkdir()
        with zipfile.ZipFile(z, 'w') as f:
            entry = zipfile.ZipInfo('ollama.exe')
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            f.writestr(entry, '../target')
        with self.assertRaises(ai.LocalAIError):
            self.ai._archive_records([z])

    def test_archive_case_duplicate_rejected(self):
        z = self.tiny_zip(files={'ollama.exe': b'a', 'OLLAMA.EXE': b'b'})
        with self.assertRaises(ai.LocalAIError):
            self.ai._archive_records([z])

    def test_archive_missing_executable_rejected(self):
        z = self.tiny_zip(files={'not-runtime.txt': b'x'})
        with self.assertRaises(ai.LocalAIError):
            self.ai._archive_records([z])

    def test_archive_size_bound(self):
        z = self.tiny_zip()
        with patch.object(ai, 'MAX_EXPANDED', 1), self.assertRaises(ai.LocalAIError):
            self.ai._archive_records([z])

    def test_archive_ratio_bound(self):
        z = self.tiny_zip(files={'ollama.exe': b'0' * 1000000})
        with self.assertRaises(ai.LocalAIError):
            self.ai._archive_records([z])

    def test_archive_compression_rejected(self):
        self.root.mkdir()
        z = self.root / 'bz.zip'
        with zipfile.ZipFile(z, 'w', zipfile.ZIP_BZIP2) as f:
            f.writestr('ollama.exe', b'x')
        with self.assertRaises(ai.LocalAIError):
            self.ai._archive_records([z])

    def test_adopt_existing_pinned_cache(self):
        z = self.installed()
        self.ai.manifest.unlink()
        data = z.read_bytes()
        info = self.info(data)
        self.ai.cache.mkdir()
        (self.ai.cache / info['name']).write_bytes(data)
        with patch.object(ai, 'ARCHIVES', {'regular': info, 'rocm': {'name': 'absent.zip'}}):
            self.assertTrue(self.ai._adopt())
        self.http.assert_not_called()
        self.popen.assert_not_called()

    def test_adopt_changed_file_rejected(self):
        z = self.installed()
        self.ai.manifest.unlink()
        info = self.info(z.read_bytes())
        self.ai.cache.mkdir()
        (self.ai.cache / info['name']).write_bytes(z.read_bytes())
        self.ai.exe.write_bytes(b'tampered')
        with patch.object(ai, 'ARCHIVES', {'regular': info, 'rocm': {'name': 'absent.zip'}}):
            self.assertFalse(self.ai._adopt())
        self.assertFalse(self.ai.manifest.exists())

    def test_download_exact_sha_and_size(self):
        data = b'exact pinned bytes'
        opener = self.download_response(data, headers={'Content-Length': str(len(data))})
        result = self.ai._download(self.info(data), None, None)
        self.assertEqual(result.read_bytes(), data)
        opener.open.assert_called_once()
        self.assertFalse(list(self.ai.cache.glob('*.part')))

    def test_download_cached_without_network(self):
        data = b'cached'
        info = self.info(data)
        self.ai.cache.mkdir(parents=True)
        (self.ai.cache / info['name']).write_bytes(data)
        with patch.object(ai, 'build_opener', side_effect=AssertionError('No network')):
            self.assertEqual(self.ai._download(info, None, None).read_bytes(), data)

    def test_corrupt_cache_preserved(self):
        self.ai.cache.mkdir(parents=True)
        target = self.ai.cache / 'test.zip'
        target.write_bytes(b'bad')
        with self.assertRaises(ai.LocalAIError):
            self.ai._download(self.info(), None, None)
        self.assertEqual(target.read_bytes(), b'bad')

    def test_download_bad_length_rejected(self):
        self.download_response(b'x', headers={'Content-Length': '999'})
        with self.assertRaises(ai.LocalAIError):
            self.ai._download(self.info(b'x'), None, None)
        self.assertFalse((self.ai.cache / 'test.zip').exists())
        self.assertFalse(list(self.ai.cache.glob('*.part')))

    def test_download_bad_hash_rejected(self):
        self.download_response(b'wrong')
        with self.assertRaises(ai.LocalAIError):
            self.ai._download(self.info(b'exact'), None, None)
        self.assertFalse((self.ai.cache / 'test.zip').exists())

    def test_download_wrong_final_host_rejected(self):
        self.download_response(b'x', url='https://attacker.invalid/file')
        with self.assertRaises(ai.LocalAIError):
            self.ai._download(self.info(b'x'), None, None)

    def test_official_url_restrictions(self):
        for url in ('http://github.com/a', 'https://github.com.evil/a', 'https://user:pass@github.com/a', 'https://github.com:444/a', 'https://github.com:invalid/a'):
            with self.subTest(url=url), self.assertRaises(ai.LocalAIError):
                ai._official(url)

    def test_download_cancel_removes_own_part(self):
        event = threading.Event()
        event.set()
        self.download_response(b'x')
        with self.assertRaises(ai.LocalAICancelled):
            self.ai._download(self.info(b'x'), event, None)
        self.assertFalse((self.ai.cache / 'test.zip').exists())
        self.assertFalse(list(self.ai.cache.glob('*.part')))

    def test_environment_private_and_no_secret_inheritance(self):
        old = os.environ.copy()
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'secret', 'OLLAMA_HOST': '0.0.0.0:11434', 'HTTP_PROXY': 'http://secret'}, clear=False):
            env = self.ai._environment()
            self.assertNotIn('OPENAI_API_KEY', env)
            self.assertNotIn('HTTP_PROXY', env)
            self.assertEqual(env['OLLAMA_HOST'], '127.0.0.1:11437')
            self.assertEqual(env['OLLAMA_NO_CLOUD'], '1')
            self.assertTrue(Path(env['USERPROFILE']).is_relative_to(self.root))
            self.assertTrue(Path(env['OLLAMA_MODELS']).is_relative_to(self.root))
            self.assertEqual(os.environ['OPENAI_API_KEY'], 'secret')
        self.assertEqual(os.environ, old)

    def test_existing_server_reused_never_stopped(self):
        self.installed()
        self.online()
        self.assertTrue(self.ai.ensure_server()['ready'])
        self.popen.assert_not_called()
        self.assertFalse(self.ai.stop())

    def test_missing_model_does_not_fake_ready_or_pull(self):
        self.installed()
        self.online({'models': []})
        self.assertFalse(self.ai.ensure_server()['ready'])
        self.http.assert_not_called()

    def test_wrong_server_version_blocks_spawn(self):
        self.installed()
        self.ai._json_api = Mock(return_value={'version': 'other'})
        with self.assertRaises(ai.LocalAIError):
            self.ai.ensure_server()
        self.popen.assert_not_called()

    def test_owned_spawn_is_hidden_private_and_stoppable(self):
        self.installed()
        self.ai._json_api = Mock(side_effect=[OSError('offline'), {'version': ai.VERSION}, {'version': ai.VERSION}, self.tags()])
        proc = Mock()
        proc.poll.return_value = None
        self.popen.side_effect = None
        self.popen.return_value = proc
        self.assertTrue(self.ai.ensure_server()['ready'])
        kwargs = self.popen.call_args.kwargs
        self.assertEqual(kwargs['creationflags'], getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertFalse(kwargs['shell'])
        self.assertEqual(kwargs['env']['OLLAMA_HOST'], '127.0.0.1:11437')
        self.assertEqual(json.loads((self.ai.profile / '.ollama/server.json').read_bytes()), {'disable_ollama_cloud': True})
        self.assertTrue(self.ai.stop())
        proc.terminate.assert_called_once()
        self.assertFalse(self.ai.stop())

    def test_cancel_before_spawn(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(ai.LocalAICancelled):
            self.ai.ensure_server(event)
        self.popen.assert_not_called()

    def test_stop_kills_only_owned_timeout_process(self):
        proc = Mock()
        proc.poll.return_value = None
        proc.wait.side_effect = [subprocess.TimeoutExpired('owned', 5), 0]
        self.ai._process = proc
        self.ai.stop()
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()
        self.assertIsNone(self.ai._process)

    def test_pull_valid_success_and_tag_verified(self):
        conn = self.pull_response([{'status': 'pulling', 'completed': 2, 'total': 2}, {'status': 'success'}])
        self.ai._pull_model()
        self.assertEqual(conn.request.call_args.args[0:2], ('POST', '/api/pull'))
        self.assertEqual(json.loads(conn.request.call_args.args[2]), {'model': ai.MODEL, 'stream': True})
        conn.close.assert_called()

    def test_pull_requires_terminal_success(self):
        self.pull_response([{'status': 'pulling'}])
        with self.assertRaises(ai.LocalAIError):
            self.ai._pull_model()

    def test_pull_requires_matching_tags(self):
        self.pull_response([{'status': 'success'}])
        self.ai.status.return_value = {'model': False}
        with self.assertRaises(ai.LocalAIError):
            self.ai._pull_model()

    def test_pull_protocol_errors(self):
        cases = [[{'error': 'bad'}], [b'invalid\n'], [{}], [{'status': True}], [{'status': 'pulling', 'total': 2, 'completed': 3}], [{'status': 'pulling', 'total': True}], [{'status': 'success'}, {'status': 'pulling'}], [b'x' * 65537]]
        for rows in cases:
            with self.subTest(rows=str(rows)[:80]):
                self.pull_response(rows)
                with self.assertRaises(ai.LocalAIError):
                    self.ai._pull_model()

    def test_pull_cancel_before_request(self):
        event = threading.Event()
        event.set()
        conn = self.pull_response([])
        with self.assertRaises(ai.LocalAICancelled):
            self.ai._pull_model(event)
        conn.request.assert_not_called()

    def test_setup_explicit_full_mocked_install(self):
        z = self.tiny_zip()
        data = z.read_bytes()
        info = self.info(data)
        self.download_response(data)
        self.ai.ensure_server = Mock(return_value={'model': False})
        self.ai._process = Mock()
        self.ai._process.poll.return_value = None
        self.ai._pull_model = Mock()
        self.ai.status = Mock(return_value={'ready': True, 'model': True})
        with patch.object(ai, 'ARCHIVES', {'regular': info, 'rocm': {'name': 'optional.zip'}}), patch.object(ai.shutil, 'disk_usage', return_value=Mock(free=20 * 1024**3)):
            self.assertTrue(self.ai.setup()['ready'])
        self.assertTrue(self.ai._runtime_ok())
        self.ai._pull_model.assert_called_once()

    def test_setup_existing_ready_no_download(self):
        self.installed()
        self.ai.ensure_server = Mock(return_value={'model': True})
        self.ai.status = Mock(return_value={'ready': True})
        self.ai._download = Mock(side_effect=AssertionError('No automatic download'))
        self.assertTrue(self.ai.setup()['ready'])
        self.ai._download.assert_not_called()

    def test_setup_foreign_server_without_model_does_not_pull(self):
        self.installed()
        self.ai.ensure_server = Mock(return_value={'model': False})
        self.ai._pull_model = Mock(side_effect=AssertionError('Foreign model path must not be written'))
        with self.assertRaises(ai.LocalAIError):
            self.ai.setup()
        self.ai._pull_model.assert_not_called()

    def test_setup_low_disk_no_download(self):
        with patch.object(ai.shutil, 'disk_usage', return_value=Mock(free=1)), self.assertRaises(ai.LocalAIError):
            self.ai.setup()
        self.popen.assert_not_called()

    def test_setup_foreign_server_does_not_replace(self):
        self.ai._json_api = Mock(return_value={'version': ai.VERSION})
        with self.assertRaises(ai.LocalAIError):
            self.ai.setup()
        self.popen.assert_not_called()
        self.assertFalse(self.ai.runtime.exists())

    def test_json_api_bounded_localhost_only(self):
        self.http.side_effect = None
        conn = Mock()
        conn.getresponse.return_value = Response(b'{"version":"0.40.7"}')
        self.http.return_value = conn
        self.ai._json_api = ai.LocalAIRuntime._json_api.__get__(self.ai)
        self.ai.base_url = 'https://untrusted.invalid'
        self.assertEqual(self.ai._json_api('/api/version')['version'], ai.VERSION)
        self.http.assert_called_with('127.0.0.1', 11437, timeout=1)
        conn.close.assert_called_once()

    def test_json_api_oversize_rejected(self):
        self.http.side_effect = None
        conn = Mock()
        conn.getresponse.return_value = Response(b'x' * (ai.MAX_API + 1))
        self.http.return_value = conn
        self.ai._json_api = ai.LocalAIRuntime._json_api.__get__(self.ai)
        with self.assertRaises(ai.LocalAIError):
            self.ai._json_api('/api/tags')


if __name__ == '__main__':
    unittest.main()
