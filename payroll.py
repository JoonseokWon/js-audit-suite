"""Explicit-policy monthly pay, short-term leave, DC and cash/payable reconciliation. No tax/DB engine."""
from decimal import Decimal,ROUND_HALF_UP
from calendar import monthrange
from datetime import timedelta
from collections import defaultdict,Counter
from common import *
from estimate_controls import settings,keyed,rate,decimalnum,population,compare,CONTROL_HEADER
SCHEMA={'설정':['항목','값'],
 '인사명부':['회사코드','사번','입사일','퇴사일','급여계좌','퇴직제도','DC계좌','인사근거'],
 '급여명세':['회사코드','급여ID','사번','귀속월','월기준급여','무급일수','시간외시간','시간단가','가산배수','상여','기타수당','공제액','DC율','급여자산배부율','DC자산배부율','급여근거','상여근거','공제근거','배부근거'],
 '급여원장':['회사코드','급여ID','총급여','실지급대상','공제액','급여비용','급여배부원가','DC발생액','DC비용','DC배부원가','원장근거'],
 '급여지급':['이체ID','사번','급여ID','유형','지급일','수취계좌','지급액','이체근거'],
 '연차명세':['회사코드','사번','기초일수','발생일수','사용일수','소멸일수','예상정산비율','일단가','연차자산배부율','권리구분','정산예정일','연차근거','배부근거'],
 '급여잔액':['회사코드','사번','기초미지급급여','기말미지급급여','기초DC미지급','기말DC미지급','기초연차부채','기말연차부채','당기연차비용','당기연차배부원가','원장근거'],
 '독립통제':CONTROL_HEADER}
METRICS=['당기급여비용','당기급여배부원가','기말미지급급여','당기DC비용','당기DC배부원가','기말DC미지급','당기연차비용','당기연차배부원가','기말연차부채']
POP={'인사명부':('사번',[]),'급여명세':('급여ID',['월기준급여','시간단가','상여','기타수당','공제액']),'급여원장':('급여ID',['총급여','실지급대상','공제액','급여비용','급여배부원가','DC발생액','DC비용','DC배부원가']),'급여지급':('이체ID',['지급액']),'연차명세':('사번',['기초일수','발생일수','사용일수','소멸일수','일단가']),'급여잔액':('사번',['기초미지급급여','기말미지급급여','기초DC미지급','기말DC미지급','기초연차부채','기말연차부채','당기연차비용','당기연차배부원가'])}
FRACTIONAL={('연차명세',f) for f in ('기초일수','발생일수','사용일수','소멸일수')}
POLICY='달력일 월급 일할 / 승인 시간단가·배수·공제 재계산 / 총급여 기준 약정 DC / 단기 누적연차 / 급여비용에 유급휴가 포함·연차부채 순증감 별도 비용'
def won(v):return num(int(Decimal(v).quantize(Decimal(1),rounding=ROUND_HALF_UP)))
def monthstart(value):
    if not re.fullmatch(r'\d{4}-\d{2}',str(value)):raise AuditError('귀속월 YYYY-MM 필수')
    return day(str(value)+'-01')
def monthend(d):return date(d.year,d.month,monthrange(d.year,d.month)[1])
def analyze(t,event=None):
    c=settings(t,{'모형','허용오차','정산기한','급여정책근거','연차정책근거','DC정책근거'})
    if c['모형']!='단기급여_달력일_DC_연차순증감':raise AuditError('미지원 급여 모형')
    start,cut,deadline=day(c['시작일']),day(c['기준일']),day(c['정산기한']);tol=num(c['허용오차'],False)
    if start.day!=1 or cut!=monthend(cut) or not cut<=deadline<=cut+timedelta(days=365) or tol>1000:raise AuditError('급여 월초·월말, 정산기한 365일 이내, 허용오차 0~1000 필요')
    hr=keyed(t['인사명부'],'사번',c['회사코드']);pay=keyed(t['급여명세'],'급여ID',c['회사코드']);books=keyed(t['급여원장'],'급여ID',c['회사코드']);leave=keyed(t['연차명세'],'사번',c['회사코드']);balances=keyed(t['급여잔액'],'사번',c['회사코드']);keyed(t['급여지급'],'이체ID')
    if not hr or set(hr)!=set(leave) or set(hr)!=set(balances) or set(pay)!=set(books):raise AuditError('급여·인사·연차·원장 모집단 누락/불일치')
    iss=[];employment={};expected=set();seen=set();totals=defaultdict(lambda:defaultdict(int));calculated={};details=[];comparisons=[];payments=[];leavedetail=[];rolls=[]
    for emp,r in hr.items():
        born=day(r['입사일']);end=day(r['퇴사일']) if r['퇴사일'] not in (None,'') else date(2100,12,31)
        text(r['인사근거']);text(r['급여계좌'])
        if end<born or born>cut or r['퇴직제도'] not in ('DC','없음'):raise AuditError('입퇴사일·미지원 퇴직제도 (DB·퇴직금 별도)')
        if r['퇴직제도']=='DC':text(r['DC계좌'])
        employment[emp]=(born,end);d=start
        while d<=cut:
            if max(d,born)<=min(monthend(d),end):expected.add((emp,d.strftime('%Y-%m')))
            d=monthend(d)+timedelta(days=1)
    for acct,n in Counter(r['급여계좌'] for r in hr.values()).items():
        if n>1:issue(iss,'PAY_SHARED_ACCOUNT','여러 사번의 동일 급여계좌: 권한·명의·중복 지급 검토',acct,False)
    checks=population(t,c,POP,iss,FRACTIONAL)
    for pid,r in pay.items():
        cancelled(event);emp=text(r['사번']);d=monthstart(r['귀속월']);key=(emp,r['귀속월'])
        if emp not in hr or key not in expected or key in seen:raise AuditError('사번·귀속월 중복/고아/근무기간 밖 급여')
        seen.add(key);born,end=employment[emp];days=(min(monthend(d),end)-max(d,born)).days+1;unpaid=num(r['무급일수'],False)
        if unpaid>days:raise AuditError('무급일수가 재직일수 초과')
        base=num(r['월기준급여'],False);hours=decimalnum(r['시간외시간'],'시간외시간');hourprice=num(r['시간단가'],False);mult=rate(r['가산배수'],'가산배수',Decimal(0),Decimal(5))
        if hours>744:raise AuditError('시간외시간 월744시간 범위 초과')
        regular=won(Decimal(base)*(days-unpaid)/monthrange(d.year,d.month)[1]);overtime=won(hours*hourprice*mult);bonus=num(r['상여'],False);extra=num(r['기타수당'],False);ded=num(r['공제액'],False);text(r['급여근거']);text(r['공제근거']);text(r['배부근거'])
        if bonus:text(r['상여근거'],'상여근거')
        gross=regular+overtime+bonus+extra;net=gross-ded
        if net<0:raise AuditError('공제액이 총급여 초과')
        dc_rate=rate(r['DC율'],'DC율');dc=won(Decimal(gross)*dc_rate)
        if hr[emp]['퇴직제도']=='없음' and dc_rate!=0:raise AuditError('퇴직제도 없음의 DC율은 0 필수')
        wage_alloc=won(Decimal(gross)*rate(r['급여자산배부율']));dc_alloc=won(Decimal(dc)*rate(r['DC자산배부율']))
        vals={'총급여':gross,'실지급대상':net,'공제액':ded,'급여비용':gross-wage_alloc,'급여배부원가':wage_alloc,'DC발생액':dc,'DC비용':dc-dc_alloc,'DC배부원가':dc_alloc}
        b=books[pid];text(b['원장근거']);ref=f"급여명세!{r['_row']} / 급여원장!{b['_row']}"
        for metric,v in vals.items():compare(iss,comparisons,pid,metric,v,num(b[metric],False),ref,tol)
        if num(b['급여비용'],False)+num(b['급여배부원가'],False)!=num(b['총급여'],False) or num(b['DC비용'],False)+num(b['DC배부원가'],False)!=num(b['DC발생액'],False) or num(b['실지급대상'],False)+num(b['공제액'],False)!=num(b['총급여'],False):issue(iss,'PAY_BOOK_ROLL','급여 원장 총액·공제·배부 롤포워드 불일치',ref)
        for f,v in vals.items():totals[emp][f]+=v
        calculated[pid]={'emp':emp,'month':d,**vals};details.append({'급여ID':pid,'사번':emp,'귀속월':r['귀속월'],'재직일수':days,'무급일수':unpaid,'계산기본급':regular,'계산시간외':overtime,**vals,'원본행':ref})
    if seen!=expected:raise AuditError('재직 사번·귀속월 급여 누락: '+str(sorted(expected-seen)[:10]))
    settled=defaultdict(int);paid=defaultdict(lambda:defaultdict(int));post=defaultdict(lambda:defaultdict(int))
    for r in t['급여지급']:
        emp=text(r['사번']);pid=text(r['급여ID']);kind=r['유형'];dt=day(r['지급일']);amount=num(r['지급액'],False);text(r['이체근거'])
        if emp not in hr or kind not in ('급여','DC') or not start<=dt<=deadline:raise AuditError('지급 사번·유형·일자 범위 오류')
        account=hr[emp]['급여계좌'] if kind=='급여' else hr[emp]['DC계좌']
        if r['수취계좌']!=account or (kind=='DC' and hr[emp]['퇴직제도']!='DC'):issue(iss,'PAY_ACCOUNT','급여/DC 수취계좌 불일치',f"급여지급!{r['_row']}")
        if pid=='OPEN':limit=num(balances[emp]['기초미지급급여' if kind=='급여' else '기초DC미지급'],False)
        else:
            if pid not in calculated or calculated[pid]['emp']!=emp:raise AuditError('고아/다른 사번 지급 참조')
            if dt<max(calculated[pid]['month'],employment[emp][0]):raise AuditError('입사일/귀속월 이전 선급 지급은 미지원')
            limit=calculated[pid]['실지급대상' if kind=='급여' else 'DC발생액']
        settled[(emp,pid,kind)]+=amount
        if settled[(emp,pid,kind)]>limit:issue(iss,'PAY_OVERPAY','동일 급여/기초 참조 초과 지급',f"급여지급!{r['_row']}")
        (paid if dt<=cut else post)[emp][kind]+=amount
        payments.append({'이체ID':r['이체ID'],'사번':emp,'급여ID':pid,'유형':kind,'지급일':dt.isoformat(),'지급액':amount,'구분':'당기지급' if dt<=cut else '후속지급','원본행':f"급여지급!{r['_row']}"})
    metrics={k:0 for k in METRICS}
    for emp,b in balances.items():
        l=leave[emp];text(b['원장근거']);text(l['연차근거']);text(l['배부근거']);ref=f"연차명세!{l['_row']} / 급여잔액!{b['_row']}"
        op,earned,used,expired=[decimalnum(l[f],f) for f in ('기초일수','발생일수','사용일수','소멸일수')];unused=op+earned-used-expired
        if unused<0 or l['권리구분']!='단기누적' or not cut<=day(l['정산예정일'])<=deadline:raise AuditError('연차 잔여일수·단기누적·정산예정일 오류')
        if employment[emp][1]<cut and unused>0:raise AuditError('퇴사자의 잔여연차는 퇴직정산으로 별도 처리 필요')
        closing_leave=won(unused*num(l['일단가'],False)*rate(l['예상정산비율']));opening_leave=num(b['기초연차부채'],False);leavecharge=closing_leave-opening_leave
        alloc=won(Decimal(abs(leavecharge))*rate(l['연차자산배부율']))*(1 if leavecharge>=0 else -1)
        current=totals[emp];opw=num(b['기초미지급급여'],False);opdc=num(b['기초DC미지급'],False);wageclose=opw+current['실지급대상']-paid[emp]['급여'];dcclose=opdc+current['DC발생액']-paid[emp]['DC']
        if wageclose<0 or dcclose<0:issue(iss,'PAY_PREPAID','음수 미지급 잔액 (선급급여·선급DC는 미지원)',ref)
        for metric,v in [('기말미지급급여',wageclose),('기말DC미지급',dcclose),('기말연차부채',closing_leave),('당기연차비용',leavecharge-alloc),('당기연차배부원가',alloc)]:compare(iss,comparisons,emp,metric,v,num(b[metric],metric.startswith('당기')),ref,tol)
        # Closing positive liabilities; current expense/asset reversals preserve their signs.
        if num(b['기말연차부채'],False)-opening_leave!=num(b['당기연차비용'])+num(b['당기연차배부원가']):issue(iss,'LEAVE_BOOK_ROLL','연차 원장 순증감/비용·배부 불일치',ref)
        for prefix,col in [('급여','미지급급여'),('DC','DC미지급')]:
            opval=opw if prefix=='급여' else opdc;accrual=current['실지급대상' if prefix=='급여' else 'DC발생액']
            if opval+accrual-paid[emp][prefix]!=num(b['기말'+col],False):issue(iss,'PAY_BALANCE_ROLL',prefix+' 기초+발생-지급=기말 불일치',ref)
        vals={'당기급여비용':current['급여비용'],'당기급여배부원가':current['급여배부원가'],'기말미지급급여':wageclose,'당기DC비용':current['DC비용'],'당기DC배부원가':current['DC배부원가'],'기말DC미지급':dcclose,'당기연차비용':leavecharge-alloc,'당기연차배부원가':alloc,'기말연차부채':closing_leave}
        for k,v in vals.items():metrics[k]+=v
        rolls.append({'사번':emp,'기초미지급급여':opw,'당기실지급대상':current['실지급대상'],'당기급여지급':paid[emp]['급여'],'후속급여지급':post[emp]['급여'],'기초DC미지급':opdc,'DC발생액':current['DC발생액'],'당기DC지급':paid[emp]['DC'],'후속DC지급':post[emp]['DC'],**vals,'원본행':ref})
        leavedetail.append({'사번':emp,'기초일수':str(op),'발생일수':str(earned),'사용일수':str(used),'소멸일수':str(expired),'잔여일수':str(unused),'예상정산비율':str(rate(l['예상정산비율'])),'계산연차부채':closing_leave,'기초연차부채':opening_leave,'당기연차비용':leavecharge-alloc,'당기연차배부원가':alloc,'원본행':ref})
    for value in metrics.values():num(value)
    return result('종업원급여',c,{'급여요약':rolls,'월별급여계산':details,'급여지급대사':payments,'연차계산':leavedetail,'급여원장대사':comparisons,'원장통제':checks}|{'입력_'+k:v for k,v in t.items()},iss,metrics,{'계산정책':POLICY,'급여정책근거':c['급여정책근거'],'연차정책근거':c['연차정책근거'],'DC정책근거':c['DC정책근거'],'기준참조':'IAS19 11–16,19,51–52 / 세금·법정 최저율·DB·퇴직정산은 미지원','허용오차':tol})
