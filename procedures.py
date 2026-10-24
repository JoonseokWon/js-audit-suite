"""Shared non-UI workpaper definitions for manual and sector demo workflows."""
from common import dumps,digest

def task_definitions(ws,catalog):
    tasks=[{'id':m['id'],'title':m['name'],'purpose':m['workpaper'],'risk':m['human_required']+' / '+m['standards'],'scope':'','performed':'','conclusion':''} for m in catalog['modules']]
    tasks.extend({'id':pid,'title':title,'purpose':purpose,'risk':'원본 신뢰성·모집단·차이 원인과 충분한 추가절차는 별도 판단','scope':'','performed':'','conclusion':''} for pid,title,purpose in [('R01','원천증빙·거래배부 검토','원본 파일·행과 거래배부·현재 원장 연결 검토'),('F01','재무제표·본문·주석 대사','합계·TB 매핑·본문·선택 주석의 차이 및 입력 범위 검토'),('W01','독립 계정 증빙연습','합성 원천의 독립 사례를 검토. 현재 업무 TB에는 합산하지 않음')])
    if ws:
        for module,pid in [('GLA','G01'),('FIA','I01'),('현금분석','H01')]:
            if module in ws.latest():tasks.append({'id':pid,'title':module+' 원장 연결·검토 후보 조사','purpose':'선언한 모집단·규칙·원문을 확인하고 위험 후보의 후속절차와 판단 기록','risk':'후보는 부정 확정 아님. 미확인 데이터·추출 신뢰성·정상 대조군 확인','scope':'','performed':'','conclusion':''})
        for task in tasks:
            linked=ws.calculation_refs(task['id'])
            if linked:
                unit='' if linked['모듈'] in ('원천증빙','재무제표·주석','계정별증빙연습','GLA','FIA','현금분석') else '원'
                task['scope']='자동계산 연결: '+linked['모듈']+'\n계산값: '+' / '.join(k+' '+str(v)+unit for k,v in linked['계산지표'].items())+'\n독립 원장 대사: '+' / '.join(x['지표']+' '+x['상태'] for x in linked['원장대사'])+'\n결과 상세에서 계산표·입력 원본을 확인하고 실제 검사 범위와 수행내용을 작성하세요.'
                task['evidence_ids']=[linked['자료ID']]+([ws.latest()['원장·리드']['source_id']] if '원장·리드' in ws.latest() else [])
        for r in ws.latest().values():
            for i,x in enumerate(r['result']['issues']):tasks.append({'id':'X-'+r['id']+'-'+str(i),'title':r['module']+' 예외: '+x['code'],'purpose':'예외 원인·증거·추가절차 및 회계처리 영향 평가','risk':x['message'],'scope':x['reference'],'performed':'','conclusion':''})
        for x in ws.cross_checks():
            if x['상태']=='차이':tasks.append({'id':'B-'+digest(x)[:16],'title':x['모듈']+' TB 연결차이: '+x['지표'],'purpose':'독립 TB 연결차이 조사·회계처리 영향 및 추가절차 기록','risk':dumps(x),'scope':x['사유'],'performed':'','conclusion':''})
    return tasks
