"""Evidence-linked proposed note bridges; preserve original disclosure amounts."""
from collections import Counter, defaultdict
from common import AuditError, cancelled, issue, num, text
from onboarding.contracts import reconciliation
from .shared import prepare, finish, linked, gl_amount, tb_index, check_nonempty

AREA = '주석구성대사'


def analyze(payload, context, ledger_result, event=None):
    data, index, issues, valid = prepare(AREA, payload, context, ledger_result, event)
    balances = data['note_balances']; check_nonempty(balances, issues, '주석잔액')
    tb = tb_index(ledger_result); checks = []; movement_sums = defaultdict(int)
    balances_by_id = {}; covered = Counter(); bridge = []; components = []
    for row in balances:
        rid, account = row['record_id'], text(row.get('account_code'))
        text(row.get('note_id')); factor = num(row.get('factor'))
        if factor not in (-1, 1): raise AuditError('주석 표시부호는 ±1이어야 합니다.')
        if account not in tb: issue(issues, 'NOTE_TB_MISSING', '주석 통제계정 TB 누락', account)
        num(row.get('opening_asis')); num(row.get('closing_asis'))
        linked(row, index, issues, optional=True); balances_by_id[rid] = row
    if len({r['account_code'] for r in balances}) != len(balances):
        issue(issues, 'NOTE_ACCOUNT_DUP', '현재 범위는 주석 계정당 잔액 행 하나만 지원합니다.')
    for row in data['note_movements']:
        cancelled(event)
        bid = text(row.get('balance_id')); amount = num(row.get('amount'))
        if bid not in balances_by_id: raise AuditError('주석 변동의 잔액행ID가 없습니다.')
        balance = balances_by_id[bid]; account = balance['account_code']
        if row.get('kind') not in ('cash', 'noncash'):
            raise AuditError('주석 변동 cash/noncash 구분 필요')
        text(row.get('evidence_type')); refs = linked(row, index, issues)
        reconciliation(checks, '주석변동 원장', amount,
                       gl_amount(refs, account)*num(balance['factor']), row['record_id'], issues)
        for key in row['gl_refs']:
            if key in index and index[key]['계정코드'] == account: covered[key] += 1
        movement_sums[bid] += amount
        if balance.get('category') == 'loan':
            cash_accounts = set(text(payload['policy'].get('cash_account_codes')).split(','))
            journals = {r['전표ID'] for r in refs}
            cash = sum(num(r['차변'])-num(r['대변']) for r in index.values()
                       if r['전표ID'] in journals and r['계정코드'] in cash_accounts)
            if row['kind'] == 'cash':
                reconciliation(checks, '차입 현금변동', amount, cash, row['record_id'], issues)
            elif cash:
                issue(issues, 'NOTE_NONCASH_CLASS', '현금이 있는 차입 전표를 비현금으로 분류했습니다.', row['record_id'])
    scope = {r['account_code'] for r in balances}
    for key, row in index.items():
        if row['계정코드'] in scope and covered[key] != 1:
            issue(issues, 'NOTE_MOVEMENT_POPULATION', '주석 계정의 원장변동 누락·중복', key)
    for bid, row in balances_by_id.items():
        account = row['account_code']
        if account not in tb: continue
        opening = num(tb[account]['기초잔액'])*num(row['factor'])
        closing = opening+movement_sums[bid]
        reconciliation(checks, '주석기초 AsIs/TB', opening, num(row['opening_asis']), bid, issues)
        reconciliation(checks, '주석기말 ToBe/TB', num(tb[account]['기말잔액'])*num(row['factor']), closing, bid, issues)
        reconciliation(checks, '주석기말 AsIs/ToBe', closing, num(row['closing_asis']), bid, issues)
        bridge.append({'주석ID': row['note_id'], '계정코드': account,
            '현재기초AsIs': num(row['opening_asis']), '근거기초ToBe': opening,
            '증빙변동합계': movement_sums[bid], '현재기말AsIs': num(row['closing_asis']),
            '근거기말ToBe': closing, '수정제안차이': closing-num(row['closing_asis']),
            '상태': '초안·원본수정안함', '원본행': row['source_ref']})
    loan_sums = defaultdict(int); loan_ids = set()
    for row in data['note_components']:
        kind = row.get('component_kind'); amount = num(row.get('amount'), False)
        current = num(row.get('as_is_amount'), False)
        if kind not in ('loan', 'collateral', 'guarantee', 'restriction'):
            raise AuditError('차입/담보/보증/제한 구성유형 확인 필요')
        text(row.get('note_id')); text(row.get('details')); text(row.get('evidence_type'))
        refs = linked(row, index, issues, optional=kind != 'loan')
        if kind == 'loan':
            account = text(row.get('account_code'))
            if not any(r['계정코드'] == account for r in refs):
                issue(issues, 'NOTE_COMPONENT_ACCOUNT', '차입 구성과 연결 원장계정이 다릅니다.', row['record_id'])
            loan_sums[account] += amount; loan_ids.add(row['record_id'])
        components.append({'구성ID': row['record_id'], '주석ID': row['note_id'], '구성유형': kind,
            '현재금액AsIs': current, '근거입력금액ToBe': amount, '수정제안차이': amount-current,
            '관련구성ID': row.get('related_id', ''), '상세': row['details'],
            '증거유형': row['evidence_type'], '원본행': row['source_ref'], '상태': '근거입력·사람검토필수'})
        reconciliation(checks, '주석구성 AsIs/근거입력', amount, current, row['record_id'], issues)
    for row in data['note_components']:
        if row['component_kind'] == 'collateral' and row.get('related_id') not in loan_ids:
            issue(issues, 'NOTE_COLLATERAL_LINK', '담보가 연결될 차입 구성ID 누락', row['record_id'])
    for row in balances:
        if row.get('category') == 'loan' and row['account_code'] in tb:
            expected = num(tb[row['account_code']]['기말잔액'])*num(row['factor'])
            reconciliation(checks, '차입 구성합계 TB', expected,
                           loan_sums[row['account_code']], row['record_id'], issues)
    output = {'주석증감대사': checks, '주석AsIsToBe': bridge, '차입담보구성ToBe': components,
              '입력_주석잔액': balances, '입력_주석변동': data['note_movements'],
              '입력_주석구성': data['note_components']}
    return finish(AREA, payload, context, output, issues, index, valid,
        {'주석계정수': len(balances), '차입구성합계': sum(loan_sums.values()),
         '담보근거금액': sum(r['근거입력금액ToBe'] for r in components if r['구성유형'] == 'collateral')},
        {'원본주석수정': False, '추가한계': 'ToBe는 구조화된 근거입력·원장 대사 초안. 담보금액을 차입금액과 강제 동액 처리하지 않음. 계약 해석·누락 공시·모든 기준 공시 적합성은 별도 사람 검토.'})
