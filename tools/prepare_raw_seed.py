"""Reproduce portable, synthetic XLSX fixtures without modifying originals.

First initialization: --initialize-baseline --source-root <original bundle>
Then CI/local use: python tools/prepare_raw_seed.py [--build-pack]
Only the current native 01 ledger workbook is replaced in raw_input_seed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import AuditError, atomic, plain
from raw_sources import _catalog, _json, _selection, _workbook, build_pack, load_pack

BASELINE = ROOT / 'testdata' / 'raw_source_baseline'
SEED = ROOT / 'raw_input_seed'
CURRENT_LEDGER = ROOT / 'samples' / '통합' / '통합_v1.3_원장_리드.xlsx'
CONTEXT = {'회사코드': 'SYNTH01', '시작일': '2026-01-01', '기준일': '2026-12-31', '통화': 'KRW', '연결구분': '별도'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(obj):
    return json.dumps(plain(obj), ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')


def inside(path, boundary):
    resolved = path.resolve()
    if not resolved.is_relative_to(boundary.resolve()):
        raise AuditError('재현 대상이 전용 폴더 범위를 벗어났습니다.')
    return resolved


def read_bundle(source):
    source = Path(source).resolve()
    spec_bytes = (source / 'spec.json').read_bytes()
    spec = _json(spec_bytes, 'spec.json')
    books, _ = _selection(spec)
    sources = {'sources/spec.json': spec_bytes}
    for name, _ in books:
        path = inside(source / '배포' / name, source)
        sources['sources/' + name] = path.read_bytes()
    # The same strict extraction used at import validates the input fixture.
    catalog = _catalog(spec, sources)
    return spec, sources, catalog


def copy_bundle(source, destination):
    spec, sources, catalog = read_bundle(source)
    destination = Path(destination)
    atomic(inside(destination / 'spec.json', destination), sources['sources/spec.json'])
    for name, data in sources.items():
        if name != 'sources/spec.json':
            atomic(inside(destination / '배포' / name.removeprefix('sources/'), destination), data)
    return spec, sources, catalog


def prepare(initialize_source=None, make_pack=False):
    if initialize_source is not None:
        if Path(initialize_source).resolve() == BASELINE.resolve():
            raise AuditError('초기 복사 원천과 baseline이 같습니다.')
        copy_bundle(initialize_source, BASELINE)
    if not (BASELINE / 'spec.json').is_file():
        raise AuditError('baseline이 없습니다. --initialize-baseline --source-root로 한 번 준비하세요.')
    baseline_spec, original, baseline_catalog = read_bundle(BASELINE)
    spec, _, _ = copy_bundle(BASELINE, SEED)
    candidates = [(path, book) for path, book in _selection(spec)[0]
                  if book.get('native') and book.get('folder') == '01_현재프로그램입력'
                  and set(('시산표', '총계정원장', '계정매핑', '독립통제')) <= set(book['headers'])]
    if len(candidates) != 1:
        raise AuditError('원장·리드 native book을 유일하게 식별하지 못했습니다.')
    relative, book = candidates[0]
    current_bytes = CURRENT_LEDGER.read_bytes()
    workbook = _workbook(current_bytes, CURRENT_LEDGER.name)
    if set(workbook) != set(book['headers']):
        raise AuditError('기존과 v1.3 원장·리드의 시트 목록이 다릅니다.')
    headers, tables = {}, {}
    for sheet, raw_rows in workbook.items():
        if not raw_rows:
            raise AuditError('v1.3 빈 시트: ' + sheet)
        names = list(raw_rows[0][1])
        while names and names[-1] is None:
            names.pop()
        headers[sheet] = names
        values = []
        for row, raw in raw_rows[1:]:
            vals = raw[:len(names)] + [None] * max(0, len(names) - len(raw))
            # Keep all-null physical rows as supplied; import logs their policy.
            values.append(plain(vals))
        tables[sheet] = values
    book['headers'] = headers
    book['tables'] = tables
    # These dataset declarations describe exactly the same replaced source.
    for dataset in spec['datasets']:
        if dataset['file'] == relative:
            dataset['headers'] = headers[dataset['name']]
            dataset['rows'] = tables[dataset['name']]
    tb_names = headers['시산표']
    ai, vi = tb_names.index('계정코드'), tb_names.index('기말잔액')
    spec['balances'] = {str(row[ai]): row[vi] for row in tables['시산표'] if row[ai] is not None}
    provenance = {
        'purpose': '현재 통합업무 v1.3 원장과 원천증빙 카탈로그의 동일 원장 대사',
        'baseline_spec_sha256': sha(original['sources/spec.json']),
        'replaced_source': '배포/' + relative,
        'original_xlsx_sha256': sha(original['sources/' + relative]),
        'replacement': 'samples/통합/통합_v1.3_원장_리드.xlsx',
        'replacement_xlsx_sha256': sha(current_bytes),
        'scope': '원장·리드 1권만 교체. 나머지 15권은 baseline 원문 그대로. 합성자료이며 독립 감사증거 아님.',
    }
    spec['seed_provenance'] = provenance
    atomic(inside(SEED / '배포' / relative, SEED), current_bytes)
    atomic(SEED / 'spec.json', encode(spec))
    _, seed_sources, seed_catalog = read_bundle(SEED)
    unchanged = [name for name in original if name not in ('sources/spec.json', 'sources/' + relative)]
    if not all(seed_sources[name] == original[name] for name in unchanged):
        raise AuditError('허용한 원장 외 원문이 변경되었습니다.')
    result = {
        'schema_version': 'raw-seed-preparation-1',
        'baseline': {'path': 'testdata/raw_source_baseline', 'workbooks': len(_selection(baseline_spec)[0]),
                     'tables': len(baseline_catalog['tables']), 'spec_sha256': sha(original['sources/spec.json'])},
        'seed': {'path': 'raw_input_seed', 'workbooks': len(_selection(spec)[0]), 'tables': len(seed_catalog['tables']),
                 'spec_sha256': sha(seed_sources['sources/spec.json']), 'unchanged_workbooks': len(unchanged),
                 'tb_rows': len(next(t for t in seed_catalog['tables'] if t['dataset_id'] == 'D054')['rows']),
                 'gl_rows': len(next(t for t in seed_catalog['tables'] if t['dataset_id'] == 'D055')['rows'])},
        'provenance': provenance,
        'files': [{'path': name, 'bytes': len(data), 'sha256': sha(data)} for name, data in sorted(seed_sources.items())],
    }
    if make_pack:
        output = build_pack(SEED / '정상원천증빙.auditpack', SEED)
        imported = load_pack(output, CONTEXT)
        if imported['catalog'] != seed_catalog:
            raise AuditError('정상팩 왕복 후 catalog가 다릅니다.')
        result['pack'] = imported['source'] | {'path': 'raw_input_seed/' + output.name,
                                            'populations': len(imported['links']['populations']),
                                            'allocations': len(imported['links']['allocations'])}
    atomic(SEED / 'preparation.json', encode(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initialize-baseline', action='store_true')
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--build-pack', action='store_true')
    args = parser.parse_args()
    if args.initialize_baseline != bool(args.source_root):
        parser.error('--initialize-baseline와 --source-root는 함께 지정하세요.')
    report = prepare(args.source_root if args.initialize_baseline else None, args.build_pack)
    print(json.dumps({k: v for k, v in report.items() if k in ('baseline', 'seed', 'pack')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
