"""Strict shared population controls for the two estimate modules (KRW)."""
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from common import *

CONTROL_HEADER=['자료','지표','기대값','추출근거','추출일시','작성자']

def decimalnum(v,label='수량',signed=False):
    if v is None or isinstance(v,bool) or not re.fullmatch(r'[+-]?\d+(?:\.\d+)?',str(v).strip()):raise AuditError(label+': 소수 숫자 필수')
    d=Decimal(str(v))
    if not d.is_finite() or abs(d)>10**13 or d.as_tuple().exponent < -6 or (not signed and d<0):raise AuditError(label+': 범위/소수6자리/부호 오류')
    return d

def independent_ids(path,column):
    import csv
    path=Path(path)
    if path.stat().st_size>20*1024**2:raise AuditError('독립 ID CSV 20MB 한도')
    with path.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)) or column not in reader.fieldnames:raise AuditError('CSV 열 이름 누락·중복')
        ids=[]
        for row in reader:
            if len(ids)>=10000 or None in row:raise AuditError('독립 ID CSV 구조/10000행 한도')
            ids.append(text(row[column],'독립 ID'))
    if len(ids)!=len(set(ids)):raise AuditError('독립 ID CSV 중복')
    return {'행수':len(ids),'ID해시':digest(sorted(ids))}

def rate(v,label='비율',low=Decimal(0),high=Decimal(1)):
    if v is None or isinstance(v,bool) or not re.fullmatch(r'[+-]?\d+(?:\.\d+)?',str(v).strip()):raise AuditError(label+': 소수 비율 필수 (5%=0.05)')
    try:d=Decimal(str(v))
    except InvalidOperation as e:raise AuditError(label+': 비율 오류') from e
    if not d.is_finite() or not low<=d<=high:raise AuditError(label+': 허용범위 밖')
    return d

def settings(t,extra):
    rows=t['설정'];c={r['항목']:r['값'] for r in rows}
    if len(c)!=len(rows) or set(c)!=set(extra)|{'회사코드','시작일','기준일','통화'}:raise AuditError('설정 항목 누락·중복·미지원')
    c={k:text(v,k) for k,v in c.items()}
    if c['통화']!='KRW' or day(c['시작일'])>day(c['기준일']):raise AuditError('KRW 및 올바른 기간 필요')
    return c

def keyed(rows,key,company=None):
    out={}
    for r in rows:
        k=text(r[key],key)
        if ';' in k or k in out:raise AuditError(key+': 중복 또는 세미콜론 포함 ID')
        if company is not None and r.get('회사코드')!=company:raise AuditError('회사코드 불일치: '+key+' '+k)
        out[k]=r
    return out

def population(t,c,spec,issues,decimal_fields=None):
    """Require counts, complete key sets, signed AND absolute totals from an independent extraction."""
    expected={}
    for role,(key,fields) in spec.items():
        rows=t[role];ids=[text(r[key],key) for r in rows]
        expected[(role,'행수')]=len(rows)
        expected[(role,'ID해시')]=digest(sorted(ids))
        for f in fields:
            vals=[decimalnum(r[f],f,signed=True) if (role,f) in (decimal_fields or set()) else num(r[f]) for r in rows]
            expected[(role,f+'합계')]=sum(vals)
            expected[(role,f+'절대합계')]=sum(abs(v) for v in vals)
    supplied={};checks=[]
    for r in t['독립통제']:
        k=(text(r['자료']),text(r['지표']))
        if k in supplied:raise AuditError('독립통제 중복: '+str(k))
        text(r['추출근거'],'추출근거');text(r['작성자'],'작성자')
        try:dt=datetime.fromisoformat(str(r['추출일시']).lstrip("'"))
        except ValueError as e:raise AuditError('추출일시 ISO 시간대 필수') from e
        if dt.utcoffset() is None or dt.date()<day(c['기준일']):raise AuditError('추출일시 시간대·기준일 이후 확인 필요')
        v=r['기대값']
        if k[1]=='ID해시':
            if not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v):raise AuditError('독립 ID해시는 소문자 SHA256 64자리 필수')
        elif any(k==(role,f+suffix) for role,f in (decimal_fields or set()) for suffix in ('합계','절대합계')):v=decimalnum(v,'독립 통제값',signed=True)
        else:v=num(v)
        supplied[k]=(v,f"독립통제!{r['_row']}")
    if set(supplied)!=set(expected):raise AuditError('독립통제 필수 지표 누락·미지원: '+str(set(expected)^set(supplied)))
    for k,actual in expected.items():
        exp,ref=supplied[k];ok=actual==exp
        checks.append({'자료':k[0],'지표':k[1],'기대':exp,'실제':actual,'상태':'일치' if ok else '불일치','원본행':ref})
        if not ok:issue(issues,'POPULATION_CONTROL','독립 모집단 통제 불일치: '+str(k),ref)
    return checks

def compare(issues,rows,identity,metric,calc,book,ref,tolerance=0):
    delta=calc-book
    rows.append({'식별자':identity,'지표':metric,'계산':calc,'원장':book,'차이':delta,'허용오차':tolerance,'상태':'일치' if abs(delta)<=tolerance else '차이','원본행':ref})
    if abs(delta)>tolerance:issue(issues,'CALC_BOOK_DIFF',identity+' '+metric+' 계산과 원장 차이 '+str(delta),ref,False)
