"""One cash ledger row may have many children; each component retains evidence."""
from collections import defaultdict
from common import issue, num, text
from onboarding.contracts import reconciliation
from .sources import refs_rows, role, signed

COMPONENTS = {
    'operating': {'receivable', 'inventory', 'payable', 'revenue', 'operating_expense'},
    'asset_purchase': {'ppe_cost', 'cip', 'rou_asset'},
    'asset_sale': {'ppe_cost', 'ppe_accum', 'cip', 'disposal_gain'},
    'loan_borrowing': {'loan_long', 'loan_current'},
    'loan_repayment': {'loan_long', 'loan_current'},
    'lease_principal': {'lease_liability'},
    'interest_paid': {'interest_expense', 'interest_payable'},
    'interest_received': {'interest_income', 'interest_receivable'},
    'tax_paid': {'current_tax_expense', 'tax_payable'},
    'dividends_paid': {'equity', 'dividend_payable'},
    'dividends_received': {'dividend_income'},
    'internal_transfer': {'cash'}, 'cash_fx': {'fx_result'},
}
FIXED_CLASS = {'operating': 'operating', 'asset_purchase': 'investing',
               'asset_sale': 'investing', 'loan_borrowing': 'financing',
               'loan_repayment': 'financing', 'lease_principal': 'financing',
               'internal_transfer': 'internal', 'cash_fx': 'fx'}


def analyze(payload, source, accounts, policy, issues):
    cash = {ref: r for ref, r in source.items() if role(r, accounts) == 'cash'}
    by_parent, counterpart_use = defaultdict(list), defaultdict(list)
    ids, details, checks, totals = set(), [], [], defaultdict(int)
    for row in payload['cash_allocations']:
        aid = text(row.get('allocation_id'), '배부번호')
        parent, component = row.get('parent_gl_ref'), row.get('component')
        amount = num(row.get('amount'))
        if aid in ids:
            issue(issues, 'CF_ALLOCATION_DUPLICATE', '배부번호가 중복입니다.', aid)
        ids.add(aid)
        refs = row.get('gl_refs')
        linked = refs_rows(refs, source, issues, aid)
        if parent not in cash or parent not in (refs or []):
            issue(issues, 'CF_CASH_PARENT', '현재 현금 원장행을 부모로 연결하세요.', aid)
            continue
        if component not in COMPONENTS:
            issue(issues, 'CF_COMPONENT', '지원하지 않는 현금흐름 항목입니다.', aid)
            continue
        parent_row = cash[parent]
        counterpart = [(ref, source[ref]) for ref in (refs or [])
                       if ref in source and ref != parent]
        if not counterpart or any(r['전표ID'] != parent_row['전표ID'] for _, r in counterpart):
            issue(issues, 'CF_ALLOCATION_EVIDENCE', '부모와 같은 전표의 상대 계정 행을 연결하세요.', aid)
        if any(role(r, accounts) not in COMPONENTS[component] for _, r in counterpart):
            issue(issues, 'CF_COMPONENT_ROLE', '원금·이자·세금 등 구성항목과 상대계정이 다릅니다.', aid)
        reconciliation(checks, '배부 구성 '+aid, -sum(signed(r) for _, r in counterpart),
                       amount, ', '.join(refs or []), issues)
        if amount == 0 or amount * signed(parent_row) <= 0:
            issue(issues, 'CF_ALLOCATION_SIGN', '부모 현금행과 배부금액의 방향을 확인하세요.', aid)
        if component == 'loan_borrowing' and amount < 0 or component == 'loan_repayment' and amount > 0:
            issue(issues, 'CF_LOAN_DIRECTION', '차입·상환 방향이 현금 원장행과 다릅니다.', aid)
        for ref, r in counterpart:
            if component != 'internal_transfer':
                counterpart_use[ref].append(aid)
        by_parent[parent].append(amount)
        classification = FIXED_CLASS.get(component, policy.get(component, 'unknown'))
        if classification not in {'operating', 'investing', 'financing', 'internal', 'fx'}:
            issue(issues, 'CF_CLASSIFICATION', '분류정책을 확인하세요.', aid)
        totals[classification] += amount
        totals[component+'_cash'] += amount
        details.append({'배부번호': aid, '부모현금행': parent, '계정코드': parent_row['계정코드'],
                        '부모현금금액': signed(parent_row), '구성항목': component,
                        '배부금액': amount, '활동분류': classification,
                        '원장연결행': ', '.join(refs or []), '상대원장행': ', '.join(r for r, _ in counterpart)})
    for ref, uses in counterpart_use.items():
        if len(uses) > 1:
            issue(issues, 'CF_COUNTERPART_DUPLICATE', '같은 상대계정 행을 여러 배부에 중복 사용했습니다.', ref)
    for ref, row in cash.items():
        reconciliation(checks, '현금행 배부 '+ref, signed(row), sum(by_parent[ref]), ref, issues)
    _internal(source, accounts, details, issues, checks)
    return details, checks, totals


def _internal(source, accounts, details, issues, checks):
    journals = defaultdict(list)
    for r in details:
        if r['구성항목'] == 'internal_transfer':
            journals[source[r['부모현금행']]['전표ID']].append(r)
    for journal, children in journals.items():
        population = {k: r for k, r in source.items() if r['전표ID'] == journal}
        parents = [r['부모현금행'] for r in children]
        if (len(population) != 2 or len(parents) != 2 or len(set(parents)) != 2
                or set(parents) != set(population)
                or len({r['계정코드'] for r in population.values()}) != 2
                or any(role(r, accounts) != 'cash' for r in population.values())):
            issue(issues, 'CF_INTERNAL_PAIR', '내부이체는 서로 다른 현금 계정의 양쪽 원장행 전체가 필요합니다.', journal)
        reconciliation(checks, '내부이체 양쪽 상계 '+journal, 0,
                       sum(r['배부금액'] for r in children), journal, issues)
