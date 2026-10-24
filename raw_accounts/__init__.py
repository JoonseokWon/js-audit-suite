"""Selected, signed source-to-target allocations; never an audit conclusion.

The catalog is the only source of amounts.  The link file contains explicit
selection and allocation assertions, not replacement financial values.
"""
from collections import defaultdict
from pathlib import PurePosixPath
from common import AuditError, cancelled, day, issue, num, result, text

CONTEXT_KEYS = ('회사코드', '시작일', '기준일', '통화', '연결구분')
DATE_COLUMNS = ('전기일', 'posting_date', 'invoice_date', '송장일', '거래일', '일자', '지급일', '입금일', '기준일')
COMPANY_COLUMNS = ('회사코드', 'company_code', 'company_id')
CURRENCY_COLUMNS = ('통화', 'currency')
LIMITATIONS = [
    '선택한 행과 명시적 금액 산식의 배부만 검사하며 전체 모집단의 완전성이나 실재성을 확정하지 않습니다.',
    '원천파일·원장·통제값은 동일 생성기의 합성 자료로서 독립 감사증거가 아닙니다.',
    '거래 연결은 제출된 명시적 배부 주장입니다. 거래 실질·계약조건·권리·진위·조회 발송 및 회신통제는 미검토입니다.',
    '기간·회사 열이 없는 자료는 패키지 문맥만 확인됩니다. 자료에 없는 회사와 일자를 추정하지 않습니다.',
    '상이한 대사 단계에서 같은 거래가 반복될 수 있으므로 배부액과 차이를 전체 왜곡표시 금액으로 합산하지 않습니다.',
    '미배부는 선택 자료 사이의 연결 미확인입니다. 미기록 부채나 오류 확정으로 자동 분류하지 않습니다.',
]


def _context(c):
    if not isinstance(c, dict):
        raise AuditError('문맥 객체 필수')
    out = {k: text(c.get(k), k) for k in CONTEXT_KEYS if k != '연결구분'}
    out['연결구분'] = text(c.get('연결구분', '별도'), '연결구분')
    if out['통화'] != 'KRW' or out['연결구분'] not in ('별도', '연결') or day(out['시작일']) > day(out['기준일']):
        raise AuditError('원화 및 유효한 기간·연결구분 필수')
    return out


def _row_number(value):
    if type(value) is not int or not 2 <= value <= 10001:
        raise AuditError('실제 Excel 원본행은 2~10001 정수여야 합니다.')
    return value


def _location(table, row=None):
    return table['source_file'] + ' / ' + table['sheet'] + (f'!{row}' if row is not None else '')


def analyze(pack, context, event=None):
    """Return reviewable catalog lineage and many-to-many signed reconciliations.

    Bad structure is returned as blocking issues.  Nonzero underallocation is a
    review exception, even one won.  Invalid allocations never count as posted.
    """
    c = _context({'통화': 'KRW', '연결구분': '별도'} | context)
    issues, scope, allocation_rows, checks, inventory, unconfirmed = [], [], [], [], [], []
    populations, selected, tables = {}, {}, {}
    source_info = pack.get('source', {}) if isinstance(pack, dict) else {}

    def bad(code, message, ref='', blocking=True):
        issue(issues, code, message, ref, blocking)

    def finish():
        unmatched = sum(row['차이'] != 0 for row in checks)
        status = 'INPUT_BLOCKED' if any(i['severity'] == '차단' for i in issues) else 'EXCEPTION' if unmatched else 'REVIEW_PENDING'
        metrics = {'선택원천행수': sum(p['side'] == 'source' for p in selected.values()),
                   '선택대상행수': sum(p['side'] == 'target' for p in selected.values()),
                   '배부건수': len(allocation_rows), '미대사행수': unmatched,
                   '선택모집단수': len(populations), '카탈로그테이블수': len(tables),
                   '미확인범위수': len(unconfirmed)}
        out = result('원천증빙', c, {'원천자료목록': inventory, '원천자료범위': scope,
                     '거래배부': allocation_rows, '원천대사': checks, '연결범위': unconfirmed},
                     issues, metrics, {'status': status, 'source': source_info, '한계': LIMITATIONS,
                                      '검토상태': '작성·검토·결론 미확정', '금액단위': '부호보존 정수 원',
                                      '차이정의': '배부합계 - 원문 산식금액'})
        out['status'] = status
        return out

    try:
        if not isinstance(pack, dict):
            raise AuditError('검증된 패키지 객체 필수')
        catalog, links = pack['catalog'], pack['links']
        if not isinstance(catalog, dict) or catalog.get('schema_version') != 'raw-catalog-1':
            raise AuditError('카탈로그 버전 오류')
        if any(k not in catalog.get('context', {}) for k in CONTEXT_KEYS):
            raise AuditError('카탈로그 회사·기간·통화·연결구분 문맥 누락')
        if _context(catalog.get('context')) != c:
            bad('RAW_CONTEXT', '카탈로그 회사·기간·통화·연결구분이 업무와 다릅니다.', 'catalog.json/context')
        if not isinstance(links, dict) or links.get('schema_version') != 'raw-links-1':
            raise AuditError('연결 파일 버전 오류')
        if any(k not in links.get('context', {}) for k in CONTEXT_KEYS):
            raise AuditError('연결 회사·기간·통화·연결구분 문맥 누락')
        if _context(links.get('context')) != c:
            bad('RAW_CONTEXT', '연결 회사·기간·통화·연결구분이 업무와 다릅니다.', 'links.json/context')
        table_list = catalog.get('tables')
        if not isinstance(table_list, list) or len(table_list) > 300:
            raise AuditError('카탈로그 테이블 목록/한도 오류')
        for table in table_list:
            cancelled(event)
            if not isinstance(table, dict):
                raise AuditError('카탈로그 테이블 객체 필수')
            dataset = text(table.get('dataset_id'), '자료ID')
            if dataset in tables:
                raise AuditError('카탈로그 자료ID 중복: ' + dataset)
            filename, sheet = text(table.get('source_file'), '원천파일'), text(table.get('sheet'), '원천시트')
            if not filename.startswith('sources/') or '..' in PurePosixPath(filename).parts or '\\' in filename:
                raise AuditError('원천파일 경로 오류')
            headers = table.get('headers')
            rows = table.get('rows')
            if not isinstance(headers, list) or not headers or len(headers) > 80 or any(not isinstance(h, str) or not h.strip() for h in headers) or len(set(headers)) != len(headers):
                raise AuditError('카탈로그 헤더 누락·중복·형식 오류')
            if not isinstance(rows, list) or len(rows) > 10000:
                raise AuditError('카탈로그 행 목록/한도 오류')
            indexed = {}
            for row in rows:
                n = _row_number(row.get('row'))
                if n in indexed or not isinstance(row.get('values'), list) or len(row['values']) != len(headers):
                    raise AuditError('원본행 중복 또는 헤더·값 개수 불일치: ' + dataset)
                indexed[n] = dict(zip(headers, row['values']))
            tables[dataset] = dict(table, _rows=indexed)
        pop_list, allocations = links.get('populations'), links.get('allocations')
        if not isinstance(pop_list, list) or len(pop_list) > 600 or not isinstance(allocations, list) or len(allocations) > 50000:
            raise AuditError('모집단·배부 목록/한도 오류')
        same_side = set()
        for pos, pop in enumerate(pop_list):
            cancelled(event)
            ref = f'links.json/populations/{pos}'
            try:
                if not isinstance(pop, dict):
                    raise AuditError('모집단 객체 필수')
                pid = text(pop.get('population_id'), '모집단ID')
                if pid in populations:
                    raise AuditError('모집단ID 중복: ' + pid)
                dataset = text(pop.get('dataset_id'), '자료ID')
                if dataset not in tables:
                    raise AuditError('카탈로그에 없는 자료ID: ' + dataset)
                if pop.get('company_code') != c['회사코드']:
                    bad('RAW_COMPANY', '선택 모집단 회사가 업무와 다릅니다.', ref)
                    continue
                side = pop.get('side')
                if side not in ('source', 'target'):
                    raise AuditError('모집단 side는 source/target 필수')
                label = text(pop.get('label'), '범위명')
                formula = pop.get('amount_columns')
                table = tables[dataset]
                if not isinstance(formula, dict) or not formula or any(k not in table['headers'] or type(v) is not int or v not in (-1, 1) for k, v in formula.items()):
                    raise AuditError('금액 산식은 원문 열과 정수 부호 +1/-1만 허용')
                row_numbers = pop.get('rows')
                if not isinstance(row_numbers, list) or len(row_numbers) > 10000:
                    raise AuditError('선택행 목록/한도 오류')
                if len(set(_row_number(n) for n in row_numbers)) != len(row_numbers):
                    raise AuditError('모집단 원본행 중복')
                date_columns = pop.get('date_columns')
                inferred_dates = [k for k in DATE_COLUMNS if k in table['headers']][:1]
                if date_columns is None:
                    date_columns = inferred_dates
                if not isinstance(date_columns, list) or len(set(date_columns)) != len(date_columns) or any(k not in table['headers'] for k in date_columns):
                    raise AuditError('기간 검사 열이 원문에 없습니다.')
                if not set(inferred_dates).issubset(date_columns):
                    raise AuditError('원문 거래/전기 기간 열의 검사를 생략할 수 없습니다.')
                populations[pid] = dict(pop, date_columns=date_columns)
                total, valid = 0, 0
                for n in row_numbers:
                    loc = _location(table, n)
                    identity = (side, dataset, n, tuple(sorted(formula.items())))
                    if identity in same_side:
                        bad('RAW_POP_DUP', '같은 side의 동일 원천행·금액 산식이 중복 선택되었습니다.', loc)
                        continue
                    same_side.add(identity)
                    if n not in table['_rows']:
                        bad('RAW_REFERENCE', '선택행이 원문 카탈로그에 없습니다.', loc)
                        continue
                    raw = table['_rows'][n]
                    invalid = False
                    for k in COMPANY_COLUMNS:
                        if k in raw and raw[k] != c['회사코드']:
                            bad('RAW_COMPANY', '원문 행 회사가 업무와 다릅니다.', loc + '/' + k)
                            invalid = True
                    for k in CURRENCY_COLUMNS:
                        if k in raw and raw[k] != c['통화']:
                            bad('RAW_CURRENCY', '원문 행 통화가 업무와 다릅니다.', loc + '/' + k)
                            invalid = True
                    for k in date_columns:
                        try:
                            if not day(c['시작일']) <= day(raw[k]) <= day(c['기준일']):
                                bad('RAW_PERIOD', '원문 행이 선택 업무기간 밖입니다. 후속기간 자료는 별도 업무 범위가 필요합니다.', loc + '/' + k)
                                invalid = True
                        except (AuditError, TypeError):
                            bad('RAW_PERIOD', '원문 기간 값이 공란이거나 날짜 형식이 아닙니다.', loc + '/' + k)
                            invalid = True
                    try:
                        amount = sum(num(raw[k]) * factor for k, factor in formula.items())
                        num(amount)
                    except AuditError as exc:
                        bad('RAW_AMOUNT', '원문 금액은 공란·bool·문자·소수·범위초과를 0으로 대체할 수 없습니다: ' + str(exc), loc)
                        invalid = True
                    if invalid:
                        continue
                    selected[(pid, n)] = {'population_id': pid, 'row': n, 'side': side, 'dataset_id': dataset,
                                          'label': label, 'amount': amount, 'ref': loc, 'formula': formula}
                    total += amount
                    valid += 1
                scope.append({'모집단ID': pid, '자료ID': dataset, '범위명': label, '구분': side,
                              '선택원본행': row_numbers, '산식': formula, '선택행수': len(row_numbers),
                              '유효행수': valid, '부호금액합계': total, '기간검사열': date_columns,
                              '회사열': [k for k in COMPANY_COLUMNS if k in table['headers']], '원본위치': _location(table),
                              '범위': '명시 선택집합; 전체 모집단 아님'})
                if not date_columns or not any(k in table['headers'] for k in COMPANY_COLUMNS):
                    unconfirmed.append({'범위': label, '상태': '원문 문맥 일부 미확인', '사유': '원문 회사/기간 열이 없는 항목은 패키지 선언 문맥만 확인', '원본위치': _location(table)})
            except (AuditError, TypeError, KeyError) as exc:
                bad('RAW_POPULATION', str(exc), ref)
        ids, pairs, sums = set(), set(), defaultdict(int)
        for pos, allocation in enumerate(allocations):
            cancelled(event)
            ref = f'links.json/allocations/{pos}'
            try:
                if not isinstance(allocation, dict):
                    raise AuditError('배부 객체 필수')
                aid = text(allocation.get('allocation_id'), '배부ID')
                transaction = text(allocation.get('transaction_id'), '거래ID')
                if aid in ids:
                    bad('RAW_ALLOC_DUP', '배부ID 중복', ref)
                    continue
                ids.add(aid)
                if allocation.get('company_code') != c['회사코드']:
                    bad('RAW_COMPANY', '배부 회사가 업무와 다릅니다.', ref)
                    continue
                endpoints = []
                for side in ('source', 'target'):
                    endpoint = allocation.get(side)
                    if not isinstance(endpoint, dict):
                        raise AuditError('원천/대상 endpoint 필수')
                    key = (text(endpoint.get('population_id')), _row_number(endpoint.get('row')))
                    if key not in selected or selected[key]['side'] != side:
                        bad('RAW_REFERENCE', '미등록·오류 행/모집단 또는 source/target 방향 오류', ref + '/' + side)
                        endpoints = []
                        break
                    endpoints.append(key)
                if len(endpoints) != 2:
                    continue
                pair = tuple(endpoints)
                if pair in pairs:
                    bad('RAW_ALLOC_DUP', '같은 원천·대상 연결쌍 중복. 분할은 단일 쌍 금액으로 합쳐 제시하세요.', ref)
                    continue
                pairs.add(pair)
                amount = num(allocation.get('amount'))
                if amount == 0:
                    bad('RAW_ALLOC_AMOUNT', '0원 배부는 연결 증거가 되지 않습니다.', ref)
                    continue
                source, target = [selected[key] for key in endpoints]
                if source['dataset_id'] == target['dataset_id'] and source['row'] == target['row']:
                    bad('RAW_SELF_LINK', '동일 원문 행을 자신의 대사 대상으로 사용할 수 없습니다.', ref)
                    continue
                if any(row['amount'] == 0 or (row['amount'] > 0) != (amount > 0) for row in (source, target)):
                    bad('RAW_SIGN', '원천·대상 산식과 배부의 부호가 다릅니다. abs로 상쇄하지 않습니다.', ref)
                    continue
                for key in endpoints:
                    sums[key] += amount
                allocation_rows.append({'배부ID': aid, '거래ID': transaction, '회사코드': c['회사코드'], '배부금액': amount,
                                        '원천모집단': source['population_id'], '원천자료ID': source['dataset_id'], '원천행': source['row'],
                                        '대상모집단': target['population_id'], '대상자료ID': target['dataset_id'], '대상행': target['row'],
                                        '원천위치': source['ref'], '대상위치': target['ref'], '상태': '배부 주장; 원문 금액과 별도 대사'})
            except (AuditError, TypeError, KeyError) as exc:
                bad('RAW_ALLOCATION', str(exc), ref)
        for key, row in selected.items():
            actual, expected = sums[key], row['amount']
            difference = actual - expected
            over = abs(actual) > abs(expected)
            if over:
                bad('RAW_OVERALLOC', '원문 금액보다 과다 배부되었습니다.', row['ref'])
            elif difference:
                bad('RAW_UNALLOCATED', '선택 원문에 미배부/부족배부가 있습니다. 미기록과 미제출 여부는 추가 검토가 필요합니다.', row['ref'], False)
            checks.append({'모집단ID': row['population_id'], '자료ID': row['dataset_id'], '범위명': row['label'], '구분': row['side'],
                           '원본행': row['row'], '원문산식': row['formula'], '원문금액': expected, '배부합계': actual, '차이': difference,
                           '상태': '과배부·차단' if over else '미배부·검토' if difference else '금액일치·미검토', '원본위치': row['ref']})
        chosen_by_table = defaultdict(set)
        for row in selected.values():
            chosen_by_table[row['dataset_id']].add(row['row'])
        for dataset, table in tables.items():
            inventory.append({'자료ID': dataset, '파일': table['source_file'], '시트': table['sheet'],
                              '카탈로그행수': len(table['_rows']), '선택고유행수': len(chosen_by_table[dataset]),
                              '상태': '선택범위만 대사' if chosen_by_table[dataset] else '미연결·원문보존', '원본위치': _location(table)})
        for entry in links.get('unconfirmed', []):
            if isinstance(entry, dict):
                unconfirmed.append(entry)
        if not populations:
            bad('RAW_EMPTY_SCOPE', '선택 모집단이 없습니다. 원문 보존만 수행되었으며 대사는 미실행입니다.', 'links.json', False)
    except (AuditError, KeyError, TypeError, AttributeError, ValueError) as exc:
        bad('RAW_INPUT', str(exc), 'catalog.json / links.json')
    cancelled(event)
    return finish()


def build_links(catalog):
    """Build only known explicit relationships in the existing synthetic pack.

    No guessed amount matching and no forced totals. Missing targets leave the
    source selected and unallocated. Empty optional families remain unconfirmed.
    """
    c = _context(catalog['context'])
    tables = catalog.get('tables', [])
    populations, allocations, unconfirmed = [], [], []

    def find(book, sheet):
        found = [t for t in tables if PurePosixPath(t['source_file']).name == book + '.xlsx' and t['sheet'] == sheet]
        if len(found) != 1:
            return None
        return found[0]

    def records(table):
        return [(row['row'], dict(zip(table['headers'], row['values']))) for row in table['rows']]

    def population(pid, table, side, formula, rows, label):
        populations.append({'population_id': pid, 'company_code': c['회사코드'], 'dataset_id': table['dataset_id'],
                            'rows': list(rows), 'amount_columns': formula, 'side': side, 'label': label})

    def link(prefix, source, source_row, target, target_row, transaction, amount):
        allocations.append({'allocation_id': f'{prefix}-{len(allocations)+1:04}', 'company_code': c['회사코드'],
                            'transaction_id': str(transaction), 'source': {'population_id': source, 'row': source_row},
                            'target': {'population_id': target, 'row': target_row}, 'amount': amount})

    def join(name, source, target, source_formula, target_formula, source_key, target_key, label, source_filter=None, target_filter=None):
        if source is None or target is None:
            unconfirmed.append({'범위': label, '상태': '미확인', '사유': '등록된 원천 또는 대상 테이블이 없습니다.'})
            return
        sr = [(n, r) for n, r in records(source) if source_filter is None or source_filter(r)]
        tr = [(n, r) for n, r in records(target) if target_filter is None or target_filter(r)]
        population(name + '-S', source, 'source', source_formula, [n for n, _ in sr], label + ' 원천')
        population(name + '-T', target, 'target', target_formula, [n for n, _ in tr], label + ' 대상')
        index = defaultdict(list)
        for n, r in tr:
            index[target_key(r)].append((n, r))
        for n, r in sr:
            key = source_key(r)
            matches = index.get(key, [])
            if len(matches) != 1 or key is None or (isinstance(key, str) and not key.strip()) or (isinstance(key, tuple) and any(v in (None, '') for v in key)):
                unconfirmed.append({'범위': label, '상태': '미확인', '사유': '명시 참조의 대상이 없거나 중복입니다.', '원본위치': _location(source, n)})
                continue
            try:
                amount = sum(num(r[k]) * v for k, v in source_formula.items())
                if amount:
                    link(name, name + '-S', n, name + '-T', matches[0][0], key, amount)
            except (AuditError, KeyError):
                # analyze reports the original invalid value; never create 0.
                continue

    gl = find('01_원장_리드_합성자료', '총계정원장')
    bank = find('05_확장검사_합성자료', '은행거래')
    book = find('05_확장검사_합성자료', '은행장부')
    invoices = find('03_매출_합성자료', 'invoices')
    sales_gl = find('03_매출_합성자료', 'ledger')
    ar = find('03_매출_매입_재고', '채권_송장연결')
    purchases = find('03_매출_매입_재고', '매입_송장_잔액')
    join('BANK_BOOK', bank, book, {'금액': 1}, {'금액': 1}, lambda r: (r['계좌'], r['참조']), lambda r: (r['계좌'], r['참조']), '은행거래↔은행장부')
    join('BOOK_GL', book, gl, {'금액': 1}, {'차변': 1, '대변': -1}, lambda r: r['참조'], lambda r: r['전표ID'], '은행장부↔현금계정 원장', target_filter=lambda r: r['계정코드'] == '1000')
    join('SALES_SUB', invoices, sales_gl, {'supply_amount': 1}, {'revenue_credit': 1, 'revenue_debit': -1},
         lambda r: (r['invoice_id'], r['invoice_line_id']), lambda r: (r['invoice_id'], r['invoice_line_id']), '매출 송장 공급가액↔매출보조원장')
    join('SALES_GL', sales_gl, gl, {'revenue_credit': 1, 'revenue_debit': -1}, {'대변': 1, '차변': -1},
         lambda r: (r['journal_id'], r['journal_line_id']), lambda r: (r['전표ID'], r['행ID']), '매출보조원장↔매출계정 원장', target_filter=lambda r: r['계정코드'] == '4000')
    if ar and invoices:
        ar_rows = records(ar)
        # The documented invoice-to-journal bridge, not an amount-based guess.
        bridge = defaultdict(list)
        for _, r in ar_rows:
            bridge[r['송장ID']].append(r['원장전표ID'])
        def invoice_journal(r):
            found = bridge.get(r['invoice_id'], [])
            return found[0] if len(found) == 1 else None
        join('SALES_AR_GL', invoices, gl, {'total_amount': 1}, {'차변': 1, '대변': -1}, invoice_journal, lambda r: r['전표ID'],
             '송장 총액↔채권계정 원장(채권·송장 참조 사용)', target_filter=lambda r: r['계정코드'] == '1300' and r['전표ID'].startswith('J-S'))
    join('PURCHASE_GL', purchases, gl, {'공급가액': 1, '세액': 1}, {'대변': 1, '차변': -1},
         lambda r: r['원장전표ID'], lambda r: r['전표ID'], '매입 송장 총액↔매입채무 원장',
         target_filter=lambda r: r['계정코드'] == '2400' and r['전표ID'].startswith('J-PO'))
    unconfirmed.extend([
        {'범위': '입고·출고·재고 수량 및 취득원가', '상태': '미확인', '사유': '일부 자료에 거래별 원 단위 원가 또는 공통 연결키가 없습니다. 수량×단가와 단위환산은 본 열합산 배부의 지원범위 밖입니다.'},
        {'범위': '후속 회수·급여 지급·리스 월별 지급과 개별 은행거래', '상태': '미확인', '사유': '일부 2027 후속자료 및 연간 집계 원장을 개별 당기 은행거래로 간주하지 않습니다.'},
        {'범위': '토지 권리·자산 취득증빙 및 나머지 계정군', '상태': '미확인', '사유': '등록 원문은 보존하되 거래별 상호 대사 및 감사 판단은 별도 절차가 필요합니다.'},
    ])
    return {'schema_version': 'raw-links-1', 'context': c, 'populations': populations,
            'allocations': allocations, 'unconfirmed': unconfirmed}
