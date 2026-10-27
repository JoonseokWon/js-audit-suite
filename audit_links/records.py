"""Human-entered assessments/responses/performance; no inferred decisions."""
from copy import deepcopy
import uuid
from common import AuditError, digest, now, day
from audit_workflow import payload
from human_input import text
from .state import refresh, pin
from .validation import assertions, optional, RATINGS, current_plan, source_selections, run_selections


def _begin(ws, expected_head):
    before = ws.assert_writeable(expected_head=expected_head)
    refresh(ws)
    if ws.verify_sources():
        raise AuditError('등록 원본 사본의 변경·누락을 먼저 해결하세요.')
    return before


def _write(ws, kind, record, actor, before):
    record.update(actor=text(actor, '기록자'), at=now(), revision=uuid.uuid4().hex)
    ws._append(kind, record, expected_head=before); ws.refresh(); refresh(ws)
    return deepcopy(record)


def save_assessment(ws, value, actor, *, expected_head=None):
    before = _begin(ws, expected_head)
    keys = ('risk_id', 'assertions', 'inherent_rating', 'inherent_reason', 'control_rating',
            'control_reason', 'significant_risk', 'significant_reason')
    record = payload(value, keys, keys); rid = text(record['risk_id'], '위험ID')
    risk = current_plan(ws, rid); record['assertions'] = assertions(record['assertions'])
    if any(item['risk_assertion'] not in risk['assertions'] for item in record['assertions']):
        raise AuditError('분류한 주장은 기존 위험에 사람이 등록한 주장과 일치해야 합니다.')
    for key in ('inherent_rating', 'control_rating'):
        if record[key] not in RATINGS:
            raise AuditError('고유위험·통제위험은 사람이 등급을 선택하거나 미확인으로 두세요.')
    if record['significant_risk'] is not None and type(record['significant_risk']) is not bool:
        raise AuditError('유의적위험은 사람 선택 True/False 또는 미확인 None만 허용합니다.')
    for key in ('inherent_reason', 'control_reason', 'significant_reason'):
        record[key] = optional(record[key], key)
    record.update(id=rid, risk_id=rid, pin=pin(ws), risk_hash=digest(risk))
    return _write(ws, 'audit_link_assessment', record, actor, before)


def save_response(ws, value, actor, *, expected_head=None):
    before = _begin(ws, expected_head)
    keys = ('id', 'risk_id', 'procedure_id', 'assertions', 'nature', 'timing', 'extent', 'sources', 'run_ids')
    record = payload(value, keys, set(keys)-{'id'})
    rid, pid = text(record['risk_id'], '위험ID'), text(record['procedure_id'], '절차ID')
    risk, link = current_plan(ws, rid, pid)
    assessment = ws.audit_links_state['assessments'].get(rid)
    if not assessment or assessment['pin'] != pin(ws) or assessment['risk_hash'] != digest(risk):
        raise AuditError('현재 자료·위험 기준의 구조화 위험평가를 먼저 저장하세요.')
    record['assertions'] = assertions(record['assertions'])
    if any(item not in assessment['assertions'] for item in record['assertions']):
        raise AuditError('대응절차 주장은 현재 위험평가의 분류된 주장 중에서 선택하세요.')
    identifier = text(record.get('id') or uuid.uuid4().hex, '대응ID')
    previous = ws.audit_links_state['responses'].get(identifier)
    if previous and (previous['risk_id'], previous['procedure_id']) != (rid, pid):
        raise AuditError('기존 대응ID를 다른 위험·절차에 전용할 수 없습니다.')
    for key in ('nature', 'timing', 'extent'):
        record[key] = text(record[key], key)
    record['sources'] = source_selections(ws, record['sources'])
    record['runs'] = run_selections(ws, record.pop('run_ids'), pid,
                                    {item['source_id'] for item in record['sources']})
    record.update(id=text(identifier, '대응ID'), risk_id=rid, procedure_id=pid, pin=pin(ws),
                  risk_hash=digest(risk), workflow_link_hash=digest(link),
                  assessment_revision=assessment['revision'])
    return _write(ws, 'audit_link_response', record, actor, before)


def require_response(ws, response_id):
    from .status import response_issues
    response = ws.audit_links_state['responses'].get(response_id)
    if not response:
        raise AuditError('등록 대응ID가 없습니다.')
    issues = response_issues(ws, response, ws.audit_links_state)
    if issues:
        raise AuditError('대응 근거 미확인·변경: ' + ' / '.join(item[1] for item in issues[:4]))
    return response


def save_performance(ws, value, actor, *, expected_head=None):
    before = _begin(ws, expected_head)
    keys = ('response_id', 'performed', 'performed_date', 'performer', 'sufficiency', 'sufficiency_reason')
    record = payload(value, keys, keys)
    record['response_id'] = text(record['response_id'], '대응ID')
    response = require_response(ws, record['response_id'])
    for key in ('performed', 'performed_date', 'performer', 'sufficiency_reason'):
        record[key] = optional(record[key], key)
    if record['performed_date']:
        record['performed_date'] = day(record['performed_date']).isoformat()
    if record['sufficiency'] not in ('', '충분', '추가절차필요', '판단보류'):
        raise AuditError('증거 충분성은 사람이 선택하거나 미확인으로 두세요.')
    record.update(id=uuid.uuid4().hex, response_revision=response['revision'], pin=pin(ws))
    return _write(ws, 'audit_link_performance', record, actor, before)


def retire(ws, collection, record_id, actor, reason, *, expected_head=None):
    before = _begin(ws, expected_head)
    if collection not in ('assessments', 'responses', 'performances', 'workpapers'):
        raise AuditError('해제할 연결기록 종류 오류')
    previous = ws.audit_links_state[collection].get(record_id)
    if not previous:
        raise AuditError('사용 중인 연결기록ID가 아닙니다.')
    record = {'id': uuid.uuid4().hex, 'collection': collection, 'record_id': record_id,
              'reason': text(reason, '사용 해제 사유'), 'previous_record': deepcopy(previous)}
    return _write(ws, 'audit_link_retire', record, actor, before)
