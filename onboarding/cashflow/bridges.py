"""Independent accrual-to-cash bridges and indirect/direct reconciliation."""
from common import issue, num
from onboarding.contracts import reconciliation
from .sources import balance


def income(lead, accounts, roles):
    return -balance(lead, accounts, roles, '조정후')


def included(lead, accounts, roles, starting_point):
    return -sum(num(r['조정후']) for c, r in lead.items()
                if accounts.get(c, {}).get('role') in roles and
                (starting_point == 'net_profit' or accounts[c].get('profit_category') == 'operating'))


def analyze(payload, lead, accounts, policy, dep, totals, issues):
    checks, bridge = [], []
    for label, exp_roles, liability, receivable, component, received in (
        ('이자지급', {'interest_expense'}, {'interest_payable'}, set(), 'interest_paid', False),
        ('법인세지급', {'current_tax_expense'}, {'tax_payable'}, set(), 'tax_paid', False),
        ('이자수취', {'interest_income'}, set(), {'interest_receivable'}, 'interest_received', True),
        ('배당수취', {'dividend_income'}, set(), set(), 'dividends_received', True),
    ):
        pl = balance(lead, accounts, exp_roles, '조정후') * (-1 if received else 1)
        delta = (balance(lead, accounts, receivable, '조정후')-balance(lead, accounts, receivable, '기초잔액')
                 if received else -(balance(lead, accounts, liability, '조정후')
                                     -balance(lead, accounts, liability, '기초잔액')))
        expected = pl-delta
        actual = totals[component+'_cash'] * (1 if received else -1)
        reconciliation(checks, label+' 발생액·현금 독립대사', expected, actual,
                       label+' 손익/관련 채권·채무/현금배부', issues)
        bridge.append({'구분': label, '손익금액': pl, '관련채권채무증가': delta,
                       '계산현금': expected, '실제현금배부': actual, '차이': actual-expected})
    profit = -sum(num(r['조정후']) for r in lead.values() if r['표시구분'] == 'PL')
    operating_profit = -sum(num(r['조정후']) for c, r in lead.items()
                            if r['표시구분'] == 'PL' and accounts.get(c, {}).get('profit_category') == 'operating')
    start = policy.get('starting_point')
    start_amount = operating_profit if start == 'operating_profit' else profit
    # Strip separately bridged income/expense only when included in the chosen subtotal.
    separate = included(lead, accounts, {'interest_expense', 'interest_income',
                         'current_tax_expense', 'dividend_income', 'fx_result'}, start)
    gain = included(lead, accounts, {'disposal_gain'}, start)
    ar_delta = balance(lead, accounts, {'receivable'}, '조정후')-balance(lead, accounts, {'receivable'}, '기초잔액')
    ap_delta = -(balance(lead, accounts, {'payable'}, '조정후')-balance(lead, accounts, {'payable'}, '기초잔액'))
    if policy.get('inventory_method') == 'net_inventory_expensed_depreciation':
        addback, inv_delta = dep['expense'], dep['inventory_delta']-dep['capitalized']
    else:
        addback, inv_delta = dep['total'], dep['inventory_delta']
    base = start_amount-separate+addback-ar_delta-inv_delta+ap_delta-gain
    operating_separate = sum(totals[component+'_cash'] for component in (
        'interest_paid', 'interest_received', 'tax_paid', 'dividends_received', 'dividends_paid')
        if policy.get(component) == 'operating')
    cfo = base+operating_separate
    reconciliation(checks, '간접법 영업현금·현금원장 배부 비교', cfo, totals['operating'],
                   '당기손익/운전자본/상각비/이자·세금 브리지', issues)
    summary = {'net_profit': profit, 'operating_profit': operating_profit,
               'starting_amount': start_amount, 'depreciation_addback': addback,
               'inventory_adjustment': -inv_delta, 'receivable_adjustment': -ar_delta,
               'payable_adjustment': ap_delta, 'gain_adjustment': -gain,
               'separate_income_expense_adjustment': -separate,
               'operating_before_separate_cash': base, 'operating_separate_cash': operating_separate,
               'CFO': cfo, 'CFI': totals['investing'], 'CFF': totals['financing'], 'FX': totals['fx']}
    opening = balance(lead, accounts, {'cash'}, '기초잔액')
    closing = balance(lead, accounts, {'cash'}, '조정후')
    reconciliation(checks, '현금 기초·현금흐름·기말 연결', closing,
                   opening+cfo+summary['CFI']+summary['CFF']+summary['FX'], '현금 독립통제/현재 리드', issues)
    summary.update(cash_opening=opening, cash_closing=closing,
                   cash_movement=closing-opening, internal_transfer_net=totals['internal'])
    reported, seen = [], set()
    for row in payload['reported_flows']:
        line = row.get('line')
        if line in seen or line not in summary:
            issue(issues, 'CF_REPORTED_SCOPE', '작성 현금흐름표의 항목이 중복되거나 범위 밖입니다.', str(line))
            continue
        seen.add(line)
        reconciliation(reported, '작성 현금흐름표 '+line, summary[line], num(row.get('amount')), line, issues)
    if not {'CFO', 'CFI', 'CFF', 'FX', 'cash_opening', 'cash_closing'} <= seen:
        issue(issues, 'CF_REPORTED_MISSING', '작성 현금흐름표의 영업·투자·재무·환율·기초·기말 항목이 필요합니다.')
    return summary, checks, bridge, reported
