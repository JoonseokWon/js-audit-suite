"""Explicit fresh-history public audit-only v1.7 release operations. No action on import.

Credentials come from the existing Git credential helper and stay in memory.
Git sends source files once through its normal pack protocol. Release assets
use the GitHub upload API; no per-source-file blob upload is performed.
"""
from __future__ import annotations

import argparse
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
REMOTE = 'https://github.com/' + REPOSITORY + '.git'
TAG = 'v1.7.0'
BRANCH = 'main'
SOURCE_NAME = 'audit-suite-source-v1.7.0.zip'
DEFAULT_WINDOWS_NAME = 'AuditSuite-Windows-v1.7.0.zip'
WORKFLOW_PATH = '.github/workflows/audit-suite-v17.yml'
WORKFLOW_NAME = 'JS Audit Suite v1.7'
IDENTITY = '300881227+JoonseokWon@users.noreply.github.com'
MARKER = '<!-- audit-suite-v1.7 -->'
RELEASE_URL = 'https://github.com/' + REPOSITORY + '/releases/tag/' + TAG
DEFAULT_WORKFLOW = "name: JS Audit Suite v1.7\non:\n  push:\n    branches: [main]\n  pull_request:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  verify:\n    name: Audit Suite Python ${{ matrix.python-version }}\n    runs-on: windows-latest\n    timeout-minutes: 25\n    strategy:\n      fail-fast: false\n      matrix:\n        python-version: ['3.12', '3.14']\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: ${{ matrix.python-version }}\n      - name: Install dependencies\n        run: python -m pip install openpyxl==3.1.5 defusedxml==0.7.1\n      - name: Unit tests\n        run: python -X utf8 -B -m unittest discover -v\n      - name: Headless integration\n        run: python -X utf8 -B tools/verify_headless_v17.py --output-dir 검증/CI통합\n"


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


PUBLIC_ROOT_FILES = {'estimate_controls.py', 'new_specs.json', '.gitignore', 'test_account_cases.py', 'test_accruals.py', 'ledger.py', 'common.py', 'verify_v15.py', '.gitattributes', 'leases.py', 'window_capture.py', 'procedure_catalog.json', 'samples_specs.json', 'test_core_calculation_links.py', 'exporter.py', 'accruals.py', 'raw_binding.py', 'procedures.py', 'review_support.py', 'display_schema.py', 'test_raw_sources.py', 'test_raw_accounts.py', 'verify_v14.py', 'ecl.py', 'test_estimates.py', 'test_financial_bridge.py', 'README.md', 'test_integration_v14.py', 'AGENTS.md', 'runtime.py', 'requirements.txt', 'analytics_validation.py', 'app.py', 'test_sector_demo.py', 'adapters.py', 'AuditSuite.spec', 'payroll.py', 'v12_specs.json', 'sector_demo.py', 'test_cash_analytics.py', 'v13_specs.json', 'test_fia.py', 'test_inventory_payroll.py', 'test_gla.py', 'test_suite.py', 'test_v15_integration.py', 'inventory.py', 'verify_v17.py', 'worker_cases.json', 'INTEGRATION_CONTRACT.md', 'account_cases.py', 'analytics_support.py', 'verify.py', 'workspace.py', 'extensions.py', 'verify_v16.py'}

PUBLIC_SOURCE_DIRS = {'engines','raw_sources','raw_accounts','financial_bridge','worker_library',
                     'gla','fia','cash_analytics','samples','templates','testdata','raw_input_seed',
                     'reference_evidence','raw_analytics','sector_resources','.runtime','문서','ci','라이선스','tools'}
FORBIDDEN_PARTS = {'.git','.venv','node_modules','__pycache__','.env','config.local.json',
                   'adc.json','credentials.json','release-state.json','메일 자동화'}


def allowed_public_path(relative):
    parts = PurePosixPath(relative).parts
    if not parts or any(p.casefold() in FORBIDDEN_PARTS or p.casefold().startswith('.env.') for p in parts):
        raise RuntimeError('공개 허용목록 밖의 개인 설정/실행 파일 경로')
    lower = relative.casefold()
    if lower.endswith(('.sqlite3','.sqlite','.db','.db3','.log','.pyc','.pyo','.pem','.p12','.pfx','.key','.exe','.dll')):
        raise RuntimeError('소스 공개에 실제 업무 DB/로그/자격증명/실행파일을 포함할 수 없습니다.')
    if len(parts) == 1:
        if relative in PUBLIC_ROOT_FILES:
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
    required = {'requirements.txt', 'tools/verify_headless_v17.py', 'ci/audit-suite-v17.yml', '.gitattributes', 'README.md',
                'app.py','common.py','workspace.py','sector_demo.py','sector_resources/manifest.json','AuditSuite.spec'}
    if not required <= set(entries):
        raise RuntimeError('소스 ZIP에 requirements.txt/headless 검증 도구가 없습니다.')
    if entries['ci/audit-suite-v17.yml'] != DEFAULT_WORKFLOW.encode('utf-8'):
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
    names = [windows_name, SOURCE_NAME, 'validation.json', 'SHA256SUMS.txt']
    artifacts = {}
    for name in names:
        path = ROOT / '배포' / name
        if not path.is_file() or not 0 < path.stat().st_size < 2 * 1024**3:
            raise RuntimeError('배포 첨부파일 누락/크기 오류: ' + name)
        artifacts[name] = {'name': name, 'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())}
    validation = json.loads((ROOT / '배포/validation.json').read_text(encoding='utf-8'))
    if not isinstance(validation, dict) or validation.get('version') != '1.7.0' or validation.get('status') != 'passed':
        raise RuntimeError('validation.json은 검증을 통과한 v1.7.0 객체여야 합니다.')
    expected = {}
    for line in (ROOT / '배포/SHA256SUMS.txt').read_text(encoding='utf-8-sig').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        if not match or match[2] in expected:
            raise RuntimeError('SHA256SUMS.txt 형식/중복 오류. sha256 + 공백2개 + 파일명 형식 필수')
        expected[match[2]] = match[1]
    if set(expected) != set(names) - {'SHA256SUMS.txt'} or any(artifacts[n]['sha256'] != value for n, value in expected.items()):
        raise RuntimeError('SHA256SUMS.txt 목록 또는 실제 파일 해시가 다릅니다.')
    return artifacts, publication_files(ROOT / '배포' / SOURCE_NAME)


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
            'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'audit-suite-v17-release',
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
        user = self.call('GET', 'https://api.github.com/user')
        if user.get('login') != OWNER:
            raise RuntimeError('인증된 GitHub 계정이 요청한 소유자와 다릅니다.')
        previous = self.call('GET', 'https://api.github.com/repos/' + PREVIOUS_REPOSITORY)
        if previous.get('full_name') != PREVIOUS_REPOSITORY or previous.get('private') is not True:
            raise RuntimeError('기존 개인 저장소가 비공개 상태인지 확인하지 못했습니다.')
        repo = self.call('GET', '', optional=True)
        report = {'repository': REPOSITORY, 'private': False, 'previous_repository_private': True,
                  'authenticated_owner': OWNER, 'exists': repo is not None, 'head': None,
                  'tag_exists': False, 'tag_object': None, 'release': None}
        if repo is not None:
            if (repo.get('full_name') != REPOSITORY or repo.get('owner',{}).get('login') != OWNER
                    or repo.get('private') is not False or repo.get('visibility') != 'public'
                    or not repo.get('permissions',{}).get('push') or repo.get('archived')):
                raise RuntimeError('감사 전용 공개 저장소의 소유자·공개·쓰기 상태 확인 실패')
            branches = self.call('GET', '/branches?per_page=100')
            if len(branches) > 1 or any(b['name'] != BRANCH for b in branches):
                raise RuntimeError('신규 공개 저장소에 기대하지 않은 브랜치/내용이 있습니다.')
            ref = self.call('GET', '/git/ref/heads/' + BRANCH, optional=True) if branches else None
            if ref is not None and repo.get('default_branch') != BRANCH:
                raise RuntimeError('공개 저장소 기본 브랜치가 main이 아닙니다.')
            tags = self.call('GET', '/tags?per_page=100')
            if len(tags) > 1 or any(t['name'] != TAG for t in tags):
                raise RuntimeError('공개 저장소에 기대하지 않은 태그가 있습니다.')
            releases = self.call('GET', '/releases?per_page=100')
            if len(releases) > 1 or any(item['tag_name'] != TAG for item in releases):
                raise RuntimeError('공개 저장소에 기대하지 않은 릴리스가 있습니다.')
            tag = self.call('GET', '/git/ref/tags/' + TAG, optional=True)
            release = releases[0] if releases else None
            report.update(repo_id=repo['id'], description=repo.get('description',''),
                          head=ref['object']['sha'] if ref else None,
                          tag_exists=tag is not None, tag_object=tag.get('object') if tag else None,
                          release={'id':release['id'],'draft':release['draft'],'prerelease':release['prerelease'],
                                   'target_commitish':release['target_commitish'],'url':release['html_url']} if release else None)
        write_json(WORK / 'preflight.json', report)
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


def git(args, *, cwd=CHECKOUT, input_bytes=None, timeout=180):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
    # Hooks are never needed for publication; identity is per command, not global.
    hooks = WORK / 'disabled-hooks'
    hooks.mkdir(parents=True, exist_ok=True)
    command = ['git', '-c', 'core.autocrlf=false', '-c', 'core.filemode=false', '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=' + str(hooks),
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


def commit_files(files, state):
    """A fresh git init publishes one root commit; no private history is imported."""
    if CHECKOUT.exists():
        raise RuntimeError('새 공개 checkout이 이미 있습니다. 자동으로 재사용/초기화하지 않습니다.')
    CHECKOUT.mkdir()
    git(['init', '--object-format=sha1', '--initial-branch=' + BRANCH])
    git(['remote', 'add', 'origin', REMOTE])
    checkout_checks()
    workflow = files['ci/audit-suite-v17.yml']
    if workflow != DEFAULT_WORKFLOW.encode('utf-8'):
        raise RuntimeError('검토한 CI workflow와 소스 파일이 다릅니다.')
    changes = {**files, WORKFLOW_PATH: workflow}
    for relative,data in changes.items():
        path = CHECKOUT/Path(relative)
        if not path.resolve().is_relative_to(CHECKOUT.resolve()) or path.exists():
            raise RuntimeError('신규 공개 checkout의 파일 경로 충돌')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    pathspec = WORK/'publication-pathspec.nul'
    pathspec.write_bytes(b''.join((':(literal)'+p).encode('utf-8')+b'\0' for p in sorted(changes)))
    git(['add','-f','--pathspec-from-file='+str(pathspec),'--pathspec-file-nul'])
    staged = {p.decode('utf-8') for p in git(['diff','--cached','--name-only','-z']).split(b'\0') if p}
    if staged != set(changes):
        raise RuntimeError('공개 stage 집합이 소스 ZIP+workflow 1개와 다릅니다.')
    index = {}
    for record in git(['ls-files','--stage','-z']).split(b'\0'):
        if record:
            info,path = record.split(b'\t',1)
            mode,blob,stage = info.split(b' ')
            index[path.decode('utf-8')] = (mode.decode(),blob.decode(),stage.decode())
    if set(index) != set(changes):
        raise RuntimeError('공개 index의 전체 파일 집합이 다릅니다.')
    for relative,data in changes.items():
        if index[relative] not in (('100644',git_sha(data),'0'),('100755',git_sha(data),'0')):
            raise RuntimeError('공개 stage 원문 바이트/모드 불일치: '+relative)
    state.update(additional_files=file_manifest({WORKFLOW_PATH:workflow}),staged_paths=sorted(staged),phase='STAGED_LOCAL')
    save_state(state)
    git(['commit','-m','Publish synthetic JS audit suite v1.7 without private project history'])
    commit = git(['rev-parse','HEAD']).decode().strip()
    if git(['rev-list','--count','HEAD']).decode().strip() != '1' or len(git(['rev-list','--parents','-n','1','HEAD']).split()) != 1:
        raise RuntimeError('공개 저장소는 기존 이력을 잇지 않는 최초 커밋이어야 합니다.')
    state.update(phase='COMMITTED',commit=commit)
    save_state(state)


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
    return ('통합 감사 프로그램 v1.7 합성자료 데모입니다. 원천 증빙의 명시적 배부, 원장·리드 연결과 재무제표·주석 대사를 제공합니다.\n\n'
            '검증 범위와 한계는 validation.json 및 소스 문서를 확인하세요. 동일 생성기의 더미는 독립 감사증거가 아닙니다. '
            '실제 감사기준 준수·현장 적용을 인증하지 않으며 작성·검토·결론과 수정안 승인은 자동 확정하지 않습니다.\n\n'
            '본인 역할: 회계 요구사항·검증. 코드 구현: AI 활용. 기존 개인 저장소 이력을 포함하지 않는 감사 전용 공개 사전 릴리스입니다.\n')


def stage(api, windows_name):
    report = api.inspect()
    if STATE.exists():
        state = load_state()
        if state['phase'] in ('PUBLISHED','VERIFIED'):
            raise RuntimeError('이미 게시된 릴리스입니다. verify로 확인하세요.')
        pinned_artifacts(state)
    else:
        if report['exists']:
            raise RuntimeError('대상 저장소가 이미 있습니다. 상태 파일 없는 기존 저장소는 재사용하지 않습니다.')
        if CHECKOUT.exists():
            raise RuntimeError('상태 파일 없이 공개 checkout이 존재합니다.')
        import uuid
        assets,files = local_artifacts(windows_name)
        state = {'repository':REPOSITORY,'tag':TAG,'branch':BRANCH,'private':False,'base':None,
                 'phase':'PREPARED','repo_marker':'js-audit-suite-v17-'+uuid.uuid4().hex,
                 'windows_asset':windows_name,'local_assets':assets,'source_files':file_manifest(files)}
        save_state(state)
    if state['phase'] == 'PREPARED':
        description = 'Synthetic accounting audit portfolio; '+state['repo_marker']
        if report['exists']:
            if report['head'] or report['tag_exists'] or report['release'] or report.get('description') != description:
                raise RuntimeError('생성 요청 상태와 일치하는 빈 공개 저장소가 아닙니다.')
            if state.get('repo_id') not in (None,report['repo_id']):
                raise RuntimeError('신규 저장소 ID가 저장된 상태와 다릅니다.')
            repo_id = report['repo_id']
        else:
            repo = api.call('POST','https://api.github.com/user/repos',
                            {'name':'js-audit-suite','private':False,'auto_init':False,'description':description,
                             'has_issues':True,'has_projects':False,'has_wiki':False})
            repo_id = repo['id']
        state['repo_id'] = repo_id
        save_state(state)
        current = api.inspect()
        if (not current['exists'] or current['repo_id'] != repo_id or current['head']
                or current['tag_exists'] or current['release'] or current.get('description') != description):
            raise RuntimeError('신규 공개 저장소의 빈 상태/생성 마커 확인 실패')
        _,files = pinned_artifacts(state)
        commit_files(files,state)
    if state['phase'] == 'STAGED_LOCAL':
        raise RuntimeError('커밋 직전 중단 상태입니다. index와 상태를 검토해야 합니다.')
    if state['phase'] == 'COMMITTED':
        checkout_checks()
        if git(['rev-parse','HEAD']).decode().strip() != state['commit'] or git(['status','--porcelain=v1','-z']):
            raise RuntimeError('공개 커밋의 checkout이 변경되었습니다.')
        current = api.inspect()
        if current.get('repo_id') != state['repo_id'] or current['tag_exists'] or current['release']:
            raise RuntimeError('공개 push 전 저장소/태그/릴리스가 변경되었습니다.')
        if current['head'] is None:
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
    if current.get('repo_id') != state['repo_id'] or current['head'] != state['commit']:
        raise RuntimeError('공개 저장소의 대상 커밋/ID가 달라졌습니다.')
    if current['tag_exists'] and tag_commit(api,current['tag_object']) != state['commit']:
        raise RuntimeError('동일 태그가 다른 커밋을 가리킵니다.')
    release = api.find_release()
    if release is None:
        release = api.call('POST','/releases',{'tag_name':TAG,'target_commitish':state['commit'],
                           'name':'통합 감사 프로그램 v1.7.0 · 감사 전용 공개 데모',
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
            'assets':len(state['assets']),'private':False,'draft':True,'initial_commit_only':True}


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
        raise RuntimeError('해당 커밋의 v1.7 push CI가 없습니다.')
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


def publish(api):
    state = load_state()
    if state['phase'] != 'STAGED':
        raise RuntimeError('검증된 STAGED 상태에서만 게시할 수 있습니다.')
    pinned_artifacts(state)
    ci = ci_gate(status(api))
    current = api.inspect()
    if current['head'] != state['commit'] or current.get('repo_id') != state['repo_id']:
        raise RuntimeError('게시 전 대상 공개 저장소/커밋이 변경되었습니다.')
    if current['tag_exists'] and tag_commit(api, current['tag_object']) != state['commit']:
        raise RuntimeError('기존 태그가 배포 커밋과 다릅니다. 게시하지 않습니다.')
    release = api.call('GET', '/releases/' + str(state['release_id']))
    if not release['draft'] or release['target_commitish'] != state['commit'] or release['tag_name'] != TAG or not release['prerelease']:
        raise RuntimeError('게시할 draft/대상 커밋/태그가 다릅니다.')
    ensure_assets(api, release, state)
    body = release_notes() + '\n\nGitHub 자동 검사: [Python 3.12·3.14 성공 기록](' + ci['url'] + ')\n'
    response = api.call('PATCH', '/releases/' + str(state['release_id']),
                        {'draft': False, 'prerelease': True, 'make_latest': 'false', 'body': body})
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
    commit = api.call('GET', '/git/commits/' + state['commit'])
    if commit.get('parents') != []:
        raise RuntimeError('공개 최초 커밋에 기존 이력이 연결되어 있습니다.')
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
              'remote_git_blob_sha_exact': True, 'initial_commit_only': True, 'previous_repository_private': True, 'assets': assets, 'ci_url': ci['url']}
    state.update(phase='VERIFIED', url=release['html_url'], ci=ci)
    save_state(state)
    write_json(WORK / 'release-verified.json', output)
    return output


def main():
    parser = argparse.ArgumentParser(description='신규 감사 전용 공개 저장소의 통합 감사 프로그램 v1.7 릴리스 도구')
    parser.add_argument('--mode', required=True, choices=['inspect', 'stage', 'status', 'publish', 'verify'])
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
