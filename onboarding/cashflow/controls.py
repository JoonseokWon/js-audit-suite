"""Independent cash and validation-group balances; never cancel across groups."""
from collections import defaultdict
from common import issue, num, text
from onboarding.contracts import reconciliation
from .schema import DEBT
from .sources import role, signed


def balances(payload, lead, accounts, issues):
    checks, details = [], []
    cash_codes = {c for c in lead if accounts.get(c, {}).get('role') == 'cash'}
    seen = set()
    for row in payload['cash_controls']:
        code = text(row.get('account_code'), '현금 통제 계정')
        ref = text(row.get('source_ref'), '현금 독립 통제 근거')
        if code in seen or code not in cash_codes:
            issue(issues, 'CF_CASH_CONTROL_SCOPE', '현금 독립통제 계정이 중복되거나 범위 밖입니다.', code)
        seen.add(code)
        if code not in lead:
            continue
        reconciliation(checks, '현금 기초 독립통제 '+code, num(row.get('opening')),
                       num(lead[code]['기초잔액']), ref, issues)
        reconciliation(checks, '현금 기말 독립통제 '+code, num(row.get('closing')),
                       num(lead[code]['조정후']), ref, issues)
    if seen != cash_codes or not cash_codes:
        issue(issues, 'CF_CASH_CONTROL_MISSING', '선택한 모든 현금·현금성자산의 기초·기말 독립통제가 필요합니다.')
    groups = defaultdict(lambda: [0, 0])
    group_roles, group_statements = defaultdict(set), defaultdict(set)
    for code, row in lead.items():
        group = accounts.get(code, {}).get('validation_group', '')
        group_roles[group].add(accounts.get(code, {}).get('role'))
        group_statements[group].add(row['표시구분'])
        if row['표시구분'] == 'BS':
            groups[group][0] += num(row['기초잔액'])
            groups[group][1] += num(row['조정후'])
    for group, roles in group_roles.items():
        permitted = (len(roles) == 1 or roles <= {'ppe_cost', 'ppe_accum'}
                     or roles <= {'loan_long', 'loan_current'} or group_statements[group] == {'PL'})
        if not permitted or len(group_statements[group]) != 1:
            issue(issues, 'CF_GROUP_ROLE', '서로 다른 자산·부채 성격을 한 검증그룹으로 상쇄할 수 없습니다.', group)
    seen = set()
    for row in payload['group_controls']:
        group = text(row.get('validation_group'), '검증그룹')
        ref = text(row.get('source_ref'), '검증그룹 독립 통제 근거')
        if group in seen or group not in groups:
            issue(issues, 'CF_GROUP_SCOPE', '검증그룹이 중복되거나 범위 밖입니다.', group)
        seen.add(group)
        opening, closing = groups.get(group, [0, 0])
        reconciliation(checks, '그룹 기초 '+group, num(row.get('opening')), opening, ref, issues)
        reconciliation(checks, '그룹 기말 '+group, num(row.get('closing')), closing, ref, issues)
        details.append({'검증그룹': group, '원장기초': opening, '통제기초': num(row['opening']),
                        '원장기말': closing, '통제기말': num(row['closing']),
                        '기말차이': closing-num(row['closing']), '근거자료행': ref})
    if seen != set(groups):
        issue(issues, 'CF_GROUP_MISSING', '서로 다른 그룹의 차이를 상쇄하지 않도록 모든 재무상태표 그룹 통제가 필요합니다.')
    return checks, details


def debt_rollforward(source, lead, accounts, tags, allocations, issues):
    cash_refs = set()
    for row in allocations:
        if row['구성항목'] in {'loan_borrowing', 'loan_repayment', 'lease_principal'}:
            cash_refs.update(row['상대원장행'].split(', '))
    details, checks = [], []
    for code, account in accounts.items():
        if account.get('role') not in DEBT or code not in lead:
            continue
        changes = defaultdict(int)
        connected = []
        for ref, row in source.items():
            if str(row['계정코드']) != code:
                continue
            connected.append(ref)
            kind = tags.get(ref)
            if ref in cash_refs:
                category = '현금증감'
            elif kind == 'lease_new':
                category = '신규리스'
            elif kind == 'debt_reclass':
                category = '유동성대체'
            elif kind == 'fx':
                category = '환율변동'
            else:
                category = '미확인증감'
                issue(issues, 'CF_DEBT_UNEXPLAINED', '재무부채 증감의 현금·비현금 구분이 확인되지 않았습니다.', ref)
            changes[category] -= signed(row)
        opening, closing = -num(lead[code]['기초잔액']), -num(lead[code]['조정후'])
        expected = opening+sum(changes.values())
        reconciliation(checks, '재무부채 증감 '+code, closing, expected, ', '.join(connected), issues)
        details.append({'계정코드': code, '검증그룹': account['validation_group'], '기초부채': opening,
                        **{k: changes[k] for k in ('현금증감', '신규리스', '유동성대체', '환율변동', '미확인증감')},
                        '기말부채': closing, '계산기말': expected, '차이': expected-closing,
                        '원장연결행': ', '.join(connected)})
    return details, checks
