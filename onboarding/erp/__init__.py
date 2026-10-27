"""ERP/COA conversion and independently controlled, auditor-confirmed financial bridges."""
from collections import defaultdict
from common import AuditError, cancelled, digest, issue, result
import ledger
from onboarding.contracts import approval, check_payload, ledger_basis
from .schema import APPROVAL_FIELDS, FIELD_LABELS, TABLE_FIELDS, configuration
from .normalize import normalize
from .controls import make_ledger, validate_current, compare_current
from .presentation import present
from .company import verified as company_verified


def _prepare(payload, context, event=None):
    check_payload(payload,context); issues=[]
    config=configuration(payload)
    approval(payload,APPROVAL_FIELDS,issues,'원본·열/계정/부호/독립통제/보고 설정 확인')
    converted,trace,coa,totals=normalize(payload,context,config,issues,event)
    tables,checks=make_ledger(payload,context,converted,coa,totals,issues)
    return tables,trace,checks,issues


def prepare_ledger(payload, context, event=None):
    """Initial registration only. Never infer independent controls or a person's approval."""
    tables,_,_,issues=_prepare(payload,context,event)
    if not company_verified(tables['총계정원장'],context,issues):
        raise AuditError('원장 등록 전 원본 회사 열·회사코드·모집단 범위를 확인하세요. 미확인 회사는 업무 회사로 자동 확정하지 않습니다.')
    verified=ledger.analyze(tables,event)
    issues.extend(verified['issues'])
    blocking=[i for i in issues if i['severity']=='차단']
    if blocking:raise AuditError('원장 등록 전 확인: '+' / '.join(i['message'] for i in blocking[:5]))
    return tables


def _exploration(trace, converted):
    monthly=defaultdict(lambda:[0,0,0,0,0]); byref={r['원장행ID']:r for r in trace}
    journals=defaultdict(list)
    for r in converted:
        ref=r['전표ID']+'/'+r['행ID']; raw=byref[ref]
        key=(r['계정코드'],r['전기일'][:7],raw['부문'])
        t=monthly[key];t[0]+=1;t[1]+=r['차변'];t[2]+=r['대변'];t[3]+=raw['원본차변'];t[4]+=raw['원본대변']
        journals[r['전표ID']].append(r)
    pivot=[{'계정코드':a,'월':m,'부문':dept,'행수':t[0],'차변총액':t[1],'대변총액':t[2],
            '순변동':t[1]-t[2],'원본부호차변':t[3],'원본부호대변':t[4]} for (a,m,dept),t in sorted(monthly.items())]
    explore=[]
    for jid, group in journals.items():
        accounts=';'.join(sorted({r['계정코드'] for r in group}))
        for r in group:
            ref=jid+'/'+r['행ID'];raw=byref[ref]
            explore.append({'전표ID':jid,'원장행ID':ref,'계정코드':r['계정코드'],'전기일':r['전기일'],
                            '차변':r['차변'],'대변':r['대변'],'부문':raw['부문'],'적요':r['적요'],
                            '전표전체계정':accounts,'전표행수':len(group),'취소대상':raw['취소대상'],
                            '원본행':raw['원본행'],'상대계정안내':'전표 전체 탐색 · 복합분개를 일대일 배부하지 않음'})
    return pivot,explore


def analyze(payload, context, ledger_result, event=None):
    issues=[];tables={};linked=False
    detail={'자동승인':False,'검토상태':'사람 검토 전','지원범위':'확정 KRW·명시 매핑의 기계적 대사'}
    try:
        canonical,trace,checks,issues=_prepare(payload,context,event)
        cancelled(event)
        identity_ok=company_verified(canonical['총계정원장'],context,issues)
        prepared=ledger.analyze(canonical,event) if identity_ok else None
        if prepared:issues.extend(prepared['issues'])
        fresh=validate_current(ledger_result,context,issues) if identity_ok else None
        if fresh:
            compare_current(canonical['총계정원장'],fresh,checks,issues)
            fields={'시산표':('계정코드','기초잔액','당기차변','당기대변','기말잔액'),
                    '계정매핑':('계정코드','리드코드','리드명','표시구분'),
                    '감사조정':('조정ID','행ID','계정코드','차변','대변','근거','상태')}
            for name, keys in fields.items():
                left=sorted(tuple(str(r[k]) for k in keys) for r in canonical[name])
                right=sorted(tuple(str(r[k]) for k in keys) for r in fresh['tables']['입력_'+name])
                if left!=right:issue(issues,'ERP_LEDGER_BASIS','별도 TB·확인 조정과 현재 원장의 기준이 다릅니다.',name)
        pivot,explore=_exploration(trace,canonical['총계정원장'])
        tables={'원본부호변환':trace,'독립통제대사':checks,'계정월부문분석':pivot,
                '전표전체탐색':explore,'조정전후리드':prepared['tables']['리드스케줄'] if prepared else []}
        if fresh:tables.update(present(payload,prepared,issues))
        linked=bool(fresh) and not any(i['severity']=='차단' for i in issues)
        detail.update(회사식별확인=identity_ok,회사식별범위='원본의 명시 회사열·코드 매핑 대조. 실제 소속·추출 신뢰성 인증 아님.',
                      입력확인대상해시=digest({k:payload.get(k) for k in APPROVAL_FIELDS}),
                      원장결과해시=ledger_basis(ledger_result) if ledger_result else '',
                      원본자료해시=digest(payload.get('source_rows',[])),
                      원본해시안내='행별 원본 SHA는 선언값입니다. 원본 Excel 가져오기는 실제 파일 SHA와 행을 함께 보존합니다.',
                      매핑정책해시=digest({k:payload.get(k) for k in ('column_mapping','company_mapping','coa_mapping','config','presentation_mapping')}))
    except (AuditError,KeyError,TypeError,ValueError) as exc:
        issue(issues,'ERP_INPUT',str(exc));tables={}
    detail['현재원장연결']=linked
    metrics={'원본행수':len(tables.get('원본부호변환',[])),
             '원장연결행수':len(tables.get('전표전체탐색',[])),
             '보고대사항목수':len(tables.get('조정후본문주석대사',[])),
             '차이항목수':sum(bool(r['차이']) for r in tables.get('조정후본문주석대사',[]))}
    return result('실무자료·원장',context,tables,issues,metrics,detail)


from .samples import sample, negative_cases
