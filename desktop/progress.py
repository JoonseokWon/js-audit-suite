"""Read-only process guidance. Saved records never certify an audit opinion."""
from pathlib import Path

STAGES = (
    ('company', '회사·업무 선택', '회사를 선택하거나 저장된 감사 업무를 여세요.', '업무 요약'),
    ('plan', '감사계획 수립', '감사체계·중요성과 적용할 절차·범위를 기록하세요.', '계획·절차·취합'),
    ('data', '자료 등록·검사', '필요한 자료를 등록하고 해당 검사를 실행하세요.', '자료·검사'),
    ('correction', '자료 오류 보완', '입력 오류와 원본 누락을 보완한 뒤 다시 검사하세요.', '자료·검사'),
    ('reconcile', '원장 대사', '원장 통제값과 계정별 계산값을 비교하고 차이를 조사하세요.', '원장·리드'),
    ('risk', '위험평가·절차 설계', '자료를 바탕으로 위험을 평가하고 감사절차·증거를 연결하세요.', '계획·절차·취합'),
    ('workpaper', '감사조서 작성', '실제 수행내용·일자·증거와 판단·결론을 기록하세요.', '절차·조서'),
    ('review', '감사조서 검토', '현재 자료의 조서와 AI 적용내용을 검토하고 요청·의견을 정리하세요.', '절차·조서'),
    ('archive', '감사파일 보관', '검토를 마친 기록을 보관 파일로 저장하고 파일을 확인하세요.', '계획·절차·취합'),
)
PLAN_CODES = {
    'LEGACY_F01_UNCLASSIFIED', 'SCOPE_EMPTY', 'SCOPE_ID_STALE', 'REQUIRED_SCOPE_MISSING',
    'RISK_STALE', 'RISK_EVIDENCE_MISSING', 'RISK_PROCEDURE_ORPHAN', 'RISK_LINK_MISSING',
    'PROCEDURE_PLAN_MISSING', 'PROCEDURE_PLAN_STALE', 'PROCEDURE_RISK_ORPHAN',
    'PROCEDURE_LINK_ORPHAN', 'PROCEDURE_EVIDENCE_MISSING', 'SELECTED_PROCEDURE_EXCLUDED',
}
WRITE_FIELDS = ('purpose', 'risk', 'scope', 'performed', 'conclusion', 'performed_date', 'preparer')


def _written(record, required):
    if not record or record.get('current_state') == '자료변경·재검토':
        return False
    if record.get('excluded'):
        return not required and bool(record.get('excluded_reason')) and bool(record.get('preparer'))
    return (all(str(record.get(key, '')).strip() for key in WRITE_FIELDS)
            and bool(record.get('evidence_ids')) and record.get('current_state') != '검토의견')


def summarize_progress(state):
    """Derive current/next stages from normalized values without mutating state."""
    state = state or {}
    has_company = bool(state.get('has_workspace'))
    latest = state.get('latest', {})
    workflow = state.get('workflow', {})
    codes = {row['code'] for row in workflow.get('blockers', [])}
    profile = workflow.get('profile') or {}
    selected = {row['procedure_id'] for row in profile.get('scope', []) if row.get('applicable')}
    required = set(state.get('required', [])) | selected
    procedures = state.get('procedures', {})
    risks = {row['id']: row for row in workflow.get('risks', [])}
    links = {row['procedure_id']: row for row in workflow.get('procedure_links', [])}
    has_data = has_company and bool(state.get('source_count')) and bool(latest)
    plan_ready = (bool(workflow.get('active')) and bool(profile.get('materiality')) and bool(selected)
                  and not (codes & {'LEGACY_F01_UNCLASSIFIED', 'SCOPE_EMPTY', 'SCOPE_ID_STALE',
                                    'REQUIRED_SCOPE_MISSING'}))
    data_ready = has_data and 'MODULE_NOT_EXECUTED' not in codes
    errors = bool(state.get('source_errors')) or any(
        run.get('result', {}).get('blocking') or run.get('cancelled') for run in latest.values())
    errors = errors or bool(codes & {'SOURCE_INTEGRITY', 'RUN_BLOCKED'})
    ledger = latest.get('원장·리드')
    cross = state.get('cross', [])
    reconciled = bool(ledger) and not ledger.get('result', {}).get('blocking') and all(
        row.get('상태') == '일치' or (row.get('상태') == '차이' and row.get('review_recorded'))
        for row in cross)
    planned = plan_ready and bool(risks) and not (codes & PLAN_CODES)
    for pid in selected:
        link = links.get(pid, {})
        planned = planned and bool(link.get('risk_ids')) and bool(link.get('evidence_ids'))
        planned = planned and all(rid in risks and pid in risks[rid].get('procedure_ids', [])
                                  for rid in link.get('risk_ids', []))
    considered = required | set(procedures)
    written = bool(considered) and all(_written(procedures.get(pid), pid in required) for pid in considered)
    written = written and not (codes & {'WORKPAPER_MISSING', 'WORKPAPER_EVIDENCE_MISMATCH'})
    written = written and all(all(links.get(pid, {}).get(key) for key in
                                 ('performed', 'performed_date', 'performer')) for pid in selected)
    reviewed = written and all(
        record.get('current_state') == '검토기록완료'
        and (not record.get('ai_required') or record.get('ai_approved'))
        for record in procedures.values())
    reviewed = reviewed and all(row.get('state') in ('검토완료', '취소') for row in state.get('requests', []))
    reviewed = reviewed and all(row.get('resolved') for row in state.get('notes', []))
    reviewed = reviewed and not (codes & {'WORKPAPER_REVIEW_PENDING', 'UNSELECTED_WORKPAPER_REVIEW_PENDING',
                                        'AI_APPROVAL_PENDING', 'REQUEST_PENDING', 'REVIEW_NOTE_PENDING'})
    ready_to_archive = all((data_ready, not errors, reconciled, planned, written, reviewed))
    archived = (ready_to_archive and workflow.get('locked') and not workflow.get('blockers')
                and bool(state.get('archive_matches_current')))
    completed = dict(company=has_company, plan=plan_ready, data=data_ready, correction=has_data and not errors,
                     reconcile=reconciled, risk=planned, workpaper=written, review=reviewed, archive=archived)
    stages = [dict(id=key, title=title, description=description, route=route,
                   complete=bool(completed[key]), applicable=key != 'correction' or bool(errors))
              for key, title, description, route in STAGES]
    if not state.get('source_count') and has_company:
        next(row for row in stages if row['id'] == 'data')['description'] = '감사할 회사·기간의 원장과 명세서 등 필요한 자료를 등록하세요.'
    pending = [stage for stage in stages if stage['applicable'] and not stage['complete']]
    current = pending[0] if pending else dict(
        id='confirmed', title='보관 파일 확인', route='계획·절차·취합',
        description='현재 자료 버전의 보관 파일을 확인했어요. 감사완료 판단은 검토자가 확인해요.')
    return {'current': current, 'next_steps': pending[:3], 'stages': stages,
            'scope': '저장된 자료·수행·검토 기록을 기준으로 안내해요. 실제 감사완료 판단은 별도예요.'}


def workspace_progress(ws, last_archive=None):
    """Read existing workspace APIs; do not save, approve, lock or create files."""
    if ws is None:
        return summarize_progress(None)
    from common import digest
    workflow = ws.workflow_status()
    latest = ws.latest()
    procedures = {}
    for pid, record in ws.procedures.items():
        ai = ws.ai_status(pid)
        procedures[pid] = dict(record, current_state=ws.procedure_state(record),
                               ai_required=ai.get('required', False), ai_approved=ai.get('approved', False))
    cross = []
    for row in ws.cross_checks():
        record = procedures.get('B-' + digest(row)[:16], {})
        reviewed = (_written(record, True) and record.get('current_state') == '검토기록완료'
                    and (not record.get('ai_required') or record.get('ai_approved')))
        cross.append(dict(row, review_recorded=bool(reviewed)))
    archive = last_archive or {}
    archived_head = archive.get('head') or {}
    matches = (archive.get('valid') is True and archive.get('mode') == 'final'
               and archive.get('manifest', {}).get('engagement_id') == ws.engagement['id']
               and isinstance(archived_head, dict) and archived_head.get('hash') == ws.head
               and archive.get('basis') == ws.basis() and bool(archive.get('path'))
               and Path(archive['path']).is_file())
    return summarize_progress({
        'has_workspace': True, 'source_count': len(ws.sources), 'latest': latest,
        'workflow': workflow, 'procedures': procedures, 'required': ws.required_procedures(),
        'cross': cross, 'requests': list(ws.requests.values()), 'notes': list(ws.notes.values()),
        'source_errors': False if workflow.get('active') else bool(ws.verify_sources()),
        'archive_matches_current': matches,
    })
