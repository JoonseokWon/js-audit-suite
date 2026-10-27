"""Account/procedure-scoped human records with explicit bounded packet coverage."""
from copy import deepcopy
from common import AuditError,digest
from .packet_scope import compact_status

RISK_KINDS=('human_assertion_risk_assessment','human_risk_response',
            'human_actual_performance','human_workpaper_connection')
HUMAN_KINDS=RISK_KINDS+('misstatement_record',)


def _guard(ws,pid,item,allowed):
    if not isinstance(item,dict) or item.get('kind') not in allowed or not isinstance(item.get('data'),dict):
        raise AuditError('AI 연결 근거의 종류·자료 형식이 유효하지 않습니다.')
    data=item['data'];expected={key:ws.context[key] for key in ('회사코드','시작일','기준일')}
    if item.get('procedure_id',pid)!=pid or data.get('procedure_id',pid)!=pid or data.get('workpaper_id',pid)!=pid:
        raise AuditError('다른 절차의 사람 기록을 AI 근거에 포함할 수 없습니다.')
    if 'procedure_ids' in data and pid not in data['procedure_ids']:
        raise AuditError('선택 절차에 연결하지 않은 사람 기록을 AI에 전송할 수 없습니다.')
    context=data.get('pin',{}).get('context')
    if context is not None and context!=expected:
        raise AuditError('다른 회사·기간의 위험대응 기록을 AI에 전송할 수 없습니다.')
    for key,expected_key in (('company_code','회사코드'),('start_date','시작일'),('cutoff_date','기준일')):
        if key in data and data[key]!=expected[expected_key]:
            raise AuditError('다른 회사·기간의 왜곡표시 기록을 AI에 전송할 수 없습니다.')


def add_references(ws,pid,packet,ref,before_anchors=None):
    import audit_links,misstatements
    sections={};entries=[];anchors=[];remaining=[];seen=set();accepted={};omitted={}
    for name,read,allowed in (('audit_links',audit_links.packet,RISK_KINDS),
                              ('misstatements',misstatements.packet,('misstatement_record',))):
        info=read(ws,pid);records=info.get('references',[])
        if not records:continue
        entries.append((name,info,records));accepted[name]=[];omitted[name]=[]
        for item in records:
            _guard(ws,pid,item,allowed)
            target=remaining if item['kind'] in seen else anchors
            target.append((name,item));seen.add(item['kind'])
    if entries and before_anchors:before_anchors()
    for anchor,items in ((True,anchors),(False,remaining)):
        for name,item in items:
            links={key:deepcopy(value) for key,value in item.items() if key not in ('kind','data')}
            rid=ref(item['kind'],item['data'],**links)
            if anchor and not rid:
                raise AuditError('선택된 사람 기록 종류별 최소 근거가 AI 한도를 초과했습니다. 관련 기록 범위를 줄이세요.')
            (accepted[name] if rid else omitted[name]).append((rid,item))
    for name,info,records in entries:
        included=accepted[name];missing=omitted[name];kind_rows=[]
        for kind in dict.fromkeys(item['kind'] for item in records):
            all_items=[item for item in records if item['kind']==kind]
            count=sum(item['kind']==kind for _,item in included)
            kind_rows.append([kind,len(all_items),count,len(all_items)-count])
        sections[name]={'available_references':len(records),'included_references':len(included),
            'omitted_references':len(missing),'included_reference_ids':[rid for rid,_ in included],
            'full_reference_manifest_hash':digest(records),'omitted_reference_hash':digest([item for _,item in missing]),
            'kind_columns':['kind','available','included','omitted'],'kind_rows':kind_rows,
            'scope':info.get('scope','사람 입력·회계적 관련성 미검증. 발췌 범위만 제공.')}
        if info.get('inventory'):sections[name]['source_inventory']=deepcopy(info['inventory'])
        rows=info.get('rows',[])
        if rows:sections[name].update(compact_status(rows))
        performances=[item for item in records if item['kind']=='human_actual_performance']
        if performances:
            recorded=sum(bool(str(item['data'].get('performed','')).strip() and
                              str(item['data'].get('performed_date','')).strip()) for item in performances)
            sections[name]['human_performance_inventory']={'available_records':len(performances),
                'recorded_inputs':recorded,'unrecorded_or_partial_inputs':len(performances)-recorded,
                'full_manifest_hash':digest(performances),'actual_performance_verified':False}
    if sections:
        packet['linked_human_records']=sections
        packet['limitations'].append('위험대응·왜곡표시는 사람이 선택·기록한 내용의 발췌입니다. 현재 연결·버전 점검이 회계적 판단이나 실제 수행을 인증하지 않습니다.')
    return sections
