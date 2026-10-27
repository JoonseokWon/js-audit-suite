"""Collect numerical differences as review candidates, never audit misstatements."""
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from common import AuditError, digest, num

SCOPE = '자동검토후보이며 감사상 왜곡표시·수정분개 확정이 아닙니다. 사람이 원인·금액·중복·분류를 확인하세요.'
DIFFERENCE_COLUMNS = ('차이', '차이(원)', '차이금액', '금액차이', '잔액차이',
                      '원금차이', '이자차이', '공급가액차이', '세액차이', 'difference')
IDENTITY_COLUMNS = ('전표ID','거래ID','계약ID','비용ID','청구ID','송장ID',
                    'invoice_id','contract_id','asset_id','계정코드','지표')


def _number(value):
    if value is None or isinstance(value,bool):return None
    try:
        numeric=Decimal(str(value))
        if not numeric.is_finite():return None
        return int(numeric) if numeric==numeric.to_integral_value() else format(numeric,'f')
    except (InvalidOperation,TypeError,ValueError):return None


def _candidate(ws, run, table, index, row, column, delta, *, cross=False):
    source=ws.sources[run['source_id']]
    label=str(next((row[key] for key in ('검사','지표','비교','check','reason_code','항목','key') if row.get(key)),table))
    monetary=not any(word in (label+column).upper() for word in ('행수','건수','수량','비율','일수','기간','QTY','QUANTITY','UNIT_PRICE'))
    if column=='difference' and table not in ('자산비교','원장양방향대사'):
        monetary=monetary and ('AMOUNT' in label.upper() or '금액' in label)
    if isinstance(delta,str):monetary=False
    if column not in DIFFERENCE_COLUMNS:monetary=False
    origin={key:row[key] for key in ('원본행','근거','reference','원본행번호','계정코드') if key in row}
    identity={key:row[key] for key in IDENTITY_COLUMNS if row.get(key) not in (None,'')}
    key={'run_id':run['id'],'table':table,'row_index':index,'row_hash':digest(row),'column':column}
    return {'id':'MC-'+digest(key)[:24], **key, 'module':run['module'],
            'source_id':source['id'],'sha256':source['sha256'],'result_hash':run['result_hash'],
            'procedure_id':'F03', 'unit':'KRW' if monetary else '수량·통제값',
            'amount':delta if monetary else None,'observed_delta':delta,
            'label':label,'identity':identity,'origin':origin,'row':deepcopy(row),
            'cross_check':cross,'state':'자동검토후보','scope':SCOPE}


def candidates(ws):
    """Read only. Input tables, balances and warning-only amounts are not summed."""
    out=[];latest=ws.latest()
    for run in latest.values():
        for table, rows in run['result'].get('tables',{}).items():
            if table.startswith('입력_') or not isinstance(rows,list):continue
            for index,row in enumerate(rows,1):
                if not isinstance(row,dict):continue
                for column in DIFFERENCE_COLUMNS:
                    delta=_number(row.get(column))
                    if delta is not None and Decimal(str(delta)):
                        out.append(_candidate(ws,run,table,index,row,column,delta))
    for index,row in enumerate(ws.cross_checks(),1):
        delta=_number(row.get('차이'));run=latest.get(row.get('모듈'))
        if run and delta is not None and Decimal(str(delta)):
            out.append(_candidate(ws,run,'독립TB대사',index,row,'차이',delta,cross=True))
    return out


def duplicate_suggestions(rows):
    """Same source/amount is a connection suggestion, not proof of one error."""
    groups=defaultdict(list)
    for row in rows:
        if row['amount'] is not None:
            groups[(row['source_id'], abs(row['amount']))].append(row['id'])
    return [{'candidate_ids':values,'reason':'같은 원천자료·절대금액. 동일 오류 여부는 사람이 확인하며 자동 차감하지 않습니다.'}
            for values in groups.values() if len(values)>1]
