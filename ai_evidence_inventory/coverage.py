"""Count actual final row excerpts; hashes never stand in for read content."""
from common import AuditError
from .hashing import canonical_hash


def default_plan(run,limit):
    names=sorted((n for n in run['result']['tables'] if not n.startswith('입력_')),
        key=lambda n:(not any(k in n for k in ('대사','예외','차이','미확인','통제')),n))
    return names[:limit]


def inventory(packet,runs,selected_tables=None,table_hashes=None):
    if table_hashes is None:table_hashes={}
    ids=[r.get('id') for r in runs]
    if any(not isinstance(rid,str) or not rid for rid in ids) or len(set(ids))!=len(ids):
        raise AuditError('계산표 명세의 실행ID가 없거나 중복되었습니다.')
    by_id={r['id']:r for r in runs};indices={r['id']:n for n,r in enumerate(runs)}
    included={};references=0
    for ref in packet['references']:
        if ref['kind']!='calculation_row':continue
        run=by_id.get(ref.get('run_id'));data=ref.get('data',{})
        name=data.get('table');row_index=ref.get('table_row')
        if run is None or ref.get('result_hash')!=run['result_hash']:
            raise AuditError('계산 발췌의 실행·결과 버전이 명세와 다릅니다.')
        table=run['result']['tables'].get(name)
        if table is None or type(row_index) is not int or not 1<=row_index<=len(table):
            raise AuditError('계산 발췌 행 식별자가 없습니다. 현재 근거로 다시 생성하세요.')
        if ref.get('row_hash')!=canonical_hash(table[row_index-1]):
            raise AuditError('계산 발췌 행 해시가 현재 결과와 다릅니다.')
        included.setdefault((run['id'],name),set()).add(row_index);references+=1
    tables=[];total=selected=0
    for run in runs:
        names=default_plan(run,packet['limits']['max_tables']) if selected_tables is None else selected_tables.get(run['id'],[])
        if any(n not in run['result']['tables'] for n in names):raise AuditError('계산표 선택 계획 오류')
        for name,rows in run['result']['tables'].items():
            count=len(rows);chosen=included.get((run['id'],name),set());omitted=count-len(chosen)
            reasons={}
            if name.startswith('입력_'):
                if omitted:reasons['input_source_only']=omitted
            elif name not in names:
                if omitted:reasons['table_limit']=omitted
            else:
                eligible=min(count,packet['limits']['rows_per_table'])
                beyond=sum(i>eligible for i in chosen)
                row_limited=count-eligible-beyond
                budget_limited=eligible-sum(i<=eligible for i in chosen)
                if row_limited:reasons['row_limit']=row_limited
                if budget_limited:reasons['reference_or_character_budget']=budget_limited
            if sum(reasons.values())!=omitted:raise AuditError('계산 발췌 포함·생략 집계 오류')
            key=(run['id'],run['result_hash'],name)
            if key not in table_hashes:table_hashes[key]=canonical_hash(rows)
            tables.append({'run':indices[run['id']],'table':name,'available':count,
                'included':len(chosen),'omitted':omitted,'hash':table_hashes[key],'reasons':reasons})
            total+=count;selected+=len(chosen)
    return {'schema':'calculation-inventory-1',
        'runs':[{'id':r['id'],'module':r['module'],'result_hash':r['result_hash']} for r in runs],
        'tables':tables,'table_count':len(tables),'available':total,'included':selected,
        'omitted':total-selected,'duplicate_row_references':references-selected,
        'scope':'계산 결과표의 고유 발췌행 집계. 전체 행 내용·모집단 거래건수·감사 수행 완료율이 아님.'}
