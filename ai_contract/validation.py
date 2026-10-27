"""Validate the typed channel exactly; free narrative stays quarantined."""
from copy import deepcopy
from common import AuditError, dumps
from .catalog import build_catalog
from .headers import identity, response_context,validate_header
from .render import render
from .versions import CONTRACT_VERSION, FIELDS


def validate_response(packet,parsed):
    validate_header(packet)
    if not isinstance(parsed,dict) or set(parsed)!={'context','claims','proposals','citations'}:
        raise AuditError('AI 응답 항목이 계약과 다릅니다. 구조화 항목과 격리 제안을 구분해야 합니다.')
    if parsed['context']!=response_context(packet):raise AuditError('다른 회사·절차·근거 버전의 AI 응답을 차단했습니다.')
    catalog=build_catalog(packet);allowed={c['claim_id']:c for c in catalog['claims']}
    claims=parsed['claims']
    if not isinstance(claims,list) or not 1<=len(claims)<=len(allowed):raise AuditError('구조화 AI 근거 항목 수 오류')
    seen=set()
    for item in claims:
        if (not isinstance(item,dict) or not isinstance(item.get('claim_id'),str)
                or item['claim_id'] not in allowed or item['claim_id'] in seen):
            raise AuditError('구조화 AI 항목이 없거나 중복되었습니다.')
        if dumps(item)!=dumps(allowed[item['claim_id']]):
            raise AuditError('AI가 근거 종류·상태·값·단위·참조를 바꿨습니다. 초안을 적용하지 않았습니다.')
        seen.add(item['claim_id'])
    if not set(catalog['required_ids'])<=seen:raise AuditError('필수 예외·대사 구조화 근거가 빠졌습니다.')
    proposals=parsed['proposals'];citations=parsed['citations']
    if not isinstance(proposals,dict) or set(proposals)!=set(FIELDS) or any(
            not isinstance(v,str) or not v.strip() or len(v)>6000 for v in proposals.values()):
        raise AuditError('격리 AI 제안의 다섯 항목 구조 오류')
    refs={r['id'] for r in packet['references']}
    if not isinstance(citations,dict) or set(citations)!=set(FIELDS):raise AuditError('격리 제안의 근거 인용 구조 오류')
    for field,ids in citations.items():
        if (not isinstance(ids,list) or not ids or any(not isinstance(i,str) for i in ids)
                or len(ids)!=len(set(ids)) or any(i not in refs for i in ids)):
            raise AuditError('격리 제안이 현재 존재하지 않거나 중복된 근거를 인용했습니다.')
    ordered=[c for c in catalog['claims'] if c['claim_id'] in seen]
    fields,verified_citations=render(packet,ordered)
    from export_support.text import require_xml_text
    for field,value in fields.items():require_xml_text(value,'프로그램 근거 기록 '+field)
    return {'contract_version':CONTRACT_VERSION,'acceptance_state':'quarantined_proposal',
        'fields':deepcopy(proposals),'unverified_proposals':deepcopy(proposals),
        'proposal_citations':deepcopy(citations),'typed_claims':deepcopy(ordered),
        'verified_fields':fields,'verified_citations':verified_citations,
        'claim_catalog_scope':catalog['scope'],
        'typed_claims_origin':'Program-provided records copied by the model; checked for exact equality, not independent verification.',
        'semantic_verification':'unverified narrative; typed equality is not evidence authenticity or human audit performance'}
