"""Append-only projections; reading candidates/status never changes an engagement."""
from copy import deepcopy
from common import digest

KINDS = {'audit_link_assessment', 'audit_link_response', 'audit_link_performance',
         'audit_link_workpaper', 'audit_link_retire'}
PLANNING = KINDS - {'audit_link_workpaper'}
SCOPE = ('사람이 선택한 위험·주장·대응·수행·조서 연결의 기계적 점검입니다. '
         '파일·결과 해시 일치가 실제 수행이나 증거의 충분성·적합성, 감사완료를 뜻하지 않습니다.')


def refresh(ws):
    state = {'assessments': {}, 'responses': {}, 'performances': {}, 'workpapers': {}}
    mapping = {'audit_link_assessment': 'assessments', 'audit_link_response': 'responses',
               'audit_link_performance': 'performances', 'audit_link_workpaper': 'workpapers'}
    for event in ws.events:
        kind, data = event['kind'], event['data']
        if kind in mapping:
            state[mapping[kind]][data['id']] = deepcopy(data)
        elif kind == 'audit_link_retire':
            state[data['collection']].pop(data['record_id'], None)
    ws.audit_links_state = state
    return state


def basis(ws):
    state = refresh(ws)
    history = [event for event in ws.events if event['kind'] in PLANNING]
    if not history:
        return None
    return {'schema': 'audit-links-1', 'history_hash': digest(history),
            **{key: deepcopy(value) for key, value in state.items() if key != 'workpapers'}}


def context(ws):
    return {key: ws.engagement[key] for key in ('회사코드', '시작일', '기준일')}


def pin(ws):
    # Do not use ws.basis(): that includes our own event and would stale itself.
    from audit_workflow import workflow_basis
    return {'data_basis': ws.data_basis(), 'workflow_hash': digest(workflow_basis(ws)),
            'context': context(ws)}


def workpaper_hash(record):
    # Review bookkeeping is separate; a textual edit creates a new edit_revision.
    excluded = {'state', 'reviewer', 'reviewed_at', 'review_note', 'updated_at'}
    return digest({key: value for key, value in record.items() if key not in excluded})


def latest_performance(state, response_id):
    return next((value for value in reversed(list(state['performances'].values()))
                 if value['response_id'] == response_id), None)


def latest_binding(state, response_id):
    return next((value for value in reversed(list(state['workpapers'].values()))
                 if value['response_id'] == response_id), None)
