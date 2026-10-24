"""Application integration checks, shared unchanged between source and frozen builds."""
from pathlib import Path
import json,time,traceback,sys
from common import atomic,dumps,digest,AuditError

def self_test(report_path,legacy=True):
    report_path=Path(report_path);report_path.parent.mkdir(parents=True,exist_ok=True)
    checks=[];root=None;observations=[]
    def check(value,name):
        if not value:raise AssertionError(name)
        checks.append(name)
    try:
        if legacy:
            from verify import self_test as old_test
            check(old_test(report_path.parent/'legacy/report.json')==0,'legacy_213_cases_and_native_ui')
        import tkinter as tk
        from app import App,resource,CATALOG
        from workspace import Workspace
        from window_capture import capture_window
        import exporter
        root=tk.Tk();app=App(root)
        app.start_demo(report_path.parent/'통합업무',full=True)
        deadline=time.monotonic()+180
        while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
        check(not app.busy,'full_demo_finished')
        check(len(app.ws.latest())==12,'twelve_modules_present')
        check(all(r['result']['blocking']==0 for r in app.ws.latest().values()),'twelve_inputs_not_blocked')
        check(len(app.ws.cross_checks())==32 and all(r['상태']=='일치' for r in app.ws.cross_checks()),'thirty_two_current_ledger_links')
        app.nb.select(app.tabs['결과 상세'])
        for module,table,count in [('재무제표·주석','재무제표대사',94),('원천증빙','현재원장연결',141)]:
            app.result_module.set(module);app.choose_result_module();app.result_table.set(table);app.load_table();root.update()
            check(len(app.table_rows)==count,module+'_native_table_rows')
            capture_window(root,report_path.parent/(module+'_화면.png'))
            check(bool(app.result_tree.get_children()),module+'_native_table_visible')
        for pid in ('F01','R01'):
            app.load_procedure(pid);check(bool(app.proc_text['scope'].get('1.0','end').strip()),pid+'_draft_links')
            app.save_procedure();p=app.ws.procedures[pid]
            check(not p['performed'] and not p['conclusion'] and not p['reviewer'],pid+'_no_human_conclusion')
        exporter.export(app.ws,report_path.parent/'통합감사_미검토초안_v1.4.xlsx',CATALOG)
        check(all(p['state']=='작성중' for p in app.ws.procedures.values()),'draft_export_keeps_preparation_state')
        app.nb.select(app.tabs['절차·조서']);app.load_procedure('F01');root.update();capture_window(root,report_path.parent/'재무제표_조서화면.png')
        app.clear_request()
        for k,v in {'title':'합성 계약 추가 요청','requested_from':'가상 담당','due_date':'2026-12-31','note':'가상 원천자료 검토 범위 확인'}.items():app.request_vars[k].set(v)
        app.save_request();check(len(app.ws.requests)==1,'evidence_request_saved')
        app.request_state.set('검토완료');app.request_evidence.selection_set(0);app.save_request()
        check(next(iter(app.ws.requests.values()))['state']=='검토완료','received_source_required_and_saved')
        app.nb.select(app.tabs['자료요청']);root.update();capture_window(root,report_path.parent/'자료요청_화면.png')
        normal_ws=app.ws
        def fresh(folder):return Workspace(folder,create={'회사코드':'SYNTH01','회사명':'독립 합성 연습','시작일':'2026-01-01','기준일':'2026-12-31','회계체계':'K-IFRS','감사기준':'학습용','작성자':'합성작성자','더미업무':True})
        entries=json.loads(resource('worker_cases.json').read_text(encoding='utf-8'))
        for ix,entry in enumerate(entries):
            app.ws=fresh(report_path.parent/'계정연습'/entry['case_id']);app.current_pid=None
            run=app.ws.execute('계정별증빙연습',resource(entry['file']));app.refresh()
            actual={r['검사ID']:r for r in run['result']['tables']['계정별검사']}
            for e in entry['expected']:
                for a,b in [('상태','status'),('기대','expected_value'),('실제','actual_value'),('차이','difference')]:check(actual[e['check_id']][a]==e[b],entry['case_id']+'_'+e['check_id']+'_'+a)
            check(not run['result']['detail']['현재원장연결'],entry['case_id']+'_isolated')
            observations.append({'case':entry['case_id'],'checks':len(actual),'blocking':run['result']['blocking'],'review':run['result']['review']})
        app.ws=normal_ws;app.refresh()
        financial_root=resource('samples','재무제표');expected=json.loads((financial_root/'financial_cases/cases.json').read_text(encoding='utf-8'))
        for entry in expected['cases']:
            r=normal_ws.execute('재무제표·주석',financial_root/'financial_cases'/entry['file'])['result']
            for key in ('blocking','review'):
                if key in entry:check(r[key]==entry[key],entry['name']+'_'+key)
            if 'required_code' in entry:check(entry['required_code'] in [i['code'] for i in r['issues']],entry['name']+'_code')
            observations.append({'case':entry['name'],'blocking':r['blocking'],'review':r['review']})
        from raw_accounts.samples import CASES
        for name in CASES:
            folder=resource('samples','공통거래',name);oracle=json.loads((folder/'검증결과.json').read_text(encoding='utf-8'))
            ws=fresh(report_path.parent/'공통거래'/name);gl=ws.execute('원장·리드',folder/'원장_공통거래.xlsx');run=ws.execute('원천증빙',folder/('공통거래_'+name+'.auditpack'))
            blocked=oracle['raw_status']=='INPUT_BLOCKED' or oracle['ledger_blocking']>0
            check(bool(run['result']['blocking'])==blocked,name+'_current_workspace_blocking')
            if not blocked:check((run['result']['review']>0)==(oracle['raw_status']=='EXCEPTION'),name+'_workspace_difference')
            observations.append({'case':name,'blocking':run['result']['blocking'],'review':run['result']['review']})
        result={'ok':True,'frozen':bool(getattr(sys,'frozen',False)),'checks':checks,'legacy_cases':213,
                'independent_account_cases':33,'account_expectations':300,'financial_cases':14,'common_transaction_cases':10,
                'observations':observations,'evidence_scope':'114 tables indexed; selected 32 allocations only; 8 unconfirmed scopes retained',
                'limitations':['Windows development PC, not clean OS','Native widget invocation, no OS file-dialog automation','Synthetic evidence only']}
        atomic(report_path,json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8'));return 0
    except Exception as exc:
        atomic(report_path,json.dumps({'ok':False,'error':str(exc),'traceback':traceback.format_exc(),'checks':checks},ensure_ascii=False,indent=2).encode('utf-8'));return 1
    finally:
        if root:
            try:
                from window_capture import destroy_test_window
                destroy_test_window(root)
            except Exception:pass
