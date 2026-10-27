"""Append boundary recomputes program facts and preserves exact model proposals."""
from copy import deepcopy
from common import AuditError, digest, text
from .versions import CONTRACT_VERSION, PROMPT_VERSION
from .validation import validate_response


def validate_event_response(packet,response):
    from ai_provider import _loads, _check_sensitive, validate_draft_response
    if not isinstance(response,dict) or response.get('contract_version')!=CONTRACT_VERSION:
        raise AuditError('구계약 AI 초안은 조회만 가능합니다. 새 구조화 근거로 다시 생성하세요.')
    context={'company_code':packet['engagement']['company_code'],
        'procedure_id':packet['procedure']['id'],'basis':packet['basis']}
    for key,value in dict(context,packet_hash=digest(packet),prompt_version=PROMPT_VERSION).items():
        if response.get(key)!=value:raise AuditError('AI 응답의 근거·회사·절차 버전 불일치: '+key)
    raw=response.get('raw_response')
    if not isinstance(raw,str) or not raw.strip() or len(raw)>200000:
        raise AuditError('실제 모델의 수정되지 않은 JSON 원문이 필요합니다.')
    parsed=_loads(raw);_check_sensitive(parsed)
    result=validate_response(packet,parsed)
    for key in ('fields','citations'):
        expected=parsed['proposals'] if key=='fields' else parsed['citations']
        if response.get(key)!=expected:raise AuditError('모델 원문과 격리 제안·인용이 다릅니다.')
    for key in ('verified_fields','verified_citations','typed_claims','unverified_proposals'):
        if key in response and response[key]!=result[key]:raise AuditError('프로그램 고정 사실과 전달된 AI 결과가 다릅니다.')
    validate_draft_response(packet,result['fields'],parsed['citations'])
    if response.get('provider') not in ('ollama','openai'):raise AuditError('실제 지원 AI 제공자만 저장할 수 있습니다.')
    model=text(response.get('model'),'AI 모델명');_check_sensitive(model)
    return {**result,'citations':deepcopy(parsed['citations']),'raw_response':raw,
        'provider':response['provider'],'model':model,'prompt_version':PROMPT_VERSION,
        'packet_hash':digest(packet),**context}
