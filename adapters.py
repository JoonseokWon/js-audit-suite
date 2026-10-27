"""Existing calculation engines, connected in-process with common immutable results."""
from common import *
from engines.finance import practice_engine as finance
from engines.sales import ledger_engine as sales
from engines.sales.data_io import IMPORT_FIELDS
from engines.assets import engine as assets
from data_controls.reader import read_module_xlsx

MODULES=('원장·리드','금융상품','매출','감가상각','확장검사','리스','대손충당금','재고평가','종업원급여','미기록부채·비용이연','원천증빙','재무제표·주석','계정별증빙연습')
MODULES=MODULES+('GLA','FIA','현금분석')
MODULES=MODULES+ONBOARDING_MODULES
def run(module,path,context,event=None,ledger_result=None):
    if module in ONBOARDING_MODULES:
        from onboarding.integration import run
        return run(module,path,context,ledger_result,event)
    if module in ('GLA','FIA','현금분석'):
        import importlib
        engine=importlib.import_module({'GLA':'gla','FIA':'fia','현금분석':'cash_analytics'}[module])
        out=engine.analyze(path,context,ledger_result,event)
        out['source']={'name':Path(path).name,'sha256':sha(path),'bytes':Path(path).stat().st_size}
        return plain(out)
    if module in ('원천증빙','재무제표·주석','계정별증빙연습'):
        if module=='원천증빙':
            from raw_binding import analyze
            out=analyze(path,context,ledger_result,event)
        elif module=='재무제표·주석':
            from financial_bridge import analyze
            out=analyze(path,context,ledger_result,event)
        else:
            from account_cases import analyze
            out=analyze(path,context,event)
        out['source']={'name':Path(path).name,'sha256':sha(path),'bytes':Path(path).stat().st_size}
        return plain(out)
    if module=='원장·리드':
        import ledger
        tables,source=read_module_xlsx(module,path,ledger.SCHEMA,event)
    else:tables,source=read_module_xlsx(module,path,event=event)
    cancelled(event)
    if module=='원장·리드':
        import ledger
        if set(tables)!=set(ledger.SCHEMA):raise AuditError('원장·리드 입력양식을 사용하세요.')
        # Exact schema was checked in the single value-only read above.
        out=ledger.analyze(tables,event)
    elif module=='금융상품':
        r=finance.reconcile(Path(path),event);iss=[]
        errors={'검증오류','기간오류','계산불가','중복','자료누락','미지원','누락','입력오류'}
        good={'금액일치','기간확인'}
        for f in r.findings:
            if f.status not in good:issue(iss,f.status,f.message,f.references,f.status in errors or f.left is None and f.right is None)
        fs=[{'상태':f.status,'계약':str(f.key),'비교':f.check,'앞금액':f.left,'뒤금액':f.right,'차이':f.difference,'허용오차':f.tolerance,'내용':f.message,'원본행':f.references,'상세':f.details} for f in r.findings]
        metrics={}
        for k,field in [('원금','원금'),('미수이자','이자')]:
            try:metrics[k]=sum(num(x.raw[field]) for x in r.rows if x.sheet=='명세')
            except AuditError:metrics[k]=None
        out=result(module,{'기준일':r.settings['기준일']},{'금융비교':fs,'이자기간':r.period_reports,'차이집계':r.difference_summary}|{'입력_'+k:v for k,v in tables.items()},iss,metrics,{'settings':r.settings,'counts':r.counts})
    elif module=='매출':
        if set(tables)!=set(IMPORT_FIELDS):raise AuditError('매출 양식의 orders, deliveries, invoices, ledger, control 시트가 필요합니다.')
        for role,rows in tables.items():
            if rows and any(f not in rows[0] for f in IMPORT_FIELDS[role]):raise AuditError(role+': 필수 열 누락')
            for r in rows:
                r.update(_source_file=Path(path).name,_sheet=role)
                if role=='control' and isinstance(r.get('extracted_at'),str):r['extracted_at']=r['extracted_at'].lstrip("'")
        r=sales.analyze_with_ledger(tables['orders'],tables['deliveries'],tables['invoices'],tables['ledger'],tables['control'],cutoff_date=context['기준일'],amount_tolerance='0',quantity_tolerance='0',unit_price_tolerance='0')
        iss=[]
        for i in r['issues']:issue(iss,i['reason_code'],i.get('message',''),','.join(i.get('row_ids',[])),i['severity']=='ERROR' or i['reason_code']=='POPULATION_UNVERIFIED')
        out=result(module,{'회사코드':tables['control'][0].get('company_id') if len(tables['control'])==1 else '', '시작일':r['config'].get('period_start'),'기준일':r['config']['cutoff_date']},
                   {'매출대사':r['groups'],'예외':r['issues'],'원본행':r['rows'],'원장양방향대사':r['ledger_reconciliation'],'원장통제':r['population_checks'],'수행검사':r['checks']},iss,
                   {'순매출':sum(num(x['revenue_credit'])-num(x['revenue_debit']) for x in tables['ledger'])},{'summary':r['summary'],'config':r['config']})
        if r['summary']['population_status']!='PASS' and not any(i['severity']=='차단' for i in out['issues']):issue(out['issues'],'POPULATION','매출 원장 모집단 미확인')
    elif module=='감가상각':
        # Original asset reader additionally enforces exact worksheet schema and row trace.
        from engines.assets.data_io import run_file
        r=run_file(path,event);iss=[]
        for i in r['issues']:issue(iss,i['reason_code'],i['message'],i['references'],i['severity']=='ERROR')
        metrics={k:sum(num(g['calculated'][k]) for g in r['groups'] if g['calculated']) for k in ('기말원가','기말누계','당기상각')}
        out=result(module,r['config'],{'자산비교':r['findings'],'자산결과':r['groups'],'월별계산':r['monthly'],'원장통제':r['controls'],'차이집계':r['difference_summary']}|{'입력_'+k:v for k,v in tables.items()},iss,metrics,{'summary':r['summary']})
    elif module=='미기록부채·비용이연':
        import accruals
        tables,source=read_module_xlsx(module,path,accruals.SCHEMA,event)
        out=accruals.analyze(tables,event)
    elif module in ('재고평가','종업원급여'):
        import inventory,payroll
        engine=inventory if module=='재고평가' else payroll
        tables,source=read_module_xlsx(module,path,engine.SCHEMA,event)
        out=engine.analyze(tables,event)
    elif module in ('리스','대손충당금'):
        import leases,ecl
        engine=leases if module=='리스' else ecl
        tables,source=read_module_xlsx(module,path,engine.SCHEMA,event)
        out=engine.analyze(tables,event)
    elif module=='확장검사':
        import extensions
        tables,source=read_module_xlsx(module,path,extensions.SCHEMA,event);out=extensions.analyze(tables,event)
    else:raise AuditError('지원하지 않는 모듈')
    for k in ('회사코드','시작일','기준일'):
        v=out['context'].get(k)
        if v is not None and str(v)!=context[k]:issue(out['issues'],'ENGAGEMENT_SCOPE',k+'가 현재 업무와 다릅니다: '+str(v))
    out['context']=context;out['source']=source;out['blocking']=sum(i['severity']=='차단' for i in out['issues']);out['review']=sum(i['severity']=='검토' for i in out['issues'])
    cancelled(event)
    if sha(path)!=source['sha256']:raise AuditError('검사 중 파일이 변경되었습니다.')
    return plain(out)
