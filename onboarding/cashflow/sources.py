"""Current GL and approved-adjustment populations, never cached input amounts."""
from collections import defaultdict
from common import AuditError, issue, num, text
from onboarding.contracts import ledger_rows, reconciliation
from .schema import KINDS, PROFIT_ROLES, ROLES


def lists(payload):
    from .schema import TABLE_FIELDS
    for key in TABLE_FIELDS:
        rows = payload.get(key)
        if not isinstance(rows, list) or len(rows) > 10000:
            raise AuditError(key + ': 최대 10,000개 행 목록이 필요합니다.')
        if any(not isinstance(row, dict) for row in rows):
            raise AuditError(key + ': 행은 항목별 값으로 입력하세요.')
        for row in rows:
            if 'gl_refs' in TABLE_FIELDS[key]:
                refs = row.get('gl_refs')
                if not isinstance(refs, list) or any(not isinstance(r, str) for r in refs):
                    raise AuditError(key + ': 원장 연결행은 행 식별자의 목록이어야 합니다.')


def build(payload, context, ledger, issues):
    original = ledger_rows(ledger, context, issues)
    source = {k: dict(r, _origin='GL') for k, r in original.items()}
    tables = (ledger or {}).get('tables', {})
    adjustments = defaultdict(list)
    for row in tables.get('입력_감사조정', []):
        if row.get('상태') == '승인':
            adjustments[str(row['조정ID'])].append(row)
    for aid, rows in adjustments.items():
        if sum(num(r['차변']) - num(r['대변']) for r in rows):
            issue(issues, 'CF_ADJUSTMENT_BALANCE', '승인 표시된 조정의 차대변이 다릅니다.', aid)
        for r in rows:
            ref = 'AJE:' + aid + '/' + str(r['행ID'])
            if ref in source:
                issue(issues, 'CF_SOURCE_DUPLICATE', '감사조정 행 식별자가 중복입니다.', ref)
            source[ref] = dict(r, _origin='AJE', 전표ID='AJE:'+aid)
    lead = {str(r['계정코드']): r for r in tables.get('리드스케줄', [])}
    accounts = {}
    for r in payload['accounts']:
        code = text(r.get('account_code'), '계정코드')
        if code in accounts:
            issue(issues, 'CF_ACCOUNT_DUPLICATE', '계정 연결이 중복입니다.', code)
        accounts[code] = r
        if r.get('role') not in ROLES or not str(r.get('validation_group', '')).strip():
            issue(issues, 'CF_ACCOUNT_ROLE', '계정 역할·검증그룹을 확인하세요.', code)
        if code in lead:
            pl = lead[code]['표시구분'] == 'PL'
            if pl != (r.get('role') in PROFIT_ROLES):
                issue(issues, 'CF_PROFIT_MAPPING', '손익/재무상태표 구분과 현금흐름 역할이 다릅니다.', code)
            if pl and (r.get('profit_category') not in {'operating', 'investing', 'financing', 'tax'}
                       or num(lead[code]['기초잔액'])):
                issue(issues, 'CF_PROFIT_SCOPE', '손익 범주와 당기 손익의 기초 이월 여부를 확인하세요.', code)
    if set(accounts) != set(lead):
        issue(issues, 'CF_ACCOUNT_SCOPE', '현재 리드스케줄의 모든 계정을 빠짐없이 한 번씩 연결하세요.',
              ', '.join(sorted(set(accounts) ^ set(lead))))
    tags = {}
    for row in payload['movement_tags']:
        ref = text(row.get('source_ref'), '원장 증감 연결')
        if ref in tags:
            issue(issues, 'CF_TAG_DUPLICATE', '원장 증감 분류가 중복입니다.', ref)
        tags[ref] = row.get('kind')
        if row.get('kind') not in KINDS:
            issue(issues, 'CF_TAG_KIND', '설명되지 않은 증감은 자동으로 현금흐름에 포함하지 않습니다.', ref)
    if set(tags) != set(source):
        issue(issues, 'CF_TAG_SCOPE', '원장 및 승인 감사조정의 증감 분류가 누락되거나 범위 밖입니다.',
              ', '.join(sorted(set(tags) ^ set(source))))
    from .tag_rules import validate as validate_tags
    validate_tags(source, accounts, tags, issues)
    checks = []
    for code, row in lead.items():
        movements = [r for r in source.values() if str(r['계정코드']) == code]
        gl = sum(signed(r) for r in movements if r['_origin'] == 'GL')
        aje = sum(signed(r) for r in movements if r['_origin'] == 'AJE')
        reconciliation(checks, '계정 증감 '+code, num(row['조정후'])-num(row['기초잔액']),
                       gl+aje, code, issues)
        checks[-1].update(원장증감=gl, 승인조정=aje, 조정전=row['조정전'], 조정후=row['조정후'])
    return source, lead, accounts, tags, checks


def signed(row):
    return num(row['차변']) - num(row['대변'])


def role(row, accounts):
    return accounts.get(str(row['계정코드']), {}).get('role', '')


def balance(lead, accounts, roles, field):
    return sum(num(row[field]) for code, row in lead.items()
               if accounts.get(code, {}).get('role') in roles)


def refs_rows(refs, source, issues, label):
    from onboarding.contracts import require_refs
    return require_refs(refs, source, issues, label)
