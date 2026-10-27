"""Opt-in v2.5 single real call, separate from mock and rejection regressions."""
from pathlib import Path
import json
import sys
import time
from common import VERSION,atomic,digest


def self_test(report_path,runtime_root,cpu_diagnostic=False,integrated=False):
    from local_ai_runtime import LocalAIRuntime,MODEL,MODEL_DIGEST
    from ai_provider import generate_draft
    from ai_contract import validate_response,CONTRACT_VERSION
    from ai_contract.generation import generation_plan
    from .case_v25 import create_case
    from .flow_v25 import complete_flow
    from .capture import ActualCapture
    path=Path(report_path);out=path.parent
    if path.exists() or any((out/name).exists() for name in ('request-1.json','http-response-1.json','evidence-packet.json')):
        raise ValueError('Preserve all attempts; use a new private report directory.')
    out.mkdir(parents=True,exist_ok=True);checks=[];capture=ActualCapture(out)
    started=time.monotonic();manager=LocalAIRuntime(runtime_root);packet=None;response=None
    def check(ok,name):
        if not ok:raise AssertionError(name)
        checks.append(name)
    base={'version':VERSION,'frozen':bool(getattr(sys,'frozen',False)),
        'actual_openai_calls':0,'actual_human_approvals':0,'synthetic_approval_events':0,
        'model':MODEL,'model_digest':MODEL_DIGEST,
        'case_mode':'integrated_risk_misstatement' if integrated else 'sales_only_initial',
        'human_approval_scope':'synthetic state transition only; no real approval',
        'execution_mode':'explicit_cpu_diagnostic' if cpu_diagnostic else 'ollama_default_automatic_hardware',
        'independent_expected':{'normal_revenue':100000,'invoice_supply':90007,'invoice_difference':7}}
    try:
        if integrated:
            from v25_demo import actual_case
            ws,manifest=actual_case(out,check)
        else:ws,manifest=create_case(out,check)
        if integrated:
            from .gui_policy_v25 import build_request
            packet,config=build_request(ws,'A04',manager.base_url)
        else:
            packet=ws.ai_packet('A04',limits={'max_chars':12000,'max_references':40,
                'rows_per_table':3,'max_tables':8,'cell_chars':300})
            config={'provider':'ollama','model':MODEL,'endpoint':manager.base_url,
                    'num_ctx':16384,'timeout_seconds':300}
        if cpu_diagnostic:config['num_gpu']=0
        if integrated:
            from .gui_policy_v25 import describe_request
            base['ui_request_policy']=describe_request(packet,config,manager.base_url,cpu_diagnostic)
            check(base['ui_request_policy']['matches_requested_policy'],
                  'actual_request_matches_shared_GUI_policy_or_explicit_CPU_diagnostic')
            if not cpu_diagnostic:
                check(base['ui_request_policy']['matches_gui_default'],
                      'actual_default_request_equals_GUI_default_packet_and_model_options')
            check(config.get('provider')=='ollama' and config.get('model')==MODEL,
                  'shared_GUI_default_uses_the_pinned_local_model')
        check(packet['contract']['version']==CONTRACT_VERSION,'typed_contract_is_explicit')
        check('calculation_inventory' in packet,'final_calculation_inclusion_inventory_is_present')
        kinds={ref['kind'] for ref in packet['references']}
        check('calculation_row' in kinds and bool({'raw_xlsx_row','raw_json'} & kinds),
              'final_packet_retains_both_calculation_and_original_excerpt_anchors')
        expected_human='user_recorded_unverified' if integrated else 'not_recorded'
        check(packet['contract']['human_performance']['state']==expected_human,
              'human_input_remains_recorded_but_unverified' if integrated else 'human_performance_stays_not_recorded')
        atomic(out/'evidence-packet.json',json.dumps(packet,ensure_ascii=False,indent=2).encode())
        state=manager.ensure_server()
        check(state['ready'] and state['runtime_verified'] and state['model_digest']==MODEL_DIGEST,
              'pinned_local_runtime_and_model_are_ready')
        with capture:response=generate_draft(packet,config)
        check(len(capture.requests)==1,'exactly_one_real_chat_call_without_retry')
        if integrated:
            from .gui_policy_v25 import transport_matches_request
            matches=transport_matches_request(config,capture.requests[0]['request_options'])
            base['ui_request_policy']['captured_options_match']=matches
            check(matches,'captured_real_transport_preserves_GUI_context_and_hardware_defaults')
        parsed=json.loads(response['raw_response']);derived=validate_response(packet,parsed)
        plan=generation_plan(packet)
        check(all(parsed['proposals'][key].startswith(value) for key,value in plan['prefixes'].items()),
              'raw_response_contains_program_provided_prefixes_without_repair')
        check(parsed['citations']==plan['citations'],'raw_response_has_exact_field_source_lists')
        check(response['fields']==parsed['proposals'],'original_model_proposal_is_not_rewritten')
        check(derived['typed_claims']==response['typed_claims'],'typed_kind_status_path_value_unit_and_hash_match')
        check(response['acceptance_state']=='quarantined_proposal','free_model_prose_remains_quarantined')
        atomic(out/'response-derived-and-original.json',json.dumps(response,ensure_ascii=False,indent=2).encode())
        if integrated:
            from v25_demo import complete_actual
            flow=complete_actual(ws,packet,response,out,check)
        else:flow=complete_flow(ws,packet,response,out,check)
        report={**base,**flow,'ok':True,'status':'passed','contract_version':CONTRACT_VERSION,
            'actual_local_inference':True,'actual_model_calls':len(capture.requests),
            'current_actual_model_calls':len(capture.requests),'current_actual_openai_calls':0,
            'model':MODEL,'model_digest':MODEL_DIGEST,'packet_hash':digest(packet),
            'response_hash':digest(response['raw_response']),'transport':capture.requests,
            'gates':{'actual_local_model':True,'human_approval_preserved':True,'evidence_grounding':True,
                'edited_content_exported':True,'stale_approval_invalidated':True},
            'scope':'Exact typed copies, source membership, isolation and synthetic state transitions only. Free prose semantics and actual human performance are not verified.'}
    except Exception as exc:
        report={**base,'ok':False,'status':'failed','error':str(exc),
            'actual_local_inference':bool(capture.requests),'actual_model_calls':len(capture.requests),
            'current_actual_model_calls':len(capture.requests),'current_actual_openai_calls':0,
            'response_received':any('response_hash' in c for c in capture.requests),'transport':capture.requests,
            'scope':'One attempt preserved without response repair, retry or best-of selection. No failed stage is reported as completed.'}
    finally:manager.stop()
    if packet is not None:report['packet_hash']=digest(packet)
    report['checks']=checks;report['seconds']=round(time.monotonic()-started,2)
    atomic(path,json.dumps(report,ensure_ascii=False,indent=2).encode())
    return 0 if report['ok'] else 1
