"""Lessee, fixed equal monthly cash flows, full-month cost model. Independent implementation."""
from calendar import monthrange
from decimal import Decimal,localcontext,ROUND_HALF_UP
from common import *
from estimate_controls import settings,keyed,rate,population,compare,CONTROL_HEADER

SCHEMA={'설정':['항목','값'],
 '리스계약':['회사코드','리스ID','개시일','개월수','월지급액','지급시점','할인율종류','할인율','선급금','직접원가','복구원가','수취인센티브','내용월수','조건','계약근거','할인율근거'],
 '리스원장':['회사코드','리스ID','기말리스부채','기말사용권자산','당기리스이자','당기사용권상각','유동리스부채','비유동리스부채','원장근거'],
 '독립통제':CONTROL_HEADER}
FIELDS=['기말리스부채','기말사용권자산','당기리스이자','당기사용권상각','유동리스부채','비유동리스부채']
POP={'리스계약':('리스ID',['월지급액','선급금','직접원가','복구원가','수취인센티브']),'리스원장':('리스ID',FIELDS)}
POLICY='고정 월납 임차인 원가모형 / 월초 개시·월말 결산 / 월말후급 또는 월초선급 / 원 단위 누적잔액 반올림 / 변경·옵션·손상·외화 미지원'
def rounded(x):return int(x.quantize(Decimal(1),rounding=ROUND_HALF_UP))
def monthadd(d,n):
    y,m=divmod(d.year*12+d.month-1+n,12)
    if not 1900<=y<=2100:raise AuditError('리스 스케줄 날짜 범위 1900~2100')
    return date(y,m+1,1)
def monthend(d):return date(d.year,d.month,monthrange(d.year,d.month)[1])

def schedule(r,event=None):
    start=day(r['개시일']);n=num(r['개월수'],False);life=num(r['내용월수'],False)
    if start.day!=1 or not 1<=n<=600 or not 1<=life<=600:raise AuditError('리스 월초 개시, 1~600 개월수·내용월수 필요')
    if r['조건']!='고정월납_변경없음_옵션없음_손상없음':raise AuditError('미지원 리스 조건: 변경·옵션·손상 등은 별도 계산 필요')
    if r['지급시점'] not in ('월말후급','월초선급') or r['할인율종류'] not in ('월유효','연유효'):raise AuditError('지급시점·할인율종류 미지원')
    text(r['계약근거']);text(r['할인율근거']);p=num(r['월지급액'],False)
    extras=[num(r[f],False) for f in ('선급금','직접원가','복구원가','수취인센티브')]
    with localcontext() as ctx:
        ctx.prec=42
        q=rate(r['할인율'],'할인율')
        q=(1+q)**(Decimal(1)/12)-1 if r['할인율종류']=='연유효' else q
        advance=r['지급시점']=='월초선급'
        count=n-1 if advance else n
        def pv(count):return Decimal(p)*count if q==0 else Decimal(p)*(1-(1+q)**(-count))/q
        liability=pv(count)
        initial=rounded(liability);first=p if advance else 0
        rou=initial+first+extras[0]+extras[1]+extras[2]-extras[3]
        if rou<0 or rou>10**13:raise AuditError('사용권자산 최초원가 범위 오류')
        depmonths=min(n,life);rows=[]
        for i in range(1,n+1):
            cancelled(event);opening=rounded(liability);cash=p if not advance or i>1 else 0
            exactinterest=(liability-cash)*q if advance else liability*q
            # Revalue the remaining annuity to avoid compounding precision loss over long/high-rate leases.
            liability=pv(n-i)*((1+q) if advance else 1)
            closing=rounded(liability);interest=closing-opening+cash
            prevdep=rounded(Decimal(rou)*min(i-1,depmonths)/depmonths);accdep=rounded(Decimal(rou)*min(i,depmonths)/depmonths)
            d=monthadd(start,i-1)
            rows.append({'리스ID':r['리스ID'],'월':d.strftime('%Y-%m'),'월말':monthend(d).isoformat(),'회차':i,'기초부채':opening,'현금지급':cash,'이자비용':interest,'정밀이자':str(exactinterest),'반올림배분':str(Decimal(interest)-exactinterest),'원금상환':cash-interest,'기말부채':closing,'기초사용권':rou-prevdep,'상각비':accdep-prevdep,'누계상각':accdep,'기말사용권':rou-accdep})
        return {'최초리스부채':initial,'최초사용권자산':rou,'개시일선급지급':first,'월유효할인율':str(q),'상각개월':depmonths},rows

def analyze(t,event=None):
    c=settings(t,{'모형','허용오차','회계정책근거'})
    if c['모형']!='임차인고정월납':raise AuditError('미지원 리스 모형')
    tol=num(c['허용오차'],False)
    if tol>1000:raise AuditError('허용오차 0~1000원 범위')
    start,cut=day(c['시작일']),day(c['기준일'])
    if start.day!=1 or cut!=monthend(cut):raise AuditError('리스는 시작일 월초·기준일 월말 필요')
    contracts=keyed(t['리스계약'],'리스ID',c['회사코드']);books=keyed(t['리스원장'],'리스ID',c['회사코드'])
    if not contracts or set(contracts)!=set(books):raise AuditError('리스계약·원장 ID 모집단 누락/불일치')
    if sum(num(r['개월수'],False) for r in contracts.values())>200000:raise AuditError('리스 월별 합계 한도 200000행')
    iss=[];checks=population(t,c,POP,iss);summary=[];monthly=[];comparisons=[]
    for key,r in contracts.items():
        if day(r['개시일'])>cut:raise AuditError('기준일 후 개시 계약은 대상 모집단에서 제외·별도 검토')
        initial,rows=schedule(r,event);monthly.extend(rows);book=books[key];text(book['원장근거'])
        current=[x for x in rows if start<=day(x['월말'])<=cut]
        prior=[x for x in rows if day(x['월말'])<start];asof=[x for x in rows if day(x['월말'])<=cut]
        last=asof[-1];future=[x for x in rows if cut<day(x['월말'])<=monthend(monthadd(cut,12))]
        debt=last['기말부채'];current_debt=debt-(future[-1]['기말부채'] if future else debt)
        a={'리스ID':key,**initial,'기초리스부채':prior[-1]['기말부채'] if prior else 0,'당기신규부채':initial['최초리스부채'] if start<=day(r['개시일'])<=cut else 0,'당기현금지급':sum(x['현금지급'] for x in current),'기초사용권자산':prior[-1]['기말사용권'] if prior else 0,'당기신규사용권':initial['최초사용권자산'] if start<=day(r['개시일'])<=cut else 0,'기말리스부채':debt,'기말사용권자산':last['기말사용권'],'당기리스이자':sum(x['이자비용'] for x in current),'당기사용권상각':sum(x['상각비'] for x in current),'유동리스부채':current_debt,'비유동리스부채':debt-current_debt,'계약행':f"리스계약!{r['_row']}",'원장행':f"리스원장!{book['_row']}"}
        if a['기초리스부채']+a['당기신규부채']+a['당기리스이자']-a['당기현금지급']!=debt:raise AuditError('리스 부채 롤포워드 오류')
        if a['기초사용권자산']+a['당기신규사용권']-a['당기사용권상각']!=a['기말사용권자산']:raise AuditError('사용권자산 롤포워드 오류')
        vals={f:num(book[f],False) for f in FIELDS}
        if vals['기말리스부채']!=vals['유동리스부채']+vals['비유동리스부채']:issue(iss,'LEASE_BOOK_CLASS','원장 유동·비유동 합계 불일치',a['원장행'])
        for f in FIELDS:compare(iss,comparisons,key,f,a[f],vals[f],a['계약행']+' / '+a['원장행'],tol)
        summary.append(a)
    metrics={f:sum(r[f] for r in summary) for f in FIELDS[:4]}
    return result('리스',c,{'리스요약':summary,'월별리스':monthly,'리스원장대사':comparisons,'원장통제':checks}|{'입력_'+k:v for k,v in t.items()},iss,metrics,{'계산정책':POLICY,'허용오차':tol,'정책근거':c['회계정책근거'],'기준참조':'IFRS16 23–28,30–36; 적용 K-IFRS 1116 판본·정책은 작성자 확인'})
