"""Offline, explainable full-journal analysis on a validated current ledger.

Candidate flags are inspection prompts, never fraud findings or probabilities.
Posting dates/authors do not establish manual posting, entry time or approval.
"""
from collections import defaultdict
import calendar
from common import AuditError, cancelled, day, digest, issue, num, plain, result, text
from analytics_support import read_bound

VERSION='GLA-1.0'
EXTRA_SCHEMA={'GLA설정':['항목','값']}
SCHEMA=EXTRA_SCHEMA
DEFAULT_SETTINGS={'규칙버전':VERSION,'주말검토':'사용','월말검토':'사용','월말범위일':0,
                  '고액검토':'사용','고액기준원':1000000,'반복검토':'사용','반복최소횟수':2}
RULES={
    'GLA_WEEKEND':('주말 전기일','주말검토','제공된 전기일 중 토·일요일이 있는 전표',
                   '휴일 운영·승인 일정, 실제 거래일과 시스템 입력시각을 별도 증빙으로 확인하세요.',2),
    'GLA_MONTH_END':('월말 전기일','월말검토','달력상 월말까지 남은 일수가 설정 범위 이내인 전표',
                     '정상 결산분개 여부와 기간귀속·승인·후속 반제·증빙을 확인하세요.',1),
    'GLA_HIGH_AMOUNT':('고액 전표','고액검토','전표 차변 합계가 고액기준원 이상(차대 중복합산·abs 사용 없음)',
                       '거래 실질·계약·승인권한·상대방·기간귀속 및 전표 전체 구성행을 확인하세요.',3),
    'GLA_REPEAT':('동일 계정·차대 금액 구성 반복','반복검토','회사별 전표의 계정코드·차변·대변 구성 다중집합이 최소횟수 이상 반복',
                  '정기 정상 거래·분할 인식·취소/재기표인지 확인하고 원천 증빙 번호와 중복 인식을 조사하세요.',2),
}


def settings(rows):
    if not isinstance(rows,list):raise AuditError('GLA설정 표가 필요합니다.')
    values={}
    for r in rows:
        k=text(r.get('항목'),'GLA설정 항목')
        if k in values:raise AuditError('GLA설정 항목 중복: '+k)
        values[k]=r.get('값')
    if set(values)!=set(DEFAULT_SETTINGS):raise AuditError('GLA설정 필수 항목 누락·미지원 항목')
    if values['규칙버전']!=VERSION:raise AuditError('GLA 규칙버전은 '+VERSION+' 필요')
    for field in ('주말검토','월말검토','고액검토','반복검토'):
        if values[field] not in ('사용','미사용'):raise AuditError(field+': 사용/미사용만 허용')
    for field in ('월말범위일','고액기준원','반복최소횟수'):values[field]=num(values[field],False)
    if not 0<=values['월말범위일']<=7:raise AuditError('월말범위일은 0~7(0은 마지막 날)')
    if values['고액기준원']<=0:raise AuditError('고액기준원은 1원 이상')
    if not 2<=values['반복최소횟수']<=10000:raise AuditError('반복최소횟수는 2~10000')
    return values


def analyze(path,context,ledger_result=None,event=None):
    cancelled(event)
    tables={'현재원장연결':[],'월별집계':[],'계정별집계':[],'작성자별집계':[],
            '계정조합':[],'전표계정조합':[],'반복그룹색인':[],'검토후보':[],'규칙검토범위':[],'후속절차':[]}
    issues=[];metrics={'원장행수':0,'전표수':0,'월수':0,'계정수':0,'작성자수':0,'계정조합수':0,
                       '위험후보수':0,'위험전표수':0,'미확인규칙수':0,'복합대응미확인전표수':0}
    detail={'규칙버전':VERSION,'실행방식':'오프라인 규칙 기반. 외부 AI 전송·실제 AI 추론 없음.',
            '후보의미':'조건에 해당하는 검토 우선순위. 부정·오류 확정 또는 발생확률이 아님.',
            '반복정책':'계정·차변·대변 구성만 비교. 전표ID·전기일·적요 차이에도 정상 정기 거래가 후보가 될 수 있음.',
            '금액정책':'전표 차변합계로 규모를 표시. 차변+대변을 더하거나 부호를 abs로 변환하지 않음.',
            '계정조합정책':'계정집합 1:1과 개별 행 대응을 구분. 총2행이면서 활성 차변1행·대변1행일 때만 행 1:1. 다른 분개는 개별 대응·현금흐름 추정 금지.',
            '작성자':None,'수행':None,'검토자':None,'결론':None,'검토확정':False,'조정승인':False,'부정확정':False}
    source=None
    try:
        inputs,source,binding=read_bound(path,EXTRA_SCHEMA,context,ledger_result,event)
        tables.update(binding['tables']);issues.extend(binding['issues']);detail.update(binding['detail'])
        if not binding['valid']:
            tables['규칙검토범위']=[{'규칙ID':'GLA_ALL','상태':'차단','검사대상수':0,'후보수':0,
                '미확인수':len(inputs.get('총계정원장',[])),'조건':'입력 원장 통제 및 현재 원장 연결 필요','원본행':'공통 원장 7시트',
                '후속절차':'원장·TB·통제와 업무 범위를 보완한 뒤 현재 원장 및 분석을 재실행하세요.'}]
        else:
            config=settings(inputs['GLA설정']);detail['규칙설정']=config
            gl=inputs['총계정원장'];journals=defaultdict(list)
            for r in gl:
                cancelled(event);journals[(r['회사코드'],r['전표ID'])].append(r)
            monthly=defaultdict(list);accounts=defaultdict(list);authors=defaultdict(list)
            for r in gl:
                monthly[day(r['전기일']).strftime('%Y-%m')].append(r)
                accounts[r['계정코드']].append(r);authors[r['작성자']].append(r)
            def refs(rows):return ' | '.join('총계정원장!'+str(r['_row']) for r in rows)
            def totals(rows):return {'원장행수':len(rows),'전표수':len({(r['회사코드'],r['전표ID']) for r in rows}),
                                    '차변합계':sum(num(r['차변'],False) for r in rows),'대변합계':sum(num(r['대변'],False) for r in rows)}
            for month,rows in sorted(monthly.items()):
                tables['월별집계'].append({'월':month,**totals(rows),'순변동':sum(num(r['차변'])-num(r['대변']) for r in rows),'원본행':refs(rows)})
            leads={r['계정코드']:r for r in binding['ledger']['tables']['리드스케줄']}
            for account,lead in sorted(leads.items()):
                rows=accounts.get(account,[])
                tables['계정별집계'].append({'계정코드':account,'계정명':lead['계정명'],'리드코드':lead['리드코드'],
                    **totals(rows),'기초잔액':lead['기초잔액'],'조정전':lead['조정전'],'순변동':lead['차변']-lead['대변'],
                    '원본행':refs(rows)+(' | ' if rows else '')+lead['원본행']})
            for author,rows in sorted(authors.items()):
                tables['작성자별집계'].append({'작성자':author,**totals(rows),'월수':len({day(r['전기일']).strftime('%Y-%m') for r in rows}),
                    '사실범위':'제공된 작성자 문자열. 실제 사용자 인증·수동 여부 미확인.','원본행':refs(rows)})
            signatures=defaultdict(list);combos=defaultdict(list);facts={};compound_count=0
            for identity,rows in sorted(journals.items()):
                debit=tuple(sorted({r['계정코드'] for r in rows if num(r['차변'])!=0}))
                credit=tuple(sorted({r['계정코드'] for r in rows if num(r['대변'])!=0}))
                signature=tuple(sorted((r['계정코드'],num(r['차변']),num(r['대변'])) for r in rows))
                signatures[(identity[0],signature)].append(identity)
                account_pair=len(debit)==len(credit)==1
                debit_rows=sum(num(r['차변'])!=0 for r in rows)
                credit_rows=sum(num(r['대변'])!=0 for r in rows)
                simple=account_pair and len(rows)==2 and debit_rows==credit_rows==1
                compound=not simple
                compound_count+=compound
                label='단순 1:1' if simple else '계정집합 1:1·개별 행 대응 미확인' if account_pair else '복합분개·개별 대응 미확인' if debit and credit else '영금액·대응 미확인'
                amount=sum(num(r['차변'],False) for r in rows)
                dates=sorted({str(r['전기일']) for r in rows});key=(debit,credit,label)
                combos[key].append(identity)
                facts[identity]={'rows':rows,'amount':amount,'dates':dates,'signature':(identity[0],signature)}
                tables['전표계정조합'].append({'회사코드':identity[0],'전표ID':identity[1],'전기일':dates,
                    '차변계정집합':list(debit),'대변계정집합':list(credit),'전표차변합계':amount,'원장행수':len(rows),
                    '대응구분':label,'계정집합1대1':account_pair,'차변행수':debit_rows,'대변행수':credit_rows,
                    '개별대응확인':simple,'원본행':refs(rows)})
            for (debit,credit,label),ids in sorted(combos.items()):
                rows=[r for i in ids for r in facts[i]['rows']]
                tables['계정조합'].append({'차변계정집합':list(debit),'대변계정집합':list(credit),'대응구분':label,
                    '전표수':len(ids),'전표차변합계':sum(facts[i]['amount'] for i in ids),'전표ID':[i[1] for i in ids],
                    '원본행':refs(rows),'미확인범위':'' if label=='단순 1:1' else '개별 차대행 대응·거래 실질·현금흐름 미확인'})
            repeat_ids={}
            for signature,ids in sorted(signatures.items()):
                if len(ids)<2:continue
                group_id='GLA-REP-'+digest(signature)[:16]
                repeat_ids[signature]=group_id
                tables['반복그룹색인'].append({'반복그룹ID':group_id,'회사코드':signature[0],'전표수':len(ids),
                    '계정금액구성':[{'계정코드':a,'차변':d,'대변':c} for a,d,c in signature[1]],
                    '전표ID':[i[1] for i in ids],'원본행':refs([r for i in ids for r in facts[i]['rows']]),
                    '설정최소횟수':config['반복최소횟수'],'탐지기준충족':config['반복검토']=='사용' and len(ids)>=config['반복최소횟수'],
                    '해석':'같은 계정·차대 구성 색인. 동일 거래·오류 확정 아님.'})
            candidate_counts=defaultdict(int);risk_journals=set()
            for identity,fact in sorted(facts.items()):
                cancelled(event);dates=[day(v) for v in fact['dates']]
                repeats=signatures[fact['signature']]
                conditions={
                    'GLA_WEEKEND':(any(d.weekday()>=5 for d in dates),'전기일 '+', '.join(fact['dates'])+' 중 토·일요일'),
                    'GLA_MONTH_END':(any(calendar.monthrange(d.year,d.month)[1]-d.day<=config['월말범위일'] for d in dates),
                        '전기일 '+', '.join(fact['dates'])+f" / 월말까지 {config['월말범위일']}일 이내"),
                    'GLA_HIGH_AMOUNT':(fact['amount']>=config['고액기준원'],f"전표 차변합계 {fact['amount']:,}원 ≥ {config['고액기준원']:,}원"),
                    'GLA_REPEAT':(len(repeats)>=config['반복최소횟수'],f"동일 계정·차대 구성 {len(repeats)}회 / 기준 {config['반복최소횟수']}회 / 그룹 "+repeat_ids.get(fact['signature'],'해당없음')),
                }
                for rule,(matched,reason) in conditions.items():
                    label,enabled,_,follow,priority=RULES[rule]
                    if config[enabled]!='사용' or not matched:continue
                    candidate_counts[rule]+=1;risk_journals.add(identity)
                    cid=rule+'-'+digest(identity)[:16];origin=refs(fact['rows'])
                    candidate={'후보ID':cid,'규칙ID':rule,'후보유형':label,'회사코드':identity[0],'전표ID':identity[1],
                        '전기일':fact['dates'],'금액':fact['amount'],'사유':reason,'원본행':origin,'후속절차':follow,
                        '우선순위':priority,'반복그룹ID':repeat_ids.get(fact['signature'],'') if rule=='GLA_REPEAT' else '',
                        '상태':'검토후보(부정 확정 아님)','수행':None,'결론':None,'검토자':None}
                    tables['검토후보'].append(candidate)
                    tables['후속절차'].append({'후보ID':cid,'규칙ID':rule,'전표ID':identity[1],'필요확인':follow,
                        '원본행':origin,'수행':None,'추가증거':None,'결론':None,'검토자':None})
                    issue(issues,rule,reason+' / 정상 거래일 수 있으므로 증빙·승인 및 회계적 판단 필요',origin,False)
            for rule,(label,enabled,condition,follow,_) in RULES.items():
                active=config[enabled]=='사용'
                tables['규칙검토범위'].append({'규칙ID':rule,'규칙명':label,'상태':'검사·미검토' if active else '미적용(사용안함)',
                    '검사대상수':len(journals) if active else 0,'후보수':candidate_counts[rule],
                    '미확인수':0 if active else len(journals),'조건':condition,'설정':config,
                    '원본행':' | '.join('GLA설정!'+str(r['_row']) for r in inputs['GLA설정']),'후속절차':follow})
            for rule,label,missing in [('GLA_MANUAL','수동·자동 분개 구분','수동/자동·원천 시스템 메타 없음'),
                                       ('GLA_NIGHT','심야 시스템 입력','시간대 포함 실제 입력시각 없음. 전기일로 추정 금지'),
                                       ('GLA_APPROVAL','승인 적정성','승인자·권한·승인시각 메타 없음')]:
                tables['규칙검토범위'].append({'규칙ID':rule,'규칙명':label,'상태':'미확인','검사대상수':0,
                    '후보수':0,'미확인수':len(journals),'조건':missing,'원본행':'제공된 원장 필드 범위',
                    '후속절차':'명시적인 시스템 입력·승인 메타와 독립 통제를 수령하고 FIA 등 별도 절차로 확인하세요.'})
            tables['규칙검토범위'].append({'규칙ID':'GLA_PAIR','규칙명':'계정조합 대응','상태':'집계·복합대응 미확인' if compound_count else '집계·미검토',
                '검사대상수':len(journals),'후보수':0,'미확인수':compound_count,
                '조건':'복합분개는 계정집합만 집계. 차대 행 사이 임의 곱집합·금액 대응 없음.','원본행':'전표계정조합 표의 전표별 원본행',
                '후속절차':'복합분개는 실제 전표·거래증빙으로 개별 대응 관계를 확인하세요.'})
            metrics.update(원장행수=len(gl),전표수=len(journals),월수=len(monthly),계정수=len(leads),작성자수=len(authors),
                계정조합수=len(combos),위험후보수=len(tables['검토후보']),위험전표수=len(risk_journals),미확인규칙수=3,복합대응미확인전표수=compound_count)
            detail.update(검사대상수={'원장행수':len(gl),'전표수':len(journals)},미확인수={'메타규칙':3,'복합대응전표':compound_count},
                          부정확정=False,표시상태='검토후보·추가자료 필요' if tables['검토후보'] else '조건 해당 없음·수동 판단 미수행')
            tables.update({'입력_'+k:v for k,v in inputs.items()})
    except (AuditError,OSError,KeyError,TypeError,ValueError) as exc:
        cancelled(event);issue(issues,'GLA_INPUT',str(exc),'GLA설정 또는 공통 원장 입력')
        for key in ('월별집계','계정별집계','작성자별집계','계정조합','전표계정조합','반복그룹색인','검토후보','후속절차'):tables[key]=[]
        tables['규칙검토범위']=[{'규칙ID':'GLA_ALL','상태':'차단','검사대상수':0,'후보수':0,'미확인수':None,
            '조건':'유효한 설정·입력·현재 원장 연결 필요','원본행':'GLA설정 또는 공통 원장 입력','후속절차':'원본을 보완한 뒤 재실행하세요.'}]
    cancelled(event)
    out=result('GLA',context,tables,issues,metrics,detail)
    if source is not None:out['source']=source
    return out


def write_samples(target):
    from .samples import write_samples as write
    return write(target)
