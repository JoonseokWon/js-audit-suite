"""Read-only captured-response validation. It never calls a model or repairs text."""
from pathlib import Path
import hashlib
import json
from common import AuditError,VERSION,atomic


def replay(packet_path,response_path,report_path):
    from ai_provider import _extract,_loads,validate_draft_response
    from ai_contract import validate_response
    from ai_quality.numbers import numeric_support_report
    packet_path=Path(packet_path);response_path=Path(response_path);report_path=Path(report_path)
    if report_path.exists():raise ValueError('Preserve prior replay evidence; use a new report path.')
    artifacts=[packet_path,response_path]
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts}
    packet=_loads(packet_path.read_text(encoding='utf-8'));envelope=_loads(response_path.read_text(encoding='utf-8'))
    raw,model=_extract('ollama',envelope);parsed=_loads(raw)
    typed_ok=False;guard_ok=False;typed_error='';guard_error=''
    try:validate_response(packet,parsed);typed_ok=True
    except AuditError as exc:typed_error=str(exc)
    try:validate_draft_response(packet,parsed['proposals'],parsed['citations']);guard_ok=True
    except AuditError as exc:guard_error=str(exc)
    performed=parsed.get('proposals',{}).get('performed','');citations=parsed.get('citations',{})
    exceptions=[{'id':r['id'],'code':r['data']['code']} for r in packet['references'] if r['kind']=='exception']
    after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts}
    result={'version':VERSION,'kind':'captured_response_replay_not_new_inference','actual_model_calls':0,
        'typed_comparison_passed':typed_ok,'typed_error':typed_error,
        'narrative_safety_guard_passed':guard_ok,'narrative_guard_error':guard_error,
        'missing_exception_codes':[r['code'] for r in exceptions if r['code'] not in performed],
        'missing_performed_exception_citations':[r['id'] for r in exceptions if r['id'] not in citations.get('performed',[])],
        'numeric_source_membership':numeric_support_report(packet,parsed.get('proposals',{}),citations),
        'original_model':model,'original_done_reason':envelope.get('done_reason'),
        'source_sha256':before,'source_artifacts_unchanged':before==after,
        'scope':'Typed equality and conservative guard results are separate. Numeric citation failure is not an accounting amount error. No apply, approval, Excel export or retry is performed.'}
    atomic(report_path,json.dumps(result,ensure_ascii=False,indent=2).encode())
    return result
