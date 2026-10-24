"""Four restricted procedures. Exact matching only; no invented evidence or valuation."""
from collections import defaultdict,Counter
from common import *
SCHEMA={
 '설정':['항목','값'],
 '은행장부':['계좌','거래ID','일자','참조','금액'],
 '은행거래':['계좌','거래ID','일자','참조','금액'],
 '채권':['채권ID','거래처','발생일','만기일','기말잔액'],
 '후속회수':['회수ID','채권ID','입금일','금액','근거'],
 '발주':['발주행ID','품목','수량','단가'],
 '입고':['입고ID','발주행ID','수량'],
 '매입송장':['송장ID','발주행ID','수량','금액'],
 '장부재고':['창고','품목','단위','수량'],
 '실사':['창고','품목','단위','수량','실사일','근거'],
 '독립통제':['자료','행수','수치합계','절대합계','추출근거']}
CONTROL_FIELDS={'은행장부':'금액','은행거래':'금액','채권':'기말잔액','후속회수':'금액','발주':'수량','입고':'수량','매입송장':'금액','장부재고':'수량','실사':'수량'}
def analyze(t,event=None):
    from ledger import config
    c=config(t);iss=[];outputs={};cutoff=day(c['기준일']);start=day(c['시작일']);controls=[]
    ct={}
    for r in t['독립통제']:
        k=text(r['자료']);text(r['추출근거'])
        if k in ct or k not in CONTROL_FIELDS:issue(iss,'EXT_CONTROL_DUP','중복/미지원 독립통제',k)
        ct[k]=r
    for role,field in CONTROL_FIELDS.items():
        cancelled(event)
        if role not in ct:issue(iss,'EXT_CONTROL_MISSING','독립통제 누락: '+role);continue
        r=ct[role];n=num(r['행수'],False);expected=num(r['수치합계']);actual=sum(num(x[field]) for x in t[role]);absolute=sum(abs(num(x[field])) for x in t[role]);ok=n==len(t[role]) and expected==actual and num(r['절대합계'],False)==absolute
        controls.append({'자료':role,'기대행수':n,'실제행수':len(t[role]),'기대수치합계':expected,'실제수치합계':actual,'기대절대합계':num(r['절대합계'],False),'실제절대합계':absolute,'상태':'일치' if ok else '불일치','근거':r['추출근거']})
        if not ok:issue(iss,'EXT_CONTROL','행수/부호합계 불일치: '+role)
    if not any(t[k] for k in CONTROL_FIELDS):issue(iss,'EXT_EMPTY','확장검사 자료가 모두 비었습니다.')
    # Key collisions are explicit blockers; no arbitrary first match or silent aggregation.
    key_fields={'은행장부':('거래ID',),'은행거래':('거래ID',),'채권':('채권ID',),'후속회수':('회수ID',),'발주':('발주행ID',),'입고':('입고ID',),'매입송장':('송장ID',),'장부재고':('창고','품목'),'실사':('창고','품목')}
    duplicates=set()
    for role,fields in key_fields.items():
        keys=[tuple(text(r[f],f) for f in fields) for r in t[role]]
        for k,count in Counter(keys).items():
            if count>1:issue(iss,'EXT_DUP',role+' 키 중복: '+str(k));duplicates.add(role)
    def ref(role,r):return f"{role}!{r['_row']}"
    bidx=[]
    for role in ('은행장부','은행거래'):
        index=defaultdict(list)
        for r in t[role]:
            dt=day(r['일자']);account=text(r['계좌']);reference=text(r['참조']);amount=num(r['금액'])
            if not start<=dt<=cutoff:issue(iss,'EXT_PERIOD','은행거래 기간 밖',ref(role,r))
            index[(account,dt.isoformat(),reference,amount)].append(r)
        bidx.append(index)
    bank=[]
    for k in sorted(set(bidx[0])|set(bidx[1])):
        a,b=bidx[0].get(k,[]),bidx[1].get(k,[]);ok=len(a)==len(b)==1 and not {'은행장부','은행거래'}&duplicates
        row={'계좌':k[0],'일자':k[1],'참조':k[2],'금액':k[3],'장부행수':len(a),'은행행수':len(b),'상태':'정확대사' if ok else '미대사/모호','원본행':','.join([ref('은행장부',r) for r in a]+[ref('은행거래',r) for r in b])};bank.append(row)
        if not ok:issue(iss,'BANK_UNMATCHED','은행거래 미대사/모호',row['원본행'],False)
    outputs['은행거래대사']=bank
    receipt=defaultdict(list);ar=[];known={r['채권ID'] for r in t['채권']}
    for r in t['후속회수']:
        text(r['근거']);amount=num(r['금액'],False)
        if day(r['입금일'])<=cutoff:issue(iss,'RECEIPT_PERIOD','후속회수는 기준일 후 입금 필요',ref('후속회수',r))
        if r['채권ID'] not in known:issue(iss,'RECEIPT_ORPHAN','연결 채권 없음',ref('후속회수',r))
        receipt[r['채권ID']].append(r)
    for r in t['채권']:
        bal=num(r['기말잔액'],False);due=day(r['만기일']);born=day(r['발생일']);text(r['거래처']);days=(cutoff-due).days;rs=receipt[r['채권ID']];recovered=sum(num(x['금액'],False) for x in rs)
        if born>cutoff or born>due:issue(iss,'AR_DATE','채권 발생일/만기일 오류',ref('채권',r))
        if recovered>bal:issue(iss,'AR_OVERRECOVERY','기말채권보다 큰 회수: 충당 관계 확인',ref('채권',r),False)
        bucket='미연체' if days<=0 else '1~30일' if days<=30 else '31~60일' if days<=60 else '61~90일' if days<=90 else '90일초과'
        ar.append({'채권ID':r['채권ID'],'거래처':r['거래처'],'기말잔액':bal,'연체일수':max(0,days),'연령구간':bucket,'후속회수':recovered,'잔여':bal-recovered,'원본행':ref('채권',r)+','+','.join(ref('후속회수',x) for x in rs)})
    outputs['채권연령후속회수']=ar
    orders={r['발주행ID']:r for r in t['발주']};rec=defaultdict(list);inv=defaultdict(list)
    for r in t['입고']:num(r['수량'],False);rec[text(r['발주행ID'])].append(r)
    for r in t['매입송장']:num(r['수량'],False);num(r['금액'],False);inv[text(r['발주행ID'])].append(r)
    purchase=[]
    for k in sorted(set(orders)|set(rec)|set(inv)):
        o=orders.get(k);rs=rec[k];vs=inv[k];oq=num(o['수량'],False) if o else None;price=num(o['단가'],False) if o else None
        if o:text(o['품목'])
        rq=sum(num(r['수량'],False) for r in rs);iq=sum(num(r['수량'],False) for r in vs);amount=sum(num(r['금액'],False) for r in vs)
        ok=o is not None and bool(rs) and bool(vs) and oq==rq==iq and amount==price*iq and not {'발주','입고','매입송장'}&duplicates
        refs=','.join(([ref('발주',o)] if o else [])+[ref('입고',r) for r in rs]+[ref('매입송장',r) for r in vs])
        purchase.append({'발주행ID':k,'발주수량':oq,'입고수량':rq,'송장수량':iq,'송장금액':amount,'발주단가':price,'상태':'수치일치' if ok else '추가검토','원본행':refs})
        if not ok:issue(iss,'PURCHASE_REVIEW','발주/입고/송장 차이·누락 (미청구입고 포함)',refs,False)
    outputs['매입3자대사']=purchase
    stock={tuple(r[f] for f in ('창고','품목')):r for r in t['장부재고']};counts={tuple(r[f] for f in ('창고','품목')):r for r in t['실사']};inventory=[]
    for k in sorted(set(stock)|set(counts)):
        a,b=stock.get(k),counts.get(k);av=num(a['수량'],False) if a else None;bv=num(b['수량'],False) if b else None
        if b:
            text(b['근거'])
            if day(b['실사일'])!=cutoff:issue(iss,'COUNT_DATE','기준일 당일 실사만 지원; 기말이동 별도 필요',ref('실사',b))
        ok=a is not None and b is not None and text(a['단위'])==text(b['단위']) and av==bv and not {'장부재고','실사'}&duplicates
        refs=','.join(([ref('장부재고',a)] if a else [])+([ref('실사',b)] if b else []))
        inventory.append({'창고':k[0],'품목':k[1],'장부수량':av,'실사수량':bv,'차이':bv-av if a and b else None,'상태':'수량일치' if ok else '차이/누락','원본행':refs})
        if not ok:issue(iss,'INVENTORY_REVIEW','실사 수량·단위 차이 또는 누락',refs,False)
    outputs['재고실사대사']=inventory;outputs['확장자료통제']=controls
    outputs.update({'입력_'+k:v for k,v in t.items()})
    return result('확장검사',c,outputs,iss)
