"""Lifetime ECL provision matrix for trade receivables without significant financing."""
from collections import defaultdict
from decimal import Decimal,ROUND_HALF_UP,localcontext
from common import *
from estimate_controls import settings,keyed,rate,population,compare,CONTROL_HEADER
SCHEMA={'설정':['항목','값'],
 '채권':['회사코드','채권ID','분류군','거래처','발생일','만기일','채권잔액','측정구분','개별손실률','개별평가근거'],
 '시나리오':['시나리오ID','확률','전망근거'],
 '충당률표':['행ID','분류군','시나리오ID','연체하한','연체상한','과거손실률','전망배수','가산조정','산출근거'],
 '충당금원장':['회사코드','분류군','채권잔액','기초충당금','비용외증감','기말충당금','당기대손상각비','원장근거'],
 '충당금변동':['변동ID','분류군','유형','증감액','근거'],
 '독립통제':CONTROL_HEADER}
POP={'채권':('채권ID',['채권잔액']),'시나리오':('시나리오ID',[]),'충당률표':('행ID',[]),'충당금원장':('분류군',['채권잔액','기초충당금','비용외증감','기말충당금','당기대손상각비']),'충당금변동':('변동ID',['증감액'])}
POLICY='유의적 금융요소 없는 매출채권 전체기간 ECL / 분류군·연체일 충당률표 / 시나리오 확률가중 / 개별평가 중복제외 / 채권별 원 단위 반올림'

def analyze(t,event=None):
    c=settings(t,{'모형','할인정책','할인근거','정책근거','허용오차'})
    if c['모형']!='매출채권_유의적금융요소없음_전체기간':raise AuditError('미지원 ECL 모형 (금융기관 3단계·대여금 등 별도)')
    if c['할인정책'] not in ('손실률에포함','할인효과비유의'):raise AuditError('할인정책·근거 필수')
    tol=num(c['허용오차'],False)
    if tol>1000:raise AuditError('허용오차 0~1000원 범위')
    ar=keyed(t['채권'],'채권ID',c['회사코드']);books=keyed(t['충당금원장'],'분류군',c['회사코드'])
    scenarios=keyed(t['시나리오'],'시나리오ID');keyed(t['충당률표'],'행ID');keyed(t['충당금변동'],'변동ID')
    if not ar or not 1<=len(scenarios)<=10:raise AuditError('채권 모집단 및 1~10개 시나리오 필수')
    probs={k:rate(r['확률'],'시나리오 확률') for k,r in scenarios.items()}
    if any(p<=0 for p in probs.values()) or sum(probs.values())!=1:raise AuditError('시나리오 확률은 양수·합계 정확히 1')
    for r in scenarios.values():text(r['전망근거'])
    groups={text(r['분류군']) for r in ar.values()}
    collective={r['분류군'] for r in ar.values() if r['측정구분']=='집합'}
    if groups!=set(books):raise AuditError('채권·충당금원장 분류군 모집단 누락/불일치')
    iss=[];checks=population(t,c,POP,iss);matrix=defaultdict(list);applied=[];detail=[];comparisons=[];totals=defaultdict(lambda:[0,0]);movements=defaultdict(int)
    for r in t['충당률표']:
        group,scenario=text(r['분류군']),text(r['시나리오ID']);lo=num(r['연체하한'],False);hi=None if r['연체상한'] in (None,'') else num(r['연체상한'],False)
        if group not in collective or scenario not in scenarios or (hi is not None and hi<lo) or lo>100000:raise AuditError('충당률표 분류군·시나리오·구간 오류')
        base=rate(r['과거손실률']);mult=rate(r['전망배수'],'전망배수',Decimal(0),Decimal(100));adj=rate(r['가산조정'],'가산조정',Decimal(-1),Decimal(1))
        final=base*mult+adj
        if not 0<=final<=1:raise AuditError('조정후 손실률 범위 0~1 밖 (자동 보정하지 않음)')
        text(r['산출근거']);matrix[(group,scenario)].append((lo,hi,final,r))
        applied.append({'행ID':r['행ID'],'분류군':group,'시나리오ID':scenario,'연체하한':lo,'연체상한':hi,'과거손실률':str(base),'전망배수':str(mult),'가산조정':str(adj),'조정후손실률':str(final),'확률':str(probs[scenario]),'원본행':f"충당률표!{r['_row']}"})
    if set(matrix)!={(g,s) for g in collective for s in scenarios}:raise AuditError('충당률표 분류군·시나리오 누락')
    for key,segments in matrix.items():
        segments.sort(key=lambda x:x[0]);nextlo=0
        for lo,hi,_,_ in segments:
            if nextlo is None or lo!=nextlo:raise AuditError('연체구간 중복·공백: '+str(key))
            nextlo=None if hi is None else hi+1
        if nextlo is not None:raise AuditError('연체구간 마지막 무한상한(빈칸) 필요')
    for key,r in ar.items():
        cancelled(event);group=r['분류군'];text(r['거래처']);issued,due=day(r['발생일']),day(r['만기일']);cut=day(c['기준일'])
        if issued>cut or due<issued:raise AuditError('채권 발생·만기·기준일 오류')
        amount=num(r['채권잔액'],False);late=max(0,(cut-due).days);refs=[];weighted=Decimal(0)
        if r['측정구분']=='개별':
            weighted=rate(r['개별손실률'],'개별손실률');text(r['개별평가근거']);refs=['개별평가: '+str(r['개별평가근거'])]
        elif r['측정구분']=='집합':
            if r['개별손실률'] is not None or r['개별평가근거'] not in (None,''):raise AuditError('집합평가에 개별 손실률·근거 혼입')
            for scenario,p in probs.items():
                found=[x for x in matrix[(group,scenario)] if x[0]<=late and (x[1] is None or late<=x[1])]
                if len(found)!=1:raise AuditError('채권별 충당률 구간 단일 매칭 실패')
                weighted+=p*found[0][2];refs.append(scenario+':'+found[0][3]['행ID'])
        else:raise AuditError('측정구분 집합/개별 필수')
        exact=Decimal(amount)*weighted;loss=int(exact.quantize(Decimal(1),rounding=ROUND_HALF_UP))
        detail.append({'채권ID':key,'분류군':group,'거래처':r['거래처'],'채권잔액':amount,'연체일수':late,'측정구분':r['측정구분'],'가중손실률':str(weighted),'정밀ECL':str(exact),'계산충당금':loss,'적용근거':' / '.join(refs),'원본행':f"채권!{r['_row']}"})
        totals[group][0]+=amount;totals[group][1]+=loss
    for r in t['충당금변동']:
        g=text(r['분류군']);v=num(r['증감액']);text(r['근거'])
        if g not in books or r['유형'] not in ('제각','계정대체','기타') or (r['유형']=='제각' and v>=0):raise AuditError('충당금 변동 분류·제각 부호 오류')
        movements[g]+=v
    summary=[]
    for g,b in books.items():
        ref=f"충당금원장!{b['_row']}";text(b['원장근거']);gross=num(b['채권잔액'],False);opening=num(b['기초충당금'],False);other=num(b['비용외증감']);closing=num(b['기말충당금'],False);expense=num(b['당기대손상각비'])
        if opening+other+expense!=closing:issue(iss,'ECL_BOOK_ROLL','충당금 원장 롤포워드 불일치',ref)
        if movements[g]!=other:issue(iss,'ECL_MOVEMENT','비용외 변동 명세와 원장 불일치',ref)
        calcgross,calc=totals[g];needed=calc-opening-other
        for metric,x,y in [('기말채권잔액',calcgross,gross),('기말대손충당금',calc,closing),('당기대손상각비',needed,expense)]:compare(iss,comparisons,g,metric,x,y,ref,tol if metric!='기말채권잔액' else 0)
        summary.append({'분류군':g,'기말채권잔액':calcgross,'기초충당금':opening,'비용외증감':other,'기말대손충당금':calc,'당기대손상각비':needed,'원장기말충당금':closing,'원장대손상각비':expense,'원본행':ref})
    metrics={k:sum(r[k] for r in summary) for k in ('기말채권잔액','기말대손충당금','당기대손상각비')}
    return result('대손충당금',c,{'충당금요약':summary,'채권별ECL':detail,'적용충당률표':applied,'충당금원장대사':comparisons,'원장통제':checks}|{'입력_'+k:v for k,v in t.items()},iss,metrics,{'계산정책':POLICY,'할인정책':c['할인정책'],'할인근거':c['할인근거'],'정책근거':c['정책근거'],'기준참조':'IFRS9 5.5.15,5.5.17,B5.5.35,B5.5.44; 적용 K-IFRS1109 판본·정책 확인','허용오차':tol})
