"""Reconcile against separately supplied TB and extraction controls, never self-certify a GL."""
from collections import defaultdict
from copy import deepcopy
from common import AuditError, digest, issue, text
import ledger
from onboarding.contracts import reconciliation
from .schema import adjustment_hash, integer, rows


def adjustments(payload, accounts, issues):
    grouped=defaultdict(list); approvals={}; result=[]
    for r in rows(payload,'adjustment_approvals'):
        key=text(r.get('adjustment_id'))
        if key in approvals:raise AuditError('조정 확인 기록 중복')
        approvals[key]=r
    seen=set()
    for r in rows(payload,'adjustments'):
        key=text(r.get('adjustment_id')); ident=(key,text(r.get('line_id')))
        if ident in seen:issue(issues,'ERP_AJE_DUP','조정 행 중복',str(ident))
        seen.add(ident);grouped[key].append(r)
        d=integer(r.get('debit'),False);c=integer(r.get('credit'),False)
        if r.get('account_code') not in accounts or (d and c) or r.get('status') not in ('초안','승인'):
            raise AuditError('감사조정 계정·금액·상태 오류')
        text(r.get('evidence'))
    for key, group in grouped.items():
        if len({r['status'] for r in group})!=1 or sum(integer(r['debit'])-integer(r['credit']) for r in group):
            issue(issues,'ERP_AJE_BALANCE','조정 전표별 차대·상태 불일치',key)
            continue
        status=group[0]['status']
        if status=='승인':
            record=approvals.get(key,{})
            if not (record.get('input_hash')==adjustment_hash(group)
                    and isinstance(record.get('actor'),str) and record['actor'].strip()
                    and isinstance(record.get('reason'),str) and record['reason'].strip()):
                issue(issues,'ERP_AJE_APPROVAL','현재 조정값에 대한 확인자·사유·해시가 필요합니다.',key)
                continue
        for r in group:
            result.append({'조정ID':key,'행ID':r['line_id'],'계정코드':r['account_code'],
                           '차변':integer(r['debit']),'대변':integer(r['credit']),
                           '근거':r['evidence'],'상태':status})
    if set(approvals)-set(grouped):issue(issues,'ERP_AJE_ORPHAN','연결할 조정이 없는 확인 기록이 있습니다.')
    return result


def make_ledger(payload, context, converted, coa, totals, issues):
    tables={key:[] for key in ledger.SCHEMA}; checks=[]
    accounts={r['account_code']:r for r in coa.values()}
    settings={k:context[k] for k in ('회사코드','시작일','기준일')}
    settings.update(통화='KRW',추출범위=';'.join(sorted(accounts)))
    tables['설정']=[{'항목':k,'값':v} for k,v in settings.items()]
    tables['총계정원장']=converted
    tb={};controls={}
    for r in rows(payload,'trial_balance'):
        code=text(r.get('account_code'))
        if code in tb:raise AuditError('별도 시산표 계정 중복')
        tb[code]=r
    for r in rows(payload,'independent_controls'):
        code=text(r.get('account_code'))
        if code in controls:raise AuditError('독립통제 계정 중복')
        controls[code]=r
    if set(tb)!=set(accounts) or set(controls)!=set(accounts) or set(totals)-set(accounts):
        issue(issues,'ERP_CONTROL_SCOPE','매핑·시산표·독립통제의 계정 범위가 다릅니다.')
    for code, account in sorted(accounts.items()):
        tables['계정매핑'].append({'계정코드':code,'리드코드':account['lead_code'],
                                  '리드명':account['lead_name'],'표시구분':account['statement_type']})
        if code not in tb or code not in controls:continue
        r=tb[code]; ctl=controls[code]; actual=totals.get(code,[0]*5)
        for label,field,position in (('원본 행수','row_count',0),('원본 부호 차변','source_debit_total',1),
                                     ('원본 부호 대변','source_credit_total',2),('정규화 차변','debit_total',3),
                                     ('정규화 대변','credit_total',4)):
            expected=integer(ctl.get(field),field.startswith('source_'))
            reconciliation(checks,code+' '+label,expected,actual[position],code,issues)
        values={f:integer(r.get(f),f in ('opening','closing')) for f in ('opening','debit','credit','closing')}
        tables['시산표'].append({'회사코드':context['회사코드'],'계정코드':code,'계정명':account['account_name'],
             '기초잔액':values['opening'],'당기차변':values['debit'],'당기대변':values['credit'],'기말잔액':values['closing']})
        tables['독립통제'].append({**{k:context[k] for k in ('회사코드','시작일','기준일')},'계정코드':code,
             '원장행수':integer(ctl['row_count'],False),'차변합계':integer(ctl['debit_total'],False),
             '대변합계':integer(ctl['credit_total'],False),'기초잔액':integer(ctl.get('opening')),
             '기말잔액':integer(ctl.get('closing')),'추출근거':text(ctl.get('extract_basis')),
             '추출일시':text(ctl.get('extracted_at')),'작성자':text(ctl.get('actor'))})
        if account['statement_type']=='PL' and values['opening']:
            issue(issues,'ERP_PL_OPENING','미마감 당기 PL의 기초잔액을 확인하세요. 마감·이월을 추정하지 않습니다.',code)
    tables['감사조정']=adjustments(payload,accounts,issues)
    for sheet, items in tables.items():
        for n,r in enumerate(items,2):r.update(_row=n,_sheet=sheet)
    return tables,checks


def validate_current(current, context, issues):
    if (not isinstance(current,dict) or current.get('module')!='원장·리드'
        or type(current.get('blocking')) is not int or current['blocking']!=0
        or any(i.get('severity')=='차단' for i in current.get('issues',[]))
        or any(current.get('context',{}).get(k)!=context[k] for k in ('회사코드','시작일','기준일'))):
        issue(issues,'ERP_LEDGER_REQUIRED','현재 업무에서 독립통제를 통과한 최신 원장 검사가 필요합니다.')
        return None
    try:
        source={key:deepcopy(current['tables']['입력_'+key]) for key in ledger.SCHEMA}
        fresh=ledger.analyze(source)
        if fresh['blocking'] or any(fresh['tables'][k]!=current['tables'].get(k) for k in ('리드스케줄','원장통제')):
            raise AuditError('원장 재검산과 저장된 결과가 다릅니다.')
    except (AuditError,KeyError,TypeError,ValueError):
        issue(issues,'ERP_LEDGER_STALE','최신 원장 입력을 다시 검사하세요. 원장 결과를 재사용할 수 없습니다.')
        return None
    return fresh


def compare_current(converted, current, checks, issues):
    actual={r['전표ID']+'/'+r['행ID']:r for r in converted}
    expected={r['전표ID']+'/'+r['행ID']:r for r in current['tables']['입력_총계정원장']}
    fields=('회사코드','전표ID','행ID','전기일','계정코드','차변','대변','적요','작성자')
    for key in sorted(set(actual)|set(expected)):
        match=key in actual and key in expected and all(actual[key][f]==expected[key][f] for f in fields)
        checks.append({'검사':'현재 원장 행 연결','원본행':key,'기대':1,'실제':int(match),
                       '차이':int(match)-1,'상태':'일치' if match else '차이'})
        if not match:issue(issues,'ERP_LEDGER_ROW','변환 자료와 현재 원장의 행·값이 다릅니다.',key)
