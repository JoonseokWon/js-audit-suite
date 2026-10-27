"""Batch outcomes describe actual completed, cancelled, failed and unstarted work."""


def run_batch(ws,items,cancel,emit):
    state={'requested':len(items),'started':0,'completed':0,'saved_runs':0,'blocking_runs':0,
           'blocking_issues':0,'review_issues':0,'failed':0,'cancelled':False,'error':''}
    try:
        for module,path in items:
            if cancel.is_set():state['cancelled']=True;break
            state['started']+=1;emit('status',module+' 검사 중')
            run=ws.execute(module,path,cancel);state['saved_runs']+=1;emit('run',run)
            if run.get('cancelled') or run.get('result',{}).get('cancelled'):
                state['cancelled']=True;break
            state['completed']+=1
            result=run['result'];state['blocking_runs']+=int(bool(result.get('blocking')))
            state['blocking_issues']+=result.get('blocking',0);state['review_issues']+=result.get('review',0)
        if cancel.is_set():state['cancelled']=True
    except Exception as exc:
        from common import AuditError
        state['error']=str(exc)
        state['cancelled']=cancel.is_set()
        expected_cancel=(state['cancelled'] and isinstance(exc,AuditError)
                         and str(exc)=='사용자가 취소했습니다. 결과는 저장하지 않았습니다.')
        if not expected_cancel:state['failed']=1
    state['unstarted']=state['requested']-state['started']
    state['interrupted']=state['started']-state['completed']-state['failed']
    emit('batch_done',state)
    return state


def batch_message(state):
    if state['failed'] and state['cancelled']:title='취소 요청 중 검사 실패'
    elif state['cancelled'] and state['requested'] and state['completed']==state['requested']:title='자동검사 종료 후 취소 요청'
    elif state['cancelled']:
        title='실행 전 취소' if state['started']==0 else '일부 검사 후 취소' if state['completed'] else '검사 중 취소'
    elif state['failed']:title='검사 실패'
    elif state['requested']==0:title='실행할 검사 없음'
    elif state['blocking_runs']:title='자동검사 종료 · 차단 항목 있음'
    else:title='자동검사 종료'
    message=(f"{title}. 완료 {state['completed']}/{state['requested']}개, 실패 {state['failed']}개, "
             f"중단 {state['interrupted']}개, 미실행 {state['unstarted']}개. "
             f"차단 있는 검사 {state['blocking_runs']}개(항목 {state['blocking_issues']}개), 검토 {state['review_issues']}개.")
    if state['error']:message+=' 원인: '+state['error']
    return message+' 실제 증거 확인·판단·승인·검토는 별도로 진행하세요.'
