"""Independent gross GL controls, signed TB reconciliation, lead schedule and JE screening."""
from collections import defaultdict,Counter
from common import *
SCHEMA={
 '설정':['항목','값'],
 '시산표':['회사코드','계정코드','계정명','기초잔액','당기차변','당기대변','기말잔액'],
 '총계정원장':['회사코드','전표ID','행ID','전기일','계정코드','차변','대변','적요','작성자'],
 '계정매핑':['계정코드','리드코드','리드명','표시구분'],
 '독립통제':['회사코드','시작일','기준일','계정코드','원장행수','차변합계','대변합계','기초잔액','기말잔액','추출근거','추출일시','작성자'],
 '감사조정':['조정ID','행ID','계정코드','차변','대변','근거','상태'],
 '모듈연결':['모듈','지표','계정코드','비교기준','부호']}
METRICS={'미기록부채·비용이연':['기말미지급비용','당기발생비용','기말선급비용','당기선급상각'],'금융상품':['원금','미수이자'],'매출':['순매출'],'감가상각':['기말원가','기말누계','당기상각'],'리스':['기말리스부채','기말사용권자산','당기리스이자','당기사용권상각'],'대손충당금':['기말채권잔액','기말대손충당금','당기대손상각비'],'재고평가':['기말재고원가','기말재고평가충당금','기말재고순액','당기재고평가손실'],'종업원급여':['당기급여비용','당기급여배부원가','기말미지급급여','당기DC비용','당기DC배부원가','기말DC미지급','당기연차비용','당기연차배부원가','기말연차부채']}
def config(t):
    rows=t['설정'];c={r['항목']:r['값'] for r in rows}
    if len(c)!=len(rows) or set(c)!={'회사코드','시작일','기준일','통화','추출범위'}:raise AuditError('설정 누락·중복·미지원')
    c={k:text(v,k) for k,v in c.items()}
    if c['통화']!='KRW' or day(c['시작일'])>day(c['기준일']):raise AuditError('KRW 및 올바른 기간 필요')
    return c
def analyze(t,event=None):
    c=config(t);iss=[];checks=[];lead=[];journal=[];cross=[]
    def check(name,expected,actual,ref):
        ok=expected==actual
        checks.append({'검사':name,'기대':expected,'실제':actual,'차이':actual-expected,'상태':'일치' if ok else '불일치','근거':ref})
        if not ok:issue(iss,'LEDGER_CONTROL',name+' 불일치',ref)
    tb={};mp={};ctl={};gl=defaultdict(lambda:[0,0,0]);j=defaultdict(list);unique=set()
    for role in ('시산표','총계정원장','계정매핑','독립통제','감사조정','모듈연결'):
        for r in t[role]:
            cancelled(event);ref=f"{role}!{r['_row']}"
            if '회사코드' in r and r['회사코드']!=c['회사코드']:issue(iss,'COMPANY','회사코드가 업무와 다릅니다.',ref)
    for r in t['시산표']:
        k=text(r['계정코드'],'계정코드');text(r['계정명'],'계정명')
        if k in tb:issue(iss,'TB_DUP','시산표 계정 중복',f"시산표!{r['_row']}");continue
        x=[num(r[f],f not in ('당기차변','당기대변')) for f in ('기초잔액','당기차변','당기대변','기말잔액')];tb[k]=(r,x)
        check(k+' TB 변동',x[3],x[0]+x[1]-x[2],f"시산표!{r['_row']}")
    if not tb or not t['총계정원장']:issue(iss,'EMPTY','시산표·전체 원장 모집단이 비어 있습니다.')
    for r in t['계정매핑']:
        k=text(r['계정코드']);text(r['리드코드']);text(r['리드명'])
        if k in mp:issue(iss,'MAP_DUP','계정 중복 매핑',k)
        if r['표시구분'] not in ('BS','PL'):issue(iss,'MAP_TYPE','표시구분 BS/PL 필요',k)
        mp[k]=r
    lead_names=defaultdict(set)
    for r in mp.values():lead_names[r['리드코드']].add((r['리드명'],r['표시구분']))
    if any(len(v)>1 for v in lead_names.values()):issue(iss,'LEAD_CLASS_CONFLICT','같은 리드코드의 리드명/BS·PL 구분이 다릅니다.')
    for r in t['총계정원장']:
        k=text(r['계정코드']);jid=text(r['전표ID']);line=text(r['행ID']);text(r['작성자']);d=num(r['차변'],False);cr=num(r['대변'],False);dt=day(r['전기일']);ref=f"총계정원장!{r['_row']}"
        if d and cr:issue(iss,'BOTH_SIDES','동일 행 차대 동시 양수',ref)
        if not day(c['시작일'])<=dt<=day(c['기준일']):issue(iss,'PERIOD','통제기간 밖 전표행',ref)
        ident=(r['회사코드'],jid,line)
        if ident in unique:issue(iss,'GL_DUP','전표ID+행ID 중복',ref)
        unique.add(ident);gl[k][0]+=1;gl[k][1]+=d;gl[k][2]+=cr;j[jid].append((d,cr,r))
        if dt.weekday()>=5:journal.append({'전표ID':jid,'사유':'주말 전기일','금액':d+cr,'원본행':ref})
        if not r['적요']:journal.append({'전표ID':jid,'사유':'적요 공란','금액':d+cr,'원본행':ref})
    for jid,rs in j.items():
        if sum(d-cr for d,cr,_ in rs):issue(iss,'JE_UNBALANCED','전표 단위 차대 불일치: '+jid,','.join(str(r['_row']) for _,_,r in rs))
    for r in t['독립통제']:
        k=text(r['계정코드']);ref=f"독립통제!{r['_row']}";text(r['추출근거']);text(r['작성자'])
        if k in ctl:issue(iss,'CONTROL_DUP','독립통제 계정 중복',ref)
        if r['시작일']!=c['시작일'] or r['기준일']!=c['기준일']:issue(iss,'CONTROL_PERIOD','독립통제 기간 불일치',ref)
        try:
            stamp=datetime.fromisoformat(str(r['추출일시']).lstrip("'"))
            if stamp.tzinfo is None or stamp.date()<day(c['기준일']):raise ValueError()
        except ValueError:issue(iss,'CONTROL_TIME','기준일 이후 시간대 포함 추출시각 필요',ref)
        ctl[k]=r
    accounts=set(tb)|set(gl)|set(ctl)|set(mp)
    declared=c['추출범위'].split(';')
    if len(declared)!=len(set(declared)) or not all(declared) or set(declared)!=accounts:issue(iss,'EXTRACTION_SCOPE','독립 추출범위 계정 목록과 입력 계정 집합이 다릅니다.')
    for k in sorted(accounts):
        if k not in tb or k not in ctl or k not in mp:issue(iss,'ACCOUNT_SCOPE','TB·매핑·독립통제 범위 불일치: '+k);continue
        r,x=tb[k];g=gl[k];control=ctl[k];ref=f"독립통제!{control['_row']} / 시산표!{r['_row']}"
        for name,expected,actual in [('행수',num(control['원장행수'],False),g[0]),('차변',num(control['차변합계'],False),g[1]),('대변',num(control['대변합계'],False),g[2]),('TB 차변',x[1],g[1]),('TB 대변',x[2],g[2]),('기초잔액',num(control['기초잔액']),x[0]),('기말잔액',num(control['기말잔액']),x[3])]:check(k+' '+name,expected,actual,ref)
    if tb:
        for name,actual in [('기초 차대',sum(x[0] for _,x in tb.values())),('기말 차대',sum(x[3] for _,x in tb.values())),('당기 차대',sum(x[1]-x[2] for _,x in tb.values()))]:check(name,0,actual,'시산표 전체')
    adjustment=defaultdict(int);aj=defaultdict(list);ai=set()
    for r in t['감사조정']:
        ident=(text(r['조정ID']),text(r['행ID']));k=text(r['계정코드']);text(r['근거']);d=num(r['차변'],False);cr=num(r['대변'],False)
        if ident in ai:issue(iss,'AJE_DUP','감사조정 행 중복',str(ident))
        ai.add(ident)
        if k not in tb or r['상태'] not in ('승인','초안') or (d and cr):issue(iss,'AJE_INVALID','조정 계정·상태·차대 오류',str(ident))
        aj[ident[0]].append((r,d,cr))
    for jid,rs in aj.items():
        if sum(d-cr for _,d,cr in rs) or len({r['상태'] for r,_,_ in rs})!=1:issue(iss,'AJE_UNBALANCED','조정별 차대/상태 불일치: '+jid);continue
        if rs[0][0]['상태']=='승인':
            for r,d,cr in rs:adjustment[r['계정코드']]+=d-cr
        else:issue(iss,'AJE_DRAFT','초안 조정 미반영: '+jid,blocking=False)
    for k,(r,x) in sorted(tb.items()):
        m=mp.get(k,{})
        lead.append({'계정코드':k,'계정명':r['계정명'],'리드코드':m.get('리드코드','미매핑'),'리드명':m.get('리드명','미매핑'),'표시구분':m.get('표시구분',''),'기초잔액':x[0],'차변':x[1],'대변':x[2],'조정전':x[3],'승인조정':adjustment[k],'조정후':x[3]+adjustment[k],'원본행':f"시산표!{r['_row']}"})
    seen=set()
    for r in t['모듈연결']:
        mod=r['모듈'];metric=r['지표'];k=r['계정코드'];basis=r['비교기준'];factor=num(r['부호']);identity=(mod,metric,k)
        if identity in seen or mod not in METRICS or metric not in METRICS.get(mod,[]) or k not in tb or basis not in ('기말잔액','당기순변동') or factor not in (-1,1):issue(iss,'BIND_INVALID','모듈 연결 설정 오류',f"모듈연결!{r['_row']}");continue
        seen.add(identity);x=tb[k][1];cross.append({'모듈':mod,'지표':metric,'계정코드':k,'비교기준':basis,'부호':factor,'기대금액':(x[3] if basis=='기말잔액' else x[1]-x[2])*factor,'원본행':f"모듈연결!{r['_row']}"})
    summary={}
    for r in lead:
        k=r['리드코드'];s=summary.setdefault(k,{'리드코드':k,'리드명':r['리드명'],'표시구분':r['표시구분'],'계정수':0,**{f:0 for f in ('기초잔액','차변','대변','조정전','승인조정','조정후')}});s['계정수']+=1
        for f in ('기초잔액','차변','대변','조정전','승인조정','조정후'):s[f]+=r[f]
    if journal:issue(iss,'JE_CANDIDATE',f'전표 검토후보 {len(journal)}건 (부정 확정 아님)',blocking=False)
    return result('원장·리드',c,{'원장통제':checks,'리드스케줄':lead,'리드집계':list(summary.values()),'전표검토후보':journal,'모듈연결':cross}|{'입력_'+k:v for k,v in t.items()},iss)
