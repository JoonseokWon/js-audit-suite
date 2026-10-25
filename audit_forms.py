"""Read-only index of example forms and explicitly limited design crosswalks.

Only names, hashes and worksheet names are distributed.  This module neither
opens Excel nor evaluates formulas, refreshes links, or loads VBA.  A reference
link is not an audit procedure performed, a compliance assertion or an approval.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

from defusedxml import ElementTree

from common import AuditError

SCHEMA_VERSION = 'audit-form-registry-1'
REFERENCE_FILENAME = '2026 감사조서서식(예시)-엑셀 260827.zip'
REFERENCE_SHA256 = '0be87ba0ce6db247e75a1b70b8d2f2a20fa021cadf701ee32ae8f7d44dd66740'
REFERENCE_BYTES = 11180722
# Historical internal names describe ZIP form families, not accounting rules.
# The engagement's accounting framework and selected audit standard are separate.
FRAMEWORKS = ('KIFRS', '일반기업', '소규모기업')
FRAMEWORK_FOLDERS = {
    'KIFRS': '1. K-IFRS_2026',
    '일반기업': '2. 일반기업회계기준_2026',
    '소규모기업': '3. 소규모기업용 감사조서서식(예시)_2026',
}
FRAMEWORK_ALIASES = {'K-IFRS': 'KIFRS', 'K-IFRS_2026': 'KIFRS',
                     '일반기업회계기준': '일반기업', '소규모': '소규모기업'}
MAPPING_STATUSES = ('설계상참고', '미연결', '수동판단')
SUPPLEMENTAL_IDS = frozenset(('FS01', 'R01', 'W01', 'G01', 'I01', 'H01'))
MAX_REGISTRY_BYTES = 2_000_000
_SHA = re.compile(r'[a-f0-9]{64}\Z')
_APP_ID = re.compile(r'[CPA][0-9]{2}|F0[1-8]|FS01|[RWGIH]01')


class FormRegistryError(AuditError):
    """The registry or a requested profile is invalid; do not guess a match."""


def normalize_framework(framework):
    """Normalize a form-family selector; do not infer accounting/audit rules."""
    if not isinstance(framework, str):
        raise FormRegistryError('서식계열은 문자열로 지정하세요.')
    value = FRAMEWORK_ALIASES.get(framework.strip(), framework.strip())
    if value not in FRAMEWORKS:
        raise FormRegistryError('서식계열은 KIFRS, 일반기업, 소규모기업 중 선택하세요.')
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FormRegistryError('서식 레지스트리 JSON 키가 중복되었습니다: ' + key)
        result[key] = value
    return result


def _keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected.split()):
        raise FormRegistryError(label + ' 필드 구성이 올바르지 않습니다.')


def _text(value, label, allow_empty=False):
    if (not isinstance(value, str) or (not value and not allow_empty)
            or len(value) > 2500 or any(ord(c) < 32 for c in value)):
        raise FormRegistryError(label + ' 문자열이 올바르지 않습니다.')


def _texts(value, label):
    if not isinstance(value, list) or len(set(x for x in value if isinstance(x, str))) != len(value):
        raise FormRegistryError(label + ' 목록에 중복 또는 잘못된 값이 있습니다.')
    for item in value:
        _text(item, label)


def _count(value, label):
    if type(value) is not int or value < 0:
        raise FormRegistryError(label + ' 개수가 올바르지 않습니다.')


def _hash(value, label):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise FormRegistryError(label + ' SHA-256이 올바르지 않습니다.')


def _safe_member(member):
    _text(member, 'ZIP 멤버')
    path = PurePosixPath(member)
    if ('\\' in member or ':' in member or path.is_absolute()
            or any(p in ('', '.', '..') for p in member.split('/'))):
        raise FormRegistryError('ZIP 멤버는 안전한 상대경로여야 합니다.')


def validate_registry(registry):
    """Validate strict JSON schema, source identity and all cross-references."""
    _keys(registry, 'schema_version source scope exclusions frameworks forms procedures crosswalk', '레지스트리')
    if registry['schema_version'] != SCHEMA_VERSION:
        raise FormRegistryError('지원하지 않는 서식 레지스트리 버전입니다.')
    _text(registry['scope'], '레지스트리 범위')
    _texts(registry['exclusions'], '레지스트리 제외범위')
    if not registry['exclusions'] or registry['frameworks'] != list(FRAMEWORKS):
        raise FormRegistryError('서식계열 또는 제외범위를 확인하세요.')
    source = registry['source']
    _keys(source, 'filename sha256 bytes entries directories files file_types workbooks sheets inspection', '원본')
    if (source['filename'] != REFERENCE_FILENAME or source['sha256'] != REFERENCE_SHA256
            or source['bytes'] != REFERENCE_BYTES):
        raise FormRegistryError('확인한 공식 예시 ZIP의 이름·해시·크기와 다릅니다.')
    for key, expected in [('entries', 119), ('directories', 3), ('files', 116), ('workbooks', 82), ('sheets', 435)]:
        if type(source[key]) is not int or source[key] != expected:
            raise FormRegistryError('원본 ZIP 구성 수치와 다릅니다: ' + key)
    if source['file_types'] != {'.xlsx': 80, '.xlsm': 2, '.docx': 28, '.pdf': 2, '.doc': 2, '.hwp': 2}:
        raise FormRegistryError('원본 ZIP 확장자별 구성과 다릅니다.')
    _keys(source['inspection'], 'formulas_evaluated macros_executed external_links_refreshed binaries_distributed', '읽기 정책')
    if any(value is not False for value in source['inspection'].values()):
        raise FormRegistryError('원본 실행·전문 배포는 이 레지스트리의 범위를 벗어납니다.')
    if not isinstance(registry['forms'], list) or len(registry['forms']) != source['files']:
        raise FormRegistryError('공식 예시 파일 116개가 필요합니다.')
    forms, members, file_types = {}, set(), Counter()
    for form in registry['forms']:
        _keys(form, 'official_id form_code member title framework extension bytes sha256 sheet_names macro_container vba_present external_link_parts', '서식')
        for key in ('official_id', 'form_code', 'title'):
            _text(form[key], key)
        framework = form['framework']
        if framework not in FRAMEWORKS:
            raise FormRegistryError('서식계열이 올바르지 않습니다.')
        if (not form['official_id'].startswith('official.example.2026:' + framework + ':')
                or form['official_id'] in forms):
            raise FormRegistryError('공식 참고 ID의 namespace 또는 중복을 확인하세요.')
        _safe_member(form['member'])
        if form['member'] in members or form['member'].split('/')[0] != FRAMEWORK_FOLDERS[framework]:
            raise FormRegistryError('서식 경로 중복 또는 서식계열 혼합을 확인하세요.')
        extension = PurePosixPath(form['member']).suffix.lower()
        if extension != form['extension'] or extension not in source['file_types']:
            raise FormRegistryError('서식 확장자가 올바르지 않습니다.')
        _count(form['bytes'], '파일 크기')
        _hash(form['sha256'], '파일')
        _texts(form['sheet_names'], '시트 이름')
        if extension in ('.xlsx', '.xlsm'):
            if not form['sheet_names']:
                raise FormRegistryError('통합문서 시트가 없습니다.')
        elif form['sheet_names']:
            raise FormRegistryError('Excel 이외 파일에 시트가 지정되었습니다.')
        if (type(form['macro_container']) is not bool or type(form['vba_present']) is not bool
                or form['macro_container'] != (extension == '.xlsm')):
            raise FormRegistryError('매크로 컨테이너 표기가 올바르지 않습니다.')
        _count(form['external_link_parts'], '외부 링크')
        forms[form['official_id']] = form
        members.add(form['member'])
        file_types[extension] += 1
    if dict(file_types) != source['file_types'] or sum(len(f['sheet_names']) for f in forms.values()) != source['sheets']:
        raise FormRegistryError('서식별 구성 합계가 원본 구성과 다릅니다.')
    procedures = {}
    if not isinstance(registry['procedures'], list):
        raise FormRegistryError('앱 절차 목록이 올바르지 않습니다.')
    for procedure in registry['procedures']:
        _keys(procedure, 'app_id title namespace', '앱 절차')
        _text(procedure['app_id'], '앱 절차 ID')
        _text(procedure['title'], '앱 절차명')
        if (not _APP_ID.fullmatch(procedure['app_id']) or procedure['app_id'] in procedures
                or procedure['namespace'] != 'app.procedure'):
            raise FormRegistryError('앱 절차 ID 또는 namespace 중복을 확인하세요.')
        procedures[procedure['app_id']] = procedure
    expected_ids = ({f'C{i:02}' for i in range(1, 8)} | {f'P{i:02}' for i in range(1, 9)}
                    | {f'A{i:02}' for i in range(1, 26)} | {f'F{i:02}' for i in range(1, 9)}
                    | SUPPLEMENTAL_IDS)
    if set(procedures) != expected_ids:
        raise FormRegistryError('기존 48개와 추가 6개 앱 절차 ID를 모두 명시해야 합니다.')
    if not isinstance(registry['crosswalk'], list):
        raise FormRegistryError('참고 연결 목록이 올바르지 않습니다.')
    pairs = set()
    for mapping in registry['crosswalk']:
        _keys(mapping, 'app_id framework mapping_status scope exclusions references', '참고 연결')
        pid, framework = mapping['app_id'], mapping['framework']
        if not isinstance(pid, str) or pid not in procedures or framework not in FRAMEWORKS:
            raise FormRegistryError('참고 연결에 고아 절차 ID 또는 알 수 없는 서식계열이 있습니다.')
        pair = (pid, framework)
        if pair in pairs:
            raise FormRegistryError('절차·서식계열 연결이 중복되었습니다.')
        pairs.add(pair)
        if mapping['mapping_status'] not in MAPPING_STATUSES:
            raise FormRegistryError('연결상태는 설계상참고·미연결·수동판단만 가능합니다.')
        _text(mapping['scope'], '대응범위')
        _texts(mapping['exclusions'], '대응 제외범위')
        if not mapping['exclusions'] or not isinstance(mapping['references'], list):
            raise FormRegistryError('대응 제외범위와 참고목록이 필요합니다.')
        if (mapping['mapping_status'] == '미연결') != (len(mapping['references']) == 0):
            raise FormRegistryError('미연결 상태와 실제 참고목록이 다릅니다.')
        seen_refs = set()
        for ref in mapping['references']:
            _keys(ref, 'official_id linked_sheets reference_scope', '참고 항목')
            form_id = ref['official_id']
            if not isinstance(form_id, str) or form_id not in forms or form_id in seen_refs:
                raise FormRegistryError('참고 항목에 고아·중복 공식 ID가 있습니다.')
            seen_refs.add(form_id)
            form = forms[form_id]
            if form['framework'] != framework:
                raise FormRegistryError('다른 서식계열의 파일을 혼합할 수 없습니다.')
            _texts(ref['linked_sheets'], '연결 시트')
            if not set(ref['linked_sheets']).issubset(form['sheet_names']):
                raise FormRegistryError('원본에 없는 연결 시트입니다.')
            _text(ref['reference_scope'], '참고 범위')
    if pairs != {(pid, fw) for pid in procedures for fw in FRAMEWORKS}:
        raise FormRegistryError('모든 앱 절차의 세 서식계열별 상태를 명시해야 합니다.')
    return registry


def load_registry(path=None):
    """Return an independent validated metadata dict, including in frozen EXEs."""
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    source = root / 'form_registry.json' if path is None else Path(path)
    try:
        if not source.is_file() or not 0 < source.stat().st_size <= MAX_REGISTRY_BYTES:
            raise FormRegistryError('서식 레지스트리 파일 크기 또는 종류가 올바르지 않습니다.')
        registry = json.loads(source.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique_object,
                              parse_constant=lambda value: (_ for _ in ()).throw(FormRegistryError('비유한 JSON 숫자는 허용하지 않습니다.')))
        return validate_registry(registry)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, FormRegistryError):
            raise
        raise FormRegistryError('서식 레지스트리를 읽거나 검증하지 못했습니다.') from exc


def forms_for_procedure(pid, framework='일반기업'):
    """Return linked file metadata; [] explicitly means no design reference.

    framework selects a ZIP form family, not the engagement's accounting rules
    or audit standard. All sheet_names are inventory metadata; only
    linked_sheets are in scope.
    An empty linked_sheets list denotes a file-level reference, never all cells.
    Unknown procedure IDs raise; the financial bridge is FS01, F01 is subsequent
    events.  Synthetic X-/B- exception IDs do not have official references.
    """
    registry = load_registry()
    fw = normalize_framework(framework)
    mapping = _mapping(registry, pid, fw)
    forms = {f['official_id']: f for f in registry['forms']}
    return [{**copy.deepcopy(forms[r['official_id']]), 'app_id': pid,
             'linked_sheets': list(r['linked_sheets']), 'reference_scope': r['reference_scope'],
             'mapping_status': mapping['mapping_status'], 'scope': mapping['scope'],
             'exclusions': list(mapping['exclusions'])} for r in mapping['references']]


def _mapping(registry, pid, framework):
    if not isinstance(pid, str):
        raise FormRegistryError('앱 절차 ID는 문자열이어야 합니다.')
    for mapping in registry['crosswalk']:
        if mapping['app_id'] == pid and mapping['framework'] == framework:
            return mapping
    raise FormRegistryError('참고 연결에 없는 앱 절차 ID입니다: ' + pid)


def registry_rows(framework='일반기업', procedure_ids=None):
    """Flat display/export rows, including unlinked and manual-decision rows."""
    registry = load_registry()
    fw = normalize_framework(framework)
    ids = [p['app_id'] for p in registry['procedures']] if procedure_ids is None else list(procedure_ids)
    if len(set(x for x in ids if isinstance(x, str))) != len(ids):
        raise FormRegistryError('조회 절차 ID가 중복되었거나 올바르지 않습니다.')
    titles = {p['app_id']: p['title'] for p in registry['procedures']}
    forms = {f['official_id']: f for f in registry['forms']}
    rows = []
    for pid in ids:
        mapping = _mapping(registry, pid, fw)
        for ref in mapping['references'] or [None]:
            form = forms[ref['official_id']] if ref else None
            rows.append({'절차ID': pid, '절차명': titles[pid], '서식계열': fw,
                         '공식서식ID': form['official_id'] if form else '',
                         '서식번호': form['form_code'] if form else '',
                         '파일': form['member'] if form else '',
                         '서식명': form['title'] if form else '',
                         '시트': ' / '.join(ref['linked_sheets']) if ref else '',
                         '참고단위': '시트명' if ref and ref['linked_sheets'] else ('파일' if ref else '미연결'),
                         '연결상태': mapping['mapping_status'], '대응범위': mapping['scope'],
                         '참고범위': ref['reference_scope'] if ref else '',
                         '제외범위': ' / '.join(mapping['exclusions']),
                         '원본ZIP_SHA256': registry['source']['sha256'],
                         '파일_SHA256': form['sha256'] if form else '',
                         '주의': '설계상 참고 연결. 필수절차·공식 적합성·실제 수행·감사완료를 뜻하지 않음'})
    return rows


def procedure_ids_validation(catalog):
    """Check the 48 catalog IDs; six supplemental workflow IDs are intentional."""
    registry = load_registry()
    if isinstance(catalog, dict):
        catalog = catalog.get('modules', catalog.get('procedures', []))
    if not isinstance(catalog, (list, tuple)):
        raise FormRegistryError('절차 카탈로그 목록이 필요합니다.')
    ids = [item.get('id', item.get('app_id')) if isinstance(item, dict) else item for item in catalog]
    errors = []
    if any(not isinstance(pid, str) or not pid for pid in ids):
        raise FormRegistryError('카탈로그 절차 ID가 올바르지 않습니다.')
    if len(set(ids)) != len(ids):
        errors.append('카탈로그 절차 ID 중복')
    registered = {p['app_id'] for p in registry['procedures']}
    registry_only = sorted(registered - set(ids) - SUPPLEMENTAL_IDS)
    catalog_only = sorted(set(ids) - registered)
    if registry_only:
        errors.append('카탈로그에 없는 기본 절차: ' + ', '.join(registry_only))
    if catalog_only:
        errors.append('참고 연결에 없는 카탈로그 절차: ' + ', '.join(catalog_only))
    return {'ok': not errors, 'errors': errors, 'registry_only': registry_only,
            'catalog_only': catalog_only, 'supplemental_ids': sorted(SUPPLEMENTAL_IDS)}


def _workbook_metadata(data):
    """Read workbook XML names only, without cell/formula/VBA content."""
    with zipfile.ZipFile(BytesIO(data)) as book:
        names = book.namelist()
        info = book.getinfo('xl/workbook.xml')
        if info.file_size > 2_000_000:
            raise FormRegistryError('통합문서 메타데이터가 너무 큽니다.')
        root = ElementTree.fromstring(book.read(info))
        sheets = [s.attrib['name'] for s in root.findall('{*}sheets/{*}sheet')]
        return {'sheet_names': sheets, 'vba_present': any(n.lower().endswith('/vbaproject.bin') for n in names),
                'external_link_parts': sum(n.startswith('xl/externalLinks/externalLink') and n.endswith('.xml') for n in names)}


def verify_local_reference_zip(path):
    """Verify an explicitly chosen local copy of the known ZIP, never extract.

    Hash/size mismatch stops before parsing any ZIP member.  No network lookup,
    formula evaluation, application launch, macro load or external link refresh.
    """
    registry = load_registry()
    result = {'ok': False, 'errors': [], 'sha256': '', 'counts': {},
              'member_hashes_verified': 0, 'workbooks_verified': 0, 'sheets_verified': 0,
              'formulas_evaluated': False, 'macros_executed': False, 'external_links_refreshed': False}
    try:
        source = Path(path)
        if not source.is_file() or source.suffix.lower() != '.zip' or source.stat().st_size != REFERENCE_BYTES:
            result['errors'].append('확인한 로컬 예시 ZIP과 파일 종류 또는 크기가 다릅니다.')
            return result
        # Parse the same immutable bytes whose hash was checked.  Reopening the
        # pathname after hashing would permit a concurrent replacement race.
        with source.open('rb') as handle:
            archive_bytes = handle.read(REFERENCE_BYTES + 1)
        if len(archive_bytes) != REFERENCE_BYTES:
            result['errors'].append('원본 ZIP을 읽는 중 파일 크기가 변경되었습니다.')
            return result
        result['sha256'] = hashlib.sha256(archive_bytes).hexdigest()
        if result['sha256'] != REFERENCE_SHA256:
            result['errors'].append('원본 ZIP SHA-256 불일치. 내부 파일을 읽지 않았습니다.')
            return result
        expected = {f['member']: f for f in registry['forms']}
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            infos = archive.infolist()
            files = [i for i in infos if not i.is_dir()]
            result['counts'] = {'entries': len(infos), 'directories': len(infos) - len(files), 'files': len(files),
                                'file_types': dict(Counter(PurePosixPath(i.filename).suffix.lower() for i in files))}
            if len({i.filename for i in infos}) != len(infos) or set(i.filename for i in files) != set(expected):
                result['errors'].append('ZIP 멤버 중복 또는 구성 불일치')
            if (len(infos), len(infos) - len(files), len(files)) != (119, 3, 116):
                result['errors'].append('ZIP 항목·폴더·파일 수 불일치')
            for info in files:
                _safe_member(info.filename)
                form = expected.get(info.filename)
                if form is None:
                    continue
                if info.file_size != form['bytes'] or info.file_size > 30_000_000:
                    result['errors'].append('멤버 크기 불일치: ' + info.filename)
                    continue
                data = archive.read(info)
                if hashlib.sha256(data).hexdigest() != form['sha256']:
                    result['errors'].append('멤버 해시 불일치: ' + info.filename)
                    continue
                result['member_hashes_verified'] += 1
                if form['extension'] in ('.xlsx', '.xlsm'):
                    metadata = _workbook_metadata(data)
                    if any(metadata[key] != form[key] for key in metadata):
                        result['errors'].append('통합문서 메타데이터 불일치: ' + info.filename)
                    else:
                        result['workbooks_verified'] += 1
                        result['sheets_verified'] += len(metadata['sheet_names'])
        result['ok'] = (not result['errors'] and result['member_hashes_verified'] == 116
                        and result['workbooks_verified'] == 82 and result['sheets_verified'] == 435)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError, ElementTree.ParseError) as exc:
        result['errors'].append('로컬 참고 ZIP 검증 실패: ' + type(exc).__name__)
    return result
