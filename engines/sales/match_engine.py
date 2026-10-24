"""Deterministic evidence comparisons. No AI, audit opinion or row allocation."""
from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from uuid import uuid4
import re
from .data_io import FIELDS, LABELS, MAX_ROWS

RULES_VERSION='sales-evidence-v1.1-input-dimensions'
ZERO=Decimal('0'); ONE=Decimal('1')
NUMERIC={'quantity','accepted_quantity','unit_price','tax_rate','supply_amount','tax_amount','total_amount'}
DATE_FIELDS={'order_date','delivery_date','acceptance_date','invoice_date'}
IDENTITY={'orders':('order_id','order_line_id'),'deliveries':('delivery_id','delivery_line_id'),'invoices':('invoice_id','invoice_line_id')}
KEY=('order_id','order_line_id','item_code')
MESSAGES={
 'INVALID_INPUT':'필수값·날짜·수치·지원 범위를 확인하세요',
 'DUPLICATE_RECORD':'동일 증빙 ID와 동일 내용이 반복되어 최초 1행만 합산했습니다',
 'CONFLICTING_IDENTITY':'동일 증빙 ID의 내용이 달라 해당 ID의 모든 행을 집계에서 제외했습니다',
 'AFTER_CUTOFF':'기준일 이후 증빙으로 기준일 집계에서 제외했습니다',
 'ACCEPTANCE_AFTER_CUTOFF':'검수일이 기준일 이후여서 검수수량만 기준일 집계에서 제외했습니다',
 'MISSING_ORDER':'정확히 연결되는 기준일 내 주문·계약 행이 없습니다',
 'ITEM_MISMATCH':'같은 주문번호·주문행번호에 다른 품목코드가 있습니다',
 'CUSTOMER_MISMATCH':'주문과 거래처 ID가 다릅니다',
 'UNIT_MISMATCH':'주문과 수량 단위가 다릅니다',
 'CURRENCY_MISMATCH':'주문과 청구 통화가 다릅니다',
 'TAX_RATE_MISMATCH':'주문과 청구 세율이 다릅니다',
 'UNIT_PRICE_MISMATCH':'세전 기준 단가가 허용오차를 초과합니다',
 'SUPPLY_AMOUNT_MISMATCH':'청구 공급가액이 수량·단가 기준 계산과 다릅니다',
 'TAX_AMOUNT_MISMATCH':'청구 세액이 공급가액·세율 기준 계산과 다릅니다',
 'EXPECTED_TOTAL_MISMATCH':'청구 합계금액이 수량·단가 기준 기대 합계와 다릅니다',
 'TOTAL_AMOUNT_MISMATCH':'청구 합계금액이 공급가액+세액과 다릅니다',
 'CONTRACT_AMOUNT_MISMATCH':'청구 공급가액이 주문 단가 기준 계산과 다릅니다',
 'OVER_DELIVERY':'납품수량이 주문수량보다 많습니다',
 'BILLED_ABOVE_ACCEPTED':'청구수량이 기준일 검수수량보다 많습니다',
 'PENDING_DELIVERY':'미납품 주문 잔량이 있습니다',
 'PENDING_ACCEPTANCE':'납품되었으나 기준일 미검수인 수량이 있습니다',
 'UNBILLED_ACCEPTED':'검수되었으나 청구되지 않은 수량이 있습니다',
 'MISSING_DELIVERY':'기준일 내 연결된 납품증빙이 없습니다',
 'MISSING_INVOICE':'기준일 내 연결된 청구증빙이 없습니다',
 'DATE_SEQUENCE':'문서일 또는 검수일의 시간 순서를 확인하세요',
}

RULE_FAMILIES={'INVALID_INPUT':'INPUT-001','DUPLICATE_RECORD':'ID-001','CONFLICTING_IDENTITY':'ID-002','MISSING_ORDER':'LINK-001','ITEM_MISMATCH':'LINK-002','CUSTOMER_MISMATCH':'LINK-002','UNIT_MISMATCH':'LINK-002','CURRENCY_MISMATCH':'LINK-002','OVER_DELIVERY':'QTY-001','BILLED_ABOVE_ACCEPTED':'QTY-002','PENDING_DELIVERY':'QTY-003','PENDING_ACCEPTANCE':'QTY-003','UNBILLED_ACCEPTED':'QTY-003','MISSING_DELIVERY':'QTY-003','MISSING_INVOICE':'QTY-003','UNIT_PRICE_MISMATCH':'PRICE-001','TAX_RATE_MISMATCH':'TAX-001','TAX_AMOUNT_MISMATCH':'TAX-001','DATE_SEQUENCE':'DATE-001','AFTER_CUTOFF':'DATE-002','ACCEPTANCE_AFTER_CUTOFF':'DATE-002'}

def _s(v):
    if v is None: return ''
    if isinstance(v,(datetime,date)): return v.strftime('%Y-%m-%d')
    return str(v).strip()

def _d(v):
    # Thousands separators accepted only as conventional groups; no exponent notation.
    import re
    t=_s(v)
    if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?',t): raise ValueError('숫자 형식이 올바르지 않습니다')
    d=Decimal(t.replace(',',''))
    if not d.is_finite() or abs(d)>Decimal('1000000000000000'): raise ValueError('수치 범위를 벗어났습니다')
    if len(d.as_tuple().digits)>24: raise ValueError('소수 정밀도가 너무 큽니다')
    return d

def _date(v):
    t=_s(v)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',t): raise ValueError('날짜는 YYYY-MM-DD 형식이어야 합니다')
    return date.fromisoformat(t)

def _fmt(v):
    if isinstance(v,Decimal): return format(v,'f')
    if isinstance(v,(date,datetime)): return v.isoformat()
    return v

def _rounded(v): return v.quantize(ONE,rounding=ROUND_HALF_UP)

def _analyze(orders: list[dict], deliveries: list[dict], invoices: list[dict], cutoff_date: str | None=None, amount_tolerance='1', quantity_tolerance='0', unit_price_tolerance='0.01') -> dict:
    for role,rs in [('orders',orders),('deliveries',deliveries),('invoices',invoices)]:
        if len(rs)>MAX_ROWS: raise ValueError(f'{role}: 테이블당 최대 {MAX_ROWS:,}행까지 허용합니다')
    cutoff=_date(cutoff_date or '2026-09-30')
    amt_tol=_d(amount_tolerance); qty_tol=_d(quantity_tolerance); price_tol=_d(unit_price_tolerance)
    if amt_tol<0 or price_tol<0 or qty_tol!=0: raise ValueError('허용오차는 음수가 될 수 없으며 수량 허용오차는 0으로 고정됩니다')
    if amt_tol>100 or price_tol>100: raise ValueError('금액·단가 허용오차는 100원 이하여야 합니다')
    run_id=str(uuid4())
    config={'run_id':run_id,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'cutoff_date':cutoff.isoformat(),'rules_version':RULES_VERSION,'amount_tolerance_krw':str(amt_tol),'unit_price_tolerance_krw':str(price_tol),'quantity_tolerance':'0','rounding':'ROUND_HALF_UP, line amount to KRW integer','scope':'KRW / EA / positive integer quantities / tax_rate 0 or 0.10','allocation':'Aggregate by order_id + order_line_id + item_code. No row-level allocation.','conclusion':'Evidence comparison only; no audit assurance, fraud or revenue-recognition conclusion'}
    rows=[]; issues=[]; checks=[]; groups=defaultdict(list); issues_by_key=defaultdict(list)
    def issue(code,key,row_ids=(),severity='REVIEW',detail=''):
        finding={'finding_id':f'F{len(issues)+1:05d}','rule_id':RULE_FAMILIES.get(code,'AMOUNT-001'),'reason_code':code,'severity':severity,'key':' | '.join(key),'row_ids':list(row_ids),'message':MESSAGES.get(code,code),'detail':detail,'procedure_status':'PERFORMED','unresolved':severity in ('ERROR','REVIEW','OPEN'),'reviewer_note':''}
        issues.append(finding); issues_by_key[key].append(finding); return finding
    for role,source in [('orders',orders),('deliveries',deliveries),('invoices',invoices)]:
        for i,raw in enumerate(source):
            r={'role':role,'row_id':f'{role}:{i+1}','source_file':_s(raw.get('_source_file',role)), 'sheet':_s(raw.get('_sheet','data')),'source_row':raw.get('_row',i+2),'data':{f:_s(raw.get(f,'')) for f in FIELDS[role]},'valid':True,'included':False,'disposition':'INCLUDED','errors':list(raw.get('_input_errors',[])), 'raw_values':{f:_s(raw.get(f,'')) for f in FIELDS[role]}}
            if r['errors']: r['valid']=False
            values=r['data']; key=tuple(values.get(f,'') for f in KEY); r['key']=key
            for f in FIELDS[role]:
                v=values[f]
                optional=False
                if f=='acceptance_date':
                    try: optional=_d(values.get('accepted_quantity',''))==0
                    except ValueError: pass
                try:
                    if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',v): raise ValueError('지원하지 않는 제어 문자')
                    if not v and not optional: raise ValueError('필수값 없음')
                    if v.startswith('='): raise ValueError('수식은 사용할 수 없습니다')
                    if f in NUMERIC:
                        values[f]=_d(v)
                        if values[f]<0: raise ValueError('음수는 지원하지 않습니다')
                        if f=='quantity' and values[f]<=0: raise ValueError('수량은 0보다 커야 합니다')
                        if f in ('supply_amount','tax_amount','total_amount') and values[f]!=values[f].to_integral_value(): raise ValueError('KRW 표시 금액은 정수여야 합니다')
                        if f in ('quantity','accepted_quantity') and values[f]!=values[f].to_integral_value(): raise ValueError('EA 수량은 정수여야 합니다')
                    elif f in DATE_FIELDS: values[f]=_date(v) if v else None
                    elif len(v)>200: raise ValueError('문자열이 200자를 초과합니다')
                    if f=='currency' and v!='KRW': raise ValueError('KRW만 지원합니다')
                    if f=='unit' and v!='EA': raise ValueError('EA 단위만 지원합니다')
                    if f=='price_basis' and v not in ('NET','GROSS'): raise ValueError('NET 또는 GROSS만 지원합니다')
                    if f=='tax_rate' and values[f] not in (ZERO,Decimal('0.10')): raise ValueError('세율 0 또는 0.10만 지원합니다')
                except (ValueError,InvalidOperation,TypeError) as exc:
                    r['valid']=False; r['errors'].append(f'{f}: {exc}')
            if role=='deliveries' and r['valid']:
                if values['accepted_quantity']>values['quantity']: r['valid']=False; r['errors'].append('accepted_quantity: 검수수량이 납품수량보다 많습니다')
                if values['accepted_quantity']>0 and not values['acceptance_date']: r['valid']=False; r['errors'].append('acceptance_date: 양수 검수수량에는 검수일이 필요합니다')
            if not r['valid']:
                r['disposition']='INVALID'; issue('INVALID_INPUT',key,[r['row_id']],'ERROR','; '.join(r['errors']))
            rows.append(r); groups[key].append(r)
    # Normalize payload independently of source provenance, then deduplicate by immutable identity.
    for role in FIELDS:
        identities=defaultdict(list)
        for r in rows:
            if r['role']==role and all(r['data'].get(f) for f in IDENTITY[role]): identities[tuple(r['data'][f] for f in IDENTITY[role])].append(r)
        for identity,rs in identities.items():
            if len(rs)<2: continue
            payloads={tuple(r['data'][f] for f in FIELDS[role]) for r in rs}
            if len(payloads)>1:
                for r in rs: r['disposition']='CONFLICT'; r['valid']=False
                for key in dict.fromkeys(r['key'] for r in rs): issue('CONFLICTING_IDENTITY',key,[r['row_id'] for r in rs],'ERROR',str(identity))
            else:
                for r in rs[1:]: r['disposition']='DUPLICATE'
                issue('DUPLICATE_RECORD',rs[0]['key'],[r['row_id'] for r in rs],'REVIEW',f'{len(rs)}행 중 1행만 집계')
    for r in rows:
        if not r['valid'] or r['disposition'] in ('DUPLICATE','CONFLICT'): continue
        d=r['data'][{'orders':'order_date','deliveries':'delivery_date','invoices':'invoice_date'}[r['role']]]
        if d>cutoff:
            r['disposition']='AFTER_CUTOFF'; issue('AFTER_CUTOFF',r['key'],[r['row_id']],'INFO')
        else: r['included']=True
    # Usable order identities identify wrong item codes without guessing a match.
    order_items=defaultdict(set)
    for r in rows:
        if r['role']=='orders': order_items[tuple(r['key'][:2])].add(r['key'][2])
    def check(rule,key,r,expected,observed,tolerance):
        diff=observed-expected; passed=abs(diff)<=tolerance
        checks.append({'check_id':f'C{len(checks)+1:05d}','rule_id':RULE_FAMILIES.get(rule,'AMOUNT-001'),'reason_code':rule,'key':' | '.join(key),'row_id':r['row_id'],'expected':_fmt(expected),'observed':_fmt(observed),'difference':_fmt(diff),'tolerance':_fmt(tolerance),'result':'PASS' if passed else 'FAIL','procedure_status':'PERFORMED'})
        if not passed:
            f=issue(rule,key,[r['row_id']],'REVIEW',f'예상 {_fmt(expected)} / 기재 {_fmt(observed)} / 차이 {_fmt(diff)}')
            f.update(expected=_fmt(expected),actual=_fmt(observed),difference=_fmt(diff),tolerance=_fmt(tolerance))
    summaries=[]
    for key,rs in sorted(groups.items()):
        usable=[r for r in rs if r['included']]
        os=[r for r in usable if r['role']=='orders']; ds=[r for r in usable if r['role']=='deliveries']; inv=[r for r in usable if r['role']=='invoices']
        order=os[0] if len(os)==1 else None
        if not order and (ds or inv):
            issue('MISSING_ORDER',key,[r['row_id'] for r in ds+inv])
            future_orders=[r for r in rs if r['role']=='orders' and r['valid'] and r['disposition']=='AFTER_CUTOFF']
            for future_order in future_orders:
                for r in ds+inv:
                    if (r['data'].get('delivery_date') or r['data'].get('invoice_date'))<future_order['data']['order_date']:
                        issue('DATE_SEQUENCE',key,[future_order['row_id'],r['row_id']],detail='납품 또는 청구일이 기준일 이후 주문일보다 빠릅니다')
        if tuple(key[:2]) in order_items and key[2] not in order_items[tuple(key[:2])]: issue('ITEM_MISMATCH',key,[r['row_id'] for r in rs])
        if order:
            o=order['data']; base_price=o['unit_price'] if o['price_basis']=='NET' else o['unit_price']/(ONE+o['tax_rate'])
            for r in ds+inv:
                v=r['data']
                for field,code in [('customer_id','CUSTOMER_MISMATCH'),('unit','UNIT_MISMATCH')]:
                    if v[field]!=o[field]: issue(code,key,[order['row_id'],r['row_id']])
                docdate=v.get('delivery_date') or v.get('invoice_date')
                if docdate<o['order_date']: issue('DATE_SEQUENCE',key,[order['row_id'],r['row_id']],detail='납품 또는 청구일이 주문일보다 빠릅니다')
                if r['role']=='invoices':
                    if v['currency']!=o['currency']: issue('CURRENCY_MISMATCH',key,[order['row_id'],r['row_id']])
                    if v['tax_rate']!=o['tax_rate']: issue('TAX_RATE_MISMATCH',key,[order['row_id'],r['row_id']])
                    net=v['unit_price'] if v['price_basis']=='NET' else v['unit_price']/(ONE+v['tax_rate'])
                    check('UNIT_PRICE_MISMATCH',key,r,base_price,net,price_tol)
                    check('CONTRACT_AMOUNT_MISMATCH',key,r,_rounded(v['quantity']*base_price),v['supply_amount'],amt_tol)
        for r in ds:
            v=r['data']
            if v['acceptance_date'] and v['acceptance_date']<v['delivery_date']: issue('DATE_SEQUENCE',key,[r['row_id']],detail='검수일이 납품일보다 빠릅니다')
            if v['acceptance_date'] and v['acceptance_date']>cutoff: issue('ACCEPTANCE_AFTER_CUTOFF',key,[r['row_id']],'INFO')
        for r in inv:
            v=r['data']; net=v['unit_price'] if v['price_basis']=='NET' else v['unit_price']/(ONE+v['tax_rate'])
            check('SUPPLY_AMOUNT_MISMATCH',key,r,_rounded(v['quantity']*net),v['supply_amount'],amt_tol)
            expected_supply=_rounded(v['quantity']*net); expected_tax=_rounded(expected_supply*v['tax_rate'])
            check('TAX_AMOUNT_MISMATCH',key,r,expected_tax,v['tax_amount'],amt_tol)
            check('EXPECTED_TOTAL_MISMATCH',key,r,expected_supply+expected_tax,v['total_amount'],amt_tol)
            check('TOTAL_AMOUNT_MISMATCH',key,r,v['supply_amount']+v['tax_amount'],v['total_amount'],amt_tol)
        ordered=sum((r['data']['quantity'] for r in os),ZERO)
        delivered=sum((r['data']['quantity'] for r in ds),ZERO)
        accepted=sum((r['data']['accepted_quantity'] for r in ds if r['data']['acceptance_date'] and r['data']['acceptance_date']<=cutoff),ZERO)
        billed=sum((r['data']['quantity'] for r in inv),ZERO)
        ids=[r['row_id'] for r in usable]
        if order:
            if delivered>ordered: issue('OVER_DELIVERY',key,ids)
            if delivered<ordered: issue('PENDING_DELIVERY',key,ids,'OPEN')
            if delivered>accepted: issue('PENDING_ACCEPTANCE',key,ids,'OPEN')
            if accepted>billed: issue('UNBILLED_ACCEPTED',key,ids,'OPEN')
            if not ds: issue('MISSING_DELIVERY',key,[order['row_id']],'OPEN')
            if not inv: issue('MISSING_INVOICE',key,[order['row_id']],'OPEN')
        if billed>accepted: issue('BILLED_ABOVE_ACCEPTED',key,ids)
        related=issues_by_key[key]
        severities={x['severity'] for x in related}
        status='ERROR' if 'ERROR' in severities else 'REVIEW' if 'REVIEW' in severities else 'OPEN' if 'OPEN' in severities or not order else 'MATCHED'
        if not usable and all(r['disposition'] in ('AFTER_CUTOFF','DUPLICATE') for r in rs): status='EXCLUDED'
        summaries.append({'key':' | '.join(key),'order_id':key[0],'order_line_id':key[1],'item_code':key[2],'customer_id':order['data']['customer_id'] if order else '', 'status':status,'ordered_qty':_fmt(ordered),'delivered_qty':_fmt(delivered),'accepted_qty':_fmt(accepted),'billed_qty':_fmt(billed),'undelivered_qty':_fmt(max(ZERO,ordered-delivered)),'unaccepted_qty':_fmt(max(ZERO,delivered-accepted)),'unbilled_accepted_qty':_fmt(max(ZERO,accepted-billed)),'billed_supply_amount':_fmt(sum((r['data']['supply_amount'] for r in inv),ZERO)),'billed_total_amount':_fmt(sum((r['data']['total_amount'] for r in inv),ZERO)),'reason_codes':list(dict.fromkeys(x['reason_code'] for x in related)),'source_row_ids':[r['row_id'] for r in rs],'unresolved':status in ('ERROR','REVIEW','OPEN'),'reviewer_note':''})
    flat=[]
    for r in rows:
        flat.append({'row_id':r['row_id'],'role':r['role'],'source_file':r['source_file'],'sheet':r['sheet'],'source_row':r['source_row'],'key':' | '.join(r['key']),'included':r['included'],'disposition':r['disposition'],**{k:_fmt(v) for k,v in r['data'].items()},'validation_errors':r['errors'],'raw_values':r['raw_values']})
    config.update(input_files=list(dict.fromkeys(r['source_file'] for r in rows)),input_row_count=len(rows),included_row_count=sum(r['included'] for r in rows),excluded_row_count=sum(not r['included'] for r in rows))
    return {'config':config,'summary':{'groups':len(summaries),'source_rows':len(rows),'included_rows':sum(r['included'] for r in rows),**{s:sum(g['status']==s for g in summaries) for s in ('MATCHED','OPEN','REVIEW','ERROR','EXCLUDED')}},'groups':summaries,'issues':issues,'checks':checks,'rows':flat}


def analyze(orders, deliveries, invoices, cutoff_date=None, amount_tolerance="1", quantity_tolerance="0", unit_price_tolerance="0.01"):
    with localcontext() as ctx:
        ctx.prec=60
        return _analyze(orders,deliveries,invoices,cutoff_date,amount_tolerance,quantity_tolerance,unit_price_tolerance)
