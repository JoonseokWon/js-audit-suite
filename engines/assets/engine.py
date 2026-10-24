"""Independent KRW cost-model audit assistant. No upstream source is incorporated."""
from collections import Counter,defaultdict
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP,localcontext
from pathlib import Path
import calendar,hashlib,json,re

VERSION='asset-audit-1.0'
METHODS=('정액법','정률법','이중체감법','연수합계법','생산량비례법')
METRICS=('전기말원가','전기말누계','당기상각','기말원가','기말누계')
SCHEMA={
 '설정':('항목','값'),
 '자산':('회사코드','자산ID','자산명','분류','취득일','사용가능일','취득원가','잔존가치','내용월수','상각방법','연상각률','총예정생산량','처분일','처분대가',*METRICS,'근거문서'),
 '변경':('회사코드','자산ID','적용월','추가원가','잔여내용월수','변경잔존가치','변경방법','변경연상각률','근거문서'),
 '생산량':('회사코드','자산ID','월','생산량','근거문서'),
 '원장':('회사코드','자산ID',*METRICS,'근거문서'),
 '통제':('회사코드','시작일','기준일','대상계정범위','원장행수',*METRICS,'추출근거','추출일시','작성자')}
SETTINGS=('회사코드','시작일','기준일','개시월','처분월','허용오차','정책근거','모형범위')
MAX_MONEY=Decimal('1000000000000')
class InputError(ValueError):pass
def dec(value,label='금액',integer=False):
    if value is None or isinstance(value,bool):raise InputError(label+': 필수 숫자 누락')
    s=str(value).strip()
    if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?',s):raise InputError(label+': 숫자 형식 오류')
    d=Decimal(s.replace(',',''))
    if not d.is_finite() or d<0 or d>MAX_MONEY or (integer and d!=d.to_integral_value()):raise InputError(label+': 지원 범위 밖 숫자')
    return d
def money(v,label='금액'):return dec(v,label,True)
def text(v,label='값'):
    if v is None or not str(v).strip() or len(str(v))>500:raise InputError(label+': 필수 텍스트 누락/길이 오류')
    return str(v).strip()
def day(v,label='날짜'):
    if isinstance(v,datetime):v=v.date()
    if isinstance(v,date):d=v
    else:
        try:d=date.fromisoformat(text(v,label))
        except ValueError as e:raise InputError(label+': YYYY-MM-DD 날짜 필요') from e
    if not 1900<=d.year<=2100:raise InputError(label+': 1900~2100 지원')
    return d
def month(v):
    s=text(v,'월')
    if not re.fullmatch(r'\d{4}-\d{2}',s):raise InputError('월: YYYY-MM 필요')
    return idx(day(s+'-01'))
def idx(d):return d.year*12+d.month-1
def ym(i):return f'{i//12:04d}-{i%12+1:02d}'
def rounded(d):return d.quantize(Decimal(1),rounding=ROUND_HALF_UP)
def plain(v):
    if isinstance(v,Decimal):return format(v,'f')
    if isinstance(v,(date,datetime)):return v.isoformat()
    if isinstance(v,dict):return {k:plain(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)):return [plain(x) for x in v]
    return v

def settings(table):
    pairs=table['설정'];keys=[r['항목'] for r in pairs]
    if set(keys)!=set(SETTINGS) or len(keys)!=len(set(keys)):raise InputError('설정 항목 누락/중복/미지원')
    c={r['항목']:r['값'] for r in pairs};c['회사코드']=text(c['회사코드']);c['정책근거']=text(c['정책근거'])
    c['시작일']=day(c['시작일']);c['기준일']=day(c['기준일'])
    if c['시작일']!=date(c['기준일'].year,1,1):raise InputError('시작일은 기준연도 1월 1일이어야 합니다.')
    if c['기준일'].day!=calendar.monthrange(c['기준일'].year,c['기준일'].month)[1]:raise InputError('기준일은 월말이어야 합니다.')
    if c['개시월'] not in ('당월','익월') or c['처분월'] not in ('포함','제외'):raise InputError('월할 정책: 개시월 당월/익월, 처분월 포함/제외 필요')
    c['허용오차']=money(c['허용오차'])
    if c['허용오차'] not in (0,1):raise InputError('허용오차는 0원 또는 1원만 지원합니다.')
    if c['모형범위']!='원가모형-손상등없음':raise InputError('손상·재평가·매각예정·비한정 자산 등은 현재 미지원입니다.')
    return c

def _method(method,life,rate):
    if method not in METHODS:raise InputError('상각방법 미지원: '+str(method))
    if method!='생산량비례법' and (life is None or life<1 or life>1200):raise InputError('내용월수: 1~1200 필요')
    if method in ('이중체감법','연수합계법') and life%12:raise InputError(method+': 12의 배수 내용월수 필요')
    if method=='정률법' and (rate is None or not 0<rate<1):raise InputError('정률법 연상각률: 0~1 사이 소수 필요')

def calculate_asset(a,events,production,c,cancel=None):
    """Monthly rounding; annual opening-book-value rate. Changes take effect at month start."""
    acq=day(a['취득일']);available=day(a['사용가능일']);cost=money(a['취득원가']);salvage=money(a['잔존가치'])
    if cost<=0 or available<acq:raise InputError('양수 취득원가 및 취득일 이후 사용가능일 필요')
    if a['분류'] not in ('유형','무형-유한'):raise InputError('원가모형 유형/유한내용 무형만 지원 (토지·비한정·재평가·손상 등은 별도 검토)')
    method=text(a['상각방법']);life=int(money(a['내용월수'])) if a['내용월수'] not in (None,'') else None
    rate=dec(a['연상각률']) if a['연상각률'] not in (None,'') else None
    _method(method,life,rate)
    units=dec(a['총예정생산량']) if a['총예정생산량'] not in (None,'') else None
    if method=='생산량비례법' and (units is None or units<=0):raise InputError('생산량비례법 총예정생산량 필수')
    disposal=day(a['처분일']) if a['처분일'] not in (None,'') else None
    proceeds=money(a['처분대가']) if a['처분대가'] not in (None,'') else None
    if bool(disposal)!=(proceeds is not None) or (disposal and disposal<acq):raise InputError('처분일·대가 함께 필요, 취득 전 처분 불가')
    text(a['근거문서'],'자산 근거문서')
    start=idx(available)+(c['개시월']=='익월');end=idx(c['기준일']);prior=idx(c['시작일'])-1
    if end-idx(acq)>1200:raise InputError('취득 이후 1200개월 범위 초과')
    stop=idx(disposal)-(c['처분월']=='제외') if disposal else end
    if events and method=='생산량비례법':raise InputError('생산량비례법 변경 이벤트는 현재 미지원')
    if production and method!='생산량비례법':raise InputError('비생산량법 자산에 생산량 입력')
    parsed={}
    for e in events:
        when=month(e['적용월']);text(e['근거문서'],'변경 근거')
        if when<start or (disposal and when>stop):raise InputError('변경월은 상각개시 이후·상각대상 처분월 이내여야 합니다.')
        if when in parsed:raise InputError('같은 자산·월 변경 중복 (동시 변경은 한 행에 입력)')
        add=money(e['추가원가']);newlife=int(money(e['잔여내용월수'])) if e['잔여내용월수'] not in (None,'') else None
        newsalvage=money(e['변경잔존가치']) if e['변경잔존가치'] not in (None,'') else None
        newmethod=e['변경방법'] or method
        newrate=dec(e['변경연상각률']) if e['변경연상각률'] not in (None,'') else None
        if newmethod=='생산량비례법':raise InputError('생산량비례법으로 변경 미지원')
        if not add and all(e[f] in (None,'') for f in ('잔여내용월수','변경잔존가치','변경방법','변경연상각률')):raise InputError('변경 내용 없음')
        parsed[when]=(add,newlife,newsalvage,e['변경방법'],newrate,e['_ref'])
    prod={}
    for p in production:
        when=month(p['월']);text(p['근거문서'],'생산량 근거')
        if when in prod:raise InputError('동일 자산·월 생산량 중복')
        if when<start or when>min(stop,end):raise InputError('생산량이 상각 대상월 밖입니다.')
        prod[when]=dec(p['생산량'])
    if method=='생산량비례법' and set(prod)!=set(range(start,min(stop,end)+1)):raise InputError('월별 생산량 누락 (0생산도 0으로 명시)')
    book=cost;accum=Decimal(0);current=Decimal(0);rows=[];cumulative_units=Decimal(0)
    prior_cost=cost if acq<=date(c['기준일'].year-1,12,31) else Decimal(0);prior_accum=Decimal(0)
    acquisition_current=cost if c['시작일']<=acq<=c['기준일'] else Decimal(0);capex_current=Decimal(0)
    disposal_cost=Decimal(0);disposal_accum=Decimal(0)
    close_cost=cost if acq<=c['기준일'] else Decimal(0);close_accum=Decimal(0)
    origin=start;end_life=start+(life or 1200)-1;basis=cost;annual_amount=None;rate_year=None;disposal_nb=None
    for m in range(start,end+1):
        if cancel is not None and cancel.is_set():raise InputError('취소됨')
        if m>stop:break
        add=Decimal(0);eventref=''
        if m in parsed:
            add,nlife,nsalv,nmethod,nrate,eventref=parsed[m]
            book+=add;cost+=add;basis=book;origin=m
            if m<=prior:prior_cost+=add
            else:capex_current+=add
            close_cost+=add
            if nlife is not None:end_life=m+nlife-1
            if nsalv is not None:salvage=nsalv
            if nmethod:method=nmethod
            if nrate is not None:rate=nrate
            life=end_life-m+1;_method(method,life,rate);annual_amount=None;rate_year=None
        opening=book;raw=Decimal(0)
        if m<=end_life and book>salvage:
            remaining=book-salvage
            with localcontext() as context:
                context.prec=50
                if method=='정액법':raw=max(basis-salvage,Decimal(0))/Decimal(end_life-origin+1)
                elif method in ('정률법','이중체감법'):
                    if rate_year!=m//12:
                        annual_amount=book*(rate if method=='정률법' else Decimal(24)/Decimal(life));rate_year=m//12
                    raw=annual_amount/12
                elif method=='연수합계법':
                    years=Decimal(life)/12;year_index=(m-origin)//12
                    raw=max(basis-salvage,Decimal(0))*(years-year_index)/(years*(years+1)/2)/12
                else:
                    cumulative_units+=prod[m]
                    if cumulative_units>units:raise InputError('누적 생산량이 총예정생산량 초과')
                    raw=max(basis-salvage,Decimal(0))*prod[m]/units
                dep=min(rounded(raw),remaining)
                # Finite time-based useful life: allocate the residual rounding/tail at expiry.
                if method!='생산량비례법' and m==end_life:dep=remaining
        else:
            dep=Decimal(0)
            if method=='생산량비례법':
                cumulative_units+=prod[m]
                if cumulative_units>units:raise InputError('누적 생산량이 총예정생산량 초과')
        book-=dep;accum+=dep
        if m<=prior:prior_accum=accum
        else:current+=dep
        close_accum=accum
        rows.append({'월':ym(m),'방법':method,'월초장부':opening-add,'추가원가':add,'상각기준장부':opening,'잔존가치':salvage,'계산전상각':raw,'월상각':dep,'누계':accum,'월말장부':book,'변경근거':eventref})
    if disposal and disposal<=c['기준일']:
        if disposal>=c['시작일']:disposal_cost=close_cost;disposal_accum=accum
        disposal_nb=book;close_cost=Decimal(0);close_accum=Decimal(0)
        if disposal<c['시작일']:prior_cost=Decimal(0);prior_accum=Decimal(0)
    # Before use, recognised historical cost remains, without depreciation.
    return {'전기말원가':prior_cost,'전기말누계':prior_accum,'당기상각':current,'기말원가':close_cost,'기말누계':close_accum,
            '기말장부':close_cost-close_accum,'처분직전장부':disposal_nb,'처분손익':proceeds-disposal_nb if disposal_nb is not None and disposal>=c['시작일'] else None,
            '당기취득원가':acquisition_current,'당기추가원가':capex_current,'당기처분원가':disposal_cost,'당기처분누계':disposal_accum,
            'schedule':rows}

def analyze(tables,source=None,cancel=None):
    c=settings(tables);issues=[];findings=[];groups=[];monthly=[]
    rows=[]
    for sheet in SCHEMA:
        for i,raw in enumerate(tables[sheet],2):
            number=raw.get('_source_row',i)
            rows.append({'row_id':f'{sheet}!{number}','sheet':sheet,'source_row':number,'raw':{k:raw.get(k) for k in SCHEMA[sheet]}})
    def issue(code,detail,key='',severity='ERROR',refs=''):
        issues.append({'severity':severity,'reason_code':code,'key':key,'message':detail,'references':refs})
    index={name:defaultdict(list) for name in ('자산','변경','생산량','원장')}
    for row in rows:
        name=row['sheet'];raw=row['raw']
        if name not in index:continue
        try:
            company=text(raw['회사코드'],'회사코드');aid=text(raw['자산ID'],'자산ID')
            if company!=c['회사코드']:raise InputError('설정 회사와 불일치')
            index[name][(company,aid)].append({**raw,'_ref':row['row_id']})
        except InputError as e:issue('INPUT_INVALID',str(e),refs=row['row_id'])
    # Independent ERP export controls; rows/each gross metric are compared without netting.
    controls=[];control_ok=True
    try:
        if len(tables['통제'])!=1:raise InputError('통제 시트는 독립 추출근거 1행 필요')
        ctrl=tables['통제'][0]
        for f in ('대상계정범위','추출근거','추출일시','작성자'):text(ctrl[f],f)
        stamp=datetime.fromisoformat(str(ctrl['추출일시']).removeprefix("'"))
        if stamp.tzinfo is None or stamp.date()<c['기준일']:raise InputError('추출일시는 기준일 이후 시간대 포함 ISO 시각 필요')
        if ctrl['회사코드']!=c['회사코드'] or day(ctrl['시작일'])!=c['시작일'] or day(ctrl['기준일'])!=c['기준일']:raise InputError('통제 회사/기간 불일치')
        for field in ('원장행수',*METRICS):
            expected=money(ctrl[field],field)
            actual=Decimal(len(tables['원장'])) if field=='원장행수' else sum((money(r[field],field) for r in tables['원장']),Decimal(0))
            ok=expected==actual;control_ok &= ok
            controls.append({'검사':field,'기대':expected,'실제':actual,'차이':actual-expected,'상태':'PASS' if ok else 'FAIL','근거':ctrl['추출근거']})
        if not control_ok:raise InputError('원장 행수/금액의 독립 통제합계 불일치')
    except (InputError,ValueError,TypeError) as e:
        control_ok=False;issue('POPULATION_CONTROL_FAILED',str(e),refs='통제!2')
    if not tables['자산']:issue('EMPTY_POPULATION','자산대장 없음')
    population_ok=control_ok and not any(i['severity']=='ERROR' for i in issues)
    keys=set().union(*(set(x) for x in index.values()))
    for key in sorted(keys):
        if cancel is not None and cancel.is_set():raise InputError('취소됨')
        label=' / '.join(key);start_issues=len(issues);aset=index['자산'][key];ledger=index['원장'][key]
        refs=', '.join(r['_ref'] for name in index for r in index[name].get(key,[]))
        g={'key':label,'asset_id':key[1],'name':aset[0].get('자산명','') if aset else '', 'status':'일치','references':refs,'calculated':None};groups.append(g)
        if len(aset)!=1 or len(ledger)!=1:
            issue('KEY_MISSING_OR_DUPLICATE','자산/원장 정확키는 각각 1행 필요 (누락·중복 차단)',label,refs=refs)
            g['status']='오류';continue
        a=aset[0];l=ledger[0]
        try:
            text(a['자산명']);text(l['근거문서'],'원장 근거')
            calculated=calculate_asset(a,index['변경'][key],index['생산량'][key],c,cancel)
            for field in METRICS:
                av=money(a[field],field);lv=money(l[field],field);cv=calculated[field]
                for check,left,right in (('대장-원장 '+field,av,lv),('재계산-대장 '+field,cv,av)):
                    diff=left-right;tol=c['허용오차'] if field in ('당기상각','전기말누계','기말누계') else Decimal(0)
                    status='일치' if diff==0 else '반올림차이' if abs(diff)<=tol else '차이'
                    findings.append({'key':label,'check':check,'left':left,'right':right,'difference':diff,'tolerance':tol,'status':status,'references':refs})
                    if diff:issue('ROUNDING_DIFFERENCE' if abs(diff)<=tol else 'AMOUNT_DIFFERENCE',check+': '+str(diff)+'원',label,'WARN',refs)
            g['calculated']={k:v for k,v in calculated.items() if k!='schedule'}
            if money(a['잔존가치'])>=money(a['취득원가']):issue('ESTIMATE_REVIEW','잔존가치가 원가 이상: 0원 상각의 추정 근거를 별도 검토',label,'WARN',refs)
            if calculated['기말원가'] and calculated['기말장부']==0 and not a['처분일']:issue('ESTIMATE_REVIEW','완전상각 후 보유: 내용연수·사용상태 추정 재검토 후보 (자동 오류 판정 아님)',label,'WARN',refs)
            for r in calculated['schedule']:monthly.append({'자산키':label,**r})
            if len(monthly)>200000:raise InputError('월별 계산행 200,000개 한도 초과. 모집단을 나누세요.')
            if not population_ok:issue('POPULATION_UNVERIFIED','독립 원장 통제/입력 모집단 검증이 완료되지 않음',label,refs=refs)
        except (InputError,ValueError,InvalidOperation,TypeError,KeyError) as e:issue('INPUT_OR_SCOPE_ERROR',str(e),label,refs=refs)
        own=issues[start_issues:]
        g['status']='오류' if any(i['severity']=='ERROR' for i in own) else '검토' if own else '일치'
    totals={}
    for f in findings:
        t=totals.setdefault(f['check'],{'비교':f['check'],'건수':0,'차이건수':0,'부호합계':Decimal(0),'절대합계':Decimal(0)})
        t['건수']+=1;t['차이건수']+=int(f['difference']!=0);t['부호합계']+=f['difference'];t['절대합계']+=abs(f['difference'])
    return {'version':VERSION,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'config':plain(c),'rows':plain(rows),'groups':plain(groups),'findings':plain(findings),
            'issues':issues,'monthly':plain(monthly),'controls':plain(controls),'difference_summary':plain(list(totals.values())),
            'source':source or {},'summary':{'자산수':len(groups),'입력행':len(rows),'월별행':len(monthly),'모집단':'PASS' if population_ok else 'FAIL',
            **dict(Counter(g['status'] for g in groups)),'오류건수':sum(i['severity']=='ERROR' for i in issues),'차이':sum(f['difference']!=0 for f in findings)}}
