"""Read-only snapshots, small packet references and export rows for common integration."""
from copy import deepcopy
from .state import refresh, SCOPE
from .status import status


def snapshot(ws):
    return status(ws)


def packet(ws, pid):
    state = refresh(ws)
    responses = [r for r in state['responses'].values() if r['procedure_id'] == pid]
    risk_ids = {r['risk_id'] for r in responses}
    risk_ids.update(rid for rid, r in ws.workflow_risks.items() if pid in r['procedure_ids'])
    response_ids = {r['id'] for r in responses}; references = []
    for kind, records in (
        ('human_assertion_risk_assessment', [a for rid, a in state['assessments'].items() if rid in risk_ids]),
        ('human_risk_response', responses),
        ('human_actual_performance', [p for p in state['performances'].values() if p['response_id'] in response_ids]),
        ('human_workpaper_connection', [b for b in state['workpapers'].values() if b['response_id'] in response_ids])):
        for record in records:
            references.append({'kind': kind, 'data': deepcopy(record), 'procedure_id': pid,
                               'human_record_only': True})
    state_status = status(ws)
    relevant = [row for row in state_status['rows'] if row['procedure_id'] == pid or
                (row['risk_id'] in risk_ids and not row['procedure_id'])]
    return {'active': state_status['active'], 'scope': SCOPE, 'references': references,
            'rows': relevant, 'blockers': [r for r in relevant if not r['ok']]}


def snapshot_rows(ws):
    result = status(ws)
    return [{'위험ID': r['risk_id'], '절차ID': r['procedure_id'], '대응ID': r['response_id'],
             '상태': r['status'], '점검코드': r['code'], '내용': r['message']} for r in result['rows']]


def candidates(ws):
    """Only identifiers/source hashes; no automatic choices, assessments or approvals."""
    refresh(ws)
    return {'risks': deepcopy(list(ws.workflow_risks.values())),
            'procedure_links': deepcopy(list(ws.workflow_procedure_links.values())),
            'sources': [{'source_id': s['id'], 'name': s['name'], 'sha256': s['sha256']} for s in ws.sources.values()],
            'runs': [{'run_id': r['id'], 'module': r['module'], 'source_id': r['source_id'],
                      'result_hash': r['result_hash'], 'blocking': r['result']['blocking'],
                      'cancelled': r.get('cancelled', False)} for r in ws.latest().values()],
            'scope': '선택 후보만 표시합니다. 관련 회사·기간·주장·절차는 사람이 확인해야 합니다.'}
