"""Read-only case progress; never infer audit performance or sign-off."""
from .definition import TARGET_PID
from .manifest import load_manifest


def case_status(ws):
    from ai_workpapers import procedure_fingerprint
    ws.refresh();manifest = load_manifest(ws.root);latest = ws.latest()
    counts = {k:sum(r['result'].get(k,0) for r in latest.values()) for k in ('blocking','review')}
    ai = ws.ai_status(TARGET_PID);procedure = ws.procedures.get(TARGET_PID,{})
    drafts = [d for d in ws.ai_drafts.values() if d['procedure_id']==TARGET_PID]
    fingerprint = procedure_fingerprint(ws,TARGET_PID)
    applied_id = procedure.get('ai_draft_id')
    current_drafts = [d for d in drafts if d['basis']==ws.basis()
        and (d['id']==applied_id or d['packet']['procedure']['fingerprint']==fingerprint)]
    stages = [dict(s,state='직접 확인 필요') for s in manifest['steps']]
    stages[0]['state'] = '프로그램 검사 기록 있음' if all(m in latest for m in ('원장·리드','매출')) else '자료 검사 필요'
    stages[1]['state'] = '예외 '+str(counts['blocking'])+'개·검토 '+str(counts['review'])+'개' if any(counts.values()) else '현재 계산 차이 없음·사람 검토 필요'
    stages[2]['state'] = ('현재 근거 초안 '+str(len(current_drafts))+'개') if current_drafts else ('이전 근거 초안만 있음·다시 생성 필요' if drafts else '초안 미생성')
    stages[3]['state'] = '적용 내용 있음·수정은 사람이 확인' if ai['required'] else '초안 미적용'
    stages[4]['state'] = ai['state']+' / 별도 검토 '+(procedure.get('state') or '미착수')
    stages[5]['state'] = '현재 작성 상태로 Excel 초안 저장 가능·전체 감사완료 아님'
    applied = ws.ai_drafts.get(procedure.get('ai_draft_id'))
    needs_rerun = bool(procedure and (procedure.get('basis')!=ws.basis()
        or ai['required'] and (not applied or applied.get('basis')!=ws.basis()))
        or drafts and not current_drafts)
    if needs_rerun:next_step = '자료·실행이 변경됐습니다. 현재 근거로 AI 초안을 다시 생성하고 내용을 확인하세요.'
    elif not current_drafts:next_step = '오류와 근거를 확인한 뒤 A04에서 로컬 AI 초안을 생성하세요.'
    elif not ai['required']:next_step = '저장된 초안을 읽고 적용한 뒤 사람이 수정·저장하세요.'
    elif not ai['approved']:next_step = '저장한 문장·근거·예외를 확인한 사람이 내용 승인 기록을 직접 입력하세요.'
    else:next_step = '현재 승인 범위와 별도 검토 상태를 확인하고 Excel 초안을 저장하세요.'
    return dict(target_pid=TARGET_PID, stages=stages, next_step=next_step,
        ai_state=ai, needs_rerun=needs_rerun, **counts,
        human_approval_scope='이 상태 안내는 실제 감사수행·판단·승인을 대신하지 않음')
