"""Synthetic v2 wire fixtures. No network, inference, or production fallback."""
from copy import deepcopy
from common import digest,dumps
from ai_contract import build_catalog,validate_response,PROMPT_VERSION
from ai_contract.headers import response_context


def response_from_fields(packet,fields,citations,model='unit-fixture-no-model-call'):
    parsed={'context':response_context(packet),'claims':build_catalog(packet)['claims'],
        'proposals':deepcopy(fields),'citations':deepcopy(citations)}
    derived=validate_response(packet,parsed)
    return {**derived,'citations':deepcopy(citations),'provider':'ollama','model':model,
        'prompt_version':PROMPT_VERSION,'packet_hash':digest(packet),**parsed['context'],
        'raw_response':dumps(parsed)}


def sync_response(response):
    import json
    parsed=json.loads(response['raw_response'])
    parsed.update(proposals=deepcopy(response['fields']),citations=deepcopy(response['citations']),
        context={key:response[key] for key in ('company_code','procedure_id','basis')})
    response['unverified_proposals']=deepcopy(response['fields'])
    response['proposal_citations']=deepcopy(response['citations'])
    response['raw_response']=dumps(parsed)
    return response
