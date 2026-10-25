"""Retain gross noncash asset/debt movements outside cash-flow totals."""
from common import issue, num, text
from onboarding.contracts import reconciliation
from .schema import ASSETS
from .sources import refs_rows, role, signed

RULES = {'asset_transfer': (ASSETS, ASSETS),
         'lease_new': ({'rou_asset'}, {'lease_liability'}),
         'debt_reclass': ({'loan_long', 'loan_current'}, {'loan_long', 'loan_current'}),
         'debt_fx': ({'fx_result', 'loan_long', 'loan_current', 'lease_liability'},
                     {'fx_result', 'loan_long', 'loan_current', 'lease_liability'})}


def analyze(payload, source, accounts, tags, issues):
    details, checks, seen, ids = [], [], set(), set()
    for row in payload['noncash']:
        item = text(row.get('item_id'), '비현금 명세번호')
        kind = row.get('kind')
        amount = num(row.get('amount'), signed=False)
        debit, credit, refs = row.get('debit_account'), row.get('credit_account'), row.get('gl_refs')
        linked = refs_rows(refs, source, issues, item)
        if item in ids or seen.intersection(refs or []):
            issue(issues, 'CF_NONCASH_DUPLICATE', '비현금 명세번호·원장행이 중복입니다.', item)
        ids.add(item); seen.update(refs or [])
        if kind not in RULES or debit == credit or amount == 0:
            issue(issues, 'CF_NONCASH_KIND', '지원되는 비현금 증감 구분·서로 다른 계정·금액을 확인하세요.', item)
            continue
        dr_roles, cr_roles = RULES[kind]
        if (accounts.get(str(debit), {}).get('role') not in dr_roles
                or accounts.get(str(credit), {}).get('role') not in cr_roles):
            issue(issues, 'CF_NONCASH_ROLE', '비현금 증감 구분과 차대변 계정의 역할이 다릅니다.', item)
        if kind == 'debt_fx' and not any(role(r, accounts) == 'fx_result' for r in linked):
            issue(issues, 'CF_NONCASH_FX', '외화 재무부채 증감은 환차손익 행과 연결하세요.', item)
        journals = {r['전표ID'] for r in linked}
        population = {k for k, r in source.items() if r['전표ID'] in journals}
        if len(journals) != 1 or population != set(refs or []):
            issue(issues, 'CF_NONCASH_JOURNAL', '지원 범위의 비현금 전표 전체 행을 연결하세요.', item)
        if any(role(r, accounts) == 'cash' for r in linked):
            issue(issues, 'CF_NONCASH_CONTAINS_CASH', '현금이 포함된 전표를 비현금거래로 제외할 수 없습니다.', item)
        expected_tag = 'fx' if kind == 'debt_fx' else kind
        if any(tags.get(ref) != expected_tag for ref in refs or []):
            issue(issues, 'CF_NONCASH_TAG', '원장 증감 분류와 비현금 명세가 다릅니다.', item)
        actual_dr = sum(signed(r) for r in linked if str(r['계정코드']) == str(debit))
        actual_cr = -sum(signed(r) for r in linked if str(r['계정코드']) == str(credit))
        reconciliation(checks, '비현금 차변 '+item, amount, actual_dr, ', '.join(refs or []), issues)
        reconciliation(checks, '비현금 대변 '+item, amount, actual_cr, ', '.join(refs or []), issues)
        if any(str(r['계정코드']) not in {str(debit), str(credit)} for r in linked):
            issue(issues, 'CF_NONCASH_ACCOUNT_SCOPE', '지원하는 단일 차변·단일 대변 계정 이외의 행이 있습니다.', item)
        details.append({'명세번호': item, '증감구분': kind, '차변계정': debit, '대변계정': credit,
                        '금액': amount, '원장연결행': ', '.join(refs or []),
                        '용도': '비현금 증감 및 공시 검토자료; 공시 필요 여부는 사람이 검토'})
    expected = {ref for ref, r in source.items() if tags.get(ref) in
                {'asset_transfer', 'lease_new', 'debt_reclass'}}
    expected |= {ref for ref, r in source.items() if tags.get(ref) == 'fx'
                 and not any(role(x, accounts) == 'cash' for x in source.values()
                             if x['전표ID'] == r['전표ID'])}
    if seen != expected:
        issue(issues, 'CF_NONCASH_SCOPE', '비현금 증감 원장행의 누락·범위 밖 연결이 있습니다.',
              ', '.join(sorted(seen ^ expected)))
    return details, checks
