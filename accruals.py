"""Fixed KRW services: subsequent-source search, accrued liabilities and prepaid allocation."""
from datetime import timedelta,datetime
from calendar import monthrange
from decimal import Decimal,ROUND_HALF_UP
from collections import defaultdict
from common import *
from estimate_controls import settings,keyed,population,CONTROL_HEADER

MODULE='미기록부채·비용이연'
SCHEMA={'설정':['항목','값'],
 '용역계약':['회사코드','비용ID','거래처ID','구분','용역시작','용역종료','총공급가액','배분방법','비용계정','잔액계정','회계처리구분','계약근거'],
 '비용원장':['회사코드','비용ID','기초부채','당기발생비용','당기부채결제','기말부채','기초선급','당기선급지급','당기선급상각','기말선급','원장근거'],
 '후속송장':['회사코드','증빙ID','비용ID','거래처ID','송장번호','송장행ID','증빙일','공급가액','귀속시작','귀속종료','배분방법','증빙근거'],
 '대금지급':['회사코드','지급ID','비용ID','거래처ID','유형','지급일','공급가액지급','은행참조','지급근거'],
 '독립통제':CONTROL_HEADER}
BOOK_FIELDS=SCHEMA['비용원장'][2:-1]
POP={'용역계약':('비용ID',['총공급가액']),'비용원장':('비용ID',BOOK_FIELDS),'후속송장':('증빙ID',['공급가액']),'대금지급':('지급ID',['공급가액지급'])}
METRICS=['기말미지급비용','당기발생비용','기말선급비용','당기선급상각']
SCOPE_KEYS=['미지급계정범위','발생비용계정범위','선급계정범위','선급상각계정범위']
POLICY='확정 용역 공급가액 / 시작·종료일 포함 / 일할 또는 완전한 달 월할 / 누적액 원 단위 반올림 후 당기 차감 / 원장 대사 및 수정안 초안'

def codes(v):
    parts=text(v,'대상계정').split(';')
    if any(not x.strip() or x!=x.strip() for x in parts) or len(parts)!=len(set(parts)):raise AuditError('대상계정 범위 중복·공백')
    return sorted(parts)

def period(a,b,method):
    a,b=day(a),day(b)
    if b<a or (b-a).days>3660:raise AuditError('용역기간 순서 또는 3660일 한도')
    if method not in ('일할','월할'):raise AuditError('배분방법은 일할/월할')
    if method=='월할' and (a.day!=1 or b.day!=monthrange(b.year,b.month)[1]):raise AuditError('월할은 용역 시작월 1일·종료월 말일 필요')
    return a,b

def earned(total,a,b,method,cut):
    """Round cumulative earned amount, so opening + current = closing at any boundary."""
    if cut<a:return 0
    if cut>=b:return total
    if method=='일할':numer=(cut-a).days+1;denom=(b-a).days+1
    else:
        if cut.day!=monthrange(cut.year,cut.month)[1]:raise AuditError('월할 보고기간은 월초~월말 필요')
        numer=(cut.year-a.year)*12+cut.month-a.month+1;denom=(b.year-a.year)*12+b.month-a.month+1
    return int((Decimal(total)*numer/denom).quantize(Decimal(1),rounding=ROUND_HALF_UP))

def analyze(t,event=None):
    c=settings(t,{'모형','후속검색종료일','허용오차','회계정책근거',*SCOPE_KEYS})
    if c['모형']!='확정용역_미지급선급':raise AuditError('미지원 미지급·선급 모형')
    start,cut=day(c['시작일']),day(c['기준일']);search_end=day(c['후속검색종료일']);before=start-timedelta(days=1)
    if not cut<search_end<=cut+timedelta(days=366):raise AuditError('후속검색종료일은 기준일 이후 366일 이내')
    tol=num(c['허용오차'],False)
    if tol>1000:raise AuditError('허용오차 0~1000원')
    scopes={m:codes(c[k]) for m,k in zip(METRICS,SCOPE_KEYS)}
    if set(scopes[METRICS[0]])&set(scopes[METRICS[2]]) or set(scopes[METRICS[1]])&set(scopes[METRICS[3]]):raise AuditError('미지급·선급 비교 계정은 분리해야 합니다')
    contracts=keyed(t['용역계약'],'비용ID',c['회사코드']);books=keyed(t['비용원장'],'비용ID',c['회사코드'])
    keyed(t['후속송장'],'증빙ID',c['회사코드']);keyed(t['대금지급'],'지급ID',c['회사코드'])
    if set(contracts)!=set(books):raise AuditError('용역계약·비용원장 비용ID 모집단 누락/불일치')
    iss=[];checks=population(t,c,POP,iss)
    for r in t['독립통제']:
        if datetime.fromisoformat(str(r['추출일시']).lstrip("'")).date()<search_end:raise AuditError('독립통제 추출일시가 후속검색종료일보다 빠릅니다')
    payments=defaultdict(list);payment_rows=[];invoice_rows=[];seen_invoices=set();bank_refs=set();invoice_totals=defaultdict(int)
    parsed={}
    for k,r in contracts.items():
        cancelled(event);a,b=period(r['용역시작'],r['용역종료'],r['배분방법']);amt=num(r['총공급가액'],False)
        if amt==0:raise AuditError('계약 총공급가액은 양수')
        if r['구분'] not in ('미지급','선급') or r['회계처리구분']!='확정용역비용':raise AuditError('확정 용역비용 미지급/선급만 지원. 재고·자산취득·추정충당·외화·세금은 별도 절차')
        text(r['거래처ID']);text(r['계약근거']);expense=text(r['비용계정']);balance=text(r['잔액계정'])
        idx=0 if r['구분']=='미지급' else 2
        if balance not in scopes[METRICS[idx]] or expense not in scopes[METRICS[idx+1]]:raise AuditError('용역계약 계정이 선언한 대상계정 범위 밖입니다')
        if r['배분방법']=='월할' and (start.day!=1 or cut.day!=monthrange(cut.year,cut.month)[1]):raise AuditError('월할 보고기간은 월초~월말 필요')
        parsed[k]=(a,b,amt)
    for r in t['대금지급']:
        cancelled(event);key=r['비용ID'];dt=day(r['지급일']);v=num(r['공급가액지급'],False);ref=f"대금지급!{r['_row']}";text(r['지급근거']);text(r['거래처ID']);bank=text(r['은행참조'])
        if v==0 or dt>search_end:raise AuditError('지급액은 양수이고 지급일은 후속검색종료일 이내여야 합니다')
        if bank in bank_refs:raise AuditError('은행참조 중복. 배분 지급은 원천 이체행을 구분하세요')
        bank_refs.add(bank)
        if key is None or key=='':
            if not cut<dt<=search_end or r['유형']!='미분류':raise AuditError('미분류 지급은 기준일 이후 후속검색기간만 허용')
            issue(iss,'ACC_UNMATCHED_PAYMENT','후속 지급에 연결된 용역·원장 근거가 없습니다. 귀속·계정·부채 누락 확인 필요',ref,False);state='미확인'
        else:
            key=text(key)
            if key not in contracts:raise AuditError('대금지급의 고아 비용ID')
            target=contracts[key];typ='미지급결제' if target['구분']=='미지급' else '선급지급'
            if r['유형']!=typ or r['거래처ID']!=target['거래처ID']:raise AuditError('지급 유형·거래처와 계약 불일치')
            payments[key].append((dt,v,ref));state='기초이전' if dt<start else '당기' if dt<=cut else '후속'
        payment_rows.append({'지급ID':r['지급ID'],'비용ID':key,'지급일':dt.isoformat(),'공급가액지급':v,'구분':state,'은행참조':bank,'원본행':ref})
    for r in t['후속송장']:
        cancelled(event);dt=day(r['증빙일']);a,b=period(r['귀속시작'],r['귀속종료'],r['배분방법']);v=num(r['공급가액'],False);ref=f"후속송장!{r['_row']}";text(r['증빙근거'])
        ident=(text(r['거래처ID']),text(r['송장번호']),text(r['송장행ID']))
        if ident in seen_invoices:raise AuditError('거래처·송장번호·행ID 중복')
        seen_invoices.add(ident)
        if not cut<dt<=search_end or v==0:raise AuditError('후속송장은 양수 공급가액과 기준일 이후 검색기간 증빙일 필요')
        k=r['비용ID'];amount=earned(v,a,b,r['배분방법'],cut)
        if k is None or k=='':
            issue(iss,'ACC_UNMATCHED_INVOICE','후속 송장에 연결된 용역·원장이 없습니다. 기말 귀속·계상 여부 확인 필요',ref,False);state='미확인'
        else:
            k=text(k)
            if k not in contracts:raise AuditError('후속송장의 고아 비용ID')
            ca,cb,total=parsed[k];contract=contracts[k]
            if ident[0]!=contract['거래처ID'] or a<ca or b>cb:raise AuditError('송장 거래처·귀속기간과 계약 불일치')
            invoice_totals[k]+=v
            if invoice_totals[k]>total:issue(iss,'ACC_INVOICE_EXCESS','연결 송장 공급가액이 계약 총액을 초과합니다. 중복청구·범위 확인 필요',ref)
            state='기말전귀속' if amount else '후기귀속'
        invoice_rows.append({'증빙ID':r['증빙ID'],'비용ID':k,'거래처ID':ident[0],'증빙일':dt.isoformat(),'귀속시작':a.isoformat(),'귀속종료':b.isoformat(),'공급가액':v,'기말전귀속참고액':amount,'연결상태':state,'원본행':ref})
    summary=[];comparisons=[];proposals=[];metrics={m:0 for m in METRICS}
    def compare(k,field,calc,book,ref):
        delta=calc-book;state='일치' if delta==0 else '허용범위내차이' if abs(delta)<=tol else '차이'
        comparisons.append({'비용ID':k,'지표':field,'계산':calc,'원장':book,'차이':delta,'허용오차':tol,'상태':state,'원본행':ref})
        if delta:issue(iss,'ACC_BOOK_DIFF',k+' '+field+' 차이 '+str(delta)+'원. 허용범위 내 차이도 검토합니다',ref,False)
    for k,r in contracts.items():
        cancelled(event);b=books[k];a,end,total=parsed[k];method=r['배분방법'];prior=earned(total,a,end,method,before);cum=earned(total,a,end,method,cut);cur=cum-prior
        vals={f:num(b[f],False) for f in BOOK_FIELDS};text(b['원장근거']);ref=f"용역계약!{r['_row']} / 비용원장!{b['_row']}";p=payments[k]
        beforepaid=sum(v for dt,v,_ in p if dt<start);paid=sum(v for dt,v,_ in p if start<=dt<=cut);afterpaid=sum(v for dt,v,_ in p if cut<dt<=search_end)
        expected={f:0 for f in BOOK_FIELDS}
        if r['구분']=='미지급':
            op=prior-beforepaid;closing=cum-beforepaid-paid
            if op<0 or closing<0:raise AuditError('미지급 계약의 선지급·초과결제는 미지원. 선급 분류·지급 배분 검토 필요')
            if beforepaid+paid+afterpaid>total:issue(iss,'ACC_PAYMENT_EXCESS','계약 전체 지급액이 총공급가액을 초과합니다',ref)
            expected.update(기초부채=op,당기발생비용=cur,당기부채결제=paid,기말부채=closing)
            if vals['기초부채']+vals['당기발생비용']-vals['당기부채결제']!=vals['기말부채']:issue(iss,'ACC_BOOK_ROLL','미지급 원장 기초+발생-결제=기말 불일치',ref)
            if any(vals[f] for f in BOOK_FIELDS[4:]):raise AuditError('미지급 행의 선급 원장 열은 0이어야 합니다')
            metrics['기말미지급비용']+=closing;metrics['당기발생비용']+=cur
            delta=cur-vals['당기발생비용'];closing_delta=closing-vals['기말부채'];safe=op==vals['기초부채'] and paid==vals['당기부채결제'] and delta==closing_delta
            if delta or closing_delta:proposals.append({'비용ID':k,'수정유형':'미지급 계상 검토','차변계정':r['비용계정'] if safe and delta>0 else r['잔액계정'] if safe and delta<0 else '', '대변계정':r['잔액계정'] if safe and delta>0 else r['비용계정'] if safe and delta<0 else '', '금액':abs(delta) if safe else None,'상태':'검토 초안' if safe else '기초·결제 대사 후 결정','원본행':ref})
        else:
            if len(p)!=1 or p[0][1]!=total or p[0][0]>cut or p[0][0]>end:raise AuditError('선급은 기준일까지 총액 1회 지급 계약만 지원. 분할·미지급·환불·변경은 별도')
            if p[0][0]>=start and prior:raise AuditError('전기 용역의 당기 선급 지급은 과거 미지급·기간오류 별도 검토 필요')
            op=total-prior if p[0][0]<start else 0;add=total if start<=p[0][0]<=cut else 0;closing=total-cum
            expected.update(기초선급=op,당기선급지급=add,당기선급상각=cur,기말선급=closing)
            if vals['기초선급']+vals['당기선급지급']-vals['당기선급상각']!=vals['기말선급']:issue(iss,'ACC_BOOK_ROLL','선급 원장 기초+지급-상각=기말 불일치',ref)
            if any(vals[f] for f in BOOK_FIELDS[:4]):raise AuditError('선급 행의 미지급 원장 열은 0이어야 합니다')
            metrics['기말선급비용']+=closing;metrics['당기선급상각']+=cur
            delta=cur-vals['당기선급상각'];safe=op==vals['기초선급'] and add==vals['당기선급지급'] and closing-vals['기말선급']==-delta
            if delta or closing!=vals['기말선급']:proposals.append({'비용ID':k,'수정유형':'선급 상각 검토','차변계정':r['비용계정'] if safe and delta>0 else r['잔액계정'] if safe and delta<0 else '', '대변계정':r['잔액계정'] if safe and delta>0 else r['비용계정'] if safe and delta<0 else '', '금액':abs(delta) if safe else None,'상태':'검토 초안' if safe else '기초·지급 대사 후 결정','원본행':ref})
        for field in BOOK_FIELDS:compare(k,field,expected[field],vals[field],ref)
        summary.append({'비용ID':k,'거래처ID':r['거래처ID'],'구분':r['구분'],'용역시작':a.isoformat(),'용역종료':end.isoformat(),'총공급가액':total,'배분방법':method,'전기까지누적귀속':prior,'기말까지누적귀속':cum,**expected,'후속지급':afterpaid,'비용계정':r['비용계정'],'잔액계정':r['잔액계정'],'원본행':ref})
    for v in metrics.values():num(v)
    account_rows=[{'지표':m,'대상계정':';'.join(scopes[m]),'계산금액':v} for m,v in metrics.items()]
    return result(MODULE,c,{'비용기간배분':summary,'비용원장대사':comparisons,'후속송장검색':invoice_rows,'지급귀속대사':payment_rows,'수정분개검토':proposals,'대상계정집계':account_rows,'원장통제':checks}|{'입력_'+k:v for k,v in t.items()},iss,metrics,{'계산정책':POLICY,'정책근거':c['회계정책근거'],'대상계정':scopes,'후속검색종료일':search_end.isoformat(),'허용오차':tol,'기준참조':'발생주의 및 기말 현재 조건에 대한 후속증거: IAS1 27–28, IAS10 3/8; 감사증거/IPE: ISA500 9. 한국 적용 판본·기간 및 인식판단은 실제 업무에서 확인','지원범위':'KRW 공급가액 기준 확정 용역. 부가세·외화·재고/자산취득·변경/환불·추정충당은 별도. 지급 원천은 계약 전체 이력과 미분류 후속지급, 송장은 전체 후속검색 범위의 독립 추출 필요'})
