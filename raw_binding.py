"""Bind a raw evidence package to the actual pinned workspace ledger, not a declared balance."""
from common import *

def analyze(path,context,ledger_result=None,event=None):
    from raw_sources import load_pack
    from raw_accounts import analyze as analyze_accounts
    import ledger
    scope={**context,'통화':context.get('통화','KRW'),'연결구분':context.get('연결구분','별도')}
    pack=load_pack(path,scope,event)
    out=analyze_accounts(pack,context,event)
    rows=[];out['tables']['현재원장연결']=rows
    if not ledger_result or ledger_result.get('blocking'):
        issue(out['issues'],'RAW_LEDGER_REQUIRED','차단 없는 현재 원장·리드 검사를 먼저 실행하세요.')
    else:
        for role,key in [('총계정원장','행ID'),('시산표','계정코드')]:
            headers=ledger.SCHEMA[role]
            candidates=[t for t in pack['catalog']['tables'] if t['sheet']==role and t['headers']==headers]
            actual=ledger_result['tables'].get('입력_'+role,[])
            if len(candidates)!=1 or not actual:
                issue(out['issues'],'RAW_LEDGER_SOURCE','원천팩의 '+role+' 선택이 모호하거나 현재 원장 입력이 없습니다.');continue
            table=candidates[0]
            expected=[dict(zip(headers,r['values'])) for r in table['rows']]
            def index(records):
                values={}
                for r in records:
                    identity=dumps([r.get('회사코드'),r.get('전표ID'),r.get('행ID')]) if role=='총계정원장' else dumps([r.get('회사코드'),r.get(key)])
                    if identity in values:raise AuditError('원장 행/계정 ID 중복')
                    values[identity]={h:r.get(h) for h in headers}
                return values
            left,right=index(expected),index(actual)
            for identity in sorted(left.keys()|right.keys()):
                matched=left.get(identity)==right.get(identity)
                rows.append({'구분':role,'식별자':identity,'상태':'일치' if matched else '차이','원천자료ID':table['dataset_id'],
                             '원천값':left.get(identity),'현재원장값':right.get(identity),'원본위치':table['source_file']+'#'+role})
                if not matched:issue(out['issues'],'RAW_CURRENT_LEDGER_DIFF','원천팩과 현재 업무 '+role+' 값/범위 차이',role+':'+identity)
    out['blocking']=sum(i['severity']=='차단' for i in out['issues']);out['review']=sum(i['severity']=='검토' for i in out['issues'])
    out['status']='INPUT_BLOCKED' if out['blocking'] else 'EXCEPTION' if out['review'] else 'REVIEW_PENDING'
    out['detail']['status']=out['status']
    out['detail']['현재원장대사행수']=len(rows)
    out['detail']['현재원장결과해시']=digest(ledger_result) if ledger_result else None
    return plain(out)
