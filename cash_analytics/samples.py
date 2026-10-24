"""Synthetic bank transactions bound to the existing v1.3 GL, not real evidence."""
from copy import deepcopy
from pathlib import Path
import json
from common import num
from tools.analytics_fixtures import load_base, write_input
from . import SCHEMA


def _tables(base):
    out = {name: [] for name in SCHEMA}
    out['분석설정'] = [{'항목': key, '값': value} for key, value in [
        ('대상계정', '1000;1100'), ('반복지급검색일수', 7), ('계좌변경검색일수', 7),
        ('집중최소지급건수', 3), ('집중비율퍼센트', 80)]]
    for tb in base['시산표']:
        if tb['계정코드'] in ('1000', '1100'):
            out['현금계좌'].append({'회사코드': 'SYNTH01', '계좌ID': 'FAKE-CASH' + tb['계정코드'], '계정코드': tb['계정코드'],
                                  '통화': 'KRW', '기초잔액': tb['기초잔액'], '기말잔액': tb['기말잔액']})
    for i, row in enumerate([r for r in base['총계정원장'] if r['계정코드'] in ('1000', '1100')], 1):
        amount = num(row['차변'])-num(row['대변'])
        party, counter, proof = 'SYNTH-' + row['전표ID'], 'FAKE-EXT-' + row['전표ID'], 'DOC-' + row['전표ID']
        bid, aid = 'SYN-B' + str(i).zfill(3), 'FAKE-CASH' + row['계정코드']
        out['은행거래'].append({'회사코드': 'SYNTH01', '은행거래ID': bid, '계좌ID': aid, '거래일': row['전기일'],
                                '입금': max(amount, 0), '출금': max(-amount, 0), '거래처ID': party, '상대계좌': counter,
                                '지급근거ID': proof, '거래구분': '일회'})
        out['현금원장선택'].append({'회사코드': 'SYNTH01', '전표ID': row['전표ID'], '행ID': row['행ID'], '계좌ID': aid,
                                    '거래처ID': party, '상대계좌': counter, '지급근거ID': proof, '거래구분': '일회'})
        out['현금배부'].append({'배부ID': 'SYN-A' + str(i).zfill(3), '회사코드': 'SYNTH01', '은행거래ID': bid,
                                '전표ID': row['전표ID'], '행ID': row['행ID'], '금액': amount})
        if amount < 0:
            out['거래처계좌'].append({'회사코드': 'SYNTH01', '거래처ID': party, '상대계좌': counter, '소유구분': '외부',
                                      '근거': 'SYNTHETIC ONLY / 가상 거래처 확인자료'})
            out['지급근거'].append({'회사코드': 'SYNTH01', '지급근거ID': proof, '거래처ID': party, '승인총액': -amount,
                                    '통화': 'KRW', '지급유형': '일회', '근거': 'SYNTHETIC ONLY / 가상 지급승인'})
    first = next(r for r in out['은행거래'] if r['출금'] > 0)
    out['계좌변경'] = [{'변경ID': 'SYN-CH001', '회사코드': 'SYNTH01', '거래처ID': first['거래처ID'],
                          '이전계좌': 'FAKE-OLD', '신규계좌': first['상대계좌'], '효력일': '2025-01-01',
                          '승인일': '2024-12-30', '근거': 'SYNTHETIC ONLY / 전기 변경 이력, 금년 직후 지급 아님'}]
    _controls(out)
    return out


def _controls(extra, update_end=False):
    extra['은행독립통제'] = []
    for account in extra['현금계좌']:
        rows = [r for r in extra['은행거래'] if r['계좌ID'] == account['계좌ID']]
        incoming, outgoing = sum(r['입금'] for r in rows), sum(r['출금'] for r in rows)
        extra['은행독립통제'].append({'회사코드': 'SYNTH01', '계좌ID': account['계좌ID'], '시작일': '2026-01-01', '기준일': '2026-12-31',
                                      '행수': len(rows), '입금합계': incoming, '출금합계': outgoing,
                                      '추출근거': 'SYNTHETIC ONLY / 같은 생성기 통제 예시; 실제 독립 은행 추출 아님',
                                      '추출일시': '2027-01-02T09:00:00+09:00', '작성자': '합성통제작성자'})
        if update_end:
            account['기말잔액'] = account['기초잔액']+incoming-outgoing


def _set_config(extra, key, value):
    next(r for r in extra['분석설정'] if r['항목'] == key)['값'] = value


def _replace_party(extra, rows, party, account, proof=None, kind='일회', approved=None):
    extra['거래처계좌'].append({'회사코드': 'SYNTH01', '거래처ID': party, '상대계좌': account, '소유구분': '외부',
                                '근거': 'SYNTHETIC ONLY / 가상 외부 계좌'})
    for row in rows:
        row.update(거래처ID=party, 상대계좌=account, 거래구분=kind)
        if proof:
            row['지급근거ID'] = proof
        else:
            found = next(r for r in extra['지급근거'] if r['지급근거ID'] == row['지급근거ID'])
            found.update(거래처ID=party, 지급유형=kind)
    if proof:
        extra['지급근거'].append({'회사코드': 'SYNTH01', '지급근거ID': proof, '거래처ID': party,
                                  '승인총액': approved if approved is not None else sum(r['출금'] for r in rows),
                                  '통화': 'KRW', '지급유형': kind, '근거': 'SYNTHETIC ONLY / 반복·분할 검증용 승인'})


def _transfer_base(base):
    base = deepcopy(base)
    n = max(r['_row'] for r in base['총계정원장'])+1
    for offset, (code, debit, credit) in enumerate([('1000', 0, 100000), ('1100', 100000, 0)]):
        base['총계정원장'].append({'회사코드': 'SYNTH01', '전표ID': 'J-SYN-TRANSFER', '행ID': str(offset+1),
                                     '전기일': '2026-06-01', '계정코드': code, '차변': debit, '대변': credit,
                                     '적요': 'SYNTHETIC ONLY / 자기 계좌간 이체', '작성자': '합성작성자', '_row': n+offset, '_sheet': '총계정원장'})
        tb = next(r for r in base['시산표'] if r['계정코드'] == code)
        tb['당기차변'] += debit; tb['당기대변'] += credit; tb['기말잔액'] += debit-credit
        ctl = next(r for r in base['독립통제'] if r['계정코드'] == code)
        ctl['원장행수'] += 1; ctl['차변합계'] += debit; ctl['대변합계'] += credit; ctl['기말잔액'] += debit-credit
    return base


def _write_native(path, base):
    from openpyxl import Workbook
    from ledger import SCHEMA as NATIVE
    book = Workbook(); book.remove(book.active)
    for name, headers in NATIVE.items():
        sheet = book.create_sheet(name); sheet.append(headers)
        for row in base[name]:
            sheet.append([row.get(key) for key in headers])
    book.save(path); book.close()
    return path


def _sync_declared_payment_metadata(extra):
    """Declare the same payment/batch metadata on selected GL endpoints.

    This only constructs a synthetic fixture. analyze never repairs mismatches.
    GL IDs/amounts and current-ledger rows are never changed here.
    """
    banks = {r['은행거래ID']: r for r in extra['은행거래']}
    meta = ('거래처ID', '상대계좌', '지급근거ID', '거래구분')
    for selected in extra['현금원장선택']:
        linked = [banks[r['은행거래ID']] for r in extra['현금배부'] if r['은행거래ID'] in banks
                  and (r['회사코드'], r['전표ID'], r['행ID']) == (selected['회사코드'], selected['전표ID'], selected['행ID'])]
        if linked and all(tuple(r.get(k) for k in meta) == tuple(linked[0].get(k) for k in meta) for r in linked):
            selected.update({k: linked[0].get(k) for k in meta})


def write_samples(target):
    target = Path(target); target.mkdir(parents=True, exist_ok=True)
    base = load_base()
    original = _tables(base)
    cases = []
    def emit(ident, extra=None, *, blocking=False, review=False, codes=(), custom_base=None, current=None, sync_meta=True):
        filename = '현금_' + ident + '.xlsx'
        actual = deepcopy(original if extra is None else extra)
        if sync_meta:
            _sync_declared_payment_metadata(actual)
        write_input(target/filename, SCHEMA, actual, base if custom_base is None else custom_base)
        row = {'id': ident, 'file': filename, 'blocking': blocking, 'review': review, 'required_codes': list(codes)}
        if current:
            row['current_ledger'] = current
        cases.append(row)
    emit('01_정상')
    extra = deepcopy(original)
    equal = [r for r in extra['은행거래'] if r['출금'] == 120000]
    _replace_party(extra, equal, 'SYNTH-REPEAT', 'FAKE-REPEAT', 'DOC-REPEAT', approved=120000)
    _set_config(extra, '반복지급검색일수', 90)
    emit('02_반복지급후보', extra, review=True, codes=['CASH_REPEAT_CANDIDATE', 'CASH_APPROVED_EXCESS'])
    extra = deepcopy(original)
    _replace_party(extra, [r for r in extra['은행거래'] if r['출금']], 'SYNTH-CONCENTRATION', 'FAKE-CONCENTRATION')
    emit('03_상대계좌집중후보', extra, review=True, codes=['CASH_CONCENTRATION'])
    extra = deepcopy(original)
    chosen = next(r for r in extra['은행거래'] if r['출금'] == 50000)
    extra['계좌변경'] = [{'변경ID': 'SYN-CH-RECENT', '회사코드': 'SYNTH01', '거래처ID': chosen['거래처ID'],
                          '이전계좌': 'FAKE-OLD', '신규계좌': chosen['상대계좌'], '효력일': '2026-09-30',
                          '승인일': '2026-09-29', '근거': 'SYNTHETIC ONLY / 계좌변경 직후 검증'}]
    emit('04_계좌변경직후후보', extra, review=True, codes=['CASH_ACCOUNT_CHANGE'])
    extra = deepcopy(original)
    equal = [r for r in extra['은행거래'] if r['출금'] == 120000]
    _replace_party(extra, equal, 'SYNTH-REGULAR', 'FAKE-REGULAR', 'DOC-REGULAR', kind='정기', approved=240000)
    _set_config(extra, '반복지급검색일수', 90)
    emit('05_정상반복유사대조', extra)
    extra = deepcopy(original)
    row = next(r for r in extra['은행거래'] if r['출금'] == 3300000)
    row['출금'] = 1650000; row['거래구분'] = '분할'
    second = deepcopy(row); second['은행거래ID'] += '-PART2'; extra['은행거래'].append(second)
    proof = next(r for r in extra['지급근거'] if r['지급근거ID'] == row['지급근거ID']); proof['지급유형'] = '분할'
    allocation = next(r for r in extra['현금배부'] if r['은행거래ID'] == row['은행거래ID']); allocation['금액'] = -1650000
    another = deepcopy(allocation); another.update(배부ID='SYN-PART2', 은행거래ID=second['은행거래ID']); extra['현금배부'].append(another)
    _controls(extra)
    emit('06_합법분할지급대조', extra)
    extra = deepcopy(original)
    picked = [r for r in extra['은행거래'] if r['출금'] in (50000, 10000)]
    first, second = picked
    first['출금'] = 60000
    extra['은행거래'].remove(second)
    next(r for r in extra['현금배부'] if r['은행거래ID'] == second['은행거래ID'])['은행거래ID'] = first['은행거래ID']
    _replace_party(extra, [first], 'SYNTH-BATCH', 'FAKE-BATCH', 'DOC-BATCH', kind='분할', approved=60000)
    _controls(extra)
    emit('07_여러원장합산지급', extra)
    extra = deepcopy(original); extra['현금배부'][0]['금액'] //= 2
    emit('08_부분배부잔여', extra, review=True, codes=['CASH_RESIDUAL'])
    extra = deepcopy(original)
    extra['은행거래'].append({'회사코드': 'SYNTH01', '은행거래ID': 'SYN-BANK-ONLY', '계좌ID': 'FAKE-CASH1000', '거래일': '2026-12-31',
                              '입금': 1, '출금': 0, '거래처ID': 'SYNTH-UNCONFIRMED', '상대계좌': 'FAKE-UNKNOWN', '지급근거ID': 'DOC-UNKNOWN', '거래구분': '일회'})
    _controls(extra, update_end=True)
    emit('09_은행만잔여1원', extra, review=True, codes=['CASH_RESIDUAL', 'CASH_BALANCE_DIFF'])
    extra = deepcopy(original)
    removed = extra['은행거래'].pop(0)
    extra['현금배부'] = [r for r in extra['현금배부'] if r['은행거래ID'] != removed['은행거래ID']]
    _controls(extra, update_end=True)
    emit('10_장부만잔여', extra, review=True, codes=['CASH_RESIDUAL', 'CASH_BALANCE_DIFF'])
    extra = deepcopy(original); removed = extra['은행거래'].pop(0)
    extra['현금배부'] = [r for r in extra['현금배부'] if r['은행거래ID'] != removed['은행거래ID']]
    emit('11_은행누락통제탐지', extra, blocking=True, review=True, codes=['CASH_CONTROL'])
    extra = deepcopy(original); extra['현금배부'][0]['금액'] *= -1
    emit('12_부호반전', extra, blocking=True, review=True, codes=['CASH_ALLOC_SIGN'])
    extra = deepcopy(original); extra['현금배부'].append(deepcopy(extra['현금배부'][0]))
    emit('13_중복배부', extra, blocking=True, codes=['CASH_ALLOCATION'])
    extra = deepcopy(original); extra['현금배부'][0]['금액'] -= 1
    emit('14_과배부', extra, blocking=True, codes=['CASH_OVERALLOC'])
    extra = deepcopy(original); extra['은행거래'][0]['회사코드'] = 'SYNTH02'
    emit('15_은행회사혼입', extra, blocking=True, review=True, codes=['CASH_BANK_INPUT'])
    extra = deepcopy(original); extra['은행거래'][0]['거래일'] = '2027-01-01'
    emit('16_은행기간밖', extra, blocking=True, review=True, codes=['CASH_BANK_INPUT'])
    extra = deepcopy(original); extra['현금원장선택'].pop()
    emit('17_현금원장행선택누락', extra, blocking=True, review=True, codes=['CASH_GL_SCOPE'])
    extra = deepcopy(original); extra['은행독립통제'][0]['행수'] += 1
    emit('18_독립행수통제오류', extra, blocking=True, codes=['CASH_CONTROL'])
    extra = deepcopy(original); extra['현금계좌'][0]['기말잔액'] += 1
    emit('19_은행기말잔액오류', extra, blocking=True, review=True, codes=['CASH_CONTROL'])
    extra = deepcopy(original); extra['지급근거'] = []
    emit('20_규칙메타미제출', extra)
    changed = deepcopy(base); changed['총계정원장'][0]['적요'] += ' / 현재 업무와 다름'
    emit('21_현재원장불일치', custom_base=changed, blocking=True, codes=['AN_LEDGER_DIFF'])
    transfer = _transfer_base(base); extra = _tables(transfer)
    transfer_rows = [r for r in extra['은행거래'] if r['지급근거ID'] == 'DOC-J-SYN-TRANSFER']
    for row in transfer_rows:
        row.update(거래처ID='SYNTH-SELF', 상대계좌='FAKE-CASH1100' if row['출금'] else 'FAKE-CASH1000',
                   지급근거ID='DOC-OWN-TRANSFER', 거래구분='자금이체')
    extra['지급근거'] = [r for r in extra['지급근거'] if r['지급근거ID'] != 'DOC-J-SYN-TRANSFER']
    extra['지급근거'].append({'회사코드': 'SYNTH01', '지급근거ID': 'DOC-OWN-TRANSFER', '거래처ID': 'SYNTH-SELF',
                              '승인총액': 100000, '통화': 'KRW', '지급유형': '자금이체', '근거': 'SYNTHETIC ONLY / 자사 계좌 이체 승인'})
    extra['거래처계좌'].append({'회사코드': 'SYNTH01', '거래처ID': 'SYNTH-SELF', '상대계좌': 'FAKE-CASH1100',
                                '소유구분': '자사', '근거': 'SYNTHETIC ONLY / 소유 계좌 목록'})
    companion = '현금_22_자금이체_현재원장.xlsx'; _write_native(target/companion, transfer)
    emit('22_정상자금이체대조', extra, custom_base=transfer, current=companion)
    extra = deepcopy(original); extra['은행거래'].append(deepcopy(extra['은행거래'][0]))
    emit('23_은행거래ID중복', extra, blocking=True, codes=['CASH_BANK_INPUT'])
    extra = deepcopy(original); extra['현금계좌'][0]['통화'] = 'USD'
    emit('24_KRW외통화', extra, blocking=True, codes=['CASH_ACCOUNT'])
    extra = deepcopy(original); extra['은행거래'][0]['출금'] = None
    emit('25_원문금액공란', extra, blocking=True, review=True, codes=['CASH_BANK_INPUT'])
    extra = deepcopy(original); extra['은행거래'][0]['출금'] = True
    emit('26_bool금액', extra, blocking=True, review=True, codes=['CASH_BANK_INPUT'])
    extra = deepcopy(original)
    extra['현금원장선택'][0].update(거래처ID='SYNTH-CONTRADICTING', 상대계좌='FAKE-CONTRADICTING', 지급근거ID='DOC-CONTRADICTING')
    emit('27_양방향지급메타모순', extra, blocking=True, review=True, codes=['CASH_LINK_META'], sync_meta=False)
    extra = deepcopy(original); extra['은행거래'][0]['거래처ID'] = None
    emit('28_양방향메타미제출', extra)
    (target/'cases.json').write_text(json.dumps({'module': '현금분석', 'cases': cases,
        'normal_oracle': {'은행거래수': 12, '선택원장행수': 12, '입금합계': 2700000, '출금합계': 4350000,
                          '1000기초': 4200000, '1000기말': 2550000, '1100기초': 1000000, '1100기말': 1000000},
        'evidence_limit': '동일 생성기의 합성 자료. 독립적인 실제 은행/승인 증거 아님. 기대값은 입력으로 전달하지 않음.'}, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'normal': target/cases[0]['file'], 'cases': cases}
