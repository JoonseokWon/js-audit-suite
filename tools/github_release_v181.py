"""Explicit fast-forward public audit-only v1.8.1 release operations. No action on import.

Credentials come from the existing Git credential helper and stay in memory.
Git sends source files once through its normal pack protocol. Release assets
use the GitHub upload API; no per-source-file blob upload is performed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'GitHub공개릴리스'
STATE = WORK / 'release-state.json'
CHECKOUT = WORK / 'checkout'
OWNER = 'JoonseokWon'
PREVIOUS_REPOSITORY = OWNER + '/for-ax-node-project'
REPOSITORY = OWNER + '/js-audit-suite'
SOURCE_PREFIX = 'js-audit-suite/'
BASE_COMMIT = 'c47250b5c092010342462a6a63d23692fd062637'
PREVIOUS_TAG = 'v1.8.0'
PREVIOUS_RELEASES = {'v1.7.0':'2562258ac0e0c02db8f3b9f0d98036740ab67aab',
                     'v1.7.1':'fbd5be7f074c1be978a3ba604acd564703e1c3c2',
                     'v1.8.0':BASE_COMMIT}
OLD_WORKFLOW_PATHS = ('.github/workflows/audit-suite-v17.yml',
                      '.github/workflows/audit-suite-v171.yml',
                      '.github/workflows/audit-suite-v18.yml')
REMOTE = 'https://github.com/' + REPOSITORY + '.git'
TAG = 'v1.8.1'
BRANCH = 'main'
SOURCE_NAME = 'js-audit-suite-v1.8.1-source.zip'
DEFAULT_WINDOWS_NAME = 'JS-Audit-Suite-v1.8.1-windows.zip'
VALIDATION_NAME = 'validation-report.json'
WORKFLOW_PATH = '.github/workflows/audit-suite-v181.yml'
WORKFLOW_NAME = 'JS Audit Suite v1.8.1'
IDENTITY = '300881227+JoonseokWon@users.noreply.github.com'
MARKER = '<!-- audit-suite-v1.8.1 -->'
RELEASE_URL = 'https://github.com/' + REPOSITORY + '/releases/tag/' + TAG
DEFAULT_WORKFLOW = """name: JS Audit Suite v1.8.1
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  verify:
    name: Audit Suite Python ${{ matrix.python-version }}
    runs-on: windows-latest
    timeout-minutes: 25
    strategy:
      fail-fast: false
      matrix:
        python-version: ['3.12', '3.14']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: python -m pip install openpyxl==3.1.5 defusedxml==0.7.1
      - name: Unit tests
        run: python -X utf8 -B -m unittest discover -v
      - name: Headless integration
        run: python -X utf8 -B tools/verify_headless_v17.py --output-dir 검증/CI통합
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def save_state(state):
    write_json(STATE, state)


def load_state():
    if not STATE.is_file():
        raise RuntimeError('릴리스 상태가 없습니다. --mode stage를 먼저 실행하세요.')
    state = json.loads(STATE.read_text(encoding='utf-8'))
    if state.get('repository') != REPOSITORY or state.get('tag') != TAG or state.get('branch') != BRANCH:
        raise RuntimeError('상태 파일의 저장소·태그·브랜치가 이 도구와 다릅니다.')
    return state


def safe_source_path(name):
    if (not isinstance(name, str) or not name.startswith(SOURCE_PREFIX) or '\\' in name or ':' in name
            or len(name) > 240 or re.search(r'[\x00-\x1f]', name)):
        raise RuntimeError('소스 ZIP 경로가 허용 범위 밖입니다.')
    parts = PurePosixPath(name).parts
    if any(p in ('', '.', '..') or p.casefold() == '.git' or p.endswith((' ', '.')) for p in name.split('/')):
        raise RuntimeError('소스 ZIP의 경로 구성요소가 안전하지 않습니다.')
    reserved = {'con', 'prn', 'aux', 'nul'} | {'com' + str(i) for i in range(1, 10)} | {'lpt' + str(i) for i in range(1, 10)}
    if any(p.split('.', 1)[0].casefold() in reserved or any(ch in p for ch in '<>"|?*') for p in parts):
        raise RuntimeError('Windows에서 안전하지 않은 소스 파일명입니다.')
    return name


PUBLIC_ROOT_FILES = {'.gitattributes', 'v12_specs.json', 'test_raw_accounts.py', 'test_core_calculation_links.py', 'test_account_cases.py', 'INTEGRATION_CONTRACT.md', 'procedures.py', 'verify_v16.py', 'README.md', 'analytics_support.py', 'requirements.txt', 'display_schema.py', 'leases.py', 'test_raw_sources.py', 'window_capture.py', 'test_runtime_gui.py', 'test_fia.py', 'verify_v14.py', 'account_cases.py', 'test_integration_v14.py', 'payroll.py', 'test_cash_analytics.py', 'adapters.py', 'ledger.py', 'AuditSuite.spec', 'procedure_catalog.json', 'analytics_validation.py', 'estimate_controls.py', 'v13_specs.json', 'verify.py', 'samples_specs.json', 'review_support.py', 'inventory.py', 'verify_v15.py', 'app.py', 'desktop_display.py', 'extensions.py', 'test_inventory_payroll.py', 'test_estimates.py', 'worker_cases.json', 'test_desktop_display.py', 'test_suite.py', 'accruals.py', 'test_accruals.py', 'workspace.py', 'new_specs.json', 'test_financial_bridge.py', 'windows.manifest', 'common.py', 'test_gla.py', 'runtime.py', 'verify_v18.py', 'raw_binding.py', 'sector_demo.py', '.gitignore', 'ecl.py', 'test_v15_integration.py', 'test_sector_demo.py', 'verify_v17.py', 'AGENTS.md', 'exporter.py'}

PUBLIC_ROOT_FILES.update({'ai_workpapers.py','ai_provider.py','test_ai_workpapers.py',
                          'test_ai_provider.py','verify_v18.py','verify_v171.py',
                          'ai_desktop.py','local_ai_runtime.py','test_ai_desktop.py',
                          'test_local_ai_runtime.py','verify_ai_actual.py'})
PUBLIC_ROOT_FILES.update({'windows_text.py','test_windows_text.py','verify_ime_patch.py',
                          'app_paths.py','test_app_paths.py'})

PUBLIC_SOURCE_DIRS = {'engines','raw_sources','raw_accounts','financial_bridge','worker_library',
                     'gla','fia','cash_analytics','samples','templates','testdata','raw_input_seed',
                     'reference_evidence','raw_analytics','sector_resources','.runtime','문서','ci','라이선스','tools','assets','디자인'}
FORBIDDEN_PARTS = {'.git','.venv','node_modules','__pycache__','.env','config.local.json',
                   'adc.json','credentials.json','release-state.json','메일 자동화',
                   '로컬ai','local-ai','local_ai','.ollama','ollama','models','model',
                   'privateprofile','private-profile','private_profile','github공개릴리스',
                   'build','dist','.cache'}


def allowed_public_path(relative):
    safe_source_path(SOURCE_PREFIX+relative)
    parts = PurePosixPath(relative).parts
    if not parts or any(p.casefold() in FORBIDDEN_PARTS or p.casefold().startswith('.env.') for p in parts):
        raise RuntimeError('공개 허용목록 밖의 개인 설정/실행 파일 경로')
    lower = relative.casefold()
    if parts[0].casefold() in ('배포','검증','로컬ai') and relative!='검증/.gitkeep':
        raise RuntimeError('배포·검증·로컬 AI 디렉터리는 공개 소스에서 제외합니다.')
    if parts[0] == '.runtime' and (len(parts)<3 or parts[1] not in ('tcl_library','tk_library')):
        raise RuntimeError('기존 Tcl/Tk 스크립트 외 런타임/AI 캐시 공개 차단')
    compressed_script_data=(relative=='.runtime/tcl_library/cookiejar/public_suffix_list.dat.gz')
    if not compressed_script_data and lower.endswith(('.sqlite3','.sqlite','.db','.db3','.log','.pyc','.pyo','.pem','.p12','.pfx','.key','.exe','.dll','.bin','.gguf','.safetensors','.onnx','.pt','.pth','.zip','.7z','.tar','.gz')):
        raise RuntimeError('소스 공개에 실제 업무 DB/로그/자격증명/실행파일을 포함할 수 없습니다.')
    if len(parts) == 1:
        if relative in PUBLIC_ROOT_FILES:
            return
    elif parts[0] in ('assets','디자인'):
        if relative=='assets/portable-config.json':return
        if len(parts)!=2 or Path(relative).suffix.lower() not in ('.png','.ico','.md'):
            raise RuntimeError('아이콘 자산은 해당 폴더의 PNG/ICO/출처 Markdown만 공개합니다.')
        return
    elif parts[0] in PUBLIC_SOURCE_DIRS:
        return
    elif relative == '검증/.gitkeep':
        return
    elif parts[0] == 'sector_verification' and Path(relative).suffix in ('.json','.md') and len(parts) <= 4:
        return
    raise RuntimeError('감사 전용 소스 허용목록 밖 경로: ' + relative)


def publication_files(path):
    if not path.is_file() or path.stat().st_size > 100 * 1024**2:
        raise RuntimeError('100MB 이하 소스 ZIP이 필요합니다.')
    entries, seen, total = {}, set(), 0
    with ZipFile(path) as z:
        if not 1 <= len(z.infolist()) <= 12000:
            raise RuntimeError('소스 ZIP 파일 개수 한도 오류')
        for info in z.infolist():
            if info.is_dir():
                if info.filename == SOURCE_PREFIX:
                    continue
                safe_source_path(info.filename.rstrip('/'))
                continue
            name = safe_source_path(info.filename)
            normalized = unicodedata.normalize('NFC', name).casefold()
            mode = (info.external_attr >> 16) & 0o170000
            if normalized in seen or mode not in (0, stat.S_IFREG) or info.flag_bits & 1:
                raise RuntimeError('소스 ZIP 중복·symlink·특수파일·암호화 차단')
            seen.add(normalized)
            total += info.file_size
            if info.file_size > 30 * 1024**2 or total > 300 * 1024**2 or info.file_size > max(info.compress_size, 1) * 1000:
                raise RuntimeError('소스 ZIP 압축·크기 한도 초과')
            relative = name[len(SOURCE_PREFIX):]
            allowed_public_path(relative)
            entries[relative] = z.read(info)
    required = {'requirements.txt', 'tools/verify_headless_v17.py', 'ci/audit-suite-v181.yml', '.gitattributes', 'README.md',
                'app.py','common.py','workspace.py','sector_demo.py','sector_resources/manifest.json','AuditSuite.spec',
                'desktop_display.py','windows.manifest','test_desktop_display.py','verify_v18.py',
                'ai_workpapers.py','ai_provider.py','test_ai_workpapers.py','test_ai_provider.py',
                'ai_desktop.py','local_ai_runtime.py','test_ai_desktop.py','test_local_ai_runtime.py',
                'verify_ai_actual.py',
                'test_runtime_gui.py','문서/v1.8_사용안내.md','문서/AI응답계약.md',
                'windows_text.py','test_windows_text.py','verify_ime_patch.py','app_paths.py','test_app_paths.py',
                'tools/github_release_v181.py'}
    if not required <= set(entries):
        raise RuntimeError('소스 ZIP에 requirements.txt/headless 검증 도구가 없습니다.')
    if entries['ci/audit-suite-v181.yml'] != DEFAULT_WORKFLOW.encode('utf-8'):
        raise RuntimeError('소스 CI가 검토한 root workflow와 다릅니다.')
    if entries['.gitattributes'].strip() != b'* -text':
        raise RuntimeError('소스 바이트 보존용 .gitattributes 확인 실패')
    return entries


def file_manifest(files):
    return [{'path': path, 'bytes': len(data), 'sha256': sha(data), 'git_blob_sha': git_sha(data)}
            for path, data in sorted(files.items())]


def local_artifacts(windows_name):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.zip', windows_name) or windows_name == SOURCE_NAME:
        raise RuntimeError('Windows 첨부파일 이름은 배포 폴더의 ASCII ZIP 이름이어야 합니다.')
    names = [windows_name, SOURCE_NAME, VALIDATION_NAME, 'SHA256SUMS.txt']
    artifacts = {}
    for name in names:
        path = ROOT / '배포' / name
        if not path.is_file() or not 0 < path.stat().st_size < 2 * 1024**3:
            raise RuntimeError('배포 첨부파일 누락/크기 오류: ' + name)
        artifacts[name] = {'name': name, 'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())}
    validation = json.loads((ROOT / '배포' / VALIDATION_NAME).read_text(encoding='utf-8'))
    validate_current_evidence(validation,artifacts,ROOT/'배포'/windows_name)
    expected = {}
    for line in (ROOT / '배포/SHA256SUMS.txt').read_text(encoding='utf-8-sig').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        if not match or match[2] in expected:
            raise RuntimeError('SHA256SUMS.txt 형식/중복 오류. sha256 + 공백2개 + 파일명 형식 필수')
        expected[match[2]] = match[1]
    if set(expected) != set(names) - {'SHA256SUMS.txt'} or any(artifacts[n]['sha256'] != value for n, value in expected.items()):
        raise RuntimeError('SHA256SUMS.txt 목록 또는 실제 파일 해시가 다릅니다.')
    files=publication_files(ROOT/'배포'/SOURCE_NAME)
    if len(files)!=validation['source']['files']:
        raise RuntimeError('소스 ZIP의 실제 파일 개수가 검증 보고서와 다릅니다.')
    return artifacts,files


def validate_current_evidence(validation,artifacts,windows_zip):
    """Gate the final v1.8.1 executable, not a renamed v1.8.0 test report.

    Actual inference may be a clearly labelled previous-version baseline. Real
    key-driven IME, portable layout, native/source saves and icon checks must
    refer to the current executable and finished assets.
    """
    if not isinstance(validation,dict) or validation.get('version')!='1.8.1' or validation.get('status')!='passed':
        raise RuntimeError('현재 v1.8.1 passed 검증 보고서가 필요합니다.')
    count=validation.get('unit_tests')
    if type(count) is not int or count<723:
        raise RuntimeError('현재 v1.8.1 전체 단위검사 723개 이상의 완료 기록이 필요합니다.')
    for field in ('actual_hardware_ime_test','portable_layout_verified','icon_embedded_verified','source_frozen_observations_identical'):
        if validation.get(field) is not True:
            raise RuntimeError('현재 실행파일 검증 누락: '+field)
    if not isinstance(validation.get('actual_inference_scope'),str) or not validation['actual_inference_scope'].strip():
        raise RuntimeError('실제 AI 재실행 또는 이전 버전 baseline 재사용 범위를 명시하세요.')
    exe=validation.get('exe');source=validation.get('source');ime=validation.get('ime_verification')
    if not isinstance(exe,dict) or exe.get('name')!='통합 회계감사 v1.8.1.exe' or type(exe.get('bytes')) is not int or not 0<exe['bytes']<100*1024**2 or not re.fullmatch('[0-9a-f]{64}',str(exe.get('sha256',''))):
        raise RuntimeError('현재 EXE의 이름·크기·SHA256 명세가 필요합니다.')
    if (not isinstance(source,dict) or source.get('name')!=SOURCE_NAME
            or type(source.get('files')) is not int or source['files']<1725
            or source.get('sha256')!=artifacts[SOURCE_NAME]['sha256']):
        raise RuntimeError('현재 소스 ZIP 해시·이전 1725개 경로 보존 명세가 필요합니다.')
    if (not isinstance(ime,dict) or ime.get('status')!='passed'
            or ime.get('tested_exe_sha256')!=exe['sha256']
            or not isinstance(ime.get('checks'),list) or not ime['checks']
            or any(not isinstance(item,str) or not item.strip() for item in ime['checks'])):
        raise RuntimeError('실제 키 입력 IME 검사와 최종 EXE SHA256이 연결되어야 합니다.')
    with ZipFile(windows_zip) as archive:
        if archive.testzip() is not None:raise RuntimeError('Windows ZIP CRC 검사 실패')
        names=[i.filename for i in archive.infolist() if not i.is_dir()]
        candidates=[name for name in names if PurePosixPath(name).name==exe['name']]
        if len(candidates)!=1:raise RuntimeError('Windows ZIP에 현재 EXE가 정확히 하나 있어야 합니다.')
        path=PurePosixPath(candidates[0])
        if (path.is_absolute() or '..' in path.parts or '\\' in str(path)
                or path.parent.name!='실행파일'):
            raise RuntimeError('Windows ZIP의 EXE는 실행파일 하위 폴더에 있어야 합니다.')
        payload=archive.read(str(path))
        if len(payload)!=exe['bytes'] or sha(payload)!=exe['sha256']:
            raise RuntimeError('Windows ZIP의 EXE가 실제 IME·아이콘 검증 대상과 다릅니다.')
        config=str(path.parent/'portable-config.json')
        if names.count(config)!=1:raise RuntimeError('EXE 옆 portable-config.json이 필요합니다.')
        if not isinstance(json.loads(archive.read(config).decode('utf-8-sig')),dict):
            raise RuntimeError('portable-config.json은 JSON 객체여야 합니다.')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise RuntimeError('인증 헤더를 보존하기 위해 GitHub API 리디렉션을 차단했습니다.')


class GitHub:
    def __init__(self):
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
        proc = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                              text=True, capture_output=True, env=env, timeout=30)
        if proc.returncode:
            raise RuntimeError('기존 Git 인증을 불러오지 못했습니다. 인증 내용은 출력하지 않습니다.')
        values = dict(line.split('=', 1) for line in proc.stdout.splitlines() if '=' in line)
        self._token = values.get('password')
        if not self._token:
            raise RuntimeError('기존 Git 인증이 없습니다.')
        self._opener = urllib.request.build_opener(NoRedirect())

    def call(self, method, path, data=None, raw=None, optional=False):
        url = path if path.startswith('https://') else 'https://api.github.com/repos/' + REPOSITORY + path
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc not in ('api.github.com', 'uploads.github.com') or parsed.username or parsed.password:
            raise RuntimeError('허용된 GitHub 공식 API 주소가 아닙니다.')
        body = raw if raw is not None else json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else None
        request = urllib.request.Request(url, data=body, method=method, headers={
            'Authorization': 'Bearer ' + self._token, 'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'audit-suite-v181-release',
            'Content-Type': 'application/octet-stream' if raw is not None else 'application/json'})
        try:
            with self._opener.open(request, timeout=180) as response:
                output = response.read()
                return json.loads(output) if output else None
        except urllib.error.HTTPError as exc:
            if optional and exc.code in (404, 409):
                return None
            raise RuntimeError(f'GitHub API {method} HTTP {exc.code}: {parsed.path}') from None
        except urllib.error.URLError:
            raise RuntimeError('GitHub API 네트워크 오류. 응답/인증 내용은 출력하지 않습니다.') from None

    def inspect(self):
        user = self.call('GET','https://api.github.com/user')
        if user.get('login') != OWNER:
            raise RuntimeError('인증된 GitHub 계정이 요청한 소유자와 다릅니다.')
        previous = self.call('GET','https://api.github.com/repos/'+PREVIOUS_REPOSITORY)
        if previous.get('full_name') != PREVIOUS_REPOSITORY or previous.get('private') is not True:
            raise RuntimeError('기존 개인 저장소가 비공개 상태인지 확인하지 못했습니다.')
        repo = self.call('GET','')
        if (repo.get('full_name') != REPOSITORY or repo.get('owner',{}).get('login') != OWNER
                or repo.get('private') is not False or repo.get('visibility') != 'public'
                or not repo.get('permissions',{}).get('push') or repo.get('archived')
                or repo.get('default_branch') != BRANCH):
            raise RuntimeError('기존 감사 전용 공개 저장소의 소유자·공개·쓰기·main 상태 확인 실패')
        branches = self.call('GET','/branches?per_page=100')
        if len(branches) != 1 or branches[0]['name'] != BRANCH:
            raise RuntimeError('공개 저장소에 기대하지 않은 브랜치가 있습니다.')
        head = self.call('GET','/git/ref/heads/'+BRANCH)['object']['sha']
        tags = self.call('GET','/tags?per_page=100')
        expected=set(PREVIOUS_RELEASES)
        if len(tags)!=len({t['name'] for t in tags}) or {t['name'] for t in tags} not in (expected,expected|{TAG}):
            raise RuntimeError('공개 저장소의 이전 두 버전/새 태그 집합이 다릅니다.')
        releases = self.call('GET','/releases?per_page=100')
        by_tag={r['tag_name']:r for r in releases}
        if len(releases)!=len(by_tag) or set(by_tag) not in (expected,expected|{TAG}):
            raise RuntimeError('공개 저장소의 이전 두 버전/새 릴리스 집합이 다릅니다.')
        preserved={}
        for old_tag,old_commit in PREVIOUS_RELEASES.items():
            ref=self.call('GET','/git/ref/tags/'+old_tag)
            if tag_commit(self,ref['object'])!=old_commit:
                raise RuntimeError('기존 공개 태그가 변경되었습니다: '+old_tag)
            old_release=by_tag[old_tag]
            if old_release['draft'] or old_release['target_commitish']!=old_commit:
                raise RuntimeError('기존 공개 릴리스의 대상/게시 상태가 다릅니다: '+old_tag)
            preserved[old_tag]={'commit':old_commit,'release_id':old_release['id'],
                                'release_sha256':previous_release_fingerprint(old_release)}
        tag=self.call('GET','/git/ref/tags/'+TAG,optional=True)
        release=by_tag.get(TAG)
        report={'repository':REPOSITORY,'private':False,'previous_repository_private':True,
                'authenticated_owner':OWNER,'exists':True,'repo_id':repo['id'],'head':head,
                'previous_tag':PREVIOUS_TAG,'previous_tag_commit':BASE_COMMIT,
                'previous_releases':preserved,
                'tag_exists':tag is not None,'tag_object':tag.get('object') if tag else None,
                'release':{'id':release['id'],'draft':release['draft'],'prerelease':release['prerelease'],
                           'target_commitish':release['target_commitish'],'url':release['html_url']} if release else None}
        write_json(WORK/'preflight.json',report)
        return report

    def find_release(self):
        found = self.call('GET', '/releases/tags/' + TAG, optional=True)
        if found is not None:
            return found
        for page in range(1, 11):
            releases = self.call('GET', f'/releases?per_page=100&page={page}')
            matches = [r for r in releases if r['tag_name'] == TAG]
            if len(matches) > 1:
                raise RuntimeError('동일 태그 릴리스가 중복되었습니다.')
            if matches:
                return matches[0]
            if len(releases) < 100:
                return None
        raise RuntimeError('릴리스 목록 한도 초과. 동일 태그 여부를 확정하지 못했습니다.')


def previous_release_fingerprint(release):
    fields=('id','tag_name','target_commitish','name','body','draft','prerelease','published_at','created_at','updated_at')
    record={k:release.get(k) for k in fields}
    record['assets']=sorted([{k:a.get(k) for k in ('id','name','size','digest','state','created_at','updated_at')}
                             for a in release.get('assets',[])],key=lambda a:a['name'])
    return sha(json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))


def preserved_previous(report,state):
    if (report.get('repo_id')!=state.get('repo_id') or report.get('previous_tag_commit')!=BASE_COMMIT
            or set(report.get('previous_releases',{}))!=set(PREVIOUS_RELEASES)
            or report.get('previous_releases')!=state.get('previous_releases')):
        raise RuntimeError('기존 저장소 ID/v1.7.0·v1.7.1·v1.8.0 태그·릴리스가 변경되었습니다. 자동 수정하지 않습니다.')


def git(args, *, cwd=CHECKOUT, input_bytes=None, timeout=180):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
    # Hooks are never needed for publication; identity is per command, not global.
    hooks = WORK / 'disabled-hooks'
    hooks.mkdir(parents=True, exist_ok=True)
    command = ['git', '-c', 'safe.directory='+CHECKOUT.resolve().as_posix(), '-c', 'core.autocrlf=false', '-c', 'core.filemode=false', '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=' + str(hooks),
               '-c', 'user.name=JoonseokWon', '-c', 'user.email=' + IDENTITY] + list(args)
    proc = subprocess.run(command, cwd=cwd, input=input_bytes, capture_output=True, env=env, timeout=timeout)
    if proc.returncode:
        # Git stderr can contain credential-bearing helper diagnostics; omit it.
        raise RuntimeError('Git 작업 실패: ' + next((arg for arg in args if not arg.startswith('-')), 'command') + '. 인증 내용과 상세 출력은 저장하지 않았습니다.')
    return proc.stdout


def checkout_checks():
    if not CHECKOUT.is_dir() or CHECKOUT.is_symlink() or CHECKOUT.resolve() != (WORK.resolve() / 'checkout'):
        raise RuntimeError('릴리스 checkout 경로가 예상 범위를 벗어났습니다.')
    if git(['remote', 'get-url', 'origin']).decode().strip() != REMOTE:
        raise RuntimeError('checkout origin이 지정 저장소와 다릅니다.')
    if not (CHECKOUT / '.git').is_dir() or (CHECKOUT / '.git').is_symlink():
        raise RuntimeError('릴리스 전용 checkout만 사용할 수 있습니다.')


def commit_files(files,state):
    """Clone the exact existing main and append one commit without deleting old files."""
    if CHECKOUT.exists():
        checkout_checks()
    else:
        git(['clone','--branch',BRANCH,'--single-branch','--',REMOTE,str(CHECKOUT)],cwd=WORK,timeout=600)
        checkout_checks()
    if git(['rev-parse','HEAD']).decode().strip() != state['base'] or git(['status','--porcelain=v1','-z']):
        raise RuntimeError('checkout 기준 커밋/작업 상태가 달라졌습니다. 사용자 변경을 덮어쓰지 않습니다.')
    old={}
    for record in git(['ls-tree','-rz','HEAD']).split(b'\0'):
        if record:
            info,path=record.split(b'\t',1);mode,kind,blob=info.split(b' ')
            if kind != b'blob' or mode not in (b'100644',b'100755'):
                raise RuntimeError('기존 저장소의 예상 밖 submodule/symlink 파일을 자동 변경하지 않습니다.')
            old[path.decode('utf-8')]={'mode':mode.decode(),'sha':blob.decode()}
    if not set(OLD_WORKFLOW_PATHS)<=set(old) or WORKFLOW_PATH in old:
        raise RuntimeError('기존/새 workflow 보존 기준이 다릅니다.')
    if set(old)-set(OLD_WORKFLOW_PATHS)-set(files):
        raise RuntimeError('기존 v1.8.0 소스 파일이 새 ZIP에서 누락되었습니다. 자동 삭제하지 않습니다.')
    immutable=('sector_resources/','samples/','templates/','testdata/','raw_input_seed/',
               'reference_evidence/','raw_analytics/','.runtime/')
    if any(path.startswith(immutable) and git_sha(files[path])!=entry['sha'] for path,entry in old.items() if path in files):
        raise RuntimeError('이전 공개 계산·더미 원천자료·Tcl 스크립트가 변경되었습니다.')
    if any(p.startswith('.github/') for p in files):
        raise RuntimeError('소스 ZIP은 별도 root workflow를 포함할 수 없습니다.')
    workflow=files['ci/audit-suite-v181.yml']
    if workflow != DEFAULT_WORKFLOW.encode('utf-8'):
        raise RuntimeError('검토한 v1.8.1 workflow와 소스 파일이 다릅니다.')
    changes={**files,WORKFLOW_PATH:workflow}
    for relative,data in changes.items():
        path=CHECKOUT/Path(relative)
        if not path.resolve().is_relative_to(CHECKOUT.resolve()) or path.is_symlink():
            raise RuntimeError('공개 checkout 내부 경로 검증 실패')
        if path.exists() and (not path.is_file() or relative not in old or git_sha(path.read_bytes()) != old[relative]['sha']):
            raise RuntimeError('변경 전 checkout 원문 SHA가 기존 추적 파일과 다릅니다.')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    expected_changed={p for p,data in changes.items() if old.get(p,{}).get('sha') != git_sha(data)}
    if not expected_changed:raise RuntimeError('커밋할 변경이 없습니다.')
    pathspec=WORK/'publication-pathspec.nul'
    pathspec.write_bytes(b''.join((':(literal)'+p).encode('utf-8')+b'\0' for p in sorted(changes)))
    git(['add','-f','--pathspec-from-file='+str(pathspec),'--pathspec-file-nul'])
    staged={p.decode('utf-8') for p in git(['diff','--cached','--name-only','-z']).split(b'\0') if p}
    if staged != expected_changed or not staged <= set(changes):
        raise RuntimeError('실제 공개 stage 파일과 명시 변경 허용목록이 다릅니다.')
    index={}
    for record in git(['ls-files','--stage','-z']).split(b'\0'):
        if record:
            info,path=record.split(b'\t',1);mode,blob,stage=info.split(b' ')
            index[path.decode('utf-8')]=(mode.decode(),blob.decode(),stage.decode())
    if set(index) != set(old)|set(changes):
        raise RuntimeError('전체 index에 기존 파일 삭제 또는 허용목록 밖 파일이 있습니다.')
    for relative,data in changes.items():
        if index.get(relative) not in (('100644',git_sha(data),'0'),('100755',git_sha(data),'0')):
            raise RuntimeError('stage의 소스 원문 바이트/모드가 다릅니다.')
    previous_workflows={}
    for old_path in OLD_WORKFLOW_PATHS:
        payload=(CHECKOUT/old_path).read_bytes()
        if git_sha(payload)!=old[old_path]['sha'] or index[old_path][1]!=old[old_path]['sha']:
            raise RuntimeError('기존 root workflow가 변경되었습니다: '+old_path)
        previous_workflows[old_path]=payload
    state.update(additional_files=file_manifest({**previous_workflows,WORKFLOW_PATH:workflow}),
                 staged_paths=sorted(staged),phase='STAGED_LOCAL')
    save_state(state)
    git(['commit','-m','Improve Korean workpaper editing and portable layout in JS audit suite v1.8.1'])
    commit=git(['rev-parse','HEAD']).decode().strip()
    parents=git(['rev-list','--parents','-n','1','HEAD']).decode().split()
    if parents != [commit,state['base']] or state['base'] != BASE_COMMIT:
        raise RuntimeError('패치 커밋이 지정 v1.8.0 main을 유일 부모로 잇지 않습니다.')
    state.update(phase='COMMITTED',commit=commit,patch_commits=[commit]);save_state(state)


def pinned_artifacts(state):
    assets, files = local_artifacts(state['windows_asset'])
    if assets != state['local_assets'] or file_manifest(files) != state['source_files']:
        raise RuntimeError('처음 stage한 첨부파일/소스가 변경되었습니다. 기존 릴리스 파일을 바꾸지 않습니다.')
    return assets, files


def ensure_assets(api, release, state):
    actual = {a['name']: a for a in release['assets']}
    if len(actual) != len(release['assets']) or set(actual) != set(state['local_assets']):
        raise RuntimeError('릴리스 첨부파일 집합이 기대 목록과 다릅니다.')
    records = []
    for name, expected in state['local_assets'].items():
        asset = actual[name]
        if asset.get('digest') != 'sha256:' + expected['sha256'] or asset.get('size') != expected['bytes'] or asset.get('state') != 'uploaded':
            raise RuntimeError('업로드 첨부파일 SHA256·크기·완료상태 불일치: ' + name)
        records.append(dict(expected, asset_id=asset['id'], url=asset['browser_download_url']))
    return records


def release_notes():
    path = WORK / 'release-notes.md'
    if path.is_file():
        if path.stat().st_size > 100000:
            raise RuntimeError('릴리스 설명 크기 한도 초과')
        return path.read_text(encoding='utf-8')
    return ('통합 감사 프로그램 v1.8.1 한글 조서 편집·포터블 배치 수정입니다. 조서 본문과 승인 메모를 Windows Unicode 편집기로 바꾸고 실행파일·데이터 위치를 구분합니다. '
            '독자 제작 아이콘을 사용하며 기존 계산·AI 근거·사람 승인·독립 검토 통제를 유지합니다.\n\n'
            '현재 EXE의 실제 키 입력 검사, 저장·재열기·Excel 검사와 실제 AI 추론의 버전별 범위는 validation-report.json을 확인하세요. '
            '현재 버전에서 재실행한 검사와 이전 버전 baseline 증거를 구별합니다.\n\n'
            '로컬 AI 런타임·모델·키·실제 업무 DB는 공개 배포에 포함하지 않습니다. AI 내용 승인과 전체 감사 완료는 다르며, 합성자료는 독립 감사증거가 아닙니다.\n\n'
            '본인 역할: 회계 요구사항·검증. 코드 구현: AI 활용. v1.7.0·v1.7.1·v1.8.0 이력을 보존한 사전 릴리스입니다.\n')


def stage(api,windows_name):
    report=api.inspect()
    if STATE.exists():
        state=load_state()
        if state['phase'] in ('PUBLISHED','VERIFIED'):
            raise RuntimeError('이미 게시된 패치 릴리스입니다. verify로 확인하세요.')
        pinned_artifacts(state);preserved_previous(report,state)
    else:
        if report['head'] != BASE_COMMIT or report['tag_exists'] or report['release']:
            raise RuntimeError('지정 v1.8.0 main/새 태그 부재 상태가 아닙니다. 덮어쓰지 않습니다.')
        if CHECKOUT.exists():raise RuntimeError('상태 파일 없이 checkout이 존재합니다.')
        assets,files=local_artifacts(windows_name)
        state={'repository':REPOSITORY,'tag':TAG,'branch':BRANCH,'private':False,'base':BASE_COMMIT,
               'repo_id':report['repo_id'],'previous_releases':report['previous_releases'],'phase':'PREPARED',
               'windows_asset':windows_name,'local_assets':assets,'source_files':file_manifest(files)}
        save_state(state)
    if state['phase'] == 'PREPARED':
        if report['head'] != state['base'] or report['tag_exists'] or report['release']:
            raise RuntimeError('준비 이후 main/새 태그/릴리스가 달라졌습니다.')
        _,files=pinned_artifacts(state);commit_files(files,state)
    if state['phase'] == 'STAGED_LOCAL':
        raise RuntimeError('커밋 직전 중단 상태입니다. index와 상태를 검토해야 합니다.')
    if state['phase'] == 'COMMITTED':
        checkout_checks()
        if git(['rev-parse','HEAD']).decode().strip() != state['commit'] or git(['status','--porcelain=v1','-z']):
            raise RuntimeError('공개 커밋의 checkout이 변경되었습니다.')
        current = api.inspect()
        preserved_previous(current,state)
        if current['tag_exists'] or current['release']:
            raise RuntimeError('공개 push 전 저장소/태그/릴리스가 변경되었습니다.')
        if current['head'] == state['base']:
            git(['push','origin','HEAD:refs/heads/'+BRANCH],timeout=600)
        elif current['head'] != state['commit']:
            raise RuntimeError('원격에 다른 내용이 있습니다. 강제 push하지 않습니다.')
        if api.inspect()['head'] != state['commit']:
            raise RuntimeError('공개 push 후 커밋 확인 실패')
        state['phase'] = 'PUSHED';save_state(state)
    if state['phase'] not in ('PUSHED','DRAFT_CREATED','STAGED'):
        raise RuntimeError('이 상태에서는 공개 draft 업로드를 재개할 수 없습니다.')
    pinned_artifacts(state)
    current = api.inspect()
    preserved_previous(current,state)
    if current['head'] != state['commit']:
        raise RuntimeError('공개 저장소의 대상 커밋/ID가 달라졌습니다.')
    if current['tag_exists'] and tag_commit(api,current['tag_object']) != state['commit']:
        raise RuntimeError('동일 태그가 다른 커밋을 가리킵니다.')
    release = api.find_release()
    if release is None:
        release = api.call('POST','/releases',{'tag_name':TAG,'target_commitish':state['commit'],
                           'name':'통합 감사 프로그램 v1.8.1 · 한글 편집·포터블 배치',
                           'body':release_notes(),'draft':True,'prerelease':True,'make_latest':'false'})
    if not release['draft'] or not release['prerelease'] or release['tag_name'] != TAG or release['target_commitish'] != state['commit']:
        raise RuntimeError('공개 draft의 태그/대상 커밋/사전 릴리스 상태가 다릅니다.')
    if state.get('release_id') not in (None,release['id']):
        raise RuntimeError('공개 draft ID가 기존 상태와 다릅니다.')
    state.update(phase='DRAFT_CREATED',release_id=release['id']);save_state(state)
    existing = {a['name']:a for a in release['assets']}
    if len(existing) != len(release['assets']) or not set(existing) <= set(state['local_assets']):
        raise RuntimeError('공개 draft에 예상 밖/중복 첨부파일이 있습니다.')
    for name in state['local_assets']:
        if name in existing:continue
        target = release['upload_url'].split('{',1)[0]+'?'+urllib.parse.urlencode({'name':name})
        api.call('POST',target,raw=(ROOT/'배포'/name).read_bytes())
    release = api.call('GET','/releases/'+str(state['release_id']))
    state.update(phase='STAGED',assets=ensure_assets(api,release,state));save_state(state)
    return {'phase':'STAGED','commit':state['commit'],'source_files':len(state['source_files']),
            'assets':len(state['assets']),'private':False,'draft':True,'base_commit':state['base'],'previous_release_preserved':True}


REVISION_ALLOWED_PATHS={'test_app_paths.py','test_windows_text.py','test_desktop_display.py',
                        'test_local_ai_runtime.py','tools/github_release_v181.py','ci/audit-suite-v181.yml'}


def patch_commits(state):
    chain=state.get('patch_commits',[state.get('commit')])
    if (state.get('base')!=BASE_COMMIT or not isinstance(chain,list) or not 1<=len(chain)<=20
            or any(not isinstance(c,str) or not re.fullmatch('[0-9a-f]{40}',c) for c in chain)
            or len(set(chain))!=len(chain) or chain[-1]!=state.get('commit')):
        raise RuntimeError('원래 BASE에서 이어지는 공개 패치 커밋 목록이 유효하지 않습니다.')
    return chain


def verify_patch_chain(api,state):
    parent=BASE_COMMIT;last=None
    for commit in patch_commits(state):
        last=api.call('GET','/git/commits/'+commit)
        if [p.get('sha') for p in last.get('parents',[])]!=[parent]:
            raise RuntimeError('공개 패치 이력이 BASE부터 연속된 단일 부모 fast-forward가 아닙니다.')
        parent=commit
    return last


def revision_plan(state,assets,files):
    if state.get('phase')!='STAGED':raise RuntimeError('게시되지 않은 STAGED draft에서만 revise를 시작할 수 있습니다.')
    patch_commits(state)
    old={r['path']:r for r in state['source_files']};new={r['path']:r for r in file_manifest(files)}
    if set(old)!=set(new):raise RuntimeError('revise는 기존 소스 파일의 추가/삭제를 허용하지 않습니다.')
    changed=sorted(p for p in new if new[p]!=old[p])
    if not changed or not set(changed)<=REVISION_ALLOWED_PATHS:
        raise RuntimeError('revise는 CI 경로 테스트와 릴리스 helper 두 파일의 변경만 허용합니다.')
    if set(assets)!=set(state['local_assets']):raise RuntimeError('revise 첨부파일 이름 네 개를 보존해야 합니다.')
    old_ids={a['name']:a['asset_id'] for a in state.get('assets',[])}
    if set(old_ids)!=set(assets):raise RuntimeError('기존 STAGED 첨부 ID 네 개가 필요합니다.')
    return {'phase':'PREPARED','before':copy.deepcopy(state),'assets':assets,'source_files':file_manifest(files),
            'changed_paths':changed,'old_asset_ids':old_ids,'asset_steps':{}}


def _revision_release(api,state,heads):
    report=api.inspect();preserved_previous(report,state)
    if report['head'] not in heads or report.get('tag_exists'):
        raise RuntimeError('revise 중 원격 HEAD/새 태그가 달라졌습니다. 태그 이동/강제 push는 하지 않습니다.')
    release=api.call('GET','/releases/'+str(state['release_id']))
    if (release.get('id')!=state['release_id'] or not release.get('draft') or not release.get('prerelease')
            or release.get('tag_name')!=TAG or release.get('target_commitish') not in heads):
        raise RuntimeError('현재 v1.8.1 draft/대상/ID가 달라졌습니다. 기존 공개 릴리스는 수정하지 않습니다.')
    return report,release


def _revision_tree_check(expected):
    tree={}
    for record in git(['ls-tree','-rz','HEAD']).split(b'\0'):
        if record:
            info,path=record.split(b'\t',1);mode,kind,blob=info.split(b' ')
            if kind!=b'blob' or mode not in (b'100644',b'100755'):raise RuntimeError('revise checkout에 예상 밖 모드가 있습니다.')
            tree[path.decode('utf-8')]=(mode.decode(),blob.decode())
    if set(tree)!=set(expected) or any(tree[p][1]!=r['git_blob_sha'] for p,r in expected.items()):
        raise RuntimeError('revise checkout HEAD가 보존된 STAGED 소스 원문과 다릅니다.')
    return tree


def _revision_commit(files,state):
    revision=state['revision'];old=revision['before'];checkout_checks()
    old_expected={r['path']:r for r in old['source_files']+old['additional_files']}
    new_expected={r['path']:r for r in revision['source_files']+old['additional_files']}
    head=git(['rev-parse','HEAD']).decode().strip()
    if head==old['commit']:
        tree=_revision_tree_check(old_expected)
        if git(['ls-files','--others','--exclude-standard','-z']):raise RuntimeError('revise checkout에 사용자 미추적 파일이 있습니다.')
        for relative,expected in old_expected.items():
            path=CHECKOUT/relative
            if not path.resolve().is_relative_to(CHECKOUT.resolve()) or path.is_symlink() or not path.is_file():raise RuntimeError('revise checkout 파일 경로/원본 오류')
            acceptable={expected['git_blob_sha']}
            if relative in revision['changed_paths']:acceptable.add(new_expected[relative]['git_blob_sha'])
            if git_sha(path.read_bytes()) not in acceptable:raise RuntimeError('revise 중 사용자 파일 변경을 발견했습니다. 덮어쓰지 않습니다.')
        for relative in revision['changed_paths']:
            temporary=WORK/('revision-write-'+sha(relative.encode())+'.tmp')
            temporary.write_bytes(files[relative]);os.replace(temporary,CHECKOUT/relative)
        pathspec=WORK/'revision-pathspec.nul'
        pathspec.write_bytes(b''.join((':(literal)'+p).encode()+b'\0' for p in revision['changed_paths']))
        git(['add','--pathspec-from-file='+str(pathspec),'--pathspec-file-nul'])
        index={}
        for record in git(['ls-files','--stage','-z']).split(b'\0'):
            if record:
                info,path=record.split(b'\t',1);mode,blob,stage=info.split(b' ')
                index[path.decode()]=(mode.decode(),blob.decode(),stage.decode())
        if set(index)!=set(new_expected) or any(index[p]!=(tree[p][0],r['git_blob_sha'],'0') for p,r in new_expected.items()):
            raise RuntimeError('revise index가 허용된 두 파일 변경과 정확히 일치하지 않습니다.')
        revision['phase']='LOCAL_STAGED';save_state(state)
        git(['commit','-m','Fix Windows CI temporary path comparison without changing audit application'])
        head=git(['rev-parse','HEAD']).decode().strip()
    # Also recover a successful local commit if the process stopped before saving.
    if git(['rev-list','--parents','-n','1','HEAD']).decode().split()!=[head,old['commit']]:
        raise RuntimeError('revise 커밋은 이전 STAGED 커밋의 단일 자식이어야 합니다.')
    _revision_tree_check(new_expected)
    if git(['status','--porcelain=v1','-z']):raise RuntimeError('revise 커밋 후 checkout 변경이 있습니다.')
    revision.update(phase='COMMITTED',commit=head)
    state.update(commit=head,patch_commits=patch_commits(old)+[head]);save_state(state)


def _revision_asset_state(release,revision):
    actual={a['name']:a for a in release['assets']}
    if len(actual)!=len(release['assets']) or not set(actual)<=set(revision['assets']):raise RuntimeError('revise draft에 예상 밖/중복 첨부가 있습니다.')
    for name,expected in revision['assets'].items():
        asset=actual.get(name);phase=revision['asset_steps'].get(name)
        if asset is None:
            if phase not in ('DELETE_PENDING','DELETED','UPLOAD_PENDING'):raise RuntimeError('revise가 삭제하지 않은 첨부가 사라졌습니다.')
            continue
        old=asset.get('id')==revision['old_asset_ids'][name]
        proof=revision['before']['local_assets'][name] if old else expected
        if (asset.get('digest')!='sha256:'+proof['sha256'] or asset.get('size')!=proof['bytes'] or asset.get('state')!='uploaded'
                or (not old and phase not in ('UPLOAD_PENDING','UPLOADED'))):
            raise RuntimeError('revise draft 첨부 ID/원래·새 SHA256이 보존된 상태와 다릅니다.')
    return actual


def revise(api):
    """Append a recoverable CI-only revision to the current, unpublished draft."""
    state=load_state()
    if state.get('phase')=='STAGED':
        report,release=_revision_release(api,state,{state['commit']})
        verified=ensure_assets(api,release,state)
        if {a['name']:a['asset_id'] for a in verified}!={a['name']:a['asset_id'] for a in state.get('assets',[])}:
            raise RuntimeError('기존 draft 첨부 ID가 원래 STAGED 기록과 다릅니다.')
        assets,files=local_artifacts(state['windows_asset'])
        if state.get('revisions') and assets==state['local_assets'] and file_manifest(files)==state['source_files']:
            return {'phase':'STAGED','commit':state['commit'],'patch_commits':patch_commits(state),
                    'changed_paths':state['revisions'][-1]['changed_paths'],'draft':True,
                    'assets':len(verified),'requires_new_exact_head_ci':True,'already_revised':True}
        revision=revision_plan(state,assets,files)
        snapshot=WORK/('revision-before-'+state['commit']+'.json')
        if snapshot.exists() and json.loads(snapshot.read_text(encoding='utf-8'))!=state:
            raise RuntimeError('기존 revise 상태 스냅샷이 다릅니다. 원본을 덮어쓰지 않습니다.')
        if not snapshot.exists():write_json(snapshot,state)
        state.update(phase='REVISING',revision=revision);save_state(state)
    if state.get('phase')!='REVISING' or 'revision' not in state:raise RuntimeError('revise 준비/재시도 상태가 아닙니다.')
    revision=state['revision'];old=revision['before']
    assets,files=local_artifacts(state['windows_asset'])
    if assets!=revision['assets'] or file_manifest(files)!=revision['source_files']:raise RuntimeError('revise 준비 이후 새 첨부/소스 ZIP이 변경되었습니다.')
    if revision['phase'] in ('PREPARED','LOCAL_STAGED'):
        _revision_release(api,state,{old['commit']})
        _revision_commit(files,state)
    target=revision['commit']
    if revision['phase']=='COMMITTED':
        checkout_checks()
        if git(['rev-parse','HEAD']).decode().strip()!=target or git(['status','--porcelain=v1','-z']):
            raise RuntimeError('revise push 전 checkout HEAD/작업 상태가 달라졌습니다.')
        _revision_tree_check({r['path']:r for r in revision['source_files']+old['additional_files']})
        report,release=_revision_release(api,state,{old['commit'],target})
        if report['head']==old['commit']:git(['push','origin','HEAD:refs/heads/'+BRANCH],timeout=600)
        report,release=_revision_release(api,state,{target,old['commit']})
        if report['head']!=target:raise RuntimeError('revise fast-forward push 대상 확인 실패')
        revision['phase']='PUSHED';save_state(state)
    report,release=_revision_release(api,state,{target}) if revision['phase'] not in ('PUSHED',) else _revision_release(api,state,{old['commit'],target})
    if report['head']!=target:raise RuntimeError('revise 원격 HEAD가 새 커밋과 다릅니다.')
    if release['target_commitish']!=target:
        release=api.call('PATCH','/releases/'+str(state['release_id']),{'tag_name':TAG,'target_commitish':target,'draft':True,'prerelease':True})
    if not release.get('draft') or release.get('target_commitish')!=target:raise RuntimeError('revise draft 새 대상 갱신 확인 실패')
    revision['phase']='RETARGETED';save_state(state)
    _revision_asset_state(release,revision)
    for name in revision['assets']:
        _,release=_revision_release(api,state,{target});actual=_revision_asset_state(release,revision);asset=actual.get(name)
        if asset and asset['id']==revision['old_asset_ids'][name]:
            revision['asset_steps'][name]='DELETE_PENDING';save_state(state)
            api.call('DELETE','/releases/assets/'+str(asset['id']))
            revision['asset_steps'][name]='DELETED';save_state(state);asset=None
        if asset is None:
            revision['asset_steps'][name]='UPLOAD_PENDING';save_state(state)
            url=release['upload_url'].split('{',1)[0]+'?'+urllib.parse.urlencode({'name':name})
            api.call('POST',url,raw=(ROOT/'배포'/name).read_bytes())
        revision['asset_steps'][name]='UPLOADED';save_state(state)
    _,release=_revision_release(api,state,{target})
    final_state={**state,'local_assets':assets,'source_files':revision['source_files']}
    final_assets=ensure_assets(api,release,final_state)
    state.update(local_assets=assets,source_files=revision['source_files'],assets=final_assets,phase='STAGED')
    state.setdefault('revisions',[]).append({'from_commit':old['commit'],'commit':target,'changed_paths':revision['changed_paths'],
        'snapshot':('revision-before-'+old['commit']+'.json'),'previous_assets':old['local_assets'],'assets':assets})
    state.pop('revision');save_state(state)
    return {'phase':'STAGED','commit':target,'patch_commits':state['patch_commits'],'changed_paths':state['revisions'][-1]['changed_paths'],
            'draft':True,'assets':len(final_assets),'requires_new_exact_head_ci':True}


def status(api):
    state = load_state()
    if 'commit' not in state:
        return {'phase': state['phase'], 'commit': None, 'runs': []}
    data = api.call('GET', '/actions/runs?' + urllib.parse.urlencode({'head_sha': state['commit'], 'per_page': 100}))
    selected = [r for r in data['workflow_runs'] if r['name'] == WORKFLOW_NAME and r['head_sha'] == state['commit']
                and r.get('path', '').split('@', 1)[0] == WORKFLOW_PATH and r.get('head_branch') == BRANCH and r.get('event') == 'push']
    records = []
    for run in selected:
        jobs = api.call('GET', '/actions/runs/' + str(run['id']) + '/jobs?per_page=100')
        if jobs.get('total_count', 0) > 100:
            raise RuntimeError('CI 작업 목록이 한도를 넘습니다.')
        records.append({'id': run['id'], 'run_number': run['run_number'], 'status': run['status'], 'conclusion': run['conclusion'],
                        'url': run['html_url'], 'jobs': [{'name': j['name'], 'status': j['status'], 'conclusion': j['conclusion'],
                        'steps': [{'name': s['name'], 'conclusion': s.get('conclusion')} for s in j['steps']]} for j in jobs['jobs']]})
    output = {'phase': state['phase'], 'commit': state['commit'], 'runs': sorted(records, key=lambda r: r['id'], reverse=True)}
    write_json(WORK / 'github-actions.json', output)
    return output


def ci_gate(report):
    if not report['runs']:
        raise RuntimeError('해당 커밋의 v1.8.1 push CI가 없습니다.')
    latest = report['runs'][0]
    if latest['status'] != 'completed' or latest['conclusion'] != 'success' or len(latest['jobs']) != 2:
        raise RuntimeError('최신 CI와 Python 2개 작업 성공 전에는 게시하지 않습니다.')
    versions = set()
    for job in latest['jobs']:
        if job['status'] != 'completed' or job['conclusion'] != 'success':
            raise RuntimeError('Python matrix 작업 성공 확인 실패')
        found = re.findall(r'(?<![\d.])3\.(?:12|14)(?![\d.])', job['name'])
        if len(found) != 1:
            raise RuntimeError('CI 작업 이름에서 Python 버전을 확인하지 못했습니다.')
        versions.add(found[0])
        steps = {s['name']: s['conclusion'] for s in job['steps']}
        if steps.get('Unit tests') != 'success' or steps.get('Headless integration') != 'success':
            raise RuntimeError('단위 테스트와 headless 통합 검사 단계가 모두 성공해야 합니다.')
    if versions != {'3.12', '3.14'}:
        raise RuntimeError('Python 3.12/3.14 matrix가 모두 성공해야 합니다.')
    return latest


def ensure_release_tag(api,state):
    """Create only this new tag, never move or replace an existing ref."""
    ref=api.call('GET','/git/ref/tags/'+TAG,optional=True)
    if ref is None:
        ref=api.call('POST','/git/refs',{'ref':'refs/tags/'+TAG,'sha':state['commit']})
    if tag_commit(api,ref['object'])!=state['commit']:
        raise RuntimeError('새 태그가 현재 검증된 커밋과 다릅니다. 태그를 덮어쓰지 않습니다.')
    return ref


def publish(api):
    state = load_state()
    if state['phase'] != 'STAGED':
        raise RuntimeError('검증된 STAGED 상태에서만 게시할 수 있습니다.')
    pinned_artifacts(state)
    ci = ci_gate(status(api))
    verify_patch_chain(api,state)
    current = api.inspect()
    preserved_previous(current,state)
    if current['head'] != state['commit'] or current.get('repo_id') != state['repo_id']:
        raise RuntimeError('게시 전 대상 공개 저장소/커밋이 변경되었습니다.')
    if current['tag_exists'] and tag_commit(api, current['tag_object']) != state['commit']:
        raise RuntimeError('기존 태그가 배포 커밋과 다릅니다. 게시하지 않습니다.')
    ensure_release_tag(api,state)
    release = api.call('GET', '/releases/' + str(state['release_id']))
    if not release['draft'] or release['target_commitish'] != state['commit'] or release['tag_name'] != TAG or not release['prerelease']:
        raise RuntimeError('게시할 draft/대상 커밋/태그가 다릅니다.')
    ensure_assets(api, release, state)
    body = release_notes() + '\n\nGitHub 자동 검사: [Python 3.12·3.14 성공 기록](' + ci['url'] + ')\n'
    response = api.call('PATCH', '/releases/' + str(state['release_id']),
                        {'tag_name':TAG,'target_commitish':state['commit'],
                         'draft': False, 'prerelease': True, 'make_latest': 'false', 'body': body})
    state.update(phase='PUBLISHED', url=response['html_url'], published_at=response.get('published_at'), ci=ci)
    save_state(state)
    return verify(api)


def tag_commit(api, obj):
    for _ in range(4):
        if obj['type'] == 'commit':
            return obj['sha']
        if obj['type'] != 'tag':
            raise RuntimeError('태그가 commit/tag 객체를 가리키지 않습니다.')
        obj = api.call('GET', '/git/tags/' + obj['sha'])['object']
    raise RuntimeError('태그 객체 깊이 한도 초과')


def verify(api):
    state = load_state()
    pinned_artifacts(state)
    report = api.inspect()
    preserved_previous(report,state)
    if report['head'] != state['commit'] or report.get('repo_id') != state['repo_id']:
        raise RuntimeError('최종 공개 저장소/커밋이 배포 상태와 다릅니다.')
    release = api.find_release()
    if (release is None or release['draft'] or not release['prerelease'] or release['id'] != state.get('release_id')
            or not report['tag_exists']):
        raise RuntimeError('게시 상태·태그·사전 릴리스 검증 실패')
    if tag_commit(api, report['tag_object']) != state['commit']:
        raise RuntimeError('태그의 최종 커밋이 배포 커밋과 다릅니다.')
    ci = ci_gate(status(api))
    assets = ensure_assets(api, release, state)
    commit = verify_patch_chain(api,state)
    tree = api.call('GET', '/git/trees/' + commit['tree']['sha'] + '?recursive=1')
    if tree.get('truncated'):
        raise RuntimeError('원격 소스 트리 목록이 잘려 exact 검증하지 못했습니다.')
    blobs = {r['path']: r for r in tree['tree'] if r['type'] == 'blob'}
    expected = {r['path']: r for r in state['source_files']}
    if set(blobs) != set(expected) | {r['path'] for r in state['additional_files']}:
        raise RuntimeError('원격 audit-suite 파일 집합이 소스 ZIP과 다릅니다.')
    for row in state['source_files'] + state['additional_files']:
        remote = blobs.get(row['path'])
        if not remote or remote['sha'] != row['git_blob_sha'] or remote.get('size') != row['bytes'] or remote['mode'] not in ('100644', '100755'):
            raise RuntimeError('소스 ZIP/README/CI의 원격 Git blob 바이트가 다릅니다: ' + row['path'])
    output = {'phase': 'VERIFIED', 'repository': REPOSITORY, 'private': False, 'tag': TAG, 'commit': state['commit'],
              'prerelease': True, 'url': release['html_url'], 'source_files': len(expected),
              'remote_git_blob_sha_exact': True, 'base_commit': state['base'], 'patch_commits':patch_commits(state), 'previous_release_preserved': True, 'preserved_tags':sorted(PREVIOUS_RELEASES), 'preserved_workflows':list(OLD_WORKFLOW_PATHS), 'previous_repository_private': True, 'assets': assets, 'ci_url': ci['url']}
    state.update(phase='VERIFIED', url=release['html_url'], ci=ci)
    save_state(state)
    write_json(WORK / 'release-verified.json', output)
    return output


def main():
    parser = argparse.ArgumentParser(description='기존 공개 저장소의 v1.8.1 fast-forward 릴리스 도구')
    parser.add_argument('--mode', required=True, choices=['inspect', 'stage', 'revise', 'status', 'publish', 'verify'])
    parser.add_argument('--windows-asset', default=DEFAULT_WINDOWS_NAME, help='배포 폴더의 Windows ZIP 이름(stage 신규 시작에만 적용)')
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    api = GitHub()
    if args.mode == 'status':
        api.inspect()
    if args.mode == 'inspect':
        output = api.inspect()
    elif args.mode == 'stage':
        output = stage(api, args.windows_asset)
    elif args.mode == 'revise':
        output = revise(api)
    elif args.mode == 'status':
        output = status(api)
    elif args.mode == 'publish':
        output = publish(api)
    else:
        output = verify(api)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('작업을 중단했습니다. 저장된 상태를 확인한 뒤 재개하세요.', file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        # Only our controlled errors are safe to print. Unexpected exceptions can
        # embed URLs/credential helper output and therefore use a generic message.
        print(str(exc) if isinstance(exc, RuntimeError) else '릴리스 도구 입력/실행 오류. 인증 내용은 출력하지 않습니다.', file=sys.stderr)
        raise SystemExit(1)
