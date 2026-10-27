"""Explicit excerpts and hashes for planning metadata, never final coverage claims."""
from copy import deepcopy
from common import digest


def profile_excerpt(profile,pid):
    scope=profile.get('scope',[]);selected=[r for r in scope if r.get('procedure_id')==pid]
    result={key:deepcopy(value) for key,value in profile.items() if key!='scope'}
    result['scope']=deepcopy(selected)
    result['scope_excerpt']={'available':len(scope),'included':len(selected),
        'omitted':len(scope)-len(selected),'full_manifest_hash':digest(scope),
        'full_record_hash':digest(profile),'policy':'선택 절차의 적용범위와 중요성·계획만 발췌. 다른 절차는 미전송.'}
    return result


def compact_status(rows,limit=4):
    columns=['code','message']
    shown=rows[:limit];counts={}
    for row in rows:
        key=(row.get('code'),row.get('status'),row.get('ok'))
        counts[key]=counts.get(key,0)+1
    return {'status_columns':columns,
        'status_rows':[[deepcopy(row.get(key)) for key in columns] for row in shown],
        'status_available':len(rows),'status_included':len(shown),'status_omitted':len(rows)-len(shown),
        'status_manifest_hash':digest(rows),'omitted_status_hash':digest(rows[limit:]),
        'status_code_columns':['code','status','ok','count'],
        'all_status_codes':[[*key,value] for key,value in counts.items()],
        'status_scope':'상태코드별 개수 전체와 처음 4개 코드·메시지 발췌. 개별 위험·대응 위치는 원기록 해시 참조.'}


def compact_attempts(records):
    """Attempt logs may overlap: never add them as final included/omitted rows."""
    result=[]
    for kind in sorted({row['kind'] for row in records}):
        items=[r for r in records if r['kind']==kind]
        enumerated=[r for r in items if 'available' in r]
        extra=[r for r in items if 'available' not in r]
        result.append({'kind':kind,'attempt_record_count':len(items),
            'enumerated_records':len(enumerated),
            'initial_available_sum':sum(r.get('available',0) for r in enumerated),
            'initial_included_sum':sum(r.get('included',0) for r in enumerated),
            'initial_omitted_sum':sum(r.get('omitted',0) for r in enumerated),
            'additional_omission_records':len(extra),
            'additional_omitted_sum':sum(r.get('omitted',0) for r in extra),
            'full_attempt_manifest_hash':digest(items),
            'scope':'발췌 시도 집계는 중복 가능. 최종 포함/생략은 references·최종 계산표 명세 기준.'})
    return result
