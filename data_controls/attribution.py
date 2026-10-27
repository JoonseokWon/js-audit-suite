"""Compare conflicting source allocations without deciding which document is right."""
from datetime import timedelta
from common import AuditError,issue


def review_invoice(contract,invoice,parsed,start,end,cut,attributed,earned,issues,output,periods):
    ca,cb,total=parsed;cid=invoice['비용ID'];ref=f"후속송장!{invoice['_row']}"
    contract_ref=f"용역계약!{contract['_row']}"
    try:
        expected=(earned(total,ca,cb,contract['배분방법'],min(end,cut))-
                  earned(total,ca,cb,contract['배분방법'],start-timedelta(days=1))) if start<=cut else 0
    except AuditError:
        expected=None
        issue(issues,'ACC_ATTRIBUTION_UNVERIFIED',
            '계약과 송장의 부분기간 배분 기준을 직접 비교할 수 없습니다. 양 원문·배분 조건을 추가 확인하세요.',
            contract_ref+' / '+ref,False)
    delta=attributed-expected if expected is not None else None
    if delta:
        issue(issues,'ACC_ATTRIBUTION_CONFLICT',
            f'같은 송장 귀속기간의 계약 기준 참고액 {expected:,}원과 송장 기준 참고액 {attributed:,}원에 '
            f'{delta:,}원 차이가 있습니다. 어느 금액이 맞는지 자동 확정하지 않으므로 원문·귀속조건을 추가 검토하세요.',
            contract_ref+' / '+ref,False)
    output.append({'비용ID':cid,'증빙ID':invoice['증빙ID'],'귀속시작':start.isoformat(),
        '귀속종료':end.isoformat(),'동일기간계약기준참고액':expected,'송장기준참고액':attributed,
        '차이':delta,'상태':'추가검토' if delta is None or delta else '기계적금액일치·원문판단별도',
        '계약원본행':contract_ref,'송장원본행':ref,'계약근거':contract['계약근거'],
        '송장근거':invoice['증빙근거'],'금액자동확정':False})
    for a,b,other in periods[cid]:
        if max(a,start)<=min(b,end):
            issue(issues,'ACC_INVOICE_PERIOD_OVERLAP',
                '같은 비용ID의 후속송장 귀속기간이 겹칩니다. 분할 청구인지 총액 내 중복 청구인지 양 원문을 확인하세요.',
                contract_ref+' / '+other+' / '+ref,False)
    periods[cid].append((start,end,ref))
