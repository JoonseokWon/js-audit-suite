"""Package only a finished v1.9.0 candidate and an explicit public allowlist.

Import performs no work. This tool never builds, tests, runs AI, repairs proof,
changes workspaces, or contacts GitHub. Missing proof is a hard failure.
"""
from __future__ import annotations

from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import os
import stat
import struct
import tempfile
import zipfile

SOURCE = Path(__file__).resolve().parents[1]
PROJECT = SOURCE.parents[1]
QA = PROJECT / '검증' / 'v1.9.0'
VERSION = '1.9.0'
SOURCE_PREFIX = 'js-audit-suite/'
WINDOWS_PREFIX = 'JS-Audit-Suite-v1.9.0/'
EXE_NAME = '통합 회계감사 v1.9.0.exe'
SOURCE_NAME = 'js-audit-suite-v1.9.0-source.zip'
WINDOWS_NAME = 'JS-Audit-Suite-v1.9.0-windows.zip'
VALIDATION_NAME = 'validation-report.json'
NAMES = (WINDOWS_NAME, SOURCE_NAME, VALIDATION_NAME, 'SHA256SUMS.txt')
BASELINE_SOURCE_SHA256 = '75914a9e36c281faf5e02b39201a45c4780f69f1c1aaafa5a4f6474852a1e767'
BASELINE_COUNT = 1739
IMMUTABLE = ('sector_resources/', 'samples/', 'templates/', 'testdata/', 'raw_input_seed/',
             'reference_evidence/', 'raw_analytics/', '.runtime/', 'tools/', 'ci/')
PINNED_POLICY_MODULES = {
    'tools/package_v181.py': '50312b7626d7de7896ab83ec6f8e7e9d4f6e972338d6dd088b6315dec4ec720c',
    'tools/package_v18.py': '08900ea472aa21de97d125f855b62eedf889d4462e3c57610db22cdc688f05a1',
}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_module(name, relative):
    path = SOURCE / relative
    require(path.resolve().is_relative_to(SOURCE.resolve()), '패키지 도구 경로 이탈')
    for part in (path, *path.parents):
        if part.exists():
            info = part.lstat()
            require(not part.is_symlink() and not getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400),
                    '연결 경로의 패키지 도구는 실행하지 않습니다.')
        if part == SOURCE:
            break
    if relative in PINNED_POLICY_MODULES:
        require(path.is_file() and sha(path.read_bytes()) == PINNED_POLICY_MODULES[relative], '보존할 기존 패키지 정책 코드가 변경되었습니다.')
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, '고정된 패키지 도구를 읽지 못했습니다.')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_policy():
    helper = load_module('_release_policy_v19', 'tools/github_release_v19.py')
    previous = load_module('_package_policy_v181', 'tools/package_v181.py')
    redactor = load_module('_package_redactor_v18', 'tools/package_v18.py')
    require(helper.TAG == 'v1.9.0' and helper.SOURCE_NAME == SOURCE_NAME, '공개 helper 버전 불일치')
    return helper, previous, redactor


def baseline_payloads(helper, previous, baseline=None):
    baseline = baseline or PROJECT / '릴리스' / 'js-audit-suite-v1.8.1-source.zip'
    path = previous.safe_file(baseline.parent, baseline.name)
    require(path.is_file() and sha(path.read_bytes()) == BASELINE_SOURCE_SHA256,
            '보존할 v1.8.1 공개 소스 ZIP 해시가 다릅니다.')
    old = {}
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None, '기준 공개 ZIP CRC 오류')
        for info in archive.infolist():
            require(not info.is_dir() and info.orig_filename == info.filename and info.filename.startswith(SOURCE_PREFIX),
                    '기준 공개 ZIP 경로 오류')
            relative = info.filename[len(SOURCE_PREFIX):]
            helper.allowed_public_path(relative)
            require(relative not in old and not info.flag_bits & 1 and stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG),
                    '기준 공개 ZIP 중복·특수파일 오류')
            old[relative] = archive.read(info)
    require(len(old) == BASELINE_COUNT, '기준 공개 소스 1739개 보존 조건 불일치')
    return old


def source_payloads(helper, previous, baseline=None, source=None):
    source = source or SOURCE
    old = baseline_payloads(helper, previous, baseline)
    selected = set(old) | helper.NEW_REQUIRED
    payloads = {}
    for relative in sorted(selected):
        helper.allowed_public_path(relative)
        path = previous.safe_file(source, relative)
        require(relative not in helper.NEW_REQUIRED | helper.HISTORICAL_UPDATES or path.is_file(), 'v1.9.0 공개 필수 현재 파일 누락: ' + relative)
        payload = path.read_bytes() if path.is_file() else old[relative]
        if relative in old and relative.startswith(IMMUTABLE) and relative not in helper.HISTORICAL_UPDATES:
            require(payload == old[relative], '이전 공개 데이터·도구·CI·Tcl 자료가 변경되었습니다: ' + relative)
        payloads[relative] = payload
    require(set(old) <= set(payloads) and set(payloads) == set(old) | helper.NEW_REQUIRED,
            '명시한 공개 파일 집합이 다릅니다.')
    require(payloads['ci/audit-suite-v19.yml'] == helper.DEFAULT_WORKFLOW.encode('utf-8'), '새 공개 CI 바이트 불일치')
    return payloads, old


def current_checks(helper, previous, source=None, project=None):
    source = source or SOURCE
    project = project or PROJECT
    proof = previous.read_json(previous.safe_file(project, '검증/v1.9.0/final-validation.json'))
    helper.validate_proof(proof)
    # Include every current root Python/spec/manifest file, not a hand-picked
    # subset of the actual application and tests.
    roots = {path.name for path in source.iterdir() if path.is_file() and path.suffix in ('.py', '.spec', '.manifest')}
    require(roots <= set(proof['build_inputs']), '현재 root Python/spec/manifest가 빌드 입력에서 누락되었습니다.')
    for relative, expected in proof['build_inputs'].items():
        path = previous.safe_file(source, relative)
        require(path.is_file() and sha(path.read_bytes()) == expected, '고정된 v1.9.0 빌드 입력 변경: ' + relative)
    ime_path = previous.safe_file(project, '검증/실제한글입력.json')
    ime = previous.read_json(ime_path)
    require(ime.get('status') == 'passed' and sha(ime_path.read_bytes()) == proof['ime']['baseline_evidence_sha256'],
            '재사용하는 v1.8.1 실제 IME 증거가 변경/누락되었습니다.')
    exe_path = previous.safe_file(project, '실행파일/' + EXE_NAME)
    require(exe_path.is_file(), '검증한 v1.9.0 EXE가 없습니다.')
    exe = exe_path.read_bytes()
    require(len(exe) == proof['exe']['bytes'] and sha(exe) == proof['exe']['sha256'], '현재 EXE가 검증한 바이트와 다릅니다.')
    require(len(exe) >= 64 and exe[:2] == b'MZ', 'Windows PE 실행파일 형식 오류')
    pe_offset = struct.unpack_from('<I', exe, 60)[0]
    require(pe_offset < len(exe) - 4 and exe[pe_offset:pe_offset + 4] == b'PE\0\0', 'Windows PE 서명 오류')
    config = previous.safe_file(project, '실행파일/portable-config.json').read_bytes()
    require(config == previous.safe_file(source, 'assets/portable-config.json').read_bytes(), '포터블 설정 원본과 실행본이 다릅니다.')
    require(json.loads(config.decode('utf-8-sig')) == {'schema_version': 1, 'data_directory': '../데이터/회사별업무'},
            '포터블 업무 상대 위치를 변경할 수 없습니다.')
    return proof, exe, config


def public_validation(helper, redactor, proof, source_zip, sources, old):
    # Publish approved summary fields, never arbitrary QA output or document text.
    public = {key: copy.deepcopy(proof[key]) for key in (
        'schema', 'version', 'status', 'unit', 'build_inputs', 'exe',
        'source_frozen_observations_identical', 'portable_layout_verified',
        'icon_embedded_verified', 'unicode_roundtrip_verified', 'current_actual_model_calls')}
    public['headless'] = {mode: {'ok': proof['headless'][mode]['ok'], 'checks': copy.deepcopy(proof['headless'][mode]['checks'])}
                          for mode in ('source', 'frozen')}
    public['unit'] = {key: proof['unit'][key] for key in ('tests', 'errors', 'failures', 'skipped')}
    public['exe'] = {key: proof['exe'][key] for key in ('name', 'bytes', 'sha256')}
    public['ime'] = {key: proof['ime'][key] for key in ('current_actual_key_test', 'baseline_version', 'baseline_evidence_sha256', 'scope')}
    public.update(supported_scope=helper.SUPPORTED_SCOPE,
                  source={'name': SOURCE_NAME, 'files': len(sources), 'sha256': sha(source_zip.read_bytes()),
                          'previous_public_paths_preserved': len(old), 'baseline_source_sha256': BASELINE_SOURCE_SHA256},
                  source_frozen_comparison_scope='같은 기호화 업무 단언의 통과 비교. 랜덤 UUID·절대경로·실행시각·raw DB/ZIP 바이트의 동일성을 주장하지 않음.',
                  previous_tags_preserved=sorted(helper.PREVIOUS_RELEASES),
                  previous_root_workflows_preserved=list(helper.OLD_WORKFLOW_PATHS),
                  historical_helper_updates=[{'path': path, 'baseline_sha256': sha(old[path]),
                                              'current_sha256': sha(sources[path]),
                                              'reason': 'v1.9.0 F01/FS01 명시적 목적의 회귀 fixture 및 고정 합성 모본 ID 설명. 현재 로컬 바이트를 배포하며 build_inputs로 고정.'}
                                             for path in sorted(helper.HISTORICAL_UPDATES)],
                  public_files_selected_by_explicit_allowlist=True,
                  official_original_documents_workspaces_models_keys_logs_excluded=True,
                  limitations=[
                      '설계상 서식 참고 연결이며 공식 82권의 전체 셀 자동작성 또는 기준 전수 준수 인증이 아님.',
                      '실제 수행·판단·승인·검토·감사완료와 감사의견은 사람의 책임이며 이름 입력은 본인인증이 아님.',
                      '현재 실제 모델 호출은 0회이며 과거 모델 증거를 새 추론 실측으로 표시하지 않음.',
                      '실제 IME 키입력은 v1.8.1 baseline 재사용. v1.9.0은 Unicode 저장·재열기·XLSX 왕복을 재검증.',
                      '소스/EXE 비교는 같은 업무 단언의 통과이며 원시 파일 해시 동일 비교가 아님.',
                      '합성자료는 독립된 실제 감사증거가 아님.',
                  ])
    return redactor.public_json(public)


def verify_inputs(previous, sources, proof, exe, config):
    for relative, expected in proof['build_inputs'].items():
        require(sha(previous.safe_file(SOURCE, relative).read_bytes()) == expected, '패키징 도중 빌드 입력 변경: ' + relative)
    for relative, payload in sources.items():
        path = previous.safe_file(SOURCE, relative)
        if path.is_file():
            require(path.read_bytes() == payload, '패키징 도중 공개 소스 변경: ' + relative)
    require(previous.safe_file(PROJECT, '실행파일/' + EXE_NAME).read_bytes() == exe, '패키징 도중 EXE 변경')
    require(previous.safe_file(PROJECT, '실행파일/portable-config.json').read_bytes() == config, '패키징 도중 포터블 설정 변경')


def write_new_or_identical(previous, folder, name, raw):
    target = previous.safe_file(folder, name)
    if target.exists():
        require(target.is_file() and target.read_bytes() == raw, '기존 다른 내용의 배포 파일은 덮어쓰지 않습니다: ' + name)
        return
    try:
        with target.open('xb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise RuntimeError('배포 대상 경합. 기존 파일을 덮어쓰지 않았습니다: ' + name) from exc
    require(target.read_bytes() == raw, '최종 배포 파일 바이트 불일치')


def main():
    helper, previous, redactor = load_policy()
    proof, exe, config = current_checks(helper, previous)
    sources, old = source_payloads(helper, previous)
    # All proof and source-policy checks finish before any output is created.
    QA.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='package-', dir=QA) as temporary:
        stage = Path(temporary)
        source_zip = stage / SOURCE_NAME
        previous.write_archive(source_zip, sources, SOURCE_PREFIX)
        require(helper.publication_files(source_zip) == sources, 'source ZIP 전체 파일 재검증 불일치')
        validation_data = public_validation(helper, redactor, proof, source_zip, sources, old)
        windows = {'실행파일/' + EXE_NAME: exe, '실행파일/portable-config.json': config,
                   'README.md': redactor.redact_text(sources['README.md'].decode('utf-8-sig')).encode('utf-8'),
                   VALIDATION_NAME: validation_data}
        for relative, payload in sources.items():
            if relative.startswith('sector_resources/'):
                windows['데이터/업종별_합성원천자료/' + relative.removeprefix('sector_resources/')] = payload
            elif relative.startswith('문서/'):
                windows[relative] = (redactor.public_json(json.loads(payload.decode('utf-8-sig'))) if relative.endswith('.json')
                                     else redactor.redact_text(payload.decode('utf-8-sig')).encode('utf-8'))
            elif relative.startswith('라이선스/'):
                windows[relative] = payload
        windows['문서/회사별업무_보관안내.txt'] = (
            '실행파일/통합 회계감사 v1.9.0.exe와 portable-config.json을 함께 두세요.\n'
            '데이터/회사별업무는 새 업무를 위한 빈 폴더이며 실제 업무·원본·키·모델을 포함하지 않습니다.\n'
            '기존 업무와 과거 EXE를 보존하고 새 버전에서 확인할 업무는 별도 보관 사본을 사용하세요.\n').encode('utf-8')
        windows['파일목록_SHA256.json'] = previous.json_bytes([{'file': name, 'bytes': len(raw), 'sha256': sha(raw)}
                                                           for name, raw in sorted(windows.items())])
        previous.write_archive(stage / WINDOWS_NAME, windows, WINDOWS_PREFIX, empty_directories=('데이터/회사별업무/',))
        (stage / VALIDATION_NAME).write_bytes(validation_data)
        assets = {name: {'name': name, 'bytes': (stage / name).stat().st_size, 'sha256': sha((stage / name).read_bytes())}
                  for name in (WINDOWS_NAME, SOURCE_NAME, VALIDATION_NAME)}
        sums = ''.join(assets[name]['sha256'] + '  ' + name + '\n' for name in (WINDOWS_NAME, SOURCE_NAME, VALIDATION_NAME)).encode('utf-8')
        (stage / 'SHA256SUMS.txt').write_bytes(sums)
        assets['SHA256SUMS.txt'] = {'name': 'SHA256SUMS.txt', 'bytes': len(sums), 'sha256': sha(sums)}
        helper.validate_current_evidence(json.loads(validation_data), assets, stage / WINDOWS_NAME)
        verify_inputs(previous, sources, proof, exe, config)
        destinations = (SOURCE / '배포', PROJECT / '릴리스' / 'v1.9.0')
        for folder in destinations:
            previous.safe_file(folder.parent, folder.name)
            folder.mkdir(parents=True, exist_ok=True)
            for name in NAMES:
                target = previous.safe_file(folder, name)
                require(not target.exists() or target.read_bytes() == (stage / name).read_bytes(),
                        '다른 내용의 기존 배포 파일은 덮어쓰지 않습니다: ' + name)
        for folder in destinations:
            for name in NAMES:
                write_new_or_identical(previous, folder, name, (stage / name).read_bytes())
        verify_inputs(previous, sources, proof, exe, config)
        require(helper.local_artifacts(WINDOWS_NAME)[0] == assets, '최종 release helper의 첨부 검증 불일치')
    report = {'version': VERSION, 'status': 'passed', 'source_files': len(sources),
              'previous_public_paths_preserved': len(old), 'current_actual_model_calls': 0,
              'supported_scope': helper.SUPPORTED_SCOPE, 'remote_operations_performed': False,
              'assets': list(assets.values())}
    (QA / 'package-validation.json').write_bytes(previous.json_bytes(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    except Exception:
        raise SystemExit('v1.9.0 패키징 입력/실행 오류. 원본을 보존하고 로컬 검증 기록을 확인하세요.')
