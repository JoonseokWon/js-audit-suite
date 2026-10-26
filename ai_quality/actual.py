"""Opt-in real local inference and synthetic human-in-the-loop state test.

Unit tests and CI must never call this function. Request/response evidence is
written only beneath the explicit private report directory.
"""
from pathlib import Path
import json
import re
import sys
import threading
import time
from common import VERSION, atomic, digest


def self_test(report_path, runtime_root):
    from local_ai_runtime import LocalAIRuntime, MODEL, MODEL_DIGEST
    from demo_case import create_demo
    from ai_provider import generate_draft, AIProviderError, validate_draft_response
    from .capture import ActualCapture
    from .actual_flow import complete_flow
    from .numbers import numeric_support_report
    path=Path(report_path)
    if path.exists():raise ValueError('Preserve prior report; select a new report directory.')
    out=path.parent;out.mkdir(parents=True,exist_ok=True)
    checks=[];start=time.monotonic();manager=LocalAIRuntime(runtime_root)
    capture=ActualCapture(out);response=None;packet=None;flow=None;state={}
    def check(ok, name):
        if not ok:raise AssertionError(name)
        if name in checks:raise AssertionError('duplicate_check_name')
        checks.append(name)
    try:
        ws,manifest=create_demo(out/'JS전자_실제모델_검증업무')
        check(ws.engagement['회사코드']=='JS_ELEC' and ws.engagement['더미업무'],
              'actual_case_is_isolated_synthetic_JS_electronics')
        check(not ws.ai_drafts and not ws.ai_approvals and not any(p.get('reviewed_at') for p in ws.procedures.values()),
              'case_starts_without_AI_or_human_approval')
        check(all(not p.get('performed_date') and not p.get('conclusion') for p in ws.procedures.values()),
              'case_starts_without_actual_human_performance_or_conclusion')
        check(ws.latest()['원장·리드']['result']['blocking']>0 and ws.latest()['매출']['result']['review']>0,
              'balanced_journal_and_invoice_omission_are_detected_before_AI')
        packet=ws.ai_packet(manifest['target_pid'],limits={
            'max_chars':12000,'max_references':40,'rows_per_table':3,'max_tables':8,'cell_chars':300})
        kinds={r['kind'] for r in packet['references']}
        check({'exception','run_summary','raw_xlsx_row','ledger_reconciliation','calculation_row'}<=kinds,
              'actual_packet_contains_raw_ledger_and_exception_references')
        atomic(out/'evidence-packet.json',json.dumps(packet,ensure_ascii=False,indent=2).encode())
        state=manager.ensure_server()
        check(state['ready'] and state['runtime_verified'] and state['model_digest']==MODEL_DIGEST,
              'pinned_runtime_server_and_model_are_ready')
        with capture:
            response=generate_draft(packet,{'provider':'ollama','model':MODEL,
                'endpoint':manager.base_url,'num_gpu':0,'num_ctx':16384,'timeout_seconds':300})
        check(len(capture.requests)>=1,'real_loopback_chat_request_completed')
        check(all(type(value) is int and value>0 for item in capture.requests
                  for value in item['inference_counts'].values()),
              'actual_HTTP_reports_positive_prompt_output_and_generation_counters')
        check(response['provider']=='ollama' and response['model']==MODEL,'actual_response_model_is_pinned_local_model')
        atomic(out/'accepted-response.json',json.dumps(response,ensure_ascii=False,indent=2).encode())
        check(bool(re.search('[가-힣]',''.join(response['fields'].values()))),'actual_response_contains_korean_workpaper_text')
        check(validate_draft_response(packet,response['fields'],response['citations']),
              'actual_fields_preserve_selected_exceptions_and_human_pending_scope')
        quality=numeric_support_report(packet,response['fields'],response['citations'])
        check(quality['passed'],'actual_numeric_tokens_exist_in_field_cited_evidence')
        cancelled=threading.Event();cancelled.set();calls_before=len(capture.requests)
        with capture:
            try:generate_draft(packet,{'provider':'ollama','model':MODEL},cancelled)
            except AIProviderError:pass
            else:raise AssertionError('cancelled_request_generated_draft')
        check(len(capture.requests)==calls_before,'pre_cancelled_request_never_reaches_transport')
        flow=complete_flow(ws,packet,response,out,check)
        report={'ok':True,'status':'passed','version':VERSION,
            'frozen':bool(getattr(sys,'frozen',False)),'checks':checks,
            'actual_local_inference':True,'current_actual_model_calls':len(capture.requests),
            'current_actual_openai_calls':0,'model':MODEL,'model_digest':MODEL_DIGEST,
            'packet_hash':digest(packet),'response_hash':digest(response),
            'human_approval_scope':'synthetic state transition only; no real approval',
            'actual_human_approvals':0,'synthetic_approval_events':flow['approval_events'],
            'workspace':str(ws.root),'actual_response_path':str(out/'accepted-response.json'),
            'export_path':flow['export_path'],'transport':capture.requests,
            'cancelled_before_connect':True,'numeric_support':quality,
            'runtime':{key:state[key] for key in ('runtime_verified','model','server','ready')},
            'gates':{'actual_local_model':True,'human_approval_preserved':True,
                'evidence_grounding':True,'edited_content_exported':True,
                'stale_approval_invalidated':True},'seconds':round(time.monotonic()-start,2)}
    except Exception as exc:
        report={'ok':False,'status':'failed','version':VERSION,'frozen':bool(getattr(sys,'frozen',False)),
            'error':str(exc),'checks':checks,'current_actual_model_calls':len(capture.requests),
            'current_actual_openai_calls':0,'actual_human_approvals':0,
            'seconds':round(time.monotonic()-start,2)}
    finally:manager.stop()
    atomic(path,json.dumps(report,ensure_ascii=False,indent=2).encode())
    return 0 if report['ok'] else 1
