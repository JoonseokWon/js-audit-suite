"""Compose new human-led registers without changing legacy workspace bases."""
from common import digest


def basis_parts(ws):
    import audit_links,misstatements
    values={'audit_links':audit_links.basis(ws),'misstatements':misstatements.basis(ws)}
    return {key:value for key,value in values.items() if value is not None}


def required_procedures(ws):
    import audit_links
    from misstatements.state import state
    result={'F03'} if state(ws)['records'] else set()
    links=audit_links.refresh(ws)
    result.update(r['procedure_id'] for r in links['responses'].values())
    return result


def snapshots(ws):
    import audit_links,misstatements
    return {'audit_links':audit_links.snapshot(ws),'misstatements':misstatements.snapshot_rows(ws)}


def workflow_rows(ws):
    import audit_links,misstatements
    rows=[]
    for namespace,state in (('MS',misstatements.status(ws)),('LINK',audit_links.status(ws))):
        if not state['active']:continue
        for item in state['blockers']:
            rows.append({'code':namespace+'_'+item['code'],'procedure_id':item.get('procedure_id',''),
                'risk_id':item.get('risk_id',''),'status':'사람입력대기','message':item['message'],
                'record_id':item.get('record_id',item.get('response_id',''))})
    return rows


def public_summary(ws):
    """Read-only progress counts; never an audit completion or approval flag."""
    import audit_links,misstatements
    links=audit_links.status(ws);ms=misstatements.status(ws)
    return {'위험연결활성':links['active'],'위험연결보완':len(links['blockers']),
            '왜곡표시집계활성':ms['active'],'왜곡표시보완':len(ms['blockers']),
            '범위':'현재 입력·연결 상태이며 실제 감사완료·감사의견이 아닙니다.'}
