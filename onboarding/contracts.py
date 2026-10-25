"""Shared scope and provenance checks; never make an audit judgment."""
from common import AuditError, day, digest, issue, num, text
from onboarding import SCHEMA


def check_payload(payload, context):
    if not isinstance(payload, dict) or payload.get('schema') != SCHEMA:
        raise AuditError('실무절차 입력 버전이 다릅니다.')
    if payload.get('context') != context:
        raise AuditError('실무절차 입력 회사·시작일·기준일이 현재 업무와 다릅니다.')
    day(context['시작일']); day(context['기준일'])
    return payload


def gl_key(row):
    return str(row['전표ID']) + '/' + str(row['행ID'])


def ledger_basis(ledger_result):
    """Stable content basis independent of a file name or execution metadata."""
    if not ledger_result:
        return ''
    return digest({'context': {k: ledger_result.get('context', {}).get(k)
                    for k in ('회사코드','시작일','기준일')},
                   'tables': ledger_result.get('tables', {}),
                   'blocking': ledger_result.get('blocking')})


def ledger_rows(ledger_result, context, issues):
    if (not ledger_result or any(ledger_result.get('context', {}).get(k) != v for k, v in context.items())
            or ledger_result.get('blocking')):
        issue(issues, 'ONB_LEDGER_REQUIRED', '현재 업무의 독립 통제를 통과한 원장·리드 검사가 필요합니다.')
        return {}
    rows = ledger_result.get('tables', {}).get('입력_총계정원장', [])
    index = {gl_key(row): row for row in rows}
    if not rows or len(index) != len(rows):
        issue(issues, 'ONB_LEDGER_KEYS', '현재 원장 행의 식별자·범위를 확인하세요.')
        return {}
    return index


def require_refs(refs, index, issues, label):
    if not isinstance(refs, list) or not refs or len(refs) != len(set(refs)):
        issue(issues, 'ONB_REFS', label + ': 원장 행 연결이 비었거나 중복입니다.', label)
        return []
    missing = [ref for ref in refs if ref not in index]
    if missing:
        issue(issues, 'ONB_REF_MISSING', label + ': 현재 원장에 없는 행입니다.', ', '.join(missing))
    return [index[ref] for ref in refs if ref in index]


def approval(payload, fields, issues, label='입력 설정'):
    """Pin an explicit person's data-mapping/policy approval to exact input values."""
    record = payload.get('approval', {})
    expected = digest({key: payload.get(key) for key in fields})
    valid = (isinstance(record, dict) and record.get('input_hash') == expected
             and isinstance(record.get('actor'), str) and bool(record['actor'].strip())
             and isinstance(record.get('reason'), str) and bool(record['reason'].strip()))
    if not valid:
        issue(issues, 'ONB_APPROVAL_REQUIRED', label + ': 현재 입력에 대한 확인자·사유·입력 해시가 필요합니다.')
    return valid


def reconciliation(rows, label, expected, actual, ref, issues, *, blocking=True):
    difference = num(actual) - num(expected)
    rows.append({'검사': label, '기대': expected, '실제': actual, '차이': difference,
                 '상태': '일치' if difference == 0 else '차이', '원본행': ref})
    if difference:
        issue(issues, 'ONB_RECONCILIATION', label + ': 차이 ' + str(difference), ref, blocking)
    return difference


def ledger_link_table(index):
    return [{'원장행ID': key, '계정코드': r['계정코드'], '차변': r['차변'], '대변': r['대변'],
             '원본행': '총계정원장!' + str(r.get('_row', ''))} for key, r in index.items()]
