"""Qualitative cash-equivalent evidence; date alone never approves a class."""
from calendar import monthrange
from common import AuditError, cancelled, day, issue, num, text
from onboarding.contracts import reconciliation
from .shared import prepare, finish, linked, tb_index, check_nonempty

AREA = '분류검토'
CRITERIA = ('short_term_commitments', 'convertible_known_amount', 'insignificant_value_risk',
            'restriction_absent', 'original_maturity', 'contract_terms')
CLASSES = {'cash', 'cash_equivalent', 'financial_asset', 'restricted_cash', 'unresolved'}


def analyze(payload, context, ledger_result, event=None):
    data, index, issues, valid = prepare(AREA, payload, context, ledger_result, event)
    items = data['classification_items']; check_nonempty(items, issues, '분류검토')
    tb = tb_index(ledger_result); checks = []; items_by_id = {}; evidence = {}; output = []
    for row in items:
        cancelled(event)
        account = text(row.get('account_code')); amount = num(row.get('amount'), False)
        for field in ('as_is_class', 'proposed_class'):
            if row.get(field) not in CLASSES: raise AuditError('지원 분류값 확인 필요')
        text(row.get('proposal_actor')); text(row.get('proposal_reason'))
        acquired, maturity = day(row.get('acquisition_date')), day(row.get('maturity_date'))
        if acquired > day(context['기준일']) or maturity < acquired:
            issue(issues, 'CLASSIFICATION_DATE', '취득일/원래만기일 순서·기간 확인 필요', row['record_id'])
        linked(row, index, issues, optional=True)
        expected_refs = {k for k, r in index.items() if r['계정코드'] == account}
        if set(row['gl_refs']) != expected_refs:
            issue(issues, 'CLASSIFICATION_LEDGER_SCOPE', '분류대상 계정 원장행의 누락·범위외 연결', row['record_id'])
        if account not in tb: issue(issues, 'CLASSIFICATION_TB', '분류대상 TB 계정 누락', account)
        else: reconciliation(checks, '분류대상 금액 TB', num(tb[account]['기말잔액']), amount, row['record_id'], issues)
        items_by_id[row['record_id']] = row
    if len({r['account_code'] for r in items}) != len(items):
        issue(issues, 'CLASSIFICATION_ACCOUNT_DUP', '현재 분류대상은 계정당 한 행만 지원합니다.')
    for row in data['classification_evidence']:
        item_id, criterion = text(row.get('item_id')), text(row.get('criterion'))
        if item_id not in items_by_id or criterion not in CRITERIA:
            raise AuditError('분류 증거의 대상/검토항목 확인 필요')
        if row.get('status') not in ('supported', 'contradicted', 'unknown'):
            raise AuditError('정성증거 상태 supported/contradicted/unknown 필요')
        text(row.get('observation')); linked(row, index, issues, optional=True)
        if (item_id, criterion) in evidence:
            issue(issues, 'CLASSIFICATION_EVIDENCE_DUP', '정성증거 검토항목 중복', row['record_id'])
        evidence[item_id, criterion] = row
    for ident, item in items_by_id.items():
        missing, conflicting, unknown = [], [], []
        for criterion in CRITERIA:
            row = evidence.get((ident, criterion))
            if row is None: missing.append(criterion)
            elif row['status'] == 'contradicted': conflicting.append(criterion)
            elif row['status'] == 'unknown': unknown.append(criterion)
        acquired, maturity = day(item['acquisition_date']), day(item['maturity_date'])
        month = acquired.month-1+3; year = acquired.year+month//12; month = month%12+1
        calendar_limit = acquired.replace(year=year, month=month,
                                          day=min(acquired.day, monthrange(year, month)[1]))
        within = maturity <= calendar_limit
        if item['proposed_class'] == 'cash_equivalent' and not within:
            conflicting.append('original_maturity_date')
        status = '상충' if conflicting else '미확인' if missing or unknown else '근거입력완비·사람판단필요'
        output.append({'분류행ID': ident, '계정코드': item['account_code'], '금액': num(item['amount']),
            '현재분류AsIs': item['as_is_class'], '사람제안ToBe': item['proposed_class'],
            '원래만기3개월이내참고': within, '취득후만기일수참고': (maturity-acquired).days,
            '누락항목': missing, '미확인항목': unknown, '상충항목': conflicting,
            '검토상태': status, '제안자': item['proposal_actor'], '제안사유': item['proposal_reason'],
            '프로그램적정판정': False, '원본행': item['source_ref']})
        issue(issues, 'CLASSIFICATION_HUMAN', ident+': '+status+'; 날짜만으로 적정 판단하지 않습니다.', ident, False)
    return finish(AREA, payload, context,
        {'분류금액대사': checks, '분류AsIsToBe검토': output, '입력_분류대상': items,
         '입력_정성증거': data['classification_evidence']}, issues, index, valid,
        {'분류대상': len(items), '미확인대상': sum(r['검토상태'] == '미확인' for r in output),
         '상충대상': sum(r['검토상태'] == '상충' for r in output)},
        {'분류자동확정': False, '추가한계': '현금성 분류 증거 체크리스트만 지원. 목적·전환성·가치변동위험·제한·계약의 입력된 관찰을 대조하며 상품 실질/사용제한 해석·최종 분류는 사람 판단.'})
