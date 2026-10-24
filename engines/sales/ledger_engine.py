"""Invoice/revenue-ledger bidirectional tie-out with independent population controls."""
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, localcontext
from .data_io import IMPORT_FIELDS, MAX_ROWS
from .match_engine import analyze as evidence_analyze, _d, _date, _s, _fmt

def analyze_with_ledger(orders,deliveries,invoices,ledger=None,control=None,**params):
    with localcontext() as ctx:
        ctx.prec=60
        return _analyze(orders,deliveries,invoices,ledger,control,**params)

def _analyze(orders,deliveries,invoices,ledger,control,**params):
    if ledger is None or control is None:raise ValueError('독립 매출원장과 원장통제 자료가 모두 필요합니다.')
    if len(ledger)>MAX_ROWS or len(control)>MAX_ROWS:raise ValueError('자료별 1,000행 한도를 초과합니다.')
    amount=_d(params.get('amount_tolerance','1'));price=_d(params.get('unit_price_tolerance','0.01'))
    if amount not in (0,1) or not 0<=price<=Decimal('0.01'):
        raise ValueError('v2 금액 허용오차는 0/1원, 단가 허용오차는 0~0.01원입니다. 원장 대사는 0원 기준입니다.')
    result=evidence_analyze(orders,deliveries,invoices,**params)
    cutoff=_date(result['config']['cutoff_date']);issues=result['issues'];rows=result['rows'];groups=result['groups']
    group_map={g['key']:g for g in groups};population=[];tieouts=[]
    def add_group(key,order_id='',line='',item=''):
        if key not in group_map:
            g={'key':key,'order_id':order_id,'order_line_id':line,'item_code':item,'customer_id':'','status':'REVIEW',
               'ordered_qty':'','delivered_qty':'','accepted_qty':'','billed_qty':'','billed_supply_amount':'','billed_total_amount':'',
               'reason_codes':[],'source_row_ids':[],'unresolved':True,'reviewer_note':''}
            groups.append(g);group_map[key]=g
        return group_map[key]
    def issue(code,key,ids=(),detail='',severity='REVIEW'):
        g=add_group(key)
        finding={'finding_id':f'L{len(issues)+1:05d}','rule_id':'LEDGER-001','reason_code':code,'severity':severity,
                 'key':key,'row_ids':list(ids),'message':detail,'detail':detail,'procedure_status':'PERFORMED','unresolved':True,'reviewer_note':''}
        issues.append(finding)
        if code not in g['reason_codes']:g['reason_codes'].append(code)
        g['source_row_ids']=list(dict.fromkeys(g['source_row_ids']+list(ids)))
        if severity=='ERROR':g['status']='ERROR'
        elif g['status']!='ERROR':g['status']='REVIEW'
        g['unresolved']=True
    # A tolerance does not erase any observed non-zero difference.
    for check in result['checks']:
        if check['result']=='PASS' and Decimal(check['difference'])!=0:
            issue('ROUNDING_DIFFERENCE',check['key'],[check['row_id']],f"{check['reason_code']}: 허용범위 내 비영차이 {check['difference']}원")
            check['result']='REVIEW'
    def trace(raw,role,index):
        return {'row_id':f'{role}:{index+1}','role':role,'source_file':_s(raw.get('_source_file',role)),
                'sheet':_s(raw.get('_sheet',role)),'source_row':raw.get('_row',index+2),
                'key':'','included':False,'disposition':'PENDING','raw_values':{f:_s(raw.get(f,'')) for f in IMPORT_FIELDS[role]}}
    def money(v):
        d=_d(v)
        if d<0 or d!=d.to_integral_value():raise ValueError('차변·대변은 0 이상 원 단위 정수여야 합니다.')
        return d
    ctl=None;control_errors=[]
    if len(control)!=1:control_errors.append('원장통제 자료는 정확히 1행이어야 합니다.')
    for i,raw in enumerate(control):
        row=trace(raw,'control',i);row['key']='원장 통제';rows.append(row)
        try:
            if raw.get('_input_errors'):raise ValueError('; '.join(raw['_input_errors']))
            if any(not _s(raw.get(f,'')) or _s(raw[f]).startswith('=') for f in IMPORT_FIELDS['control']):raise ValueError('통제자료의 모든 필드에 확정값을 입력하세요.')
            start,end=_date(raw['period_start']),_date(raw['period_end'])
            if start>end or end!=cutoff:raise ValueError('통제기간 종료일은 실행 기준일과 같고 시작일 이후여야 합니다.')
            count=_d(raw['expected_rows'])
            if count!=count.to_integral_value() or not 0<=count<=MAX_ROWS:raise ValueError('통제 행수는 0~1,000의 정수입니다.')
            accounts=[x.strip() for x in _s(raw['account_codes']).split(';')]
            if not all(accounts) or len(accounts)!=len(set(accounts)):raise ValueError('계정코드는 세미콜론으로 구분한 중복 없는 텍스트입니다.')
            extracted=datetime.fromisoformat(_s(raw['extracted_at']))
            if extracted.date()<end:raise ValueError('추출시각이 통제기간 종료일보다 빠릅니다.')
            ctl={'company_id':_s(raw['company_id']),'start':start,'end':end,'accounts':set(accounts),
                 'expected_rows':int(count),'debit':money(raw['debit_total']),'credit':money(raw['credit_total']),
                 'source_reference':_s(raw['source_reference']),'prepared_by':_s(raw['prepared_by']),'extracted_at':_s(raw['extracted_at'])}
            row.update(included=True,disposition='CONTROL',**row['raw_values'])
        except (ValueError,TypeError) as exc:
            control_errors.append(f"control!{row['source_row']}: {exc}");row['disposition']='INVALID'
    if control_errors:
        issue('CONTROL_INVALID','원장 통제',[r['row_id'] for r in rows if r['role']=='control'],' / '.join(control_errors),'ERROR');ctl=None
    parsed=[];numeric_complete=True
    for i,raw in enumerate(ledger):
        row=trace(raw,'ledger',i);d=row['raw_values'];row.update(d);rows.append(row)
        errors=list(raw.get('_input_errors',[]));debit=credit=None;posting=None
        try:debit=money(raw.get('revenue_debit'));credit=money(raw.get('revenue_credit'))
        except (ValueError,TypeError) as exc:numeric_complete=False;errors.append(str(exc))
        try:posting=_date(raw.get('posting_date'))
        except (ValueError,TypeError) as exc:errors.append(str(exc))
        for f in ('journal_id','journal_line_id','company_id','account_code','currency'):
            if not d[f] or len(d[f])>200 or d[f].startswith('='):errors.append(f+': 유효한 텍스트가 필요합니다.')
        if any(v.startswith('=') for v in d.values()):errors.append('수식은 지원하지 않습니다.')
        if d['currency']!='KRW':errors.append('KRW 매출계정만 지원합니다.')
        if debit is not None and credit is not None and debit>0 and credit>0:errors.append('한 전표행의 차변·대변을 동시에 양수로 넣을 수 없습니다.')
        if ctl:
            if d['company_id']!=ctl['company_id']:errors.append('회사코드가 통제자료와 다릅니다.')
            if d['account_code'] not in ctl['accounts']:errors.append('통제 대상 매출계정 밖의 행입니다.')
            if posting and not ctl['start']<=posting<=ctl['end']:errors.append('원장행이 통제기간 밖입니다.')
        p={'row':row,'data':d,'debit':debit,'credit':credit,'posting':posting,'errors':errors,'valid':not errors}
        parsed.append(p)
    identities=defaultdict(list)
    for p in parsed:identities[tuple(p['data'][f] for f in ('company_id','journal_id','journal_line_id'))].append(p)
    for identity,items in identities.items():
        if len(items)>1:
            for p in items:p['valid']=False;p['errors'].append('전표번호+전표행 중복. 임의 합산/첫행 선택 없이 비교 차단.')
    # Raw row count and gross debit/credit controls cannot be defeated by offsetting omissions.
    observed_debit=sum((p['debit'] for p in parsed),Decimal(0)) if numeric_complete else None
    observed_credit=sum((p['credit'] for p in parsed),Decimal(0)) if numeric_complete else None
    if ctl:
        for name,expected,observed in [('원장행수',ctl['expected_rows'],len(parsed)),('매출차변합계',ctl['debit'],observed_debit),('매출대변합계',ctl['credit'],observed_credit)]:
            passed=observed is not None and observed==expected
            population.append({'검사':name,'기대값':_fmt(expected),'실제값':_fmt(observed),'차이':_fmt(observed-expected) if observed is not None else None,'허용오차':0,'상태':'PASS' if passed else 'FAIL','근거':ctl['source_reference']})
            if not passed:issue('POPULATION_CONTROL_FAILED','원장 통제',detail=f'{name}: 기대 {_fmt(expected)} / 실제 {_fmt(observed)}',severity='ERROR')
    else:population.append({'검사':'통제자료 검증','상태':'FAIL','사유':'유효한 독립 통제자료가 없습니다.'})
    invoice_index=defaultdict(list)
    for row in rows:
        if row['role']=='invoices' and row['included']:
            invoice_index[(row['invoice_id'],row['invoice_line_id'])].append(row)
    ledger_index=defaultdict(list)
    for p in parsed:ledger_index[(p['data']['invoice_id'],p['data']['invoice_line_id'])].append(p)
    for identity in sorted(set(invoice_index)|set(ledger_index)):
        ir=invoice_index.get(identity,[]);lr=ledger_index.get(identity,[])
        key=ir[0]['key'] if ir else '원장 | '+str(identity[0] or '(증빙없음)')+' | '+str(identity[1] or '(행없음)')
        ids=[r['row_id'] for r in ir]+[p['row']['row_id'] for p in lr]
        g=add_group(key,ir[0]['order_id'] if ir else '원장',ir[0]['order_line_id'] if ir else '',ir[0]['item_code'] if ir else '')
        g['source_row_ids']=list(dict.fromkeys(g['source_row_ids']+ids))
        for p in lr:
            p['row']['key']=key;p['row']['included']=p['valid'] and bool(ctl);p['row']['disposition']='INCLUDED' if p['row']['included'] else 'INVALID'
            if p['errors']:issue('LEDGER_INVALID',key,[p['row']['row_id']],'; '.join(p['errors']),'ERROR')
        errors_before=len(issues)
        # Every side is retained; uncertain or orphan lines are never turned into zero-value matches.
        if len(ir)!=1:issue('LEDGER_WITHOUT_INVOICE' if not ir else 'INVOICE_ID_AMBIGUOUS',key,ids,'원장에 연결되는 유효한 청구 증빙이 없거나 청구 ID가 모호합니다.')
        if not lr:issue('INVOICE_WITHOUT_LEDGER',key,ids,'청구에 연결되는 매출원장 행이 없습니다.')
        observed=None;expected=None
        if len(ir)==1:
            inv=ir[0];expected=_d(inv['supply_amount'])
            if ctl and not ctl['start']<=_date(inv['invoice_date'])<=ctl['end']:
                issue('INVOICE_OUTSIDE_PERIOD',key,[inv['row_id']],'청구가 원장 통제기간 밖입니다. 기간 자료를 다시 준비하세요.')
            for p in lr:
                if p['data']['customer_id']!=inv['customer_id']:issue('LEDGER_CUSTOMER_MISMATCH',key,[inv['row_id'],p['row']['row_id']],'청구와 원장 거래처가 다릅니다.')
            if lr and all(p['valid'] for p in lr):
                observed=sum((p['credit']-p['debit'] for p in lr),Decimal(0))
                if observed!=expected:issue('LEDGER_AMOUNT_MISMATCH',key,ids,f'청구 공급가액 {expected} / 원장 순매출 {observed} / 차이 {observed-expected}')
        tied=len(ir)==1 and bool(lr) and all(p['valid'] for p in lr) and len(issues)==errors_before
        tieouts.append({'invoice_id':identity[0],'invoice_line_id':identity[1],'key':key,'invoice_supply':_fmt(expected),'ledger_net_revenue':_fmt(observed),
                        'difference':_fmt(observed-expected) if observed is not None and expected is not None else None,'tolerance':0,'status':'PASS' if tied else 'FAIL',
                        'source_row_ids':ids,'ledger_rows':len(lr),'invoice_rows':len(ir)})
    # Amounts cannot pass while population completeness or validity is unresolved.
    population_ok=bool(ctl) and all(p['상태']=='PASS' for p in population) and all(p['valid'] for p in parsed)
    for tieout in tieouts:
        tieout['amount_status']=tieout['status'];tieout['population_status']='PASS' if population_ok else 'FAIL'
        if not population_ok and tieout['status']=='PASS':tieout['status']='UNVERIFIED'
    if not population_ok:
        for g in list(groups):
            if g['status']=='MATCHED':issue('POPULATION_UNVERIFIED',g['key'],detail='독립 원장 모집단 검증이 완료되지 않아 일치 판단을 보류합니다.')
    for p in parsed:
        if not ctl:p['row']['included']=False;p['row']['disposition']='CONTROL_UNVERIFIED'
    result['ledger_reconciliation']=tieouts;result['population_checks']=population
    result['config'].update(rules_version='sales-evidence-v2.0-ledger',ledger_tolerance_krw='0',population_status='PASS' if population_ok else 'FAIL',
                            period_start=ctl['start'].isoformat() if ctl else '',control_source=ctl['source_reference'] if ctl else '',
                            control_independence='ERP 원본 화면·시산표에서 별도 확인한 통제합계. 프로그램은 출처의 독립성을 증명하지 않음',
                            revenue_basis='매출계정 대변-차변을 청구 공급가액(부가세 제외)과 정확 비교',
                            input_files=list(dict.fromkeys(r['source_file'] for r in rows)),input_row_count=len(rows),included_row_count=sum(r['included'] for r in rows),excluded_row_count=sum(not r['included'] for r in rows))
    result['summary']={'groups':len(groups),'source_rows':len(rows),'included_rows':sum(r['included'] for r in rows),'ledger_rows':len(ledger),'control_rows':len(control),
                       'population_status':result['config']['population_status'],**{s:sum(g['status']==s for g in groups) for s in ('MATCHED','OPEN','REVIEW','ERROR','EXCLUDED')}}
    return result
