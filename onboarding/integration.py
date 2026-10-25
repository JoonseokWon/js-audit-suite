"""Versioned workbench inputs and current-ledger pins in the existing workspace."""
import json
from pathlib import Path
from common import AuditError, cancelled, plain, sha,digest
from onboarding import MODULES
from onboarding.contracts import check_payload


def engine(module):
    if module==MODULES[0]:
        from onboarding import erp
        return erp
    if module==MODULES[-1]:
        from onboarding import cashflow
        return cashflow
    from onboarding import substantive
    return substantive


def fields(module):
    provider = engine(module)
    value = provider.APPROVAL_FIELDS
    return tuple(value[module] if isinstance(value, dict) else value)


def sample(module, context):
    provider = engine(module)
    return provider.sample(context) if module in (MODULES[0], MODULES[-1]) else provider.sample(module, context)


def read_input(module, path, context):
    path = Path(path)
    if path.suffix.lower() == '.xlsx':
        from onboarding.workbooks import load_input
        return load_input(module, path, context)
    if path.suffix.lower() != '.json' or path.stat().st_size > 20*1024**2:
        raise AuditError('실무절차 입력은 20MB 이하 Excel 양식 또는 JSON 확정값입니다.')
    def invalid(value):raise AuditError('유효하지 않은 입력 숫자: '+value)
    try:return json.loads(path.read_text(encoding='utf-8-sig'), parse_constant=invalid)
    except (ValueError,UnicodeError) as exc:raise AuditError('입력자료 구조를 확인하세요.') from exc


def run(module, path, context, ledger_result, event=None):
    before = sha(path)
    payload = check_payload(read_input(module, path, context), context)
    if payload.get('area', module) != module:
        raise AuditError('선택한 검사와 입력자료의 절차가 다릅니다.')
    originals=payload.get('_origin_sources',[])
    confirmation=payload.get('approval',{})
    has_confirmation=isinstance(confirmation,dict) and any(confirmation.get(k) for k in ('actor','reason','input_hash'))
    if (originals or has_confirmation) and confirmation.get('envelope_hash')!=digest({k:v for k,v in payload.items() if k!='approval'}):
        raise AuditError('자료 확인 후 원본 연결 또는 입력이 바뀌었습니다. 다시 확인하세요.')
    cancelled(event)
    provider = engine(module)
    out = (provider.analyze(payload, context, ledger_result, event) if module in (MODULES[0], MODULES[-1])
           else provider.analyze(module, payload, context, ledger_result, event))
    if out['module'] != module or out['context'] != context:
        raise AuditError('실무절차 결과 범위 불일치')
    cancelled(event)
    if sha(path) != before:raise AuditError('검사 중 입력자료가 바뀌었습니다.')
    out['source'] = {'name':Path(path).name,'sha256':before,'bytes':Path(path).stat().st_size}
    out['detail']['onboarding'] = True
    out['detail']['original_source_refs']=originals
    return plain(out)


def validate_sources(ws,out):
    ids=[]
    for source in out.get('detail',{}).get('original_source_refs',[]):
        if (not isinstance(source,dict) or source.get('id') not in ws.sources
                or ws.sources[source['id']]['sha256']!=source.get('sha256')):
            raise AuditError('입력에 연결된 원본 자료의 ID·해시가 현재 업무와 다릅니다.')
        ids.append(source['id'])
    if len(ids)!=len(set(ids)):raise AuditError('원본 연결 ID가 중복입니다.')
    out['detail']['origin_source_ids']=ids


def workspace_checks(latest, ledger):
    rows = []
    for module in MODULES:
        run = latest.get(module)
        if not run:continue
        detail = run['result'].get('detail', {})
        current = (ledger and detail.get('ledger_run_id') == ledger['id']
                   and detail.get('ledger_result_hash') == ledger['result_hash'])
        linked = detail.get('현재원장연결') is True
        valid = bool(current and linked and not ledger['result']['blocking'] and not run['result']['blocking'])
        rows.append({'모듈':module,'지표':'현재 원장·계산 근거 연결',
            '상태':'일치' if valid else '미확인','기대':None,'실제':None,'차이':None,
            '사유':'현재 원장과 입력자료의 기계적 연결. 사람의 판단·감사완료와 별도입니다.' if valid
                   else '원장 변경·입력 차단·연결 미완료입니다. 자료를 보완하고 다시 검사하세요.'})
    return rows
