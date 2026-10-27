"""Link already recorded performance to its own current workpaper, without basis cycles."""
from common import AuditError, digest
from audit_workflow import payload, strings
from human_input import text
from .state import latest_performance, workpaper_hash
from .records import _begin, _write, require_response
import uuid


def bind_workpaper(ws, response_id, value, actor, *, expected_head=None):
    before = _begin(ws, expected_head)
    response = require_response(ws, text(response_id, '대응ID'))
    keys = ('workpaper_id', 'note_ids', 'f03_id', 'misstatement_ids')
    record = payload(value, keys, keys)
    pid = record['workpaper_id']
    if pid != response['procedure_id']:
        raise AuditError('다른 절차 조서를 이 대응의 수행 조서로 연결할 수 없습니다.')
    paper = ws.procedures.get(pid)
    if not paper or paper.get('excluded') or paper.get('basis') != ws.basis():
        raise AuditError('현재 자료·위험·수행기록 기준으로 저장한 적용 조서가 필요합니다.')
    performance = latest_performance(ws.audit_links_state, response_id)
    if not performance or performance['response_revision'] != response['revision']:
        raise AuditError('현재 대응의 사람 실제 수행기록을 먼저 저장하세요.')
    if not all(performance.get(key) for key in ('performed', 'performed_date', 'performer')):
        raise AuditError('실제 수행내용·일자·수행자는 사람이 기록해야 합니다.')
    required_sources = {item['source_id'] for item in response['sources']}
    if not required_sources <= set(paper.get('evidence_ids', [])):
        raise AuditError('선택 원본이 대응절차 조서의 증거에 모두 연결되지 않았습니다.')
    record['note_ids'] = strings(record['note_ids'], '검토의견ID', allow_empty=True)
    if any(identifier not in ws.notes for identifier in record['note_ids']):
        raise AuditError('없는 검토의견ID')
    record['f03_hash'] = ''
    if record['f03_id']:
        f03 = ws.procedures.get('F03')
        if record['f03_id'] != 'F03' or not f03 or f03.get('excluded') or f03.get('basis') != ws.basis():
            raise AuditError('현재 업무·자료 기준의 F03 조서만 연결하세요.')
        record['f03_hash'] = workpaper_hash(f03)
    record['misstatement_ids'] = strings(record['misstatement_ids'], '왜곡표시ID', allow_empty=True)
    record['misstatement_revisions'] = {}
    if record['misstatement_ids']:
        from misstatements import get_record, record_status
        for identifier in record['misstatement_ids']:
            item = get_record(ws, identifier)
            if pid not in item.get('procedure_ids', []) or not record_status(ws, identifier)['current']:
                raise AuditError('다른 절차 또는 현재 근거가 아닌 왜곡표시 연결')
            record['misstatement_revisions'][identifier] = item['revision']
        if not record['f03_id']:
            raise AuditError('왜곡표시를 연결할 때 현재 F03 조서도 선택하세요.')
    record.update(id=uuid.uuid4().hex, response_id=response_id, response_revision=response['revision'],
                  performance_revision=performance['revision'], paper_hash=workpaper_hash(paper),
                  edit_revision=paper.get('edit_revision'), note_hashes={key: digest(ws.notes[key]) for key in record['note_ids']})
    return _write(ws, 'audit_link_workpaper', record, actor, before)
