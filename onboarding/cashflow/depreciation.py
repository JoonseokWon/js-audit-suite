"""Manufacturing depreciation cannot be added back twice through inventory."""
from common import issue, num
from onboarding.contracts import reconciliation
from .sources import refs_rows, role, signed


def analyze(payload, source, lead, accounts, tags, issues):
    parts, checks, used = [], [], set()
    expense, capitalized = 0, 0
    for index, row in enumerate(payload['depreciation_parts'], 1):
        kind, amount = row.get('kind'), num(row.get('amount'), signed=False)
        refs = row.get('gl_refs')
        linked = refs_rows(refs, source, issues, '상각비 '+str(index))
        if kind not in {'expense', 'inventory'}:
            issue(issues, 'CF_DEPRECIATION_KIND', '비용 상각비와 재고에 배부한 상각비를 구분하세요.')
        expected_role = 'depreciation_expense' if kind == 'expense' else 'inventory'
        if any(role(r, accounts) != expected_role for r in linked):
            issue(issues, 'CF_DEPRECIATION_ROLE', '상각비 배부 계정이 비용·재고 구분과 다릅니다.')
        if any(tags.get(ref) != 'depreciation' for ref in refs or []):
            issue(issues, 'CF_DEPRECIATION_TAG', '상각비 배부의 원장 증감 분류가 다릅니다.')
        if used.intersection(refs or []):
            issue(issues, 'CF_DEPRECIATION_DUPLICATE', '동일 상각비 원장행을 중복 배부했습니다.')
        used.update(refs or [])
        reconciliation(checks, '상각비 배부 '+str(index), sum(signed(r) for r in linked),
                       amount, ', '.join(refs or []), issues)
        expense += amount if kind == 'expense' else 0
        capitalized += amount if kind == 'inventory' else 0
        parts.append({'상각비구분': kind, '금액': amount, '원장연결행': ', '.join(refs or [])})
    expected_debits = {ref for ref, r in source.items() if tags.get(ref) == 'depreciation'
                       and role(r, accounts) in {'inventory', 'depreciation_expense'}}
    if used != expected_debits:
        issue(issues, 'CF_DEPRECIATION_SCOPE', '상각비 비용·제조배부 원장행을 빠짐없이 연결하세요.')
    accumulated = -sum(signed(r) for ref, r in source.items()
                       if tags.get(ref) == 'depreciation' and role(r, accounts) == 'ppe_accum')
    reconciliation(checks, '상각누계 증가와 비용·제조배부 합계', accumulated,
                   expense+capitalized, '감가상각누계액/비용/재고', issues)
    inv_delta = sum(num(r['조정후'])-num(r['기초잔액']) for code, r in lead.items()
                    if accounts.get(code, {}).get('role') == 'inventory')
    gross = expense+capitalized-inv_delta
    net = expense-(inv_delta-capitalized)
    reconciliation(checks, '재고 총액·순액 조정방식 비교', gross, net, '상각비 이중조정 방지', issues)
    return parts, checks, {'expense': expense, 'capitalized': capitalized,
                           'total': accumulated, 'inventory_delta': inv_delta,
                           'gross_adjustment': gross, 'net_adjustment': net}
