"""Expose the nine scoped synthetic calculators to the native app and draft workpapers."""
import copy,importlib,json
from common import *
WORKERS=('cash_finance','revenue_ar','inventory_ap','fixed_assets','leases','payroll','debt_tax','equity_disclosure','financial_reporting')
ALIASES={'회사코드':'company_code','시작일':'start_date','기준일':'end_date','통화':'currency','연결구분':'financial_statement_scope',
         'company_id':'company_code','period_start':'start_date','period_end':'end_date','consolidation':'financial_statement_scope'}
def unique(pairs):
    out={}
    for key,value in pairs:
        if key in out:raise AuditError('JSON 중복 키: '+key)
        out[key]=value
    return out
def analyze(path,context,event=None):
    p=Path(path)
    if p.stat().st_size>2*1024**2:raise AuditError('계정별 연습자료는 2MB 이하입니다.')
    data=json.loads(p.read_text(encoding='utf-8-sig'),object_pairs_hook=unique,
                    parse_constant=lambda x:(_ for _ in ()).throw(AuditError('비유한 숫자')))
    if data.get('schema_version')!='account-evidence-1' or data.get('synthetic') is not True or data.get('ledger_joined') is not False:raise AuditError('합성 독립 연습자료 양식이 아닙니다.')
    worker=data.get('worker')
    if worker not in WORKERS:raise AuditError('등록되지 않은 계정 계산기')
    cx={}
    for k,v in data['context'].items():
        alias=ALIASES.get(k,k)
        if alias in cx:raise AuditError('문맥 키 별칭 중복')
        cx[alias]=v
    for a,b in [('회사코드','company_code'),('시작일','start_date'),('기준일','end_date')]:
        if cx.get(b)!=context[a]:raise AuditError('독립 연습자료 회사/기간 불일치')
    if cx.get('currency')!='KRW' or cx.get('financial_statement_scope')!='별도':raise AuditError('KRW 별도 연습만 지원합니다.')
    case=copy.deepcopy(data['case']);case.pop('expected',None)
    docs=case.get('documents')
    if not isinstance(docs,list) or len(docs)>100:raise AuditError('증빙 개수 오류')
    ids=[d.get('document_id') for d in docs]
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):raise AuditError('증빙 ID 누락/중복')
    cancelled(event)
    engine=importlib.import_module('worker_library.'+worker+'.engine')
    try:
        if worker in ('cash_finance','leases'):checks=engine.calculate(case)
        elif worker=='equity_disclosure':checks=engine.evaluate_case(case)
        elif worker=='fixed_assets':checks=engine.evaluate(case)
        elif worker=='financial_reporting':checks=engine.evaluate(case,data.get('case_index',0))
        else:
            if worker=='revenue_ar':case['_index']=data.get('case_index',0)
            checks=engine.evaluate(case,data['context'])
    except (ValueError,KeyError,TypeError,AssertionError) as exc:
        checks=[{'check_id':'CASE_INPUT','status':'INPUT_BLOCKED','expected_value':None,'actual_value':None,'difference':None,'reason':str(exc)}]
    rows=[];issues=[]
    for item in checks:
        status=item['status'];reason=item.get('reason') or '계정별 고정 정책에 따른 원문 재계산·비교'
        if status not in ('PASS','EXCEPTION','INPUT_BLOCKED'):raise AuditError('계정 검사 상태 오류')
        refs={k:v for k,v in item.items() if k.startswith('source')}
        reference=dumps(refs) if refs else '입력 JSON /case/documents'
        row={'검사ID':item['check_id'],'상태':status,'기대':item.get('expected_value'),'실제':item.get('actual_value'),
             '차이':item.get('difference'),'사유':reason,'원본위치':reference,'후속절차':item.get('follow_up') or '원본·계약·판단 및 추가절차를 검토하세요.'}
        rows.append(row)
        if status!='PASS':issue(issues,item['check_id'],reason,reference,blocking=status=='INPUT_BLOCKED')
    originals=[{'증빙ID':d['document_id'],'문서유형':d['document_type'],'거래ID':d['transaction_id'],'원본위치':f'/case/documents/{i}/fields','원본값':d['fields']} for i,d in enumerate(docs)]
    cancelled(event)
    return result('계정별증빙연습',context,{'계정별검사':rows,'원천증빙원문':originals},issues,
       detail={'담당':worker,'사례':case.get('case_id'),'설명':case.get('description'),'현재원장연결':False,
               '범위':'독립 합성 거래 연습. 현재 업무 TB와 합산하지 않음. 일반 사용자 임의 자료용 범용 계산기가 아님.',
               '작성자':None,'검토자':None,'결론':None,'수정승인':False,'입력기대값사용':False})
