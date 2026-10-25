"""Limited indirect cash-flow model. No accounting opinion; exact KRW Decimal."""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, localcontext
import re

SCHEMA = {
    'Settings': ('key', 'value'),
    'Balances': ('account_id', 'name', 'nature', 'opening', 'closing'),
    'Mapping': ('account_id', 'method', 'line_id', 'reason', 'confirmed'),
    'CashScope': ('account_id', 'opening', 'closing', 'criteria', 'confirmed'),
    'Events': ('event_id', 'event_date', 'kind', 'category', 'line_id', 'direction', 'profit_effect', 'note', 'confirmed'),
    'Movements': ('leg_id', 'event_id', 'account_id', 'balance_effect'),
    'Adjustments': ('adjustment_id', 'event_id', 'kind', 'line_id', 'amount', 'reason', 'confirmed'),
    'Statement': ('line_id', 'category', 'amount'),
}
SETTINGS = ('entity', 'currency', 'unit', 'period_start', 'period_end', 'opening_date', 'closing_date',
            'opening_cash_control', 'closing_cash_control', 'net_income', 'net_income_control',
            'fx_cash_control', 'earnings_account_id', 'policy_note', 'policy_confirmed',
            'mapping_confirmed', 'cash_scope_confirmed', 'profit_link_confirmed')
RESERVED = {'NI', 'CFO', 'CFI', 'CFF', 'FX', 'CASH_DELTA', 'CASH_OPEN', 'CASH_CLOSE'}
ZERO = Decimal(0)


@dataclass(frozen=True)
class Row:
    sheet: str
    number: int
    values: dict

    @property
    def ref(self):
        return f'{self.sheet}!{self.number}'


@dataclass
class InputBook:
    sheets: dict
    source: str = '더미 메모리'
    digest: str = ''


@dataclass
class Issue:
    code: str
    ref: str
    key: str
    message: str
    difference: Decimal | None = None
    severity: str = 'ERROR'


@dataclass
class Result:
    book: InputBook
    issues: list = field(default_factory=list)
    lines: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)
    checks: list = field(default_factory=list)

    @property
    def status(self):
        return '미해결 · 미확정 초안' if self.issues else '대사 일치 · 사용자 확인용 초안'

    @property
    def calculable(self):
        return bool(self.lines)


class Cancelled(Exception):
    pass


def calculate(book, cancel=None):
    # 24 digit per row * 100000 input row cap fits exactly at this precision.
    with localcontext() as ctx:
        ctx.prec = 64
        return _calculate(book, cancel)


def _calculate(book, cancel):
    result = Result(book)
    fatal = False

    def stop():
        if cancel and cancel.is_set():
            raise Cancelled()

    def problem(code, ref, key, message, difference=None, structural=False):
        nonlocal fatal
        result.issues.append(Issue(code, ref, str(key), message, difference))
        fatal |= structural

    def need(row, col):
        value = row.values.get(col)
        if value is None or isinstance(value, str) and not value.strip():
            problem('MISSING_VALUE', row.ref, col, '필수값 누락', structural=True)
            return ''
        return str(value).strip()

    def number(row, col):
        raw = row.values.get(col)
        s = str(raw).strip()
        if isinstance(raw, bool) or not re.fullmatch(r'[+-]?\d+(?:\.0+)?', s):
            problem('AMOUNT_FORMAT', row.ref, col, '금액은 정수 원: 쉼표·수식·지수·소수 불가', structural=True)
            return ZERO
        try:
            n = Decimal(s)
            if not n.is_finite() or abs(n) >= Decimal('1e24'):
                raise InvalidOperation
            if isinstance(raw, (int, float)) and abs(n) >= Decimal('1e15'):
                problem('EXCEL_PRECISION', row.ref, col, '15자리 초과 금액은 정확한 텍스트로 입력', structural=True)
            return n
        except InvalidOperation:
            problem('AMOUNT_RANGE', row.ref, col, '금액 범위 초과', structural=True)
            return ZERO

    def enum(row, col, options):
        s = need(row, col)
        if s not in options:
            problem('ENUM', row.ref, col, '허용값: ' + '/'.join(options), structural=True)
        return s

    def confirm(row, col='confirmed'):
        val = enum(row, col, ('YES', 'NO'))
        if val == 'NO':
            problem('UNCONFIRMED', row.ref, col, '사용자가 분류·범위·정책을 확인해야 합니다')

    parsed = {}
    for sheet, cols in SCHEMA.items():
        stop()
        rows = book.sheets.get(sheet)
        if rows is None:
            problem('MISSING_SHEET', sheet, sheet, '필수 시트 누락', structural=True)
            rows = []
        keys = set()
        parsed[sheet] = []
        for row in rows:
            stop()
            if set(row.values) != set(cols):
                problem('SCHEMA', row.ref, sheet, '헤더 불일치', structural=True)
            key = need(row, cols[0])
            if key in keys:
                problem('DUPLICATE_KEY', row.ref, key, '중복 키: 자동 합산/마지막 행 선택 금지', structural=True)
            keys.add(key)
            data = {col: need(row, col) for col in cols}
            data['_row'] = row
            parsed[sheet].append(data)
    if set(book.sheets) - set(SCHEMA):
        problem('EXTRA_SHEET', 'Workbook', '', '정의되지 않은 추가 시트', structural=True)

    settings_rows = {x['key']: x for x in parsed['Settings']}
    settings = {x['key']: x['value'] for x in parsed['Settings']}
    for key in SETTINGS:
        if key not in settings:
            problem('MISSING_SETTING', 'Settings', key, '필수 설정 누락', structural=True)
    for key in settings.keys() - set(SETTINGS):
        problem('EXTRA_SETTING', settings_rows[key]['_row'].ref, key, '정의되지 않은 설정', structural=True)
    if fatal:
        return result
    for key in ('opening_cash_control', 'closing_cash_control', 'net_income', 'net_income_control', 'fx_cash_control'):
        r = settings_rows[key]['_row']
        settings[key] = number(Row(r.sheet, r.number, {'value': r.values['value']}), 'value')
    for key in ('opening_cash_control', 'closing_cash_control'):
        if settings[key] < 0:
            problem('NEGATIVE_CASH', settings_rows[key]['_row'].ref, key, '현금 통제합계 음수', structural=True)
    for key in ('policy_confirmed', 'mapping_confirmed', 'cash_scope_confirmed', 'profit_link_confirmed'):
        confirm(Row('Settings', settings_rows[key]['_row'].number, {key: settings[key]}), key)
    if settings['currency'] != 'KRW' or settings['unit'] != '원':
        problem('UNIT', 'Settings', '', '첫 버전은 KRW 원만 지원', structural=True)
    try:
        dates = {k: date.fromisoformat(settings[k]) for k in ('period_start', 'period_end', 'opening_date', 'closing_date')}
        if any(dates[k].isoformat() != settings[k] for k in dates):
            raise ValueError
        if dates['period_start'] > dates['period_end'] or dates['opening_date'] != dates['period_start'] - timedelta(days=1) or dates['closing_date'] != dates['period_end']:
            raise ValueError
    except (ValueError, OverflowError):
        problem('PERIOD', 'Settings', '', '기간/기초일/기말일 관계 또는 ISO 날짜 오류', structural=True)
        dates = {}

    balances = {x['account_id']: x for x in parsed['Balances']}
    mappings = {x['account_id']: x for x in parsed['Mapping']}
    scopes = {x['account_id']: x for x in parsed['CashScope']}
    events = {x['event_id']: x for x in parsed['Events']}
    movements = parsed['Movements']
    adjustments = parsed['Adjustments']
    statement = {x['line_id']: x for x in parsed['Statement']}
    for d in balances.values():
        r = d['_row']
        d['nature'] = enum(r, 'nature', ('ASSET', 'LIABILITY', 'EQUITY'))
        for c in ('opening', 'closing'):
            d[c] = number(r, c)
            if d[c] < 0:
                problem('BALANCE_SIGN', r.ref, d['account_id'], '음수 정상잔액은 이 모델에서 미지원', structural=True)
    wc_lines = set()
    for d in mappings.values():
        r = d['_row']
        d['method'] = enum(r, 'method', ('CASH', 'WC_ASSET', 'WC_LIABILITY', 'SCHEDULE', 'EXCLUDED'))
        confirm(r)
        acc = balances.get(d['account_id'])
        if not acc:
            problem('UNKNOWN_ACCOUNT', r.ref, d['account_id'], '잔액에 없는 매핑 계정', structural=True)
        elif d['method'] in ('CASH', 'WC_ASSET', 'WC_LIABILITY'):
            expected = 'LIABILITY' if d['method'] == 'WC_LIABILITY' else 'ASSET'
            if acc['nature'] != expected:
                problem('MAPPING_NATURE', r.ref, d['account_id'], '정상잔액 유형과 매핑이 불일치', structural=True)
        if d['line_id'] in RESERVED:
            problem('RESERVED_LINE', r.ref, d['line_id'], '예약 line_id 사용 불가', structural=True)
        if d['method'].startswith('WC_'):
            if d['line_id'] in wc_lines:
                problem('WC_NETTING', r.ref, d['line_id'], '운전자본 line는 계정별 유일해야 함', structural=True)
            wc_lines.add(d['line_id'])
    for key in balances.keys() - mappings.keys():
        problem('UNMAPPED', balances[key]['_row'].ref, key, '분류 매핑 누락', structural=True)
    cash_ids = {k for k, v in mappings.items() if v['method'] == 'CASH'}
    if not cash_ids:
        problem('CASH_SCOPE_EMPTY', 'Mapping', '', '포함 현금계정이 없음', structural=True)
    if cash_ids != set(scopes):
        problem('CASH_SCOPE_SET', 'CashScope', '', 'CASH 매핑 계정과 현금명세 계정 집합 불일치', structural=True)
    for d in scopes.values():
        confirm(d['_row'])
        for c in ('opening', 'closing'):
            d[c] = number(d['_row'], c)
    earn = settings['earnings_account_id']
    if earn not in balances or balances[earn]['nature'] != 'EQUITY' or mappings.get(earn, {}).get('method') != 'EXCLUDED':
        problem('EARNINGS_ACCOUNT', 'Settings', earn, '손익연결 계정은 EXCLUDED EQUITY여야 함', structural=True)
    for d in events.values():
        r = d['_row']
        d['kind'] = enum(r, 'kind', ('CASH', 'ACCRUAL', 'NONCASH', 'FX'))
        d['category'] = enum(r, 'category', ('OPERATING', 'INVESTING', 'FINANCING', 'NONE'))
        d['direction'] = enum(r, 'direction', ('INFLOW', 'OUTFLOW', 'NONE'))
        d['profit_effect'] = number(r, 'profit_effect')
        confirm(r)
        if d['line_id'] in RESERVED:
            problem('RESERVED_LINE', r.ref, d['line_id'], '예약 line_id 사용 불가', structural=True)
        try:
            ed = date.fromisoformat(d['event_date'])
            if ed.isoformat() != d['event_date'] or not dates or not dates['period_start'] <= ed <= dates['period_end']:
                raise ValueError
        except ValueError:
            problem('EVENT_PERIOD', r.ref, d['event_id'], '사건 날짜가 적용 기간 밖이거나 형식 오류', structural=True)
        if d['kind'] == 'CASH':
            if d['category'] == 'NONE' or d['direction'] == 'NONE':
                problem('CASH_CLASS', r.ref, d['event_id'], '현금 사건 분류/방향 필수', structural=True)
        elif d['category'] != 'NONE' or d['direction'] != 'NONE':
            problem('NONCASH_CLASS', r.ref, d['event_id'], '현금 외 사건은 NONE 분류/방향', structural=True)
        if d['kind'] == 'FX' and d['profit_effect'] != 0:
            problem('FX_PROFIT', r.ref, d['event_id'], '환손익은 NONCASH로 분리', structural=True)

    by_event = {k: [] for k in events}
    by_account = {k: [] for k in balances}
    event_accounts = set()
    for d in movements:
        stop()
        r = d['_row']
        d['balance_effect'] = number(r, 'balance_effect')
        pair = (d['event_id'], d['account_id'])
        if pair in event_accounts:
            problem('DUPLICATE_LEG_ACCOUNT', r.ref, str(pair), '동일 사건/계정 leg 중복', structural=True)
        event_accounts.add(pair)
        if d['event_id'] not in events or d['account_id'] not in balances:
            problem('UNKNOWN_REFERENCE', r.ref, d['leg_id'], '사건/계정 참조 누락', structural=True)
        else:
            by_event[d['event_id']].append(d)
            by_account[d['account_id']].append(d)
        if d['balance_effect'] == 0:
            problem('ZERO_LEG', r.ref, d['leg_id'], '0원 leg는 삭제하십시오', structural=True)
    adjustment_events = set()
    for d in adjustments:
        r = d['_row']
        d['amount'] = number(r, 'amount')
        d['kind'] = enum(r, 'kind', ('NONCASH', 'RECLASS'))
        confirm(r)
        if d['event_id'] in adjustment_events:
            problem('DOUBLE_ADJUSTMENT', r.ref, d['event_id'], '동일 사건 손익조정 이중반영', structural=True)
        adjustment_events.add(d['event_id'])
        if d['event_id'] not in events:
            problem('UNKNOWN_REFERENCE', r.ref, d['event_id'], '조정의 사건 참조 누락', structural=True)
        else:
            ev = events[d['event_id']]
            expected = 'NONCASH' if ev['kind'] == 'NONCASH' else 'RECLASS' if ev['kind'] == 'CASH' and ev['category'] in ('INVESTING', 'FINANCING') else None
            if not expected or d['kind'] != expected or ev['profit_effect'] == 0 or d['amount'] != -ev['profit_effect']:
                problem('ADJUSTMENT_RULE', r.ref, d['event_id'], '허용 조정 유형/손익 반대부호 전액과 불일치', structural=True)
        if d['line_id'] in RESERVED or d['line_id'] in wc_lines:
            problem('LINE_COLLISION', r.ref, d['line_id'], '조정 line가 예약/WC line와 중복', structural=True)
    for d in statement.values():
        d['amount'] = number(d['_row'], 'amount')
        d['category'] = enum(d['_row'], 'category', ('OPERATING', 'INVESTING', 'FINANCING', 'NONE', 'TOTAL'))
    if not balances or not events or not movements or not statement:
        problem('MISSING_DATA', 'Workbook', '', '잔액·사건·변동명세·초안은 빈 자료일 수 없음', structural=True)
    if fatal:
        return result

    def check(code, ref, key, actual, expected, message):
        diff = actual - expected
        result.checks.append((code, ref, key, actual, expected, diff))
        if diff != 0:
            problem(code, ref, key, message, diff)

    def add(line, cat, amount, refs, formula):
        if line in result.lines and result.lines[line][0] != cat:
            problem('LINE_COLLISION', refs, line, '다른 분류에서 동일 line_id 사용')
            return
        old = result.lines.get(line, (cat, ZERO))[1]
        result.lines[line] = (cat, old + amount)
        result.trace.append((line, cat, amount, refs, formula))

    for k, acc in balances.items():
        stop()
        legs = by_account[k]
        movement = sum((x['balance_effect'] for x in legs), ZERO)
        check('ROLLFORWARD', acc['_row'].ref, k, acc['opening'] + movement, acc['closing'], '기초 + 명세변동 ≠ 기말')
        result.trace.append(('BALANCE:' + k, 'BALANCE', movement, ', '.join(x['_row'].ref for x in legs), '기초 + 사건별 명세 = 기말'))
    for c in ('opening', 'closing'):
        assets = sum((d[c] for d in balances.values() if d['nature'] == 'ASSET'), ZERO)
        others = sum((d[c] for d in balances.values() if d['nature'] != 'ASSET'), ZERO)
        check('BS_BALANCE', 'Balances', c, assets, others, '자산 ≠ 부채+자본')
    for k, scope in scopes.items():
        for c in ('opening', 'closing'):
            check('CASH_ACCOUNT', scope['_row'].ref, k + ':' + c, scope[c], balances[k][c], '현금명세와 계정잔액 불일치')
    for c in ('opening', 'closing'):
        check('CASH_CONTROL', 'CashScope', c, sum((d[c] for d in scopes.values()), ZERO), settings[c + '_cash_control'], '현금명세와 독립 통제합계 불일치')
    ni = sum((d['profit_effect'] for d in events.values()), ZERO)
    check('PROFIT_LINK', 'Events', 'net_income', ni, settings['net_income'], '사건 손익합계와 당기순이익 불일치')
    check('PROFIT_CONTROL', 'Settings', 'net_income_control', settings['net_income'], settings['net_income_control'], '당기순이익과 손익계산서 통제값 불일치')
    add('NI', 'OPERATING', settings['net_income'], settings_rows['net_income']['_row'].ref + '; ' + ', '.join(d['_row'].ref for d in events.values()), '간접법 출발점: 손익계산서 당기순이익')
    direct = {'OPERATING': ZERO, 'INVESTING': ZERO, 'FINANCING': ZERO}
    fx = ZERO
    line_directions = {}
    for k, ev in events.items():
        stop()
        legs = by_event[k]
        ref = ev['_row'].ref
        if len(legs) < 2:
            problem('INCOMPLETE_EVENT', ref, k, '사건별 최소 두 계정 leg 필요')
        balanced = sum((x['balance_effect'] * (1 if balances[x['account_id']]['nature'] == 'ASSET' else -1) for x in legs), ZERO)
        check('EVENT_BALANCE', ref, k, balanced, ZERO, '사건 차변·대변 명세가 불균형')
        if ev['profit_effect'] != 0:
            check('EARNINGS_LINK', ref, k, sum((x['balance_effect'] for x in legs if x['account_id'] == earn), ZERO), ev['profit_effect'], '사건 손익과 이익잉여금 변동 연결 불일치')
        cash = [x for x in legs if x['account_id'] in cash_ids]
        amount = sum((x['balance_effect'] for x in cash), ZERO)
        if ev['kind'] == 'CASH':
            if len(cash) != 1 or amount == 0:
                problem('CASH_LEG', ref, k, '현금 leg는 정확히 하나이고 0원 불가')
            if ev['direction'] == 'INFLOW' and amount <= 0 or ev['direction'] == 'OUTFLOW' and amount >= 0:
                problem('CASH_SIGN', ref, k, '현금유입/유출 방향과 부호 불일치')
            if any(mappings[x['account_id']]['method'].startswith('WC_') for x in legs) and ev['category'] != 'OPERATING':
                problem('WC_CLASS', ref, k, 'WC 연관 현금사건은 영업으로 분류해야 함')
            direct[ev['category']] += amount
            if ev['category'] in ('INVESTING', 'FINANCING'):
                lid = ev['line_id']
                if lid in wc_lines or lid in {x['line_id'] for x in adjustments}:
                    problem('LINE_COLLISION', ref, lid, '직접 현금명세 line와 간접법 조정 line 충돌')
                if lid in line_directions and line_directions[lid] != ev['direction']:
                    problem('NETTING', ref, lid, '같은 명세에서 유입·유출 상계 금지')
                line_directions[lid] = ev['direction']
                add(lid, ev['category'], amount, ref + '; ' + ', '.join(x['_row'].ref for x in cash), 'CASH 사건 실제 현금 leg')
        elif ev['kind'] == 'FX':
            if len(cash) > 1:
                problem('FX_LEG', ref, k, 'FX 사건 현금 leg 최대 하나')
            fx += amount
        elif cash:
            problem('NONCASH_CASH_LEG', ref, k, '발생주의/비현금 사건에 현금계정 포함 불가')
        if ev['kind'] == 'ACCRUAL' and any(mappings[x['account_id']]['method'] not in ('WC_ASSET', 'WC_LIABILITY', 'EXCLUDED') for x in legs):
            problem('ACCRUAL_SCOPE', ref, k, '발생주의 사건은 WC/EXCLUDED만 지원')
        needs_adjust = ev['profit_effect'] != 0 and (ev['kind'] == 'NONCASH' or ev['kind'] == 'CASH' and ev['category'] in ('INVESTING', 'FINANCING'))
        if needs_adjust and k not in adjustment_events:
            problem('MISSING_ADJUSTMENT', ref, k, '비현금/분류 재조정의 명시적 손익조정 누락')
    for d in adjustments:
        add(d['line_id'], 'OPERATING', d['amount'], d['_row'].ref + '; ' + events[d['event_id']]['_row'].ref, '-사건 손익효과(1회)')
    for k, mp in mappings.items():
        if mp['method'].startswith('WC_'):
            acc = balances[k]
            removed = sum((x['balance_effect'] for x in by_account[k] if events[x['event_id']]['kind'] in ('NONCASH', 'FX')), ZERO)
            delta = acc['closing'] - acc['opening']
            amount = (delta - removed) * (-1 if mp['method'] == 'WC_ASSET' else 1)
            add(mp['line_id'], 'OPERATING', amount, acc['_row'].ref + '; ' + mp['_row'].ref + '; ' + ', '.join(x['_row'].ref for x in by_account[k]), f'{mp["method"]}: (기말 {acc["closing"]} - 기초 {acc["opening"]} - 비현금/FX {removed}) × 정상부호')
    cfo = sum((v for cat, v in result.lines.values() if cat == 'OPERATING'), ZERO)
    for lid, cat in (('CFO', 'OPERATING'), ('CFI', 'INVESTING'), ('CFF', 'FINANCING')):
        amount = cfo if lid == 'CFO' else direct[cat]
        add(lid, 'TOTAL', amount, '계산근거', cat + ' 명세 합계')
    add('FX', 'NONE', fx, 'Events!FX; Movements', '현금범위의 FX leg만')
    add('CASH_DELTA', 'TOTAL', cfo + direct['INVESTING'] + direct['FINANCING'] + fx, 'CFO + CFI + CFF + FX', '현금증감 검증')
    add('CASH_OPEN', 'TOTAL', settings['opening_cash_control'], settings_rows['opening_cash_control']['_row'].ref, '독립 기초 현금 통제합계')
    add('CASH_CLOSE', 'TOTAL', settings['closing_cash_control'], settings_rows['closing_cash_control']['_row'].ref, '독립 기말 현금 통제합계')
    check('OPERATING_DETAIL', 'Events', 'CFO', cfo, direct['OPERATING'], '간접법 영업현금흐름과 직접 현금명세 불일치')
    check('FX_CONTROL', 'Events', 'FX', fx, settings['fx_cash_control'], '현금 환율영향과 독립 통제값 불일치')
    check('CASH_CHANGE', 'Settings', 'CASH_DELTA', result.lines['CASH_DELTA'][1], settings['closing_cash_control'] - settings['opening_cash_control'], '영업+투자+재무+환율과 현금증감 불일치')
    for lid, (cat, amount) in result.lines.items():
        d = statement.get(lid)
        if not d:
            problem('STATEMENT_MISSING', 'Statement', lid, '초안 명세/합계 누락')
        else:
            if cat != d['category']:
                problem('STATEMENT_CLASS', d['_row'].ref, lid, '초안 분류 불일치')
            check('STATEMENT_DIFF', d['_row'].ref, lid, amount, d['amount'], '계산값과 초안 금액 차이')
    for lid in statement.keys() - result.lines.keys():
        problem('STATEMENT_EXTRA', statement[lid]['_row'].ref, lid, '계산근거 없는 초안 명세')
    stop()
    return result
