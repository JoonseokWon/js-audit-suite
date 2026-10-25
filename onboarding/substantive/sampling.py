"""Reproducible item selection; no MUS, automatic sample size or projection."""
from hashlib import sha256
from common import AuditError, cancelled, issue, num, text
from onboarding.contracts import reconciliation
from .shared import prepare, finish, linked, check_nonempty

AREA = '감사표본선정'


def analyze(payload, context, ledger_result, event=None):
    data, index, issues, valid = prepare(AREA, payload, context, ledger_result, event)
    population = data['population']; check_nonempty(population, issues, '표본')
    policy = payload['policy']; checks = []; coverage = []
    materiality = num(policy.get('materiality'), False)
    performance = num(policy.get('performance_materiality'), False)
    threshold = num(policy.get('high_threshold'), False)
    size = num(policy.get('random_size'), False)
    seed = text(policy.get('seed'), '재현 시드')
    if not 0 < threshold <= performance <= materiality:
        raise AuditError('0<고액층기준≤수행중요성≤전체중요성이 필요합니다.')
    if policy.get('selection_method') != 'seeded_hash_rank' or policy.get('negative_policy') != 'separate_full':
        raise AuditError('현재 seeded_hash_rank·음수별도전수 정책만 지원합니다.')
    if policy.get('sampling_unit') != 'gl_line':
        raise AuditError('현재 표본 지원단위는 GL 1행입니다. 복합분개·자산단위 기법은 별도 검토하세요.')
    accounts = set(text(policy.get('account_codes')).split(','))
    basis = policy.get('amount_basis')
    if basis not in ('debit', 'credit', 'signed'):
        raise AuditError('금액기준 debit/credit/signed 필요')
    pop_index = {}
    for row in population:
        cancelled(event)
        ident = row['record_id']; amount = num(row.get('amount'))
        if len(row['gl_refs']) != 1:
            issue(issues, 'SAMPLE_UNIT_NETTING', 'GL 1행 단위가 필요합니다. 여러 양수·음수 행을 묶어 상계할 수 없습니다.', ident)
        refs = linked(row, index, issues)
        if any(r['계정코드'] not in accounts for r in refs):
            issue(issues, 'SAMPLE_SCOPE', '승인된 계정 모집단 밖 행', ident)
        actual = sum(num(r['차변']) if basis == 'debit' else num(r['대변'])
                     if basis == 'credit' else num(r['차변'])-num(r['대변']) for r in refs)
        reconciliation(checks, '모집단금액 원장', amount, actual, ident, issues)
        coverage.extend(row['gl_refs']); pop_index[ident] = row
    expected = {key for key, row in index.items() if row['계정코드'] in accounts}
    if set(coverage) != expected or len(coverage) != len(set(coverage)):
        issue(issues, 'SAMPLE_POPULATION', '승인 계정 원장 모집단의 누락·중복·범위외 행입니다.')
    specific = set()
    for row in data['specific_items']:
        ident = text(row.get('population_id')); text(row.get('reason'))
        linked(row, index, issues)
        if ident not in pop_index or ident in specific:
            issue(issues, 'SAMPLE_SPECIFIC', '특정항목 모집단ID 누락·중복', ident)
        elif set(row['gl_refs']) != set(pop_index[ident]['gl_refs']):
            issue(issues, 'SAMPLE_SPECIFIC_LINK', '특정항목과 모집단의 원장행 연결이 다릅니다.', ident)
        specific.add(ident)
    strata, residual = {}, []
    for ident, row in pop_index.items():
        amount = num(row['amount'])
        if amount < 0: strata[ident] = '음수별도전수'
        elif amount >= threshold: strata[ident] = '고액전수'
        elif ident in specific: strata[ident] = '특정항목'
        elif amount > 0: residual.append(ident)
        else: strata[ident] = '0원별도검토'
    # Stable across Python versions, input order and OS. No global RNG state.
    ranks = {ident: sha256((seed+'\x00'+ident).encode('utf-8')).hexdigest() for ident in residual}
    ranked = sorted(residual, key=lambda ident: (ranks[ident], ident))
    if size > len(ranked):
        issue(issues, 'SAMPLE_SIZE', '사람이 정한 무작위 규모가 잔여 양수 모집단보다 큽니다.')
    for ident in ranked[:size]: strata[ident] = '무작위후보'
    selected = {ident for ident, stratum in strata.items() if stratum != '0원별도검토'}
    output = [{'모집단행ID': ident, '금액': num(row['amount']),
               '선정층': strata.get(ident, '잔여미선정'), '선정여부': ident in selected,
               '특정항목지정': ident in specific, '재현순위해시': ranks.get(ident, ''),
               '원장행ID': row['gl_refs'], '원본행': row['source_ref']}
              for ident, row in sorted(pop_index.items())]
    findings, tested = [], set()
    for row in data['errors']:
        ident = text(row.get('population_id'))
        text(row.get('reviewer')); text(row.get('reason')); linked(row, index, issues)
        if ident not in selected or ident in tested:
            issue(issues, 'SAMPLE_ERROR_SCOPE', '선정 외 또는 중복 검사입력', ident)
        tested.add(ident)
        book, audited = num(row.get('book_amount')), num(row.get('audited_amount'))
        if ident in pop_index:
            reconciliation(checks, '검사입력 장부금액', num(pop_index[ident]['amount']), book, ident, issues)
            if set(row['gl_refs']) != set(pop_index[ident]['gl_refs']):
                issue(issues, 'SAMPLE_ERROR_LINK', '검사입력과 모집단의 원장행 연결이 다릅니다.', ident)
        findings.append({'모집단행ID': ident, '장부금액': book, '사람입력검사금액': audited,
                         '발견차이': audited-book, '검토입력자': row['reviewer'],
                         '사유': row['reason'], '원본행': row['source_ref']})
        if audited != book:
            issue(issues, 'SAMPLE_FINDING', '입력된 발견차이 '+str(audited-book)+'원: 개별·합산 및 질적 영향 검토 필요', ident, False)
    if selected - tested:
        issue(issues, 'SAMPLE_UNTESTED', '선정 후보의 증빙 검사입력이 남아 있습니다.', ','.join(sorted(selected-tested)), False)
    net = sum(r['발견차이'] for r in findings); absolute = sum(abs(r['발견차이']) for r in findings)
    return finish(AREA, payload, context,
        {'표본모집단대사': checks, '선정후보': output, '입력발견오류': findings,
         '입력_모집단': population, '입력_특정항목': data['specific_items'], '입력_오류': data['errors']},
        issues, index, valid,
        {'모집단건수': len(pop_index), '선정건수': len(selected), '발견차이순액': net,
         '발견차이절대합': absolute, '미검사후보': len(selected-tested)},
        {'방법': '고액전수+특정항목+음수별도전수+승인규모 seeded SHA-256 순위 후보',
         '표본지원단위': 'GL 1행; 복합분개·자산 단위 자동 상계 미지원',
         'MUS구현': False, '표본규모자동결정': False, '오류추정투영': False,
         '추가한계': '특정항목·고액층 결과를 잔여 모집단에 투영하지 않음. 통계적 신뢰수준·표본위험·허용오류 평가는 사람 판단.'})
