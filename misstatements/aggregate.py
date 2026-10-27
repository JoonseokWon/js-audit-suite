"""Gross, human-grouped registers; no cross-error netting or trivial deletion."""
from collections import defaultdict
from copy import deepcopy
from common import digest
from .state import state, current
from .groups import group_current
from .verification import verification_state


def _record_status(ws,record,replay):
    missing=[]
    if not current(ws,record,replay):missing.append('자료·중요성 변경 후 명시적 재확인')
    if record['assessment'] in ('','검토중'):missing.append('차이의 왜곡표시 해당 여부 판단')
    if not record['judgment']:missing.append('사람의 원인·회계처리 판단 근거')
    if not record['evidence_ids']:missing.append('원본 증거 연결')
    if not {ref['source_id'] for ref in record['run_refs']}<=set(record['evidence_ids']):
        missing.append('연결된 계산·원장 실행의 원본 증거')
    if 'F03' not in record['procedure_ids']:missing.append('F03 왜곡표시 집계조서 연결')
    if record['assessment']=='왜곡표시':
        for field,label in (('classification','사실/판단/추정투영 분류'),
                            ('correction_state','수정/미수정'),('company_position','회사 확인·이견'),
                            ('period','기초/당기'),('qualitative','정성적 중요성 검토')):
            if record[field] in ('','미분류','검토중'):missing.append(label)
        if record['amount'] is None:missing.append('사람이 확인한 왜곡표시 금액')
        if not record['account_impacts']:missing.append('재무제표 계정별 영향')
        if record['tax_effect'] is None or not record['tax_basis']:missing.append('세효과 금액(0 포함)·검토 근거')
        if record['qualitative']=='있음' and not record['qualitative_note']:missing.append('정성적 중요성 사유')
        if record['company_position']=='이견있음' and not record['company_note']:missing.append('회사 이견 내용')
        if record['classification']=='추정투영' and not record['projection_basis']:missing.append('추정·투영 방법과 모집단 근거')
        if record['correction_state']=='수정':
            if record['company_position']!='수용':missing.append('회사 수정 수용 기록')
            if verification_state(ws,record,replay)!='선택GL변동일치':missing.append('실제 GL 수정 반영 대사')
    return {'id':record['id'],'current':current(ws,record,replay),'assessment':record['assessment'],
            'correction_state':record['correction_state'],
            'verification_state':verification_state(ws,record,replay),
            'missing':missing,'complete':not missing,'procedure_id':'F03'}


def record_status(ws,record_id):
    from common import AuditError
    replay=state(ws)
    if record_id not in replay['records']:raise AuditError('없는 왜곡표시 검토기록 ID')
    return _record_status(ws,replay['records'][record_id],replay)


def snapshot_rows(ws):
    replay=state(ws);membership={};group_rows=[];group_problems=[]
    for group in replay['groups'].values():
        if not group.get('active',True):
            group_rows.append({**deepcopy(group),'current':False,'aggregation_confirmed':False})
            continue
        fresh=group_current(ws,group,replay)
        records=[replay['records'][key] for key in group['member_ids']]
        consistent=len({(r['assessment'],r['period'],r['correction_state']) for r in records})==1
        usable=fresh and consistent
        for key in group['member_ids']:membership[key]=(group,usable)
        group_rows.append({**deepcopy(group),'current':fresh,'aggregation_confirmed':usable})
        if not usable:group_problems.append({'code':'MS_GROUP_RECONFIRM','record_id':group['id'],
                                           'message':'회원기록·자료 변경 또는 기간·수정상태가 상충합니다. 동일오류 그룹을 다시 판단하세요.'})
    materiality=(ws.workflow_profile or {}).get('materiality',{})
    trivial=materiality.get('clearly_trivial_threshold');register=[];impacts=[];totals=defaultdict(lambda:defaultdict(int))
    for record in replay['records'].values():
        status=_record_status(ws,record,replay);member=membership.get(record['id'])
        counted=record['assessment']=='왜곡표시' and record['amount'] is not None
        group_id=member[0]['id'] if member else ''
        if member and member[1] and member[0]['primary_id']!=record['id']:counted=False
        amount=record['amount'];tax=record['tax_effect']
        row={**deepcopy(record),**status,'group_id':group_id,'counted':counted,
             'below_trivial':bool(amount is not None and trivial is not None and abs(amount)<trivial),
             'trivial_policy':'사소기준 이하도 보존. 자동 제외하지 않으며 정성적 중요성은 별도 판단.',
             'counting_policy':'사람 확정 동일오류의 대표금액 1회. 상반 오류 상계 없음. 미확정·변경 항목은 잠정 집계.'}
        register.append(row)
        for index,impact in enumerate(record['account_impacts'],1):
            impacts.append({'record_id':record['id'],'group_id':group_id,'impact_no':index,**impact,
                            'assessment':record['assessment'],'period':record['period'],
                            'classification':record['classification'],'correction_state':record['correction_state'],
                            'amount_representative':counted,'scope':'회원별 계정영향 보존. 이 표의 합계를 전체 오류금액으로 사용하지 않습니다.'})
        if counted:
            key=(record['period'],record['classification'],record['correction_state'])
            bucket=totals[key];bucket['count']+=1;bucket['gross_amount']+=abs(amount)
            bucket['positive_amount']+=max(amount,0);bucket['negative_amount_abs']+=max(-amount,0)
            bucket['tax_positive']+=0;bucket['tax_negative_abs']+=0
            bucket['tax_unknown_count']+=int(tax is None)
            if tax is not None:
                bucket['tax_positive']+=max(tax,0);bucket['tax_negative_abs']+=max(-tax,0)
    summary=[dict(period=k[0],classification=k[1],correction_state=k[2],**values,
                  policy='부호별·절대금액 집계. 순액 상계 및 세후 중요성 자동판정 없음.') for k,values in totals.items()]
    return {'records':register,'groups':group_rows,'account_impacts':impacts,'summary':summary,
            'verifications':deepcopy(list(replay['verifications'].values())),
            'reconfirmations':deepcopy(list(replay['reconfirmations'].values())),
            'materiality':deepcopy(materiality),'group_problems':group_problems,
            'manifest_hash':digest({'records':register,'groups':group_rows})}


def status(ws):
    snap=snapshot_rows(ws);records=snap['records'];blockers=[]
    for record in records:
        for message in record['missing']:
            blockers.append({'code':'MS_REVIEW_PENDING','record_id':record['id'],
                             'procedure_id':'F03','message':message})
    blockers.extend(snap['group_problems'])
    if records:
        if not ws.workflow_profile:blockers.append({'code':'MS_MATERIALITY_PENDING','procedure_id':'F03','message':'사람이 선택한 현재 중요성 기준을 연결하세요.'})
        paper=ws.procedures.get('F03')
        if not paper or ws.procedure_state(paper)!='검토기록완료':
            blockers.append({'code':'MS_F03_REVIEW_PENDING','procedure_id':'F03','message':'현재 집계 근거로 F03 조서를 작성하고 별도 검토기록을 남기세요.'})
        elif not set(s for r in records for s in r['evidence_ids'])<=set(paper.get('evidence_ids',[])):
            blockers.append({'code':'MS_F03_EVIDENCE_MISSING','procedure_id':'F03','message':'모든 집계기록의 원본 증거를 F03 조서에 연결하세요.'})
    return {'active':bool(records),'blockers':blockers,'records':[
        {k:r[k] for k in ('id','current','assessment','correction_state','verification_state','complete','missing')}
        for r in records], 'summary':snap['summary'],'materiality':snap['materiality'],
        'scope':'기계적 입력·버전·수치 연결 점검. 왜곡표시 최종 평가·승인·감사의견은 사람이 판단합니다.'}
