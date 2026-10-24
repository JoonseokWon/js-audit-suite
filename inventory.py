"""Item/lot cost versus NRV, with explicit allowance movements and unit-level population controls."""
from decimal import Decimal,ROUND_HALF_UP
from collections import defaultdict
from common import *
from estimate_controls import settings,keyed,decimalnum,population,compare,CONTROL_HEADER
SCHEMA={'설정':['항목','값'],
 '재고명세':['회사코드','평가ID','창고','품목','단위','기말수량','원가단가','원가근거','재고구분'],
 'NRV근거':['평가ID','예상판매단가','완성필요단가','판매필요단가','근거일','추정판단','가격근거'],
 '재고원장':['회사코드','평가ID','단위','기말수량','기말원가','기초평가충당금','평가손익외증감','기말평가충당금','당기평가손실','원장근거'],
 '평가변동':['변동ID','평가ID','유형','증감액','근거'],
 '독립통제':CONTROL_HEADER}
METRICS=['기말재고원가','기말재고평가충당금','기말재고순액','당기재고평가손실']
POLICY='확정 원가단가×수량 재계산 / 평가ID별 원가와 NRV 중 낮은 금액 / 평가손익외 증감 분리 / 원 단위 반올림'
def won(v):return num(int(v.quantize(Decimal(1),rounding=ROUND_HALF_UP)))
def population_spec(t):
    views=dict(t);spec={'재고명세':('평가ID',[]),'NRV근거':('평가ID',[]),'재고원장':('평가ID',['기말원가','기초평가충당금','평가손익외증감','기말평가충당금','당기평가손실']),'평가변동':('변동ID',['증감액'])};fractional=set()
    for role in ('재고명세','재고원장'):
        units={text(r['단위'],'단위') for r in t[role]}
        for unit in units:
            name=role+'['+unit+']';views[name]=[r for r in t[role] if r['단위']==unit];spec[name]=('평가ID',['기말수량']);fractional.add((name,'기말수량'))
    return views,spec,fractional
def analyze(t,event=None):
    c=settings(t,{'모형','허용오차','평가정책근거'})
    if c['모형']!='평가ID별원가_NRV':raise AuditError('미지원 재고 평가 모형')
    tol=num(c['허용오차'],False)
    if tol>1000:raise AuditError('허용오차 0~1000원')
    stock=keyed(t['재고명세'],'평가ID',c['회사코드']);price=keyed(t['NRV근거'],'평가ID');book=keyed(t['재고원장'],'평가ID',c['회사코드']);keyed(t['평가변동'],'변동ID')
    if not stock or set(stock)!=set(price) or set(stock)!=set(book):raise AuditError('재고·NRV·원장 평가ID 모집단 누락/불일치')
    iss=[];views,spec,frac=population_spec(t);checks=population(views,c,spec,iss,frac);moves=defaultdict(int);summary=[];comparison=[];cut=day(c['기준일'])
    for r in t['평가변동']:
        k=text(r['평가ID']);v=num(r['증감액']);text(r['근거'])
        if k not in stock or r['유형'] not in ('처분감소','범위대체') or (r['유형']=='처분감소' and v>=0):raise AuditError('재고 평가변동 ID·유형·부호 오류')
        moves[k]+=v
    for k,r in stock.items():
        cancelled(event);b,p=book[k],price[k];text(r['창고']);text(r['품목']);text(r['원가근거']);text(b['원장근거']);text(p['가격근거']);text(p['추정판단'])
        if r['재고구분'] not in ('상품','제품'):raise AuditError('미지원 재고구분: 판매목적 상품·제품만 지원, 원재료·재공품은 별도 평가')
        qty=decimalnum(r['기말수량']);unit=text(r['단위']);costunit=decimalnum(r['원가단가'],'원가단가');bqty=decimalnum(b['기말수량']);ref=f"재고명세!{r['_row']} / NRV근거!{p['_row']} / 재고원장!{b['_row']}"
        if unit!=b['단위'] or qty!=bqty:issue(iss,'INV_QTY_UNIT','수량·단위 불일치 (단위환산은 별도)',ref)
        evidence_date=day(p['근거일'])
        if abs((evidence_date-cut).days)>366:raise AuditError('NRV 근거일 기준일 전후 366일 범위. 오래된 가격은 별도 평가 필요')
        sale=decimalnum(p['예상판매단가'],'판매단가');complete=decimalnum(p['완성필요단가'],'완성단가');selling=decimalnum(p['판매필요단가'],'판매필요단가');raw_nrv=qty*(sale-complete-selling)
        gross=won(qty*costunit);nrv=max(0,won(raw_nrv));allowance=max(0,gross-nrv)
        if raw_nrv<0:issue(iss,'INV_NEGATIVE_NRV','음수 NRV: 재고 장부금액은 0으로 제한. 별도 의무·충당부채 검토 필요',ref,False)
        opening=num(b['기초평가충당금'],False);other=num(b['평가손익외증감']);bookallow=num(b['기말평가충당금'],False);bookloss=num(b['당기평가손실']);bookgross=num(b['기말원가'],False)
        if moves[k]!=other:issue(iss,'INV_MOVEMENT','평가변동과 원장 증감 불일치',ref)
        if opening+other<0 or opening+other+bookloss!=bookallow or bookallow>bookgross:issue(iss,'INV_BOOK_ROLL','평가충당금 원장 롤포워드·한도 오류',ref)
        loss=allowance-opening-other
        a={'평가ID':k,'창고':r['창고'],'품목':r['품목'],'재고구분':r['재고구분'],'단위':unit,'기말수량':str(qty),'원가단가':str(costunit),'계산원가':gross,'단위NRV':str(sale-complete-selling),'총NRV':nrv,'계산평가충당금':allowance,'계산재고순액':gross-allowance,'기초평가충당금':opening,'평가손익외증감':other,'당기평가손실':loss,'근거일':evidence_date.isoformat(),'원본행':ref}
        for metric,x,y in [('기말원가',gross,bookgross),('기말평가충당금',allowance,bookallow),('당기평가손실',loss,bookloss)]:compare(iss,comparison,k,metric,x,y,ref,tol)
        summary.append(a)
    metrics={k:sum(r[f] for r in summary) for k,f in zip(METRICS,['계산원가','계산평가충당금','계산재고순액','당기평가손실'])}
    for value in metrics.values():num(value)
    return result('재고평가',c,{'재고평가요약':summary,'재고원장대사':comparison,'원장통제':checks}|{'입력_'+k:v for k,v in t.items()},iss,metrics,{'계산정책':POLICY,'정책근거':c['평가정책근거'],'기준참조':'IAS2 9,28–34 / 적용 K-IFRS1002 판본·원가·판매 추정은 수동 확인','허용오차':tol})
