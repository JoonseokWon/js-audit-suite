"""Program-owned identity and the scope of saved human input, never AI facts."""
from .versions import CONTRACT_VERSION
from common import AuditError


def identity(packet):
    engagement=packet['engagement'];procedure=packet['procedure']
    return {'company_code':engagement['company_code'],'company_name':engagement['company_name'],
        'start_date':engagement['start_date'],'end_date':engagement['end_date'],
        'procedure_id':procedure['id'],'procedure_title':procedure.get('title',''),
        'module':procedure.get('module'),'synthetic':engagement['synthetic']}


def response_context(packet):
    return {'company_code':packet['engagement']['company_code'],
        'procedure_id':packet['procedure']['id'],'basis':packet['basis']}


def attach_contract(packet, procedure=None, workflow_procedure=None):
    p=procedure or {}
    records=[]
    for source,item in (('saved_procedure',p),('workflow_procedure',workflow_procedure or {})):
        if str(item.get('performed','')).strip() and str(item.get('performed_date','')).strip():
            records.append({'source':source,'performed_date':item['performed_date'],
                'actor':item.get('performer',item.get('preparer','')),
                'AI_origin':bool(item.get('ai_draft_id'))})
    for ref in packet.get('references',[]):
        item=ref.get('data',{})
        if (ref.get('kind')=='human_actual_performance' and isinstance(item,dict)
                and str(item.get('performed','')).strip() and str(item.get('performed_date','')).strip()):
            records.append({'source':'audit_link_performance','reference_id':ref['id'],
                'performed_date':item['performed_date'],'actor':item.get('performer',''),
                'record_id':item.get('id',''),'revision':item.get('revision',''),'AI_origin':False})
    inventory=packet.get('linked_human_records',{}).get('audit_links',{}).get('human_performance_inventory',{})
    if inventory.get('recorded_inputs',0) and not any(r['source']=='audit_link_performance' for r in records):
        records.append({'source':'audit_link_performance_inventory',
            'recorded_inputs':inventory['recorded_inputs'],'full_manifest_hash':inventory['full_manifest_hash'],
            'scope':'수행기록 존재의 집계만 제공. 해당 원문 내용은 발췌 생략 상태이며 실제 수행은 미검증.'})
    recorded=bool(records)
    packet['contract']={'version':CONTRACT_VERSION,'identity':identity(packet),
        'human_performance':{'state':'user_recorded_unverified' if recorded else 'not_recorded',
            'records':records,
            'physical_performance_verified':False,
            'scope':'Saved input is not authenticated performance, evidence receipt, or an audit conclusion.'},
        'proposal_policy':'quarantined_unverified; never automatically merged into workpaper facts or performance'}
    return packet


def validate_header(packet):
    contract=packet.get('contract',{})
    if not isinstance(contract,dict) or contract.get('version')!=CONTRACT_VERSION or contract.get('identity')!=identity(packet):
        raise AuditError('구조화 AI 계약 또는 프로그램 대상 식별정보가 다릅니다.')
    human=contract.get('human_performance',{})
    if (human.get('state') not in ('not_recorded','user_recorded_unverified')
            or human.get('physical_performance_verified') is not False):
        raise AuditError('사람의 실제 수행을 AI가 확인한 상태로 만들 수 없습니다.')
    return True
