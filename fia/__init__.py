"""Explicit journal-metadata review rules; flags never establish fraud."""
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
import re

from common import AuditError, cancelled, day, issue, num, result, text

VERSION = 'FIA-1.0'
SCHEMA = {
    'FIA설정': ['항목', '값'],
    '전표메타': ['회사코드', '전표ID', '행ID', '입력시각', '입력자', '전표유형', '승인상태', '승인자', '승인시각', '부서', '원천시스템', '재분류그룹'],
}
CONFIG_KEYS = ('규칙버전', '정책명', '마감시각', '메타추출시각', '업무시간대', '업무시작', '업무종료',
               '수동집중최소전표수', '수동집중최소금액', '수동집중비율', '반복재분류최소횟수', '선승인허용')
RULES = {
    'FIA_POST_CLOSE': ('마감후 과거기간 전기', '입력시각 > 명시한 마감시각 AND 원장 전기일 <= 업무 기준일', '마감 승인·재개방 로그·전기기간과 조정 근거를 확인하세요.'),
    'FIA_MANUAL_CONCENTRATION': ('작성자별 수동전표 집중', '같은 입력자의 수동 전표 수·차변합계·전체 전표 대비 비율이 모두 설정 이상', '입력자의 담당업무·일괄입력 사유·전표 생성 및 승인 로그를 확인하세요.'),
    'FIA_SELF_APPROVAL': ('입력자와 승인자 동일', '승인상태=승인 AND 명시된 입력자=승인자', '권한분리 정책·별도 검토자·승인 로그를 확인하세요.'),
    'FIA_TIMESTAMP_ORDER': ('메타 시각 정합성', '입력/승인시각이 메타 추출시각 후이거나 선승인금지 정책에서 승인시각 < 입력시각', '서버 시간대·원본 로그·사전승인 정책·추출 범위를 확인하세요.'),
    'FIA_OUTSIDE_HOURS': ('설정 업무시간 밖 입력', '명시한 고정 시간대의 입력시각이 [업무시작,업무종료) 밖', '배치·정상 결산·담당자 근무시간과 해당 정책 적용 여부를 확인하세요.'),
    'FIA_RECLASS_REPEAT': ('명시적 반복 재분류', '같은 입력자·명시된 재분류그룹·차변/대변 계정집합의 서로 다른 전표 수가 설정 이상', '재분류 원인·원전표·반복 조정 및 정기 전표 여부를 확인하세요.'),
    'FIA_APPROVAL_STATUS': ('수동전표 승인 미완료', '전표유형=수동 AND 승인상태=대기 또는 반려', '권한 정책·후속 승인 또는 반려 후 처리와 원본 증거를 확인하세요.'),
    'FIA_METADATA_SCOPE': ('부서·원천시스템 식별', '명시된 부서와 원천시스템 모두 있어야 분류정보 확인 가능', 'ERP 추출조건과 부서·시스템 원본 매핑을 추가 요청하세요.'),
}
LIMITS = [
    '탐지는 명시 정책에 따른 검토 후보이며 부정·오류 확정이나 발생 확률이 아닙니다.',
    '원장 전기일과 메타 입력시각은 별개입니다. 결산일 후라도 마감 전 입력은 마감후 전기로 탐지하지 않습니다.',
    '입력자·수동자동·승인·부서·시스템은 제출된 메타 주장입니다. 원본 ERP 로그와 권한을 독립 확인하지 않았습니다.',
    '휴가·공휴일·개인 활동·고의성을 추정하지 않습니다. 업무시간은 명시한 고정 UTC offset과 시간 구간만 사용합니다.',
    '메타의 전표단위 필드가 모든 원장 행에서 동일한 형식만 지원합니다. 혼합 전표는 수정·분리 근거 없이 추정하지 않습니다.',
    '반복 재분류는 명시된 그룹만 검사합니다. 그룹 누락을 거래 없음으로 보지 않으며 적요로 재분류를 추정하지 않습니다.',
    '차변합계는 검토 대상 규모이며 여러 규칙에서 반복 검출된 금액을 왜곡표시 합계로 더하지 않습니다.',
]


def _stamp(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value):
        raise AuditError(label + ': 시간대가 있는 ISO8601 시각 필수')
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise AuditError(label + ': 시각 형식 오류') from exc
    if not 1900 <= stamp.year <= 2100 or stamp.utcoffset() is None:
        raise AuditError(label + ': 시각 범위 오류')
    return stamp


def _settings(tables):
    cfg = {}
    for row in tables['FIA설정']:
        key = text(row['항목'])
        if key in cfg:
            raise AuditError('FIA 설정 항목 중복')
        cfg[key] = row['값']
    if set(cfg) != set(CONFIG_KEYS) or cfg['규칙버전'] != VERSION:
        raise AuditError('FIA 필수 설정 누락·추가 또는 규칙버전 불일치')
    text(cfg['정책명'], '정책명')
    close = _stamp(cfg['마감시각'], '마감시각')
    extraction = _stamp(cfg['메타추출시각'], '메타추출시각')
    offset = cfg['업무시간대']
    if not isinstance(offset, str) or not re.fullmatch(r'[+-](?:0\d|1[0-4]):[0-5]\d', offset):
        raise AuditError('업무시간대는 고정 UTC offset 예 +09:00')
    hours, minutes = map(int, offset[1:].split(':'))
    if hours == 14 and minutes:
        raise AuditError('업무시간대 범위 오류')
    zone = timezone((1 if offset[0] == '+' else -1) * timedelta(hours=hours, minutes=minutes))
    hours_pair = []
    for key in ('업무시작', '업무종료'):
        if not isinstance(cfg[key], str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', cfg[key]):
            raise AuditError(key + ': HH:MM 필수')
        hours_pair.append(time.fromisoformat(cfg[key]))
    if hours_pair[0] >= hours_pair[1]:
        raise AuditError('같은 날의 업무시작 < 업무종료만 지원합니다.')
    for key in ('수동집중최소전표수', '수동집중최소금액', '수동집중비율', '반복재분류최소횟수'):
        cfg[key] = num(cfg[key], False)
    if not (1 <= cfg['수동집중최소전표수'] <= 10000 and 1 <= cfg['수동집중비율'] <= 100 and 2 <= cfg['반복재분류최소횟수'] <= 10000):
        raise AuditError('집중·반복 기준 범위 오류')
    if cfg['선승인허용'] not in ('예', '아니오'):
        raise AuditError('선승인허용: 예/아니오 필수')
    return cfg, close, extraction, zone, hours_pair


def _metadata(tables, context, event):
    ledger = {(r['회사코드'], r['전표ID'], r['행ID']): r for r in tables['총계정원장']}
    seen = set()
    journals = defaultdict(list)
    rows = []
    for meta in tables['전표메타']:
        cancelled(event)
        for name in SCHEMA['전표메타']:
            if meta[name] is not None and isinstance(meta[name], str) and meta[name] != meta[name].strip():
                raise AuditError('메타 식별자·표시값의 앞뒤 공백을 원문에서 확인하세요: ' + name)
        key = tuple(text(meta[k], k) for k in ('회사코드', '전표ID', '행ID'))
        if key in seen:
            raise AuditError('중복 전표 메타 복합키')
        seen.add(key)
        if key not in ledger or key[0] != context['회사코드']:
            raise AuditError('현재 입력 원장에 없는 회사·전표·행 메타')
        if meta['전표유형'] not in ('수동', '자동', '미확인') or meta['승인상태'] not in ('승인', '대기', '반려', '미확인'):
            raise AuditError('전표유형/승인상태 필수 또는 허용값 오류')
        text(meta['입력자'], '입력자')
        if meta['입력자'] == '미확인':
            raise AuditError('입력자 식별자는 필수입니다. 미확인으로 대체할 수 없습니다.')
        entered = _stamp(meta['입력시각'], '입력시각')
        approved = _stamp(meta['승인시각'], '승인시각') if meta['승인시각'] is not None else None
        if meta['승인상태'] == '승인':
            text(meta['승인자'], '승인자')
            if meta['승인자'] == '미확인':
                raise AuditError('승인 상태에는 확인한 승인자 식별자가 필수입니다.')
            if approved is None:
                raise AuditError('승인 상태에는 승인시각이 필수입니다.')
        for name in ('승인자', '부서', '원천시스템', '재분류그룹'):
            if meta[name] is not None:
                text(meta[name], name)
        gl = ledger[key]
        journals[key[1]].append((gl, meta, entered, approved))
        rows.append({'회사코드': key[0], '전표ID': key[1], '행ID': key[2], '전기일': gl['전기일'],
                     '입력시각': meta['입력시각'], '입력자': meta['입력자'], '전표유형': meta['전표유형'],
                     '승인상태': meta['승인상태'], '승인자': meta['승인자'], '승인시각': meta['승인시각'],
                     '부서': meta['부서'], '원천시스템': meta['원천시스템'], '재분류그룹': meta['재분류그룹'],
                     '원본행': f"총계정원장!{gl['_row']}", '메타행': f"전표메타!{meta['_row']}"})
    if seen != set(ledger):
        raise AuditError('전체 원장 행의 전표 메타가 누락되었습니다.')
    invariant = [k for k in SCHEMA['전표메타'] if k not in ('회사코드', '전표ID', '행ID')]
    for jid, entries in journals.items():
        for name in invariant:
            if len({m[name] for _, m, _, _ in entries}) != 1:
                raise AuditError('같은 전표의 메타 값 불일치: ' + jid + '/' + name)
    return journals, rows


def analyze(path, context, ledger_result=None, event=None):
    from analytics_support import read_bound
    tables, source, binding = read_bound(path, SCHEMA, context, ledger_result, event)
    issues = list(binding['issues'])
    output = dict(binding['tables'])
    output.update({'입력_FIA설정': tables['FIA설정'], '입력_전표메타': tables['전표메타']})
    detail = dict(binding['detail'])
    detail.update({'규칙버전': VERSION, '제약': LIMITS, '작성자': None, '검토자': None, '결론': None,
                   '수정승인': False, '부정확정': False, '분석완료': False})
    metrics = {'원장행수': 0, '전표수': 0, '검토후보수': 0, '미확인규칙수': 0}
    def finish():
        answer = result('FIA', context, output, issues, metrics, detail)
        answer['source'] = source
        return answer
    if not binding['valid']:
        return finish()
    try:
        cfg, close, extraction, zone, workhours = _settings(tables)
        if close.astimezone(zone).date() < day(context['기준일']) or extraction.astimezone(zone).date() < day(context['기준일']):
            raise AuditError('마감/추출시각은 업무 기준일 이후 또는 당일이어야 합니다.')
        journals, meta_rows = _metadata(tables, context, event)
    except AuditError as exc:
        issue(issues, 'FIA_INPUT', str(exc), 'FIA설정/전표메타')
        return finish()
    detail['설정'] = cfg
    detail['모집단'] = '현재 입력 전체 원장 행에 정확히 1:1 연결한 전표 메타. 전표 단위로 중복 제거하여 분석.'
    output['전표메타대사'] = meta_rows
    metrics.update({'원장행수': len(meta_rows), '전표수': len(journals)})
    found = []
    unknown = defaultdict(set)
    tested = defaultdict(set)

    def candidate(code, jids, reason, priority=2):
        entries = [x for jid in jids for x in journals[jid]]
        first = entries[0][1]
        row = {'규칙ID': code, '규칙버전': VERSION, '회사코드': context['회사코드'], '전표ID': ';'.join(jids),
               '입력자': first['입력자'], '부서': first['부서'], '전표유형': first['전표유형'],
               '전기일': ';'.join(sorted({str(g['전기일']) for g, _, _, _ in entries})),
               '입력시각': ';'.join(sorted({m['입력시각'] for _, m, _, _ in entries})),
               '금액': sum(num(g['차변'], False) for g, _, _, _ in entries), '조건': RULES[code][1],
               '근거': reason, '검토우선순위': priority,
               '원본행': ', '.join(f"총계정원장!{g['_row']}" for g, _, _, _ in entries),
               '메타행': ', '.join(f"전표메타!{m['_row']}" for _, m, _, _ in entries),
               '후속절차': RULES[code][2]}
        row.update({'후보ID': 'FIA-' + str(len(found) + 1).zfill(4), '사유': reason, '우선순위': priority})
        found.append(row)
        issue(issues, code, reason + ' / 검토 후보이며 부정 확정 아님', row['원본행'] + ' / ' + row['메타행'], False)

    for jid, entries in journals.items():
        cancelled(event)
        gl, meta, entered, approved = entries[0]
        for code in ('FIA_POST_CLOSE', 'FIA_TIMESTAMP_ORDER', 'FIA_OUTSIDE_HOURS'):
            tested[code].add(jid)
        if entered > close and any(day(g['전기일']) <= day(context['기준일']) for g, _, _, _ in entries):
            candidate('FIA_POST_CLOSE', [jid], '명시한 마감시각 이후에 업무기간 전기일로 입력됨', 1)
        reasons = []
        if entered > extraction:
            reasons.append('입력시각이 메타 추출시각보다 늦음')
        if approved is not None and approved > extraction:
            reasons.append('승인시각이 메타 추출시각보다 늦음')
        if approved is not None and approved < entered and cfg['선승인허용'] == '아니오':
            reasons.append('선승인금지 정책에서 승인시각이 입력시각보다 이름')
        if approved is not None and meta['승인상태'] != '승인':
            reasons.append('승인완료가 아닌 상태에 승인시각이 존재함')
        if meta['승인상태'] == '미확인':
            unknown['FIA_TIMESTAMP_ORDER'].add(jid)
        if reasons:
            candidate('FIA_TIMESTAMP_ORDER', [jid], '; '.join(reasons), 1)
        local = entered.astimezone(zone).time().replace(tzinfo=None)
        if not workhours[0] <= local < workhours[1]:
            candidate('FIA_OUTSIDE_HOURS', [jid], '명시된 고정 시간대와 업무시간 구간 밖의 입력', 3)
        if meta['승인상태'] == '미확인':
            unknown['FIA_SELF_APPROVAL'].add(jid)
        else:
            tested['FIA_SELF_APPROVAL'].add(jid)
            if meta['승인상태'] == '승인' and meta['승인자'] == meta['입력자']:
                candidate('FIA_SELF_APPROVAL', [jid], '제출 메타의 입력자와 승인자가 동일함', 1)
        if meta['전표유형'] == '미확인' or meta['승인상태'] == '미확인':
            unknown['FIA_APPROVAL_STATUS'].add(jid)
        else:
            tested['FIA_APPROVAL_STATUS'].add(jid)
            if meta['전표유형'] == '수동' and meta['승인상태'] in ('대기', '반려'):
                candidate('FIA_APPROVAL_STATUS', [jid], '명시된 수동전표의 승인상태가 ' + meta['승인상태'], 1)

    users = defaultdict(list)
    groups = defaultdict(list)
    for jid, entries in journals.items():
        _, meta, _, _ = entries[0]
        if meta['부서'] in (None, '미확인') or meta['원천시스템'] in (None, '미확인'):
            unknown['FIA_METADATA_SCOPE'].add(jid)
        else:
            tested['FIA_METADATA_SCOPE'].add(jid)
        users[meta['입력자']].append(jid)
        group = meta['재분류그룹']
        if group in (None, '미확인'):
            unknown['FIA_RECLASS_REPEAT'].add(jid)
        else:
            tested['FIA_RECLASS_REPEAT'].add(jid)
            if group != '해당없음':
                debit = tuple(sorted({g['계정코드'] for g, _, _, _ in entries if num(g['차변'], False) > 0}))
                credit = tuple(sorted({g['계정코드'] for g, _, _, _ in entries if num(g['대변'], False) > 0}))
                groups[(meta['입력자'], group, debit, credit)].append(jid)
    for user, jids in users.items():
        if any(journals[j][0][1]['전표유형'] == '미확인' for j in jids):
            unknown['FIA_MANUAL_CONCENTRATION'].update(jids)
            continue
        tested['FIA_MANUAL_CONCENTRATION'].update(jids)
        manual = [j for j in jids if journals[j][0][1]['전표유형'] == '수동']
        amount = sum(num(g['차변'], False) for j in manual for g, _, _, _ in journals[j])
        if (len(manual) >= cfg['수동집중최소전표수'] and amount >= cfg['수동집중최소금액']
                and 100 * len(manual) >= cfg['수동집중비율'] * len(jids)):
            candidate('FIA_MANUAL_CONCENTRATION', manual, f'{user}: 수동 {len(manual)}/{len(jids)}전표, 차변합계 {amount}원; 세 기준 모두 충족')
    for (_, group, _, _), jids in groups.items():
        if len(jids) >= cfg['반복재분류최소횟수']:
            candidate('FIA_RECLASS_REPEAT', jids, '명시 재분류그룹 ' + group + '의 같은 입력자·계정 방향 전표 ' + str(len(jids)) + '건')
    applied = []
    for code, (name, condition, followup) in RULES.items():
        n = sum(r['규칙ID'] == code for r in found)
        u = len(unknown[code])
        applied.append({'규칙ID': code, '규칙버전': VERSION, '규칙명': name, '상태': '검토후보' if n else '미확인' if u else '조건해당없음',
                        '검사대상수': len(tested[code]), '후보수': n, '미확인수': u, '미확인전표': ';'.join(sorted(unknown[code])),
                        '조건': condition, '설정': cfg, '후속절차': followup})
        if u:
            issue(issues, 'FIA_UNCONFIRMED', code + ': 제출자료 부족으로 ' + str(u) + '전표를 미확인으로 유지', '전표메타 / 규칙적용', False)
    absent = [r for r in meta_rows if r['부서'] in (None, '미확인') or r['원천시스템'] in (None, '미확인')]
    output['검토후보'] = found
    output['규칙적용'] = applied
    metrics.update({'검토후보수': len(found), '미확인규칙수': sum(bool(unknown[c]) for c in RULES), '메타추가미확인행수': len(absent)})
    detail['분석완료'] = True
    return finish()


def write_samples(target):
    from .samples import write_samples as write
    return write(target)
