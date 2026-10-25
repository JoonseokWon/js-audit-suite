"""Strict data checks and human-input provenance, never audit approval."""
from collections import Counter
from common import AuditError, cancelled, digest, issue, num, result, text
from onboarding.contracts import check_payload, approval, ledger_rows, require_refs, ledger_link_table

FIELDS = {
    '유형자산증감': ('assets', 'asset_movements'),
    '감사표본선정': ('population', 'specific_items', 'errors'),
    '금융기관조회': ('institution_sources', 'requests', 'responses'),
    '주석구성대사': ('note_balances', 'note_movements', 'note_components'),
    '분류검토': ('classification_items', 'classification_evidence'),
}
POPULATIONS = {'감사표본선정': ('population',), '금융기관조회': ('institution_sources',)}
APPROVAL_FIELDS = {area: ('context', 'policy') + fields for area, fields in FIELDS.items()}
ALIASES = dict(zip(('AU04', 'AU05', 'AU06', 'AU07', 'AU08'), FIELDS)) | {'CF07': '분류검토'}
LIMITS = ('확정 KRW 및 명시된 입력/매핑의 기계적 검사. 실제 감사수행·회신진위·판단·승인 기록을 만들지 않음.',
          '확인자 이름은 인증이 아님. 원본 증빙의 진실성·정책 타당성·감사결론은 사람이 검토.',
          '조정전 TB 기준. 승인조정을 자동 반영하거나 기존 원장/분류를 수정하지 않음.')


def area_name(area):
    area = ALIASES.get(area, area)
    if area not in FIELDS:
        raise AuditError('지원하지 않는 실증절차 영역입니다.')
    return area


def population_hash(area, payload):
    return digest({k: payload.get(k) for k in POPULATIONS.get(area, FIELDS[area])})


def rows(payload, key, issues):
    values = payload.get(key)
    if not isinstance(values, list) or len(values) > 10000:
        raise AuditError(key + ': 10,000행 이하 목록이 필요합니다.')
    counts = Counter()
    for row in values:
        if not isinstance(row, dict) or any(isinstance(v, dict) for v in row.values()):
            raise AuditError(key + ': 중첩 객체 없는 행이 필요합니다.')
        if any(isinstance(v, list) and any(isinstance(x, (dict, list)) for x in v) for v in row.values()):
            raise AuditError(key + ': 목록 안에는 확정 스칼라 값만 허용합니다.')
        ident = text(row.get('record_id'), key + ' 행ID')
        text(row.get('source_ref'), key + ' 원본근거')
        refs = row.get('gl_refs')
        if not isinstance(refs, list) or not all(isinstance(x, str) for x in refs):
            raise AuditError(key + ': gl_refs 목록 필요')
        counts[ident] += 1
    for ident, count in counts.items():
        if count > 1:
            issue(issues, 'SUB_DUPLICATE', key + ': 행ID 중복', ident)
    return values


def prepare(area, payload, context, ledger_result, event):
    check_payload(payload, context); cancelled(event)
    issues = []
    policy = payload.get('policy')
    if not isinstance(policy, dict) or any(isinstance(v, dict) for v in policy.values()):
        raise AuditError('flat policy가 필요합니다.')
    for key in ('policy_version', 'standard_ref', 'basis'):
        text(policy.get(key), key)
    if policy['basis'] != 'unadjusted' or policy.get('currency') != 'KRW':
        raise AuditError('현재 실증절차는 조정전 KRW만 지원합니다.')
    tables = {key: rows(payload, key, issues) for key in FIELDS[area]}
    valid = approval(payload, APPROVAL_FIELDS[area], issues, '정책·모집단 설정')
    expected = population_hash(area, payload)
    if policy.get('population_hash') != expected:
        issue(issues, 'SUB_POPULATION_CHANGED', '모집단 해시가 현재 입력과 다릅니다.')
    index = ledger_rows(ledger_result, context, issues)
    from onboarding.contracts import ledger_basis
    if policy.get('ledger_basis_hash') != ledger_basis(ledger_result):
        issue(issues, 'SUB_LEDGER_BASIS_CHANGED', '현재 원장 기초 해시가 입력의 원장과 다릅니다. 원본 매핑을 다시 검토하세요.')
    return tables, index, issues, valid


def linked(row, index, issues, *, optional=False):
    if optional and row['gl_refs'] == []:
        return []
    return require_refs(row['gl_refs'], index, issues, row['record_id'])


def gl_amount(refs, account):
    return sum(num(r['차변']) - num(r['대변']) for r in refs if r['계정코드'] == account)


def tb_index(ledger_result):
    return {r['계정코드']: r for r in (ledger_result or {}).get('tables', {}).get('입력_시산표', [])}


def check_nonempty(values, issues, label):
    if not values:
        issue(issues, 'SUB_EMPTY', label + ' 모집단이 비어 있습니다.')


def finish(area, payload, context, tables, issues, index, valid, metrics=None, extra=None):
    from .references import CHECKED, SOURCES, LIMITATION
    tables['원장행연결'] = ledger_link_table(index)
    return result(area, context, tables, issues, metrics,
        {'입력해시': digest({key: payload.get(key) for key in APPROVAL_FIELDS[area]}),
         '모집단해시': population_hash(area, payload), '정책해시': digest(payload['policy']),
         '기준참고확인일': CHECKED,
         '기준참고': [{'기준': key, '참고범위': scope, 'URL': url} for key, scope, url in SOURCES],
         '기준참고한계': LIMITATION,
         '설정확인해시일치': valid, '사람판단필수': True, '실제감사수행완료': False,
         '현재원장연결': bool(index) and valid and not any(i['severity'] == '차단' for i in issues),
         '실제승인생성': False, '지원한계': list(LIMITS), **(extra or {})})
