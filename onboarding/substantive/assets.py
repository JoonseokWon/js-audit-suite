"""Gross cost/accumulated depreciation movements, paired transfers and reversals."""
from collections import Counter, defaultdict
from common import AuditError, cancelled, day, issue, num, text
from onboarding.contracts import reconciliation
from .shared import prepare, finish, linked, gl_amount, tb_index, check_nonempty

AREA = '유형자산증감'
KINDS = {'acquisition', 'disposal', 'depreciation', 'transfer_in', 'transfer_out',
         'cancellation_in', 'cancellation_out'}


def analyze(payload, context, ledger_result, event=None):
    data, index, issues, valid = prepare(AREA, payload, context, ledger_result, event)
    assets, moves = data['assets'], data['asset_movements']
    scope_list = text(payload['policy'].get('asset_account_codes'), '명시 자산계정 범위').split(',')
    declared_scope = {code.strip() for code in scope_list}
    if not all(declared_scope) or len(declared_scope) != len(scope_list):
        raise AuditError('명시 자산계정 범위에 빈 값·중복이 있습니다.')
    check_nonempty(assets, issues, '자산등록'); check_nonempty(moves, issues, '자산변동')
    asset_index = {}; totals = defaultdict(lambda: [0, 0]); pairs = defaultdict(list)
    checks, population, pair_checks, coverage = [], [], [], Counter()
    for row in assets:
        aid = text(row.get('asset_id'))
        if aid in asset_index:
            issue(issues, 'ASSET_DUPLICATE', '자산ID 중복', aid)
        asset_index[aid] = row
        if row.get('asset_type') not in ('PPE', 'CIP'):
            raise AuditError('자산종류 PPE/CIP만 지원합니다.')
        text(row.get('cost_account'))
        if row['asset_type'] == 'PPE': text(row.get('accum_account'))
        for field in ('opening_cost', 'closing_cost', 'opening_accum', 'closing_accum'):
            num(row.get(field), False)
        if row['asset_type'] == 'CIP' and (num(row['opening_accum']) or num(row['closing_accum'])):
            issue(issues, 'CIP_ACCUM', 'CIP의 누계상각은 지원하지 않습니다.', aid)
        linked(row, index, issues, optional=True)
    for row in moves:
        cancelled(event)
        aid, kind = text(row.get('asset_id')), text(row.get('kind'))
        if aid not in asset_index or kind not in KINDS:
            raise AuditError('자산ID 또는 변동유형을 확인하세요.')
        asset = asset_index[aid]; ref = row['record_id']
        if not day(context['시작일']) <= day(row.get('date')) <= day(context['기준일']):
            issue(issues, 'ASSET_PERIOD', '통제기간 밖 자산변동', ref)
        cost, accum = num(row.get('cost_delta')), num(row.get('accum_delta'))
        proceeds, gain = num(row.get('proceeds'), False), num(row.get('gain'))
        if kind == 'depreciation' and (cost or accum <= 0 or asset['asset_type'] != 'PPE'):
            issue(issues, 'ASSET_MOVEMENT_SIGN', '상각은 PPE 누계 증가만 허용합니다.', ref)
        if kind in ('acquisition', 'transfer_in', 'cancellation_in') and (cost <= 0 or accum):
            issue(issues, 'ASSET_MOVEMENT_SIGN', '취득/대체입/취소원본은 양수 원가·누계0 필요', ref)
        if kind in ('transfer_out', 'cancellation_out') and (cost >= 0 or accum):
            issue(issues, 'ASSET_MOVEMENT_SIGN', '대체출/취소는 음수 원가·누계0 필요', ref)
        if kind != 'disposal' and (proceeds or gain):
            issue(issues, 'ASSET_DISPOSAL_ONLY', '대가·손익은 처분 행에만 입력합니다.', ref)
        refs = linked(row, index, issues)
        reconciliation(checks, '원가변동 원장', cost, gl_amount(refs, asset['cost_account']), ref, issues)
        reconciliation(checks, '누계변동 원장', -accum,
                       gl_amount(refs, asset.get('accum_account', '')), ref, issues)
        for key in row['gl_refs']:
            if key in index and index[key]['계정코드'] in {asset['cost_account'], asset.get('accum_account')}:
                coverage[key] += 1
        if kind == 'disposal':
            if cost >= 0 or accum > 0 or -accum > -cost:
                issue(issues, 'ASSET_DISPOSAL_SIGN', '처분 원가/누계 제거 금액 확인 필요', ref)
            reconciliation(checks, '처분손익', proceeds - (-cost + accum), gain, ref, issues)
            reconciliation(checks, '처분대가 현금', proceeds,
                           gl_amount(refs, text(row.get('cash_account'))), ref, issues)
            reconciliation(checks, '처분손익 원장', -gain,
                           gl_amount(refs, text(row.get('gain_account'))), ref, issues)
        totals[aid][0] += cost; totals[aid][1] += accum
        if kind.startswith(('transfer_', 'cancellation_')):
            pairs[text(row.get('pair_id'), '대체/취소 쌍ID')].append(row)
        elif row.get('pair_id'):
            issue(issues, 'ASSET_PAIR_TYPE', '대체/취소 외 쌍ID 사용', ref)
        population.append({'변동ID': ref, '자산ID': aid, '유형': kind, '원가변동': cost,
                           '누계변동': accum, '처분대가': proceeds, '처분손익': gain,
                           '원본행': row['source_ref'], '원장행ID': row['gl_refs']})
    for pair, entries in pairs.items():
        kinds = {r['kind'] for r in entries}
        transfer = kinds == {'transfer_in', 'transfer_out'}
        cancel = kinds == {'cancellation_in', 'cancellation_out'}
        same_asset = len({r['asset_id'] for r in entries}) == 1
        ok = (len(entries) == 2 and (transfer and not same_asset or cancel and same_asset)
              and sum(num(r['cost_delta']) for r in entries) == 0)
        pair_checks.append({'쌍ID': pair, '유형': '대체' if transfer else '취소',
                            '원본건수': len(entries), '원가합계': sum(num(r['cost_delta']) for r in entries),
                            '상태': '기계적 일치' if ok else '누락·중복·금액 차이'})
        if not ok: issue(issues, 'ASSET_PAIR', '대체/취소 쌍의 누락·중복·금액/자산 불일치', pair)
    account_open, account_close = defaultdict(int), defaultdict(int)
    for aid, row in asset_index.items():
        cost_delta, accum_delta = totals[aid]
        reconciliation(checks, '자산 원가 롤포워드', num(row['opening_cost'])+cost_delta,
                       num(row['closing_cost']), aid, issues)
        reconciliation(checks, '자산 누계 롤포워드', num(row['opening_accum'])+accum_delta,
                       num(row['closing_accum']), aid, issues)
        if num(row['closing_accum']) > num(row['closing_cost']):
            issue(issues, 'ASSET_NET_NEGATIVE', '기말 누계가 원가를 초과합니다.', aid)
        for account, opening, closing in ((row['cost_account'], row['opening_cost'], row['closing_cost']),
                (row.get('accum_account'), -num(row['opening_accum']), -num(row['closing_accum']))):
            if account:
                account_open[account] += num(opening); account_close[account] += num(closing)
    tb = tb_index(ledger_result)
    if set(account_open) != declared_scope:
        issue(issues, 'ASSET_DECLARED_SCOPE', '등록 원가/누계 계정과 명시 승인 범위가 다릅니다.',
              ','.join(sorted(set(account_open)^declared_scope)))
    for account in declared_scope-set(account_open):
        issue(issues, 'ASSET_SCOPE_MISSING', '명시 범위의 자산등록·잔액 근거가 누락되었습니다.', account)
    for account in account_open:
        if account not in tb:
            issue(issues, 'ASSET_TB_MISSING', '자산 통제계정 TB 누락', account); continue
        reconciliation(checks, '자산기초 TB', tb[account]['기초잔액'], account_open[account], account, issues)
        reconciliation(checks, '자산기말 TB', tb[account]['기말잔액'], account_close[account], account, issues)
    for key, row in index.items():
        if row['계정코드'] in declared_scope and coverage[key] != 1:
            issue(issues, 'ASSET_POPULATION', '자산 계정 원장 행의 누락·중복 연결', key)
    output = {'자산원가누계대사': checks, '취득처분변동모집단': population,
              '대체취소쌍검사': pair_checks, '입력_자산등록': assets, '입력_자산변동': moves}
    return finish(AREA, payload, context, output, issues, index, valid,
                  {'기말원가': sum(num(r['closing_cost']) for r in assets),
                   '기말누계': sum(num(r['closing_accum']) for r in assets),
                   '처분손익': sum(num(r['gain']) for r in moves)},
                  {'대상계정': sorted(declared_scope),
                   '범위': '사람이 명시한 선택 계정의 대사. 전체 유형자산·CIP 모집단 완전성이나 감사완료를 뜻하지 않음.',
                   '추가한계': '단일통화 원가모형 변동대사. 누락 계정범위를 자동 추정하지 않음. 취득 인식·내용연수·상각 재계산·손상·재평가·외화·현물출자는 별도 검토.'})
