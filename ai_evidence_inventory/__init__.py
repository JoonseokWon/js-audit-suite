"""Final packet coverage, including protected excerpts and completely omitted tables."""
from copy import deepcopy
from common import AuditError,dumps
from .coverage import inventory
from .hashing import canonical_hash
from .encoding import compact_manifest,table_rows


def finalize_packet(packet,runs,protected_ids=(),selected_tables=None):
    result=deepcopy(packet);protected=set(protected_ids);removed=[]
    compact=result['limits']['max_chars']<=16000 or bool(result.get('linked_human_records'))
    if compact:result.pop('supported_modules',None)
    # Earlier estimates can omit protected rows or whole tables. Replace them
    # with a single inventory calculated from the final surviving references.
    result['truncation']=[r for r in result.get('truncation',[])
        if r.get('kind') not in ('calculation_row','calculation_table','calculation_inventory','final_inventory_budget')]
    # Raw-source attempt counts predate both budget passes. Do not present them
    # as final inclusion counts after references have been removed.
    for record in result['truncation']:
        for key in ('included','omitted'):
            if key in record:record['initial_'+key]=record.pop(key)
        record['scope']='초기 발췌 시도 기록. 최종 포함은 references·계산표 명세를 확인.'
    table_hashes={};coverage=inventory(result,runs,selected_tables,table_hashes)
    ranks={'calculation_policy':0,'raw_json':1,'calculation_row':2,'raw_xlsx_row':3,'source_copy':4}
    for _ in range(len(result['references'])+1):
        result['calculation_inventory']=compact_manifest(coverage) if compact else coverage
        if removed:
            result['truncation']=[r for r in result['truncation'] if r.get('kind')!='final_inventory_budget']
            result['truncation'].append({'kind':'final_inventory_budget','omitted_references':len(removed),
                'manifest_hash':canonical_hash(removed),'reason':'계산표 명세를 포함한 최종 문자 한도'})
        if len(dumps(result))<=result['limits']['max_chars']:return result
        candidates=[]
        for pos,ref in enumerate(result['references']):
            if ref['id'] in protected or ref['kind'] not in ranks:continue
            if ref['kind'] in ('raw_json','raw_xlsx_row'):
                raw=[r for r in result['references'] if r['kind'] in ('raw_json','raw_xlsx_row')
                     and r.get('source_id')==ref.get('source_id')]
                if len(raw)<=1:continue
            if ref['kind']=='calculation_row':
                same=[r for r in result['references'] if r['kind']=='calculation_row' and r.get('run_id')==ref.get('run_id')]
                if len(same)<=1:continue
            candidates.append((ranks[ref['kind']],-pos,pos))
        if not candidates:break
        _,_,pos=min(candidates);ref=result['references'].pop(pos)
        removed.append({'id':ref['id'],'hash':canonical_hash(ref)})
        coverage=inventory(result,runs,selected_tables,table_hashes)
    raise AuditError('계산 근거와 전체 생략 명세가 문자 한도를 초과합니다. 근거 범위를 줄이거나 허용 한도를 확인하세요.')


__all__=['finalize_packet','inventory','canonical_hash','table_rows']
