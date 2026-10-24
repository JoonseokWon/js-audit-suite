"""Explicit financial statement graph, complete TB mapping and required note ties.

Structured values only: no PDF extraction, OCR, arbitrary expressions or posting.
"""
from collections import Counter,defaultdict
from decimal import Decimal
import re
from .common import AuditError,num,text,day,issue

VERSION='1.1.0'
CONTEXT=('회사코드','시작일','기준일','통화','연결구분','버전')
SETTING_FIELDS=set(CONTEXT)|{'허용오차원','TB비교기준','자산총계','부채총계','자본총계','당기손익','필수주석본문항목'}
HEADERS={
 '문서':{'문서ID','구분','문서명',*CONTEXT},
 '항목':{'문서ID','항목ID','표ID','명칭','유형','금액','단위','페이지','위치'},
 '합계관계':{'관계ID','문서ID','합계항목','구성항목','계수'},
 '계정매핑':{'계정코드','본문항목','계수'},
 '주석연결':{'연결ID','본문항목','주석문서','주석항목'},
}
UNITS={'원':1,'천원':1000,'백만원':1000000}

def reference(section,index=None):return 'financial:/'+section+('' if index is None else '/'+str(index))

def exact(value,keys,label):
    if not isinstance(value,dict) or set(value)!=set(keys):raise AuditError(label+': 필수 필드 누락·미지원 필드')

def identifier(value,label):
    value=text(value,label)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',value):raise AuditError(label+': 영문·숫자·밑줄·하이픈 ID 필요')
    return value

def won(value,unit):
    if not isinstance(unit,str) or unit not in UNITS:raise AuditError('재무제표 단위는 원·천원·백만원만 지원')
    if isinstance(value,bool) or value is None or not isinstance(value,(int,str)):
        raise AuditError('재무제표 금액 공란·실수형은 허용하지 않습니다. 확정값 문자열 필요')
    s=str(value)
    if not re.fullmatch(r'[+-]?\d{1,14}(?:\.\d{1,6})?',s):raise AuditError('재무제표 금액 형식 오류')
    amount=Decimal(s)*UNITS[unit]
    if amount!=amount.to_integral_value():raise AuditError('환산 후 원 미만 금액은 미지원')
    return num(int(amount))

def analyze(ledger,source):
    """Raise before comparisons on incomplete structure; nonzero differences stay open."""
    exact(source,{'schema_version','설정','TB문맥',*HEADERS},'재무제표 입력')
    if source['schema_version']!='1.1':raise AuditError('재무제표 schema_version은 1.1 필요')
    config=source['설정'];exact(config,SETTING_FIELDS,'재무제표 설정')
    for k in CONTEXT:text(config[k],k)
    exact(source['TB문맥'],set(CONTEXT)|{'잔액기준'},'TB 추출 문맥')
    if any(source['TB문맥'][k]!=config[k] for k in CONTEXT) or source['TB문맥']['잔액기준']!=config['TB비교기준']:
        raise AuditError('TB 추출 문맥과 재무제표 회사·기간·연결구분·버전·잔액기준 불일치')
    if config['연결구분'] not in ('연결','별도') or config['통화']!='KRW':raise AuditError('재무제표 연결/별도·KRW 설정 확인')
    if day(config['시작일'])>day(config['기준일']):raise AuditError('재무제표 기간 순서 오류')
    if config['TB비교기준']!='조정전기말잔액':raise AuditError('현재 TB 비교는 조정전 기말잔액만 지원')
    ledger_config={r['항목']:r['값'] for r in ledger['설정']}
    if any(config[k]!=ledger_config.get(k) for k in ('회사코드','시작일','기준일','통화')):
        raise AuditError('재무제표·원장 회사/기간/통화 불일치')
    tol=num(config['허용오차원'],False)
    if tol>1000000:raise AuditError('허용오차는 0~1,000,000원')
    required=config['필수주석본문항목']
    if not isinstance(required,list) or not required:
        raise AuditError('필수주석 범위는 중복 없는 비어 있지 않은 목록 필요')
    for key in required:identifier(key,'필수주석 본문 ID')
    if len(required)!=len(set(required)):raise AuditError('필수주석 범위 중복')
    for key in ('자산총계','부채총계','자본총계','당기손익'):identifier(config[key],key)
    for section,fields in HEADERS.items():
        rows=source[section]
        if not isinstance(rows,list) or not rows or len(rows)>5000:raise AuditError(section+': 1~5000행 필요')
        for i,r in enumerate(rows):exact(r,fields,reference(section,i))

    docs={};body_ids=[]
    for i,r in enumerate(source['문서']):
        key=identifier(r['문서ID'],'문서ID')
        if key in docs:raise AuditError('문서ID 중복')
        text(r['문서명'],'문서명')
        if r['구분'] not in ('본문','주석'):raise AuditError('문서 구분은 본문/주석')
        if any(r[k]!=config[k] for k in CONTEXT):raise AuditError('문서의 회사·기간·통화·연결구분·버전 불일치: '+key)
        docs[key]=(r,reference('문서',i))
        if r['구분']=='본문':body_ids.append(key)
    if len(body_ids)!=1 or len(docs)<2:raise AuditError('본문 1개와 주석 문서가 필요')
    body=body_ids[0];items={};doc_counts=Counter()
    for i,r in enumerate(source['항목']):
        doc=identifier(r['문서ID'],'항목 문서ID');key=identifier(r['항목ID'],'항목ID')
        if doc not in docs:raise AuditError('항목의 미등록 문서')
        ident=(doc,key)
        if ident in items:raise AuditError('문서 내 항목ID 중복')
        if r['유형'] not in ('명세','합계'):raise AuditError('항목 유형은 명세/합계')
        text(r['명칭']);text(r['표ID']);text(r['위치'])
        if not 1<=num(r['페이지'],False)<=10000:raise AuditError('페이지는 1~10000')
        if doc==body and r['표ID'] not in ('BS','PL'):raise AuditError('본문 표ID는 BS/PL')
        items[ident]={'row':r,'amount':won(r['금액'],r['단위']),'origin':reference('항목',i)}
        doc_counts[doc]+=1
    if set(doc_counts)!=set(docs):raise AuditError('금액 항목 없는 문서')

    edges=defaultdict(list);pairs=set();edge_ids=set()
    for i,r in enumerate(source['합계관계']):
        for field in ('문서ID','합계항목','구성항목'):identifier(r[field],field)
        ident=identifier(r['관계ID'],'관계ID');target=(r['문서ID'],r['합계항목']);child=(r['문서ID'],r['구성항목'])
        if ident in edge_ids or (target,child) in pairs:raise AuditError('합계 관계 또는 구성항목 중복')
        edge_ids.add(ident);pairs.add((target,child));factor=num(r['계수'])
        if target not in items or child not in items:raise AuditError('합계의 미등록 항목 참조')
        if items[target]['row']['유형']!='합계' or factor not in (-1,1):raise AuditError('합계 대상 유형·계수 오류')
        edges[target].append((child,factor,reference('합계관계',i)))
    for key,item in items.items():
        if (item['row']['유형']=='합계')!=(key in edges):raise AuditError('합계의 구성행 누락 또는 명세에 합계식 지정')

    # No evaluated expressions. Detect cycles and repeated leaves in nested totals.
    leaves={};visiting=set()
    def expand(key,depth=0):
        if key in visiting:raise AuditError('합계 순환 참조')
        if depth>64:raise AuditError('합계 중첩은 64단계 이내')
        if key in leaves:return leaves[key]
        visiting.add(key)
        if key not in edges:answer={key:1}
        else:
            answer={}
            for child,factor,_ in edges[key]:
                for leaf,weight in expand(child,depth+1).items():
                    if leaf in answer:raise AuditError('중첩 합계에서 동일 명세가 중복 포함: '+key[1])
                    answer[leaf]=factor*weight
        visiting.remove(key);leaves[key]=answer;return answer
    for key in items:expand(key)

    tb={r['계정코드']:r for r in ledger['시산표']}
    classes={r['계정코드']:r['표시구분'] for r in ledger['계정매핑']}
    if any(classes.get(k)=='PL' and num(r['기초잔액'])!=0 for k,r in tb.items()):
        raise AuditError('당기 손익 비교는 PL 기초잔액이 0인 미마감 TB만 지원. 전기 이월·마감 기준 확인 필요')
    mapped={};contributions=defaultdict(int);mapping_rows=[]
    for i,r in enumerate(source['계정매핑']):
        identifier(r['본문항목'],'본문항목')
        account=text(r['계정코드']);key=(body,r['본문항목']);factor=num(r['계수'])
        if account in mapped:raise AuditError('TB 계정 중복 매핑: '+account)
        if account not in tb or key not in items:raise AuditError('TB 매핑의 미등록 계정·본문 항목')
        item=items[key]
        if item['row']['유형']!='명세' or factor not in (-1,1):raise AuditError('TB는 명세 항목에 +1/-1로 1회 매핑 필요')
        if classes.get(account)!=item['row']['표ID']:raise AuditError('TB와 본문의 BS/PL 분류 불일치')
        v=num(tb[account]['기말잔액'])*factor
        mapped[account]=key;contributions[key]+=v
        mapping_rows.append({'account':account,'body_item':key[1],'body_name':item['row']['명칭'],'factor':factor,'tb_signed':num(tb[account]['기말잔액']),
                             'contribution':v,'source_origins':[f"ledger:시산표:{tb[account]['_row']}",reference('계정매핑',i),item['origin']]})
    if set(mapped)!=set(tb):raise AuditError('TB 미매핑 계정 존재(0원 계정 포함): '+', '.join(sorted(set(tb)-set(mapped))))
    body_leaves={k for k,v in items.items() if k[0]==body and v['row']['유형']=='명세'}
    if body_leaves!=set(mapped.values()):raise AuditError('TB에 연결되지 않은 본문 명세 존재')

    roots={k:(body,config[k]) for k in ('자산총계','부채총계','자본총계','당기손익')}
    if len(set(roots.values()))!=4:raise AuditError('재무제표 필수 총계 ID 중복')
    for name,key in roots.items():
        if key not in edges or items[key]['row']['표ID']!=('PL' if name=='당기손익' else 'BS'):
            raise AuditError('재무제표 필수 총계·표 구분 오류: '+name)
    balance_counts=Counter(k for name,key in roots.items() if name!='당기손익' for k in leaves[key])
    for key in body_leaves:
        if items[key]['row']['표ID']=='BS' and balance_counts[key]!=1:raise AuditError('BS 명세는 자산·부채·자본 총계 중 1회 포함 필요')
        if items[key]['row']['표ID']=='PL' and key not in leaves[roots['당기손익']]:raise AuditError('손익 명세가 당기손익 합계에서 누락')

    # Required note scope is explicit; absence is never treated as zero.
    links=[];link_ids=set();linked_body=set();linked_note=set()
    for i,r in enumerate(source['주석연결']):
        for field in ('본문항목','주석문서','주석항목'):identifier(r[field],field)
        ident=identifier(r['연결ID'],'주석 연결ID');a=(body,r['본문항목']);b=(r['주석문서'],r['주석항목'])
        if ident in link_ids or a in linked_body or b in linked_note:raise AuditError('주석 연결 중복')
        link_ids.add(ident);linked_body.add(a);linked_note.add(b)
        if a not in items or b not in items or docs[b[0]][0]['구분']!='주석':raise AuditError('필수 주석·본문 항목 누락')
        links.append((a,b,reference('주석연결',i)))
    if {k[1] for k in linked_body}!=set(required) or any((body,k) not in items for k in required):
        raise AuditError('선언한 필수 주석 연결 누락·범위 불일치')

    def origins_for(key):
        refs=[items[key]['origin'],docs[key[0]][1],reference('설정'),reference('TB문맥')]
        if key in edges:
            for child,_,ref in edges[key]:refs.extend([ref,items[child]['origin']])
        return refs
    checks=[];issues=[]
    def check(code,category,label,expected,actual,refs,formula,display_label=None):
        delta=num(actual-expected)
        state='일치' if delta==0 else '허용범위내차이' if abs(delta)<=tol else '차이'
        checks.append({'category':category,'code':code,'item':label,'item_label':display_label or label,'expected':num(expected),'actual':num(actual),
                       'difference':delta,'tolerance':tol,'status':state,'formula':formula,
                       'source_origins':list(dict.fromkeys(refs))})
        if delta:issue(issues,code,label+f' {delta:+,}원 ({state}). 허용범위 안의 차이도 검토 필요',', '.join(refs),False)
    for key,relations in edges.items():
        expected=sum(items[c]['amount']*f for c,f,_ in relations)
        check('FS_SUM','합계·소계',key[0]+':'+key[1],expected,items[key]['amount'],origins_for(key),
              ' + '.join(str(f)+'×'+c[1] for c,f,_ in relations),docs[key[0]][0]['구분']+' · '+items[key]['row']['명칭'])
    for key,item in items.items():
        if key[0]!=body:continue
        expected=sum(contributions[leaf]*weight for leaf,weight in leaves[key].items())
        refs=origins_for(key)
        for row in mapping_rows:
            if (body,row['body_item']) in leaves[key]:refs.extend(row['source_origins'])
        check('FS_TB','TB·본문',key[1],expected,item['amount'],refs,'조정전 TB 기말잔액 × 명시한 표시 부호 / 합계식',item['row']['명칭'])
    for a,b,ref in links:
        check('FS_NOTE','본문·주석',a[1]+' ↔ '+b[1],items[a]['amount'],items[b]['amount'],
              [ref]+origins_for(a)+origins_for(b),'같은 회사·기간·연결구분·버전 / 원 환산 후 비교',items[a]['row']['명칭']+' ↔ 주석')
    a,l,e=(roots[n] for n in ('자산총계','부채총계','자본총계'))
    check('FS_BALANCE','재무상태표 등식','자산 = 부채 + 자본',items[l]['amount']+items[e]['amount'],items[a]['amount'],
          origins_for(a)+origins_for(l)+origins_for(e),'자산총계 - (부채총계 + 자본총계)')
    return {'version':VERSION,'context':config,'checks':checks,'issues':issues,'mapping':mapping_rows,
            'coverage':{'tb_accounts':len(tb),'mapped_accounts':len(mapped),'required_note_ties':len(links)},
            'blocking':0,'review':len(issues),'posting_allowed':False}
