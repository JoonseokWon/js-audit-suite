"""Explicit human choices and selected-source/run identity checks."""
from copy import deepcopy
from common import AuditError, digest
from human_input import text
from audit_workflow import payload, strings
from .state import context

ASSERTIONS = {
    '거래': ('발생사실', '완전성', '정확성', '기간귀속', '분류', '표시'),
    '잔액': ('실재성', '권리와 의무', '완전성', '정확성·평가·배분', '분류', '표시'),
    '공시': ('발생사실·권리와 의무', '완전성', '분류·이해가능성', '정확성·평가', '표시'),
}
RATINGS = ('', '낮음', '보통', '높음')


def optional(value, label):
    return '' if value in ('', None) else text(value, label)


def assertions(value):
    if not isinstance(value, list) or not value or len(value) > 40:
        raise AuditError('경영진주장을 거래·잔액·공시 구분과 함께 선택하세요.')
    out = []
    for item in value:
        item = payload(item, ('category', 'assertion', 'risk_assertion'), ('category', 'assertion'))
        if item['category'] not in ASSERTIONS or item['assertion'] not in ASSERTIONS[item['category']]:
            raise AuditError('지원하는 경영진주장 분류를 사람이 선택하세요.')
        item['risk_assertion'] = text(item.get('risk_assertion') or item['assertion'], '기존 위험의 주장')
        if item in out:
            raise AuditError('경영진주장 중복')
        out.append(item)
    return out


def source_selections(ws, value):
    if not isinstance(value, list) or not value or len(value) > 100:
        raise AuditError('관련 원본을 선택하고 회사·기간·위치·관련성을 기록하세요.')
    out = []; seen = set(); expected = context(ws)
    for raw in value:
        item = payload(raw, ('source_id', 'company_code', 'start_date', 'end_date', 'locator', 'relevance'),
                       ('source_id', 'company_code', 'start_date', 'end_date', 'locator', 'relevance'))
        sid = text(item['source_id'], '자료ID')
        if sid not in ws.sources or sid in seen:
            raise AuditError('다른 업무 자료ID 또는 중복 원본 선택')
        seen.add(sid)
        for key in ('company_code', 'start_date', 'end_date', 'locator', 'relevance'):
            item[key] = optional(item[key], key)
        for key, original in (('company_code', '회사코드'), ('start_date', '시작일'), ('end_date', '기준일')):
            if item[key] and item[key] != expected[original]:
                raise AuditError('선택 원본의 회사·기간이 현재 업무와 다릅니다.')
        item['sha256'] = ws.sources[sid]['sha256']; out.append(item)
    return out


def run_selections(ws, ids, pid, source_ids):
    ids = strings(ids, '실행ID', allow_empty=True)
    module = ws.procedure_module(pid)
    allowed = {'원장·리드'} | ({module} if module else set())
    out = []
    for rid in ids:
        run = ws.runs.get(rid)
        if not run or run['module'] not in allowed or run['source_id'] not in source_ids:
            raise AuditError('다른 절차·원본의 실행 또는 없는 실행ID')
        if ws.latest().get(run['module'], {}).get('id') != rid:
            raise AuditError('이전 실행 대신 현재 모듈의 최신 실행을 선택하세요.')
        if run.get('cancelled') or run['result'].get('blocking'):
            raise AuditError('차단·취소 실행은 미확인 상태입니다. 대응 근거로 확정할 수 없습니다.')
        actual = run['result'].get('context', {})
        if actual != context(ws):
            raise AuditError('검사 결과 회사·기간이 현재 업무와 다릅니다.')
        if digest(run['result']) != run['result_hash']:
            raise AuditError('검사 결과 해시 불일치')
        out.append({'run_id': rid, 'module': run['module'], 'source_id': run['source_id'],
                    'source_hash': ws.sources[run['source_id']]['sha256'], 'result_hash': run['result_hash']})
    return deepcopy(out)


def current_plan(ws, rid, pid=None):
    risk = ws.workflow_risks.get(rid)
    if not risk:
        raise AuditError('현재 등록 위험ID가 없습니다. 기존 감사계획에서 위험을 먼저 등록하세요.')
    if risk['basis'] != ws.data_basis():
        raise AuditError('위험평가의 자료·실행이 변경되었습니다. 기존 위험평가를 먼저 갱신하세요.')
    if pid is not None:
        link = ws.workflow_procedure_links.get(pid)
        selected = {s['procedure_id'] for s in ws.workflow_profile['scope'] if s['applicable']}
        if pid not in selected or pid not in risk['procedure_ids'] or not link or rid not in link['risk_ids']:
            raise AuditError('등록 위험과 현재 적용 절차의 대응 관계가 없습니다.')
        if link['basis'] != ws.data_basis():
            raise AuditError('기존 대응절차의 자료·실행이 변경되었습니다. 계획을 갱신하세요.')
        return risk, link
    return risk
