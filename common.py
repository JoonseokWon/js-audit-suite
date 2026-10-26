"""Shared strict input and immutable, formula-safe result serialization."""
from pathlib import Path
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
from io import BytesIO
from zipfile import ZipFile,BadZipFile
import hashlib,json,re,os,tempfile

VERSION='2.3.0'
PROCEDURE_MODULES={'A02':'금융상품','A04':'매출','A12':'감가상각','A15':'리스','A07':'대손충당금','A11':'재고평가','A16':'종업원급여','A08':'미기록부채·비용이연','A09':'미기록부채·비용이연','R01':'원천증빙','FS01':'재무제표·주석','W01':'계정별증빙연습'}
PROCEDURE_MODULES.update({'G01':'GLA','I01':'FIA','H01':'현금분석'})
from onboarding import MODULES as ONBOARDING_MODULES, PROCEDURES as ONBOARDING_PROCEDURES
PROCEDURE_MODULES.update(ONBOARDING_PROCEDURES)
class AuditError(ValueError):pass
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def plain(v):
    if isinstance(v,Decimal):return format(v,'f')
    if isinstance(v,(date,datetime)):return v.isoformat()
    if isinstance(v,Path):return str(v)
    if isinstance(v,dict):return {str(k):plain(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)):return [plain(x) for x in v]
    return v
def dumps(v):return json.dumps(plain(v),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(v):return hashlib.sha256(dumps(v).encode()).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def text(v,label='값'):
    if not isinstance(v,str) or not v.strip() or len(v)>2000:raise AuditError(label+': 텍스트 필수')
    return v.strip()
def day(v):
    if isinstance(v,datetime):v=v.date()
    if isinstance(v,date):return v
    try:d=date.fromisoformat(str(v).strip())
    except ValueError as e:raise AuditError('날짜는 YYYY-MM-DD: '+str(v)) from e
    if not 1900<=d.year<=2100:raise AuditError('날짜 범위: 1900~2100')
    return d
def num(v,signed=True):
    if isinstance(v,bool) or v is None:raise AuditError('원 단위 숫자 필수')
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?',str(v).strip()):raise AuditError('숫자 형식 오류: '+str(v))
    try:d=Decimal(str(v))
    except InvalidOperation as e:raise AuditError('숫자 오류') from e
    if not d.is_finite() or d!=d.to_integral_value() or abs(d)>10**13 or (not signed and d<0):raise AuditError('원 단위 정수/범위 오류')
    return int(d)
def cancelled(event):
    if event and event.is_set():raise AuditError('사용자가 취소했습니다. 결과는 저장하지 않았습니다.')
def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.audit-',suffix='.tmp')
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if Path(tmp).exists():Path(tmp).unlink()
def read_xlsx(path,schema=None,event=None,max_rows=10000,row_limits=None):
    from xlsx_reader import read_xlsx as read
    return read(path,schema,event,max_rows,row_limits)


def issue(issues,code,message,ref='',blocking=True):issues.append({'code':code,'severity':'차단' if blocking else '검토','message':message,'reference':ref})
def result(module,context,tables,issues,metrics=None,detail=None):
    return plain({'module':module,'version':VERSION,'context':context,'tables':tables,'issues':issues,'metrics':metrics or {},'detail':detail or {},'blocking':sum(i['severity']=='차단' for i in issues),'review':sum(i['severity']=='검토' for i in issues)})
