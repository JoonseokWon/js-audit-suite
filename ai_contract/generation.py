"""Local decoding constraints, distinct from accepted facts and original prose.

The backend generates these prefixes and citation arrays. We never add them to
a received response. Citation membership does not verify narrative semantics.
"""
from copy import deepcopy
import json
from common import AuditError
from .catalog import build_catalog
from .versions import CONTRACT_VERSION,FIELDS
from .linked_records import RISK_KINDS

MAX_FIELD_CHARS=6000
_KINDS={
    'purpose':('engagement','procedure_definition'),
    'risk':('procedure_definition','exception','human_workflow_risk')+RISK_KINDS,
    'scope':('run_summary','source_copy','raw_xlsx_row','raw_json'),
    'performed':('exception','run_summary','ledger_reconciliation','calculation_row',
                 'raw_xlsx_row','raw_json','misstatement_record')+RISK_KINDS,
    'conclusion':('exception','run_summary','ledger_reconciliation','calculation_row',
                  'misstatement_record')+RISK_KINDS,
}


def prefix_pattern(prefix):
    """Escape JSON lexical contents before the llama.cpp pattern grammar."""
    if len(prefix)+20>MAX_FIELD_CHARS:
        raise AuditError('선택된 예외 목록이 너무 깁니다. AI 근거 범위를 줄이세요.')
    lexical=json.dumps(prefix,ensure_ascii=False)[1:-1]
    escaped=''.join('\\'+char if char in r'.^$*+?{}[]\|()' else char for char in lexical)
    maximum_tail=MAX_FIELD_CHARS-len(prefix)-1
    return '^'+escaped+r'[^"\\\x00-\x20][^"\\\x00-\x1F]{19,'+str(maximum_tail)+'}$'


def generation_plan(packet):
    """Select field sources by kind, without claiming model source selection."""
    refs=packet['references'];fallback=[refs[0]['id']]
    exceptions=[r for r in refs if r['kind']=='exception']
    citations={field:[r['id'] for r in refs if r['kind'] in _KINDS[field]] or fallback[:]
               for field in FIELDS}
    prefixes={}
    if exceptions:
        prefixes['performed']='선택 예외(원문 고정): '+ '; '.join(
            r['data']['code']+' ['+r['id']+']' for r in exceptions)+' | AI 서술: '
        prefixes['conclusion']='필수 경고(선택 예외): 사람이 추가조사·확인해야 합니다. AI 제안: '
    return {'version':'local-generation-1','prefixes':prefixes,'citations':citations,
        'origin':'Program-selected source lists and safety prefixes; not model-independent verification.',
        'scope':'Source membership only. Free narrative remains unverified and is never automatically applied.'}


def local_schema(packet,public_schema):
    schema=deepcopy(public_schema)
    structured=packet.get('contract',{}).get('version')==CONTRACT_VERSION
    target='proposals' if structured else 'fields'
    if structured:
        schema['properties']['claims']={'type':'array','enum':[build_catalog(packet)['program_copy_claims']]}
    plan=generation_plan(packet)
    for field,prefix in plan['prefixes'].items():
        schema['properties'][target]['properties'][field]={
            'type':'string','pattern':prefix_pattern(prefix)}
    for field,ids in plan['citations'].items():
        schema['properties']['citations']['properties'][field]={'type':'array','enum':[ids]}
    return schema


def instructions():
    return ('\n로컬 생성 제약: local_generation_plan의 각 항목 고정 인용 배열을 그대로 생성합니다. '
        'scope의 실행요약 수치를 쓰면 그 실행요약이 인용 배열에 포함되어야 합니다. '
        'performed와 conclusion의 고정 접두부는 schema대로 생성하고 뒤 AI 서술·AI 제안에는 '
        '20자 이상의 한 문단을 작성합니다. 따옴표·역슬래시·줄바꿈은 쓰지 않습니다. '
        '접두부·인용 목록은 프로그램 제공 원문·안전 경고이며 AI가 독립 검증한 사실이 아닙니다. '
        '인용에 포함되어도 다른 계정·거래·범위의 숫자를 서로 비교하거나 새로운 결론으로 만들지 않습니다.')
