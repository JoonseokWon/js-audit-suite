"""Exact current-ledger binding shared by independent explainable analyzers."""
from common import *
import ledger
from input_limits import LEDGER_LIMITS,EXCEL_DATA_ROWS

def canonical(rows,headers):
    return sorted([dumps({k:r.get(k) for k in headers}) for r in rows])

def read_bound(path,extra_schema,context,ledger_result=None,event=None):
    if set(extra_schema)&set(ledger.SCHEMA):raise AuditError('분석 시트와 공통 원장 시트 중복')
    tables,source=read_xlsx(path,{**ledger.SCHEMA,**extra_schema},event,max_rows=10000,row_limits=LEDGER_LIMITS)
    issues=[];links=[];current=None;base=None
    detail={'분석기준':'현재 업무 조정전 GL·TB. 승인조정·감사 결론 별도.',
            '입력원문SHA256':source['sha256'],'연결정책':'회사+전표ID+행ID 복합키; 현재 원장 7시트 원문 의미값 및 리드 재계산 일치',
            '모집단한계':'선언된 입력·독립통제와 현재 업무 원장 비교. ERP 추출 진위·미제출 계좌는 별도 확인.',
            '현재원장연결':False,'규칙범위':f'확정값 KRW, 원장 {EXCEL_DATA_ROWS:,}행·보조표 10,000행; 위험 후보는 부정 확정이나 발생확률이 아님'}
    def block(code,message,ref=''):issue(issues,code,message,ref)
    try:
        base=ledger.analyze({k:tables[k] for k in ledger.SCHEMA},event)
        for k in ('회사코드','시작일','기준일'):
            if base['context'].get(k)!=context.get(k):block('AN_SCOPE',k+'가 현재 업무와 다릅니다.','설정')
        if base['blocking']:block('AN_INPUT_LEDGER','분석 입력의 원장·TB·독립통제가 차단되었습니다.',';'.join(x['code'] for x in base['issues'] if x['severity']=='차단'))
    except AuditError as exc:block('AN_INPUT_LEDGER',str(exc),'공통 원장 입력')
    if not ledger_result or ledger_result.get('blocking'):
        block('AN_LEDGER_REQUIRED','현재 업무의 정상 원장·리드 실행이 필요합니다.','현재 업무 원장')
    else:
        try:
            current_tables={k:ledger_result['tables']['입력_'+k] for k in ledger.SCHEMA}
            current=ledger.analyze(current_tables,event)
            if current['blocking']:block('AN_CURRENT_CONTROL','현재 원장 입력을 재검사했을 때 통제가 차단되었습니다.')
            for key in ('리드스케줄','리드집계','원장통제','모듈연결'):
                if digest(current['tables'][key])!=digest(ledger_result['tables'].get(key)):
                    block('AN_CURRENT_STALE','현재 원장 입력과 보관한 '+key+' 결과가 다릅니다.',key)
            for k in ('회사코드','시작일','기준일'):
                if current['context'].get(k)!=context.get(k):block('AN_CURRENT_SCOPE','현재 원장의 '+k+'가 업무와 다릅니다.')
            for sheet,headers in ledger.SCHEMA.items():
                if canonical(tables[sheet],headers)!=canonical(current_tables[sheet],headers):
                    block('AN_LEDGER_DIFF','분석 입력과 현재 업무의 '+sheet+' 모집단·설정이 다릅니다.',sheet)
            for sheet,keys,fields in [('총계정원장',('회사코드','전표ID','행ID'),('계정코드','전기일','차변','대변','적요','작성자')),('시산표',('회사코드','계정코드'),('기초잔액','당기차변','당기대변','기말잔액'))]:
                left={tuple(r.get(k) for k in keys):r for r in tables[sheet]};right={tuple(r.get(k) for k in keys):r for r in current_tables[sheet]}
                for ident in sorted(set(left)|set(right)):
                    a=left.get(ident);b=right.get(ident);ok=bool(a is not None and b is not None and all(a.get(k)==b.get(k) for k in fields))
                    links.append({'구분':sheet,'식별자':' / '.join(str(x) for x in ident),'상태':'일치' if ok else '차이','분석원본행':sheet+'!'+str(a['_row']) if a else '누락','현재원장행':sheet+'!'+str(b['_row']) if b else '누락','분석값':{k:a.get(k) for k in fields} if a else None,'현재값':{k:b.get(k) for k in fields} if b else None})
            detail['현재원장결과SHA256']=digest(ledger_result)
            detail['분석원장행수']=len(tables['총계정원장']);detail['현재원장행수']=len(current_tables['총계정원장'])
        except (KeyError,TypeError,AuditError) as exc:block('AN_CURRENT_INVALID','현재 원장 입력·결과 불완전: '+str(exc))
    valid=not any(x['severity']=='차단' for x in issues)
    detail['현재원장연결']=valid
    return tables,source,{'issues':issues,'tables':{'현재원장연결':links},'detail':detail,'ledger':current,'valid':valid}
