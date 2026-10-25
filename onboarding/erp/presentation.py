"""Signed, basis-specific TB to selected BS/PL/note/cost lines and explicit netting groups."""
from collections import defaultdict
from common import AuditError, issue, text
from onboarding.contracts import reconciliation
from .schema import integer, rows

BASES={'opening':'기초잔액','movement':None,'pre_adjustment':'조정전','post_adjustment':'조정후'}


def present(payload, result, issues):
    reporting_basis=payload['config']['reporting_basis']
    lead={r['계정코드']:r for r in result['tables']['리드스케줄']}
    gl={r['전표ID']+'/'+r['행ID']:r for r in result['tables']['입력_총계정원장']}
    lines={}; seen=set(); mapped=defaultdict(set); links=[]; checks=[]; groups=defaultdict(list)
    for r in rows(payload,'presentation_mapping'):
        statement=text(r.get('statement')); line=text(r.get('line_id')); code=text(r.get('account_code'))
        basis=r.get('basis'); sign=integer(r.get('sign')); group=str(r.get('validation_group') or '')
        policy=r.get('group_policy','individual'); reason=str(r.get('group_basis') or '')
        if statement not in ('BS','PL','NOTE','COST') or code not in lead or basis not in BASES or sign not in (-1,1):
            raise AuditError('본문·주석·원가 매핑 문서/계정/기준/부호 오류')
        if (statement in ('BS','PL') or basis in ('pre_adjustment','post_adjustment')) and basis!=reporting_basis:
            issue(issues,'ERP_FS_BASIS','재무제표 전체의 공통 조정전·후 기준과 매핑이 다릅니다.',statement+'/'+line)
        if policy not in ('individual','net') or (policy=='net' and (not group or not reason.strip())):
            raise AuditError('그룹 상쇄에는 명시된 동일 그룹과 근거가 필요합니다.')
        if statement in ('BS','PL') and lead[code]['표시구분']!=statement:
            issue(issues,'ERP_STATEMENT_TYPE','BS/PL 분류와 본문 매핑이 다릅니다.',code)
        refs=str(r.get('ledger_refs') or '').split(';') if r.get('ledger_refs') else []
        identity=(statement,line,code)
        if identity in seen:raise AuditError('같은 본문 항목의 계정 매핑 중복')
        seen.add(identity); mapped[statement].add(code)
        if statement in ('BS','PL') and refs:raise AuditError('BS/PL 본문은 계정 전체를 연결해야 합니다.')
        if refs:
            if basis!='movement' or len(refs)!=len(set(refs)) or any(ref not in gl or gl[ref]['계정코드']!=code for ref in refs):
                raise AuditError('부분 원가·주석은 같은 계정의 현재 원장 행을 중복 없이 연결하세요.')
            amount=sum(gl[ref]['차변']-gl[ref]['대변'] for ref in refs)
        else:
            amount=(lead[code]['차변']-lead[code]['대변']) if basis=='movement' else lead[code][BASES[basis]]
        key=(statement,line); metadata=(basis,group,policy,reason)
        target=lines.setdefault(key,{'amount':0,'meta':metadata,'refs':[]})
        if target['meta']!=metadata:raise AuditError('한 보고 항목에 잔액 기준·검증 그룹이 혼용됐습니다.')
        target['amount']+=amount*sign;target['refs'].extend(refs or [lead[code]['원본행']])
        links.append({'문서':statement,'항목ID':line,'계정코드':code,'잔액기준':basis,
                      '원장금액':amount,'표시부호':sign,'반영금액':amount*sign,
                      '검증그룹':group,'원본행':';'.join(refs) if refs else lead[code]['원본행']})
    for statement in ('BS','PL'):
        expected={code for code,r in lead.items() if r['표시구분']==statement}
        if mapped[statement]!=expected:
            issue(issues,'ERP_PRESENTATION_SCOPE',statement+' 본문에 미매핑·중복 범위가 있습니다.',
                  ';'.join(sorted(expected-mapped[statement])))
        counts=defaultdict(int)
        for doc,_,code in seen:
            if doc==statement:counts[code]+=1
        if any(n!=1 for n in counts.values()):issue(issues,'ERP_PRESENTATION_DUP',statement+' 계정이 여러 본문 항목에 중복 반영됩니다.')
    values={}
    for r in rows(payload,'presentation_values'):
        key=(text(r.get('statement')),text(r.get('line_id')))
        if key in values:raise AuditError('보고 금액 항목 중복')
        if str(r.get('formula') or '').strip():raise AuditError('수식 캐시·TRUE를 검산 결과로 사용하지 않습니다. 확정값을 입력하세요.')
        basis=r.get('basis')
        if (key[0] in ('BS','PL') or basis in ('pre_adjustment','post_adjustment')) and basis!=reporting_basis:
            issue(issues,'ERP_FS_BASIS','재무제표 전체의 공통 조정전·후 기준과 보고금액이 다릅니다.','/'.join(key))
        unit=integer(r.get('unit'),False)
        if unit not in (1,1000):raise AuditError('보고 단위는 1 또는 1000입니다.')
        values[key]=(integer(r.get('amount'))*unit,r.get('basis'))
    if set(values)!=set(lines):issue(issues,'ERP_PRESENTATION_VALUES','매핑 항목과 보고 금액 항목 범위가 다릅니다.')
    for key, target in lines.items():
        if key not in values:continue
        reported,basis=values[key];expected=target['amount'];configured,group,policy,reason=target['meta']
        if basis!=configured:issue(issues,'ERP_BASIS_MIX','조정전/조정후·당기변동 기준이 혼용되었습니다.','/'.join(key))
        difference=reported-expected
        record={'문서':key[0],'항목ID':key[1],'잔액기준':configured,'원장기대금액':expected,
                '보고금액':reported,'차이':difference,'검증그룹':group,'그룹정책':policy,
                '상태':'일치' if not difference else '차이','원본행':';'.join(target['refs'])}
        checks.append(record)
        if group:groups[(key[0],configured,group)].append((record,policy,reason))
        elif difference:issue(issues,'ERP_PRESENTATION_DIFFERENCE','보고 항목과 원장 금액이 다릅니다.','/'.join(key))
    groupchecks=[]
    for (statement,basis,group),members in groups.items():
        residual=sum(r['차이'] for r,_,_ in members)
        net=all(policy=='net' for _,policy,_ in members) and len(members)>1
        failed=bool(residual) or (not net and any(r['차이'] for r,_,_ in members))
        groupchecks.append({'문서':statement,'잔액기준':basis,'검증그룹':group,'구성항목수':len(members),
                            '순차이':residual,'개별차이수':sum(bool(r['차이']) for r,_,_ in members),
                            '상태':'차이' if failed else '그룹 일치' if net else '개별 일치'})
        if failed:issue(issues,'ERP_VALIDATION_GROUP','같은 검증 그룹 내 차이를 확인하세요.',statement+'/'+group)
        elif net and any(r['차이'] for r,_,_ in members):
            issue(issues,'ERP_GROUP_NETTING','승인된 동일 그룹 안에서만 잔차가 상쇄됩니다. 개별 잔차는 보존했습니다.',group,False)
    return {'조정후본문주석대사':checks,'본문원장연결':links,'검증그룹':groupchecks}
