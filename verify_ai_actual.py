"""Opt-in actual local model test; never run by unit tests or GitHub CI."""
from pathlib import Path
import json,time,sys,re,traceback
import runtime
RESOURCE=runtime.configure()
from common import atomic,AuditError,digest

def self_test(report_path,runtime_root):
    out=Path(report_path).parent;out.mkdir(parents=True,exist_ok=True);checks=[];start=time.monotonic()
    def check(ok,name):
        if not ok:raise AssertionError(name)
        checks.append(name)
    try:
        from local_ai_runtime import LocalAIRuntime,MODEL,MODEL_DIGEST
        from ai_provider import generate_draft
        from workspace import Workspace
        from openpyxl import load_workbook
        import exporter
        manager=LocalAIRuntime(runtime_root);state=manager.ensure_server()
        check(state['ready'],'pinned_runtime_and_model_ready')
        ws=Workspace(out/'합성_매출누락_업무',create={'회사코드':'SYNTH01','회사명':'SYNTHETIC ONLY','시작일':'2026-01-01','기준일':'2026-12-31','회계체계':'K-IFRS','감사기준':'합성 검사','작성자':'합성시험작성자','더미업무':True})
        ws.execute('원장·리드',RESOURCE/'samples/통합/통합_01_원장정상.xlsx')
        sales=out/'SYNTHETIC_ONLY_매출_청구누락.xlsx';book=load_workbook(RESOURCE/'samples/통합/통합업무_매출정상.xlsx');book['invoices'].delete_rows(2);book.save(sales);book.close()
        run=ws.execute('매출',sales);check(run['result']['blocking']+run['result']['review']>0,'deleted_invoice_detected_by_reconciliation')
        packet=ws.ai_packet('A04',limits={'max_chars':12000,'max_references':40,'rows_per_table':3,'max_tables':8,'cell_chars':300})
        kinds={r['kind'] for r in packet['references']};check({'raw_xlsx_row','run_summary','ledger_reconciliation','exception'}<=kinds,'packet_contains_raw_reconciliation_and_exception')
        atomic(out/'근거패킷.json',json.dumps(packet,ensure_ascii=False,indent=2).encode())
        import ai_provider
        from unittest.mock import patch
        original=ai_provider._post_json
        def capture(*args,**kwargs):
            value=original(*args,**kwargs);atomic(out/'로컬모델_HTTP응답.json',json.dumps(value,ensure_ascii=False,indent=2).encode());return value
        with patch.object(ai_provider,'_post_json',side_effect=capture):
            response=generate_draft(packet,{'provider':'ollama','model':MODEL,'endpoint':manager.base_url,'num_gpu':0,'num_ctx':16384,'timeout_seconds':300})
        atomic(out/'실제응답.json',json.dumps(response,ensure_ascii=False,indent=2).encode())
        check(response['model']==MODEL,'actual_pinned_model_response')
        text='\n'.join(response['fields'].values());check(bool(re.search('[가-힣]',text)),'actual_response_contains_korean')
        check(bool(re.search('누락|차이|차단|미확인|오류',response['fields']['performed']+response['fields']['conclusion'])),'draft_acknowledges_exception_or_unverified_scope')
        did=ws.record_ai_draft(packet,response,'합성시험요청자');check('A04' not in ws.procedures,'generation_does_not_apply')
        ws.apply_ai_draft(did,'합성시험작성자');check(not ws.ai_status('A04')['approved'],'actual_ai_draft_requires_approval')
        p=dict(ws.procedures['A04']);p['conclusion']+='\n합성 시험 수정: 청구누락 사례이므로 실제 증빙 조사·판단은 수행하지 않았음.';ws.save_procedure(p)
        ws.approve_ai_content('A04','합성시험승인입력','실제 감사 승인이 아닌 합성 상태전이 시험. 원문·누락·미수행과 수정 문구를 확인하는 절차를 모사함.')
        check(ws.ai_status('A04')['approved'],'synthetic_content_approval_state_recorded')
        catalog=json.loads((RESOURCE/'procedure_catalog.json').read_text(encoding='utf-8'));target=out/'실제모델_합성_미검토조서.xlsx';exporter.export(ws,target,catalog,False)
        check(target.is_file(),'actual_model_fields_exported_to_workpaper')
        p=dict(ws.procedures['A04']);p['conclusion']+='\n변경 감지 시험';ws.save_procedure(p);check(not ws.ai_status('A04')['approved'],'editing_invalidates_synthetic_approval')
        atomic(out/'실제응답.json',json.dumps(response,ensure_ascii=False,indent=2).encode())
        report={'status':'passed','version':'1.8.0','frozen':bool(getattr(sys,'frozen',False)),'actual_local_inference':True,'actual_openai_calls':0,'case':'SYNTHETIC ONLY / deleted invoice / sales ledger reconciliation','checks':checks,'model':MODEL,'model_digest':MODEL_DIGEST,'packet_hash':digest(packet),'packet_chars':len(json.dumps(packet,ensure_ascii=False)),'references':len(packet['references']),'fields':response['fields'],'citations':response['citations'],'seconds':round(time.monotonic()-start,2),'human_approval_scope':'synthetic state-transition test, not real audit approval','runtime':{k:state[k] for k in ('ready','runtime_verified','server','model')}}
        atomic(report_path,json.dumps(report,ensure_ascii=False,indent=2).encode());return 0
    except Exception as exc:
        atomic(report_path,json.dumps({'status':'failed','error':str(exc),'checks':checks,'traceback':traceback.format_exc(),'seconds':round(time.monotonic()-start,2)},ensure_ascii=False,indent=2).encode());return 1
