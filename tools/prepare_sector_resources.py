"""Package immutable synthetic company inputs; do not import old workspaces.

Build: python tools/prepare_sector_resources.py
Check a shipped resource tree: ... --validate-only --output-dir sector_resources
Reports go to stdout, never into the manifest-controlled resource tree.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import sys
import time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT.parent / 'JS_업종별_더미업무_2026-10-23'
DEFAULT_OUTPUT = ROOT / 'sector_resources'
COMPANY_CODES = ('JS', 'JS_ELEC', 'JS_AUTO', 'JS_SEMI', 'JS_BIO')
MODULE_FILES = (
    ('원장·리드', '통합_v1.3_원장_리드.xlsx'),
    ('금융상품', '통합_v1.3_금융상품.xlsx'),
    ('매출', '통합_v1.3_매출.xlsx'),
    ('감가상각', '통합_v1.3_감가상각.xlsx'),
    ('확장검사', '통합_v1.3_확장검사.xlsx'),
    ('리스', '통합_v1.3_리스.xlsx'),
    ('대손충당금', '통합_v1.3_대손충당금.xlsx'),
    ('재고평가', '통합_v1.3_재고평가.xlsx'),
    ('종업원급여', '통합_v1.3_종업원급여.xlsx'),
    ('미기록부채·비용이연', '비용이연_01_정상.xlsx'),
    ('원천증빙', '통합_v1.4_원천증빙.auditpack'),
    ('재무제표·주석', '통합_v1.4_재무제표.json'),
    ('GLA', '통합_v1.5_GLA.xlsx'),
    ('FIA', '통합_v1.5_FIA.xlsx'),
    ('현금분석', '통합_v1.5_현금분석.xlsx'),
)
METADATA_FILES = {'master': '품목자산_마스터.json',
                  'profile': '업종설정.json', 'plan': '업종별_감사검토계획.json'}
# Frozen sector-resources-1/engine 1.7 source-manifest IDs. Do not migrate the
# immutable source bundle. New workspaces use procedures.task_definitions and
# Workspace.required_procedures, where the financial reconciliation is FS01.
COMMON_PROCEDURES = ('C02', 'C04', 'C05', 'P01', 'P07', 'A01', 'A02',
                     'A04', 'A06', 'A07', 'A08', 'A09', 'A10', 'A11',
                     'A12', 'A15', 'A16', 'R01', 'F01', 'G01', 'I01', 'H01')
CONTEXT_FIELDS = ('회사코드', '회사명', '시작일', '기준일', '회계체계', '감사기준', '작성자', '더미업무')
PACK_CONTEXT = ('회사코드', '시작일', '기준일', '통화', '연결구분')
ABSOLUTE = re.compile(r'(?<![A-Za-z])[A-Za-z]:[\\/]|file://|(?:^|["\s])/(?:Users|home|mnt|tmp)/')
SUPPLEMENTAL_PROCEDURES = {'R01', 'F01', 'G01', 'I01', 'H01'}
RESOURCE_README = """# 업종별 내장 합성자료

이 폴더는 JS·JS전자·JS자동차·JS반도체·JS바이오의 읽기 전용 연습 모본이다.
회사별 입력 15개와 품목·자산 마스터, 업종 설정, 조건부 수동 감사계획을 제공한다.
실제 기업 자료·실제 독립 증거·회계기준 적합성 인증이 아니다.

앱은 선택 회사 자료를 사용자 쓰기 위치의 새 별도 업무로 복사한 뒤 현재 원장,
원천증빙, 모듈 결과, 조서 연결을 다시 계산해야 한다. 기존 업무 DB·이력·조서와
검토 완료 상태는 내장하지 않는다. source_baseline은 이전 검증의 관찰 기록이며
계산 입력이나 검토 결론으로 사용하면 안 된다. 동적 예외 조서 ID도 매 실행 생성한다.

판매 EA 두 품목과 보관 EA/KG 두 품목은 회사별 master.json·profile.json에 있다.
포장 EA와 벌크 KG의 별도 SKU 및 합성 1:1 환산 선언은 profile.json의
explicit_unit_bridge로 연결한다. 이 선언은 자동 재고 전과정 환산 구현을 뜻하지 않는다.
수치·단위·계정은 기존 검사용 축소 모본을 유지하며 업종별 시장 수치가 아니다.

업종 추가 20주제는 활동·계약이 있을 때의 수동 계획이다. 보증·연구개발·수율·
의약품 제조 등의 활동을 더미 회사에 임의로 가정하지 않는다. 감사 수행·판단·
결론·검토·조정 승인은 비워 두며, GLA 후보도 사람이 원문과 증빙을 확인한다.
실제 AI 추론·외부 전송은 없다. 지분율·내부거래·연결제거 자료는 설정하지 않았다.

manifest.json은 자신을 제외한 모든 파일의 SHA256·크기와 회사별 입력·메타데이터,
기본 문맥·수동 검토주제·안정 절차 코드를 기록한다. 해시는 변조 비교에 사용되며
자료의 진정성이나 외부 독립성을 증명하지 않는다. 원천 16권은 .auditpack 안에만
보존하여 중복으로 풀어 두지 않는다. master.json의 profile_file만 새 이름으로 정규화했다.

reference/에는 원본 항목표·공식 출처·업종 설계·치환 근거를 참고용으로 보존했다.
참고 파일의 과거 버전/상대 원문 위치는 출처 표기이며 실행할 외부 경로가 아니다.
procedure_catalog.json은 앱의 기존 절차 카탈로그와 같은 원본 바이트다.

생성·검증: tools/prepare_sector_resources.py. --validate-only는 파일·문맥·메타데이터와
원천 패키지 및 현재 원장 일치를 검사한다. --run-engines는 추가로 실제 75회 계산한다.
검증 보고서는 표준 출력으로 내보내며 이 읽기 전용 리소스에 저장하지 않는다.
"""


class ResourceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ResourceError(message)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def strict_json(data, label):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f'{label}: duplicate key {key}')
            result[key] = value
        return result
    def constant(value):
        raise ResourceError(f'{label}: invalid numeric constant {value}')
    try:
        return json.loads(data.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ResourceError(f'{label}: invalid JSON') from exc


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_record(path, data):
    return {'path': path, 'sha256': sha(data), 'bytes': len(data)}


def safe_path(root, name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name,
            'invalid resource path')
    parts = name.split('/')
    require(not PurePosixPath(name).is_absolute() and
            all(p not in ('', '.', '..') and not p.endswith((' ', '.')) for p in parts),
            'absolute/traversal resource path')
    result = root.joinpath(*parts)
    require(result.resolve().is_relative_to(root.resolve()), 'resource path escaped root')
    require(not any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction())
                    for p in [result, *result.parents] if p.is_relative_to(root)),
            'resource links/junctions are not allowed')
    return result


def scan_portable(data, name):
    """Reject local absolute locations, including in ZIP XML/JSON, without extracting."""
    suffix = Path(name).suffix.lower()
    if suffix in ('.json', '.md', '.txt', '.xml', '.rels'):
        text = data.decode('utf-8-sig')
        require(not ABSOLUTE.search(text), f'{name}: local absolute path must not be embedded')
    elif suffix in ('.xlsx', '.auditpack'):
        with ZipFile(BytesIO(data)) as z:
            for info in z.infolist():
                require(info.file_size <= 25 * 1024**2, f'{name}: oversized ZIP member')
                if info.filename.endswith(('.json', '.xml', '.rels', '.xlsx')):
                    scan_portable(z.read(info), info.filename)


def _topic_summary(topic):
    return {key: topic[key] for key in ('id', 'title', 'workpaper_id',
                                      'additional_workpaper_ids', 'activity_condition')}


def prepare_resources(source_dir=DEFAULT_SOURCE, output_dir=DEFAULT_OUTPUT, run_engines=False):
    """Build deterministically; refuse overwrite of an existing different resource tree."""
    source, output = Path(source_dir).resolve(), Path(output_dir).resolve()
    require(source.is_dir(), 'source company pack is missing')
    require(output.is_relative_to(ROOT) and output != ROOT, 'output must be inside this v1.6 project')
    require(not output.is_relative_to(source) and not source.is_relative_to(output), 'source/output overlap')
    originals = {}
    payload = {}
    origin_records = []

    def read_source(relative):
        p = safe_path(source, relative)
        require(p.is_file(), f'missing source: {relative}')
        data = p.read_bytes()
        originals[p] = sha(data)
        return data

    def copy(relative, target):
        data = read_source(relative)
        scan_portable(data, target)
        payload[target] = data
        origin_records.append({'source_root': source.name, 'source_path': relative,
                               'source_sha256': sha(data), 'resource_path': target,
                               'resource_sha256': sha(data), 'normalization': None})
        return file_record(target, data)

    companies = []
    for code in COMPANY_CODES:
        prefix, dest = f'회사별/{code}/', f'companies/{code}/'
        inputs = [{'module': module, **copy(prefix + '입력자료/' + filename, dest + 'inputs/' + filename)}
                  for module, filename in MODULE_FILES]
        metadata = {}
        for kind, filename in METADATA_FILES.items():
            target = dest + kind + '.json'
            metadata[kind] = copy(prefix + filename, target)
            if kind == 'master':
                master = strict_json(payload[target], target)
                require(master.get('profile_file') == '업종설정.json', 'unexpected master profile reference')
                master['profile_file'] = 'profile.json'
                payload[target] = encoded(master)
                metadata[kind] = file_record(target, payload[target])
                origin_records[-1].update(resource_sha256=sha(payload[target]),
                                          normalization='profile_file: 업종설정.json → profile.json only')
        profile = strict_json(payload[metadata['profile']['path']], code + '/profile')
        plan = strict_json(payload[metadata['plan']['path']], code + '/plan')
        prior = strict_json(read_source(prefix + '검증결과.json'), code + '/prior verification')
        review = strict_json(read_source(prefix + '검토맥락.json'), code + '/prior context')
        context = {key: review['engagement'][key] for key in CONTEXT_FIELDS}
        context.update(통화='KRW', 연결구분='별도')
        topics = plan['audit_topics']
        procedures = set(COMMON_PROCEDURES)
        for topic in topics:
            procedures.add(topic['workpaper_id'])
            procedures.update(topic['additional_workpaper_ids'])
        companies.append({'code': code, 'name': profile['name'], 'sector': profile['sector'],
                          'business_description': profile['business_assumption'],
                          'context': context, 'inputs': inputs, 'metadata': metadata,
                          'industry_topics': [_topic_summary(t) for t in topics],
                          'industry_topic_count': len(topics), 'procedure_ids': sorted(procedures),
                          'source_baseline': {
                              'kind': 'prior-observation-only; never calculation input',
                              **{key: prior[key] for key in ('modules', 'current_ledger_links',
                                  'review_candidates', 'procedures', 'industry_topics')},
                              'source_file': prefix + '검증결과.json',
                              'source_sha256': originals[source / prefix / '검증결과.json'],
                              'not_external_independent_evidence': True}})

    for relative, target in (
            ('JS_업종별_항목표.xlsx', 'reference/JS_업종별_항목표.xlsx'),
            ('sector_design/official_sources.md', 'reference/official_sources.md'),
            ('sector_design/sector_audit_checks.json', 'reference/sector_audit_checks.json'),
            ('sector_design/sector_profiles.json', 'reference/sector_profiles.json')):
        copy(relative, target)
    catalog_path = ROOT / 'procedure_catalog.json'
    catalog_bytes = catalog_path.read_bytes()
    originals[catalog_path] = sha(catalog_bytes)
    legacy_catalog = ROOT.parent / 'v1.5_GLA_FIA_현금분석_2026-10-23' / 'procedure_catalog.json'
    if legacy_catalog.is_file():
        require(legacy_catalog.read_bytes() == catalog_bytes, 'catalog must match original v1.5 bytes')
        originals[legacy_catalog] = sha(catalog_bytes)
    scan_portable(catalog_bytes, 'procedure_catalog.json')
    payload['procedure_catalog.json'] = catalog_bytes
    origin_records.append({'source_root': 'engine-catalog', 'source_path': 'procedure_catalog.json',
                           'source_sha256': sha(catalog_bytes), 'resource_path': 'procedure_catalog.json',
                           'resource_sha256': sha(catalog_bytes), 'normalization': None})
    payload['README.md'] = RESOURCE_README.encode('utf-8')
    manifest = {'schema_version': 'sector-resources-1', 'engine_contract': '1.6',
                'synthetic': True, 'uses_ai_inference': False,
                'scope': 'five separate synthetic engagements; no consolidation or completed human judgment',
                'source_bundle': source.name, 'procedure_catalog': 'procedure_catalog.json',
                'procedure_policy': 'stable IDs only; runtime exception IDs are generated from the current run',
                'companies': companies,
                'files': [file_record(name, data) for name, data in sorted(payload.items())],
                'provenance': origin_records,
                'normalization_policy': 'inputs/profile/plan/catalog/reference bytes unchanged; master.profile_file only'}
    payload['manifest.json'] = encoded(manifest)
    # Inspect the complete intended tree before writing anything; never remove arbitrary paths.
    if output.exists():
        require(not output.is_symlink(), 'output cannot be a link')
        existing = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
        require(not existing - set(payload), 'existing resource tree has unlisted files; preserve it and use a new output')
        for name in existing:
            require(safe_path(output, name).read_bytes() == payload[name],
                    f'existing resource differs: {name}; preserve it and use a new output')
    for name, data in payload.items():
        path = safe_path(output, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open('xb') as handle:
                handle.write(data)
    require(all(path.read_bytes() and sha(path.read_bytes()) == digest for path, digest in originals.items()),
            'a read-only original changed during packaging')
    report = validate_resources(output, run_engines=run_engines)
    report['source_preservation'] = {'passed': True, 'files_checked': len(originals),
                                      'source_modified': 0,
                                      'input_copies_byte_identical': len(COMPANY_CODES) * len(MODULE_FILES),
                                      'master_reference_normalizations': len(COMPANY_CODES)}
    return report


def _assert_metadata(company, master, profile, plan):
    code, name, sector = company['code'], company['name'], company['sector']
    require(master['company_code'] == profile['company_code'] == plan['company_code'] == code,
            f'{code}: metadata company code mismatch')
    require(master['company_name'] == profile['name'] == plan['company_name'] == name,
            f'{code}: metadata company name mismatch')
    require(master['sector'] == profile['sector'] == sector and master['synthetic'] is True,
            f'{code}: sector/synthetic mismatch')
    require(master['profile_file'] == 'profile.json', f'{code}: master reference mismatch')
    require(profile['business_assumption'] == company['business_description'], f'{code}: business scope mismatch')
    require(all(profile.get(k) is None for k in ('human_performance', 'conclusion', 'reviewer')) and
            profile['automatic_accounting_assumptions_added'] is False, f'{code}: human judgment must be blank')
    for row in profile['manual_review_items']:
        require(all(row.get(k) is None for k in ('performed', 'conclusion', 'reviewer')),
                f'{code}: manual review has been performed')
    for group, label in [('sales', '판매품목'), ('inventory', '보관·평가품목')]:
        items = profile['items'][group]
        expected = Counter((p['code'], p['unit']) for p in items)
        actual = Counter((p['항목'], p['단위']) for p in master['items'] if p['구분'] == label)
        require(len(items) == 2 and expected == actual, f'{code}: master/profile item mismatch')
    assets = {a['asset_id']: a['name'] for a in profile['assets']}
    require([r['항목'] for r in master['items'] if r['구분'] == '유형자산'] == [assets['A01']],
            f'{code}: asset label mismatch')
    sales, inventory = profile['items']['sales'], profile['items']['inventory']
    bridge = profile['explicit_unit_bridge']
    require([r['unit'] for r in sales] == ['EA', 'EA'] and
            [r['unit'] for r in inventory] == ['EA', 'KG'] and
            bridge['sales_sku'] == sales[1]['code'] != inventory[1]['code'] == bridge['inventory_sku'] and
            (bridge['sales_unit'], bridge['inventory_unit'], bridge['ratio']) == ('EA', 'KG', 1) and
            bridge['source']['dataset_id'] == 'D024', f'{code}: explicit EA/KG bridge mismatch')
    topics = plan['audit_topics']
    require(plan['state'] == '계획·미검토' and len(topics) == (0 if code == 'JS' else 5),
            f'{code}: manual topic count/state mismatch')
    require([_topic_summary(t) for t in topics] == company['industry_topics'] and
            len(topics) == company['industry_topic_count'], f'{code}: manifest topics mismatch')
    procedures = set(COMMON_PROCEDURES)
    for topic in topics:
        execution = topic['execution']
        require(execution['state'] == '계획·미검토' and
                all(execution[k] is False for k in ('actually_performed', 'automatic_industry_judgment', 'adjustment_approved')) and
                all(execution[k] is None for k in ('preparer', 'performed', 'reviewer', 'conclusion')),
                f'{code}: industry review already performed/approved')
        procedures.add(topic['workpaper_id'])
        procedures.update(topic['additional_workpaper_ids'])
    require(sorted(procedures) == company['procedure_ids'], f'{code}: stable procedure ID mismatch')


def _strip_rows(tables, schema):
    return {sheet: [{h: row[h] for h in headers} for row in tables[sheet]]
            for sheet, headers in schema.items()}


def _validate_company_inputs(resource_root, company, run_engines):
    # No expected observation is supplied to a calculation API.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import adapters
    import ledger
    from common import read_xlsx
    from raw_sources import load_pack
    context = company['context']
    code = company['code']
    require(context['회사코드'] == code and context['회사명'] == company['name'] and
            context['더미업무'] is True and context['통화'] == 'KRW' and context['연결구분'] == '별도',
            f'{code}: engagement context mismatch')
    require(datetime.fromisoformat(context['시작일']) <= datetime.fromisoformat(context['기준일']),
            f'{code}: period mismatch')
    require(all(context[k] for k in CONTEXT_FIELDS), f'{code}: missing engagement field')
    by_module = {entry['module']: safe_path(resource_root, entry['path']) for entry in company['inputs']}
    tables, _ = read_xlsx(by_module['원장·리드'], ledger.SCHEMA)
    expected_tables = _strip_rows(tables, ledger.SCHEMA)
    settings = {r['항목']: r['값'] for r in tables['설정']}
    for key in ('회사코드', '시작일', '기준일', '통화'):
        require(settings[key] == context[key], f'{code}: ledger {key} mismatch')
    # Main ledger is independently recalculated, not taken from financial.json or old DB.
    ledger_result = adapters.run('원장·리드', by_module['원장·리드'], context)
    require(not any(i['severity'] == '차단' for i in ledger_result['issues']), f'{code}: main ledger blocked')
    for module in ('GLA', 'FIA', '현금분석'):
        embedded, _ = read_xlsx(by_module[module])
        require(_strip_rows(embedded, ledger.SCHEMA) == expected_tables,
                f'{code}: {module} differs from the actual current seven-sheet ledger')
    fs = strict_json(by_module['재무제표·주석'].read_bytes(), code + '/financial')
    for obj in [fs['설정'], fs['TB문맥'], *fs['문서']]:
        require(all(obj[k] == context[k] for k in PACK_CONTEXT), f'{code}: financial context mismatch')
    pack = load_pack(by_module['원천증빙'], context)
    require(pack['catalog']['context'] == {k: context[k] for k in PACK_CONTEXT},
            f'{code}: source catalog context mismatch')
    for module, path in by_module.items():
        if path.suffix.lower() != '.xlsx':
            continue
        native, _ = read_xlsx(path)
        for sheet, rows in native.items():
            for row in rows:
                for key in ('회사코드', 'company_id', '회사ID'):
                    require(key not in row or row[key] == code,
                            f'{code}: {module}/{sheet} company identity mismatch')
                if row.get('항목') in ('회사코드', '시작일', '기준일', '통화'):
                    require(row['값'] == context[row['항목']], f'{code}: {module}/{sheet} settings mismatch')
    observation = {'code': code, 'input_files': len(by_module),
                   'main_ledger_blocking': 0, 'ledger_rows': len(tables['총계정원장']),
                   'tb_accounts': len(tables['시산표']), 'module_links': len(tables['모듈연결']),
                   'analytics_seven_sheet_current_ledger_matches': 3,
                   'raw_catalog_tables': len(pack['catalog']['tables']),
                   'engines_executed': 1, 'extra_engine_validation': 'not requested'}
    if run_engines:
        observations = []
        for module, _ in MODULE_FILES:
            out = ledger_result if module == '원장·리드' else adapters.run(
                module, by_module[module], context, ledger_result=ledger_result)
            blocking = sum(i['severity'] == '차단' for i in out['issues'])
            require(blocking == 0, f'{code}/{module}: engine blocking issues: {out["issues"]}')
            observations.append({'module': module, 'blocking': blocking,
                                 'review': sum(i['severity'] == '검토' for i in out['issues']),
                                 'metrics': out['metrics']})
        observation.update(engines_executed=15, extra_engine_validation='passed', observations=observations)
    return observation


def validate_resources(resource_dir=DEFAULT_OUTPUT, run_engines=False):
    """Validate resource bytes and scope without the original source folder or a GUI."""
    started = time.perf_counter()
    root = Path(resource_dir).resolve()
    manifest = strict_json((root / 'manifest.json').read_bytes(), 'manifest')
    require(manifest.get('schema_version') == 'sector-resources-1' and manifest.get('engine_contract') == '1.6',
            'resource schema/engine contract mismatch')
    require(manifest['synthetic'] is True and manifest['uses_ai_inference'] is False, 'synthetic/AI scope mismatch')
    declared = {}
    for entry in manifest['files']:
        require(set(entry) == {'path', 'sha256', 'bytes'} and entry['path'] != 'manifest.json', 'invalid file record')
        path = safe_path(root, entry['path'])
        require(entry['path'] not in declared and path.is_file(), 'duplicate/missing resource')
        require(type(entry['bytes']) is int and entry['bytes'] > 0 and
                re.fullmatch(r'[0-9a-f]{64}', entry['sha256']), 'invalid file hash/size')
        data = path.read_bytes()
        require(file_record(entry['path'], data) == entry, f'{entry["path"]}: resource SHA/bytes mismatch')
        scan_portable(data, entry['path'])
        require(path.suffix.lower() not in ('.sqlite3', '.db', '.exe', '.zip'), 'prebuilt DB/executable/archive disallowed')
        declared[entry['path']] = entry
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    require(actual == set(declared) | {'manifest.json'}, 'unlisted/missing resource file')
    require([c['code'] for c in manifest['companies']] == list(COMPANY_CODES), 'company set/order mismatch')
    catalog_ref = manifest['procedure_catalog']
    require(catalog_ref == 'procedure_catalog.json' and catalog_ref in declared, 'procedure catalog missing')
    catalog = strict_json(safe_path(root, catalog_ref).read_bytes(), 'procedure catalog')
    known_ids = {row['id'] for row in catalog['modules']} | SUPPLEMENTAL_PROCEDURES
    if (ROOT / 'procedure_catalog.json').is_file():
        require((ROOT / 'procedure_catalog.json').read_bytes() == safe_path(root, catalog_ref).read_bytes(),
                'resource catalog differs from engine catalog')
    used = Counter()
    observations = []
    for company in manifest['companies']:
        code = company['code']
        require([(e['module'], Path(e['path']).name) for e in company['inputs']] == list(MODULE_FILES),
                f'{code}: module input set/order mismatch')
        for entry in company['inputs']:
            require(entry['path'].startswith(f'companies/{code}/inputs/') and
                    {k: entry[k] for k in ('path', 'sha256', 'bytes')} == declared.get(entry['path']),
                    f'{code}: input reference differs from manifest')
            used[entry['path']] += 1
        require(set(company['metadata']) == set(METADATA_FILES), f'{code}: metadata set mismatch')
        objects = {}
        for kind, entry in company['metadata'].items():
            require(entry['path'] == f'companies/{code}/{kind}.json' and entry == declared.get(entry['path']),
                    f'{code}: metadata reference differs from manifest')
            used[entry['path']] += 1
            objects[kind] = strict_json(safe_path(root, entry['path']).read_bytes(), code + '/' + kind)
        _assert_metadata(company, **objects)
        require(set(company['procedure_ids']) <= known_ids, f'{code}: unknown procedure IDs')
        observations.append(_validate_company_inputs(root, company, run_engines))
    require(len(used) == 90 and all(count == 1 for count in used.values()), 'company resource reused/missing')
    require(sum(c['industry_topic_count'] for c in manifest['companies']) == 20, 'manual topic total mismatch')
    source_copies = {p['resource_path']: p for p in manifest['provenance']}
    require(len(source_copies) == len(manifest['provenance']) and set(source_copies) == set(declared) - {'README.md'},
            'source provenance inventory mismatch')
    for name, record in source_copies.items():
        require(record['resource_sha256'] == declared[name]['sha256'], f'{name}: provenance resource hash mismatch')
        if not name.endswith('/master.json'):
            require(record['normalization'] is None and record['source_sha256'] == record['resource_sha256'],
                    f'{name}: source bytes must be preserved')
        else:
            require(record['normalization'] == 'profile_file: 업종설정.json → profile.json only',
                    f'{name}: unexpected master normalization')
    return {'status': 'passed', 'resource_schema': manifest['schema_version'],
            'engine_contract': manifest['engine_contract'], 'companies': len(observations),
            'inputs': sum(o['input_files'] for o in observations), 'metadata_files': 15,
            'manual_industry_topics': 20, 'files_hashed': len(declared),
            'total_bytes': sum(f['bytes'] for f in declared.values()),
            'manifest_sha256': sha((root / 'manifest.json').read_bytes()),
            'old_absolute_paths': 0, 'prebuilt_workspaces_or_workpapers': 0,
            'source16_workbooks_unpacked': 0, 'uses_ai_inference': False,
            'engines_executed': sum(o['engines_executed'] for o in observations),
            'observations': observations, 'elapsed_seconds': round(time.perf_counter() - started, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--run-engines', action='store_true')
    args = parser.parse_args()
    report = (validate_resources(args.output_dir, args.run_engines) if args.validate_only else
              prepare_resources(args.source_dir, args.output_dir, args.run_engines))
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
