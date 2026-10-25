"""Union of bank sources and field-level follow-up drafts; never send requests."""
from collections import Counter, defaultdict
from common import AuditError, cancelled, day, issue, num, text
from onboarding.contracts import reconciliation
from .shared import prepare, finish, linked, tb_index, check_nonempty

AREA = '금융기관조회'
FIELDS = ('deposits', 'borrowings', 'guarantees', 'collateral', 'restrictions')
SOURCE_TYPES = {'current', 'prior', 'closed', 'zero', 'guarantee', 'collateral'}


def analyze(payload, context, ledger_result, event=None):
    data, index, issues, valid = prepare(AREA, payload, context, ledger_result, event)
    sources = data['institution_sources']; check_nonempty(sources, issues, '조회대상 근거')
    targets = defaultdict(set); book = defaultdict(int); checks = []; coverage = set()
    tb = tb_index(ledger_result); current_accounts = Counter()
    scope_list = text(payload['policy'].get('financial_account_codes'), '명시 금융계정 범위').split(',')
    accounts = {account.strip() for account in scope_list}
    if not all(accounts) or len(accounts) != len(scope_list):
        raise AuditError('명시 금융계정 범위에 빈 값·중복이 있습니다.')
    for account in accounts-set(tb):
        issue(issues, 'CONFIRM_SCOPE_TB', '선언 금융계정이 현재 TB에 없습니다.', account)
    for row in sources:
        cancelled(event)
        institution, kind = text(row.get('institution_id')), text(row.get('source_type'))
        field = text(row.get('field'))
        if kind not in SOURCE_TYPES or field not in FIELDS:
            raise AuditError('조회대상 근거유형·항목을 확인하세요.')
        targets[institution].add(kind)
        amount = num(row.get('book_amount'))
        if kind != 'prior': book[institution, field] += amount
        active = any(r['계정코드'] == row.get('account_code') for r in index.values())
        refs = linked(row, index, issues, optional=kind != 'current' or not active)
        if kind == 'current':
            account = text(row.get('account_code')); factor = num(row.get('factor'))
            current_accounts[account] += 1
            if current_accounts[account] > 1:
                issue(issues, 'CONFIRM_CURRENT_DUP', '현재 범위는 금융계정당 당기 근거 한 행만 지원합니다.', account)
            if factor not in (-1, 1): raise AuditError('조회 장부금액 표시부호는 ±1')
            if account not in tb: issue(issues, 'CONFIRM_TB', '현재 조회계정 TB 누락', account)
            else:
                reconciliation(checks, '조회 장부잔액 TB', num(tb[account]['기말잔액'])*factor,
                               num(row['book_amount']), row['record_id'], issues)
                if not active and (num(tb[account]['기초잔액']) != num(tb[account]['기말잔액'])
                        or num(tb[account]['당기차변']) or num(tb[account]['당기대변'])):
                    issue(issues, 'CONFIRM_INACTIVE_TB', '무활동 계정의 TB 기초/기말·당기총액이 일치하지 않습니다.', account)
            coverage.update(k for k in row['gl_refs'] if k in index and index[k]['계정코드'] == account)
            if any(r['계정코드'] != account for r in refs):
                issue(issues, 'CONFIRM_SOURCE_ACCOUNT', '조회근거 연결계정 불일치', row['record_id'])
    if set(current_accounts) != accounts:
        issue(issues, 'CONFIRM_DECLARED_SCOPE', '당기 근거계정과 선언 금융계정 범위가 다릅니다.',
              ','.join(sorted(set(current_accounts)^accounts)))
    required = {key for key, row in index.items() if row['계정코드'] in accounts}
    if not required <= coverage:
        issue(issues, 'CONFIRM_POPULATION', '승인 금융계정 원장의 조회기관 근거가 누락되었습니다.', ','.join(sorted(required-coverage)))
    requests = {}; request_ids = set()
    for row in data['requests']:
        institution = text(row.get('institution_id')); request = text(row.get('request_id'))
        requested = row.get('requested_fields')
        if institution in requests or request in request_ids:
            issue(issues, 'CONFIRM_REQUEST_DUP', '기관/요청ID 중복', request)
        if (not isinstance(requested, list) or not all(isinstance(x, str) for x in requested)
                or len(requested) != len(set(requested)) or set(requested) != set(FIELDS)):
            issue(issues, 'CONFIRM_REQUEST_FIELDS', '예금·차입·보증·담보·제한 항목의 누락·중복', request)
        linked(row, index, issues, optional=True)
        requests[institution] = row; request_ids.add(request)
    if set(requests) != set(targets):
        issue(issues, 'CONFIRM_TARGET_UNION', '당기·전기·폐쇄·0잔액·보증/담보 기관 합집합과 요청대상이 다릅니다.',
              ','.join(sorted(set(requests)^set(targets))))
    responses = {}; reply_checks = []; followups = []
    for row in data['responses']:
        institution, field = text(row.get('institution_id')), text(row.get('field'))
        key = (institution, field)
        if institution not in requests or field not in FIELDS or row.get('request_id') != requests[institution]['request_id']:
            issue(issues, 'CONFIRM_RESPONSE_SCOPE', '요청과 연결되지 않는 회신 항목', row['record_id'])
        if key in responses: issue(issues, 'CONFIRM_RESPONSE_DUP', '동일 기관/항목 회신 중복', row['record_id'])
        day(row.get('as_of')); text(row.get('details')); num(row.get('amount'))
        if row.get('authenticity') not in ('unverified', 'person_claimed'):
            raise AuditError('회신 진위 상태는 unverified/person_claimed만 지원합니다.')
        if row['authenticity'] == 'person_claimed': text(row.get('reviewer')); text(row.get('reason'))
        linked(row, index, issues, optional=True); responses[key] = row
    for institution in sorted(targets):
        for field in FIELDS:
            row = responses.get((institution, field)); reasons = []
            if row is None:
                reasons.append('미회신/부분회신 항목')
            else:
                if (institution, field) not in book: reasons.append('장부/계약 항목 근거 미입력')
                if row['as_of'] != context['기준일']: reasons.append('다른 기준일: 기간변동 근거 필요')
                if (institution, field) in book and num(row['amount']) != book[institution, field]: reasons.append('장부와 회신 차이 조사')
                if row['authenticity'] != 'person_claimed': reasons.append('직접회신·진위 미확인')
            reply_checks.append({'기관ID': institution, '항목': field,
                '장부근거금액': book.get((institution, field)), '회신금액': None if row is None else num(row['amount']),
                '회신기준일': '' if row is None else row['as_of'],
                '검토상태': ' / '.join(reasons) if reasons else '입력대사 일치·사람 최종평가 필요',
                '진위자동판정': False, '원본행': '' if row is None else row['source_ref']})
            if reasons:
                followups.append({'기관ID': institution, '항목': field, '후속요청사유': ' / '.join(reasons),
                                  '상태': '초안·발송하지 않음'})
                issue(issues, 'CONFIRM_FOLLOWUP', institution+' '+field+': '+' / '.join(reasons), institution, False)
    output = {'조회대상합집합': [{'기관ID': key, '근거유형': sorted(value), '상태': '검토대상'}
                                 for key, value in sorted(targets.items())],
              '조회장부잔액대사': checks, '회신항목대사': reply_checks, '후속요청초안': followups,
              '입력_조회근거': sources, '입력_요청': data['requests'], '입력_회신': data['responses']}
    return finish(AREA, payload, context, output, issues, index, valid,
                  {'조회대상기관': len(targets), '후속요청항목': len(followups)},
                  {'실제발송': False, '회신진위자동확인': False,
                   '대상금융계정': sorted(accounts),
                   '범위': '사람이 명시한 금융계정·제공 기관 근거의 대사. 전체 은행관계·금융기관 모집단 완전성이나 감사완료를 뜻하지 않음.',
                   '추가한계': '합집합은 제공된 자료 범위. 누락 기관의 존재·직접회신 경로·회신 진위·미회신 대체절차·차이 원인은 사람이 확인.'})
