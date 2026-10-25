"""Ledger-connected KRW cash-flow workpaper support, with human-approved inputs."""
from common import cancelled, result
from onboarding.contracts import approval, check_payload, ledger_basis
from . import allocations, bridges, controls, depreciation, noncash, policy, sources
from .samples import negative_cases, sample
from .schema import APPROVAL_FIELDS, FIELD_LABELS, REFERENCES, TABLE_FIELDS


def analyze(payload, context, ledger_result, event=None):
    check_payload(payload, context)
    sources.lists(payload)
    cancelled(event)
    issues = []
    chosen = policy.validate(payload, context, ledger_result, issues)
    confirmed = approval(payload, APPROVAL_FIELDS, issues, '현금흐름 입력·계산정책 확인')
    source, lead, accounts, tags, account_checks = sources.build(payload, context, ledger_result, issues)
    policy.account_categories(accounts, chosen, issues)
    cash_rows, cash_checks, totals = allocations.analyze(payload, source, accounts, chosen, issues)
    cancelled(event)
    dep_rows, dep_checks, dep = depreciation.analyze(payload, source, lead, accounts, tags, issues)
    nc_rows, nc_checks = noncash.analyze(payload, source, accounts, tags, issues)
    control_checks, group_rows = controls.balances(payload, lead, accounts, issues)
    debt_rows, debt_checks = controls.debt_rollforward(source, lead, accounts, tags, cash_rows, issues)
    summary, flow_checks, bridge_rows, reported_checks = bridges.analyze(
        payload, lead, accounts, chosen, dep, totals, issues)
    cancelled(event)
    checks = account_checks+cash_checks+dep_checks+nc_checks+control_checks+debt_checks+flow_checks+reported_checks
    tables = {'입력_'+FIELD_LABELS[k]: payload[k] for k in TABLE_FIELDS}
    tables.update({'입력_회계정책': [{'항목': FIELD_LABELS.get(k,k), '값': v} for k,v in chosen.items()],
        '현금흐름표연결': [{'표시항목': k, '계산금액': v} for k,v in summary.items()],
        '계정증감대사': account_checks, '현금원장배부': cash_rows,
        '상각비배부검증': dep_rows, '비현금증감명세': nc_rows,
        '이자법인세독립대사': bridge_rows, '재무부채증감명세': debt_rows,
        '검증그룹대사': group_rows, '검사결과': checks,
        '연결원장행': [{'원장행ID': ref, '원천': row['_origin'], '계정코드': row['계정코드'],
                       '차변': row['차변'], '대변': row['대변'],
                       '원본행': str(row.get('_sheet','총계정원장'))+'!'+str(row.get('_row','')),
                       '증감구분': tags.get(ref,'미확인')} for ref,row in source.items()],
        '기준참고': REFERENCES})
    blocking = sum(i['severity']=='차단' for i in issues)
    detail = {'현재원장연결': bool(confirmed and source and lead and not blocking),
              '원장내용해시': ledger_basis(ledger_result), '입력확인': confirmed,
              '계산범위': '확정 KRW·명시 계정매핑·현금배부·승인조정·사람이 확인한 정책의 간접법 지원',
              '검토사항': '현금성자산 범위·실질 분류·기준 적용·공시 필요성과 감사결론은 사람이 검토합니다.',
              '국내시행자동추정': False, '자동승인': False, '실제AI호출': 0,
              '상각비조정': dep, '현금흐름계산': summary}
    return result('현금흐름표연결', context, tables, issues,
                  dict(summary, 연결원장행수=len(source), 검사수=len(checks)), detail)
