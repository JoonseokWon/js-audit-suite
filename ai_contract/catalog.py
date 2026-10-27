"""Bounded typed facts point to exact fields, without interpreting model prose."""
from copy import deepcopy
from common import AuditError, digest, dumps

MAX_CLAIMS=24
_PRIORITY={'exception':0,'ledger_reconciliation':1,'run_summary':2,
    'calculation_row':3,'raw_xlsx_row':4,'raw_json':5,'source_copy':6}
from .linked_records import HUMAN_KINDS
_PRIORITY.update({kind:2 for kind in HUMAN_KINDS})
_NUMERIC_KEYS=('difference','차이','계산금액','순매출','net_revenue','billed_supply_amount',
               'invoice_supply','기대','실제','expected','actual','amount','금액')


def _status(ref):
    data=ref['data']
    if not isinstance(data,dict):return None
    paths=[['상태'],['status'],['severity'],['verification_state'],['current']]
    if ref['kind']=='calculation_row':paths=[['row','상태'],['row','status']]+paths
    for path in paths:
        value=data
        for key in path:
            if not isinstance(value,dict) or key not in value:break
            value=value[key]
        else:return {'path':path,'value':deepcopy(value)}
    return None


def _primary(ref):
    data=ref['data'];kind=ref['kind']
    if not isinstance(data,dict):return [],data
    choices={'exception':('code','reason_code'),'ledger_reconciliation':('차이','상태'),
        'run_summary':('blocking','metrics'),'calculation_row':('row','table'),
        'raw_xlsx_row':('sheet','row'),'source_copy':('name',),'engagement':('company_code',),
        'procedure_definition':('id',),'misstatement_record':('amount','assessment','id'),
        'human_assertion_risk_assessment':('inherent_rating','id'),
        'human_risk_response':('nature','id'),
        'human_actual_performance':('performed_date','id'),
        'human_workpaper_connection':('workpaper_id','id')}.get(kind,())
    for key in choices:
        if key not in data:continue
        value=data[key]
        if key=='row' and isinstance(value,dict):
            for field in _NUMERIC_KEYS+tuple(value):
                if field in value and not isinstance(value[field],(dict,list)):
                    return [key,field],value[field]
        if not isinstance(value,(dict,list)):return [key],value
    # A digest is a recorded identity, not a model assertion about its contents.
    return ['@content_hash'],digest(data)


def _unit(ref,path):
    data=ref['data'];row=data.get('row',{}) if isinstance(data,dict) else {}
    for container in (row,data):
        if isinstance(container,dict):
            for key in ('unit','단위','currency','통화'):
                if key in container:return deepcopy(container[key])
    return '미지정(원문 단위 추정·변환 없음)'


def build_catalog(packet):
    refs=packet.get('references',[]);candidates=[]
    for index,ref in enumerate(refs):
        path,value=_primary(ref)
        fact={'reference_id':ref['id'],'reference_kind':ref['kind'],'status':_status(ref),
            'value_path':path,'value':deepcopy(value),'unit':_unit(ref,path),
            'reference_hash':digest(ref)}
        candidates.append((_PRIORITY.get(ref['kind'],7),index,fact))
    candidates.sort(key=lambda item:item[:2])
    mandatory=[item for item in candidates if item[2]['reference_kind'] in ('exception','ledger_reconciliation')]
    anchors=[]
    for kinds in (('calculation_row',),('raw_xlsx_row','raw_json'))+tuple((kind,) for kind in HUMAN_KINDS):
        anchor=next((item for item in candidates if item[2]['reference_kind'] in kinds),None)
        if anchor is not None:anchors.append(anchor)
    core=mandatory+anchors
    if len(core)>MAX_CLAIMS:raise AuditError('필수 예외 목록이 너무 많습니다. 대사·원문·계산을 포함한 AI 범위를 줄이세요.')
    first={item[2]['reference_id'] for item in core}
    candidates=core+[item for item in candidates if item[2]['reference_id'] not in first]
    catalog=[]
    for number,(_,_,fact) in enumerate(candidates[:MAX_CLAIMS],1):
        catalog.append({'claim_id':f'CLM{number:03}',**fact})
    omitted=[item[2] for item in candidates[MAX_CLAIMS:]]
    copied=[c for c in catalog if c['reference_id'] in first]
    if not copied:copied=catalog[:1]
    return {'claims':catalog,'program_copy_claims':copied,'required_ids':[c['claim_id'] for c in catalog
            if c['reference_kind'] in ('exception','ledger_reconciliation')],
        'scope':{'available_claims':len(candidates),'included_claims':len(catalog),
            'omitted_claims':len(omitted),'omitted_claims_hash':digest(omitted),
            'program_copy_included':len(copied),'not_requested_from_local_model':len(catalog)-len(copied),
            'program_copy_hash':digest(copied),
            'selection_origin':'Program-selected copied records; not independent model verification.',
            'scope':'One bounded typed field per included reference; not the full table/row inclusion inventory.'}}
