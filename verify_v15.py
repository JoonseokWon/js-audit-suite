from pathlib import Path
import json,sys,time,traceback
from common import atomic
def self_test(report_path):
    report_path=Path(report_path);report_path.parent.mkdir(parents=True,exist_ok=True);root=None;checks=[]
    def check(ok,name):
        if not ok:raise AssertionError(name)
        checks.append(name)
    try:
        from verify_v14 import self_test as legacy
        check(legacy(report_path.parent/'legacy_v14/report.json')==0,'prior_270_cases_and_native_checks')
        from app import App,resource,CATALOG
        from analytics_validation import exercise
        result=exercise(resource(),report_path.parent/'accounting')
        import tkinter as tk
        from window_capture import capture_window
        root=tk.Tk();app=App(root);app.start_demo(report_path.parent/'native_workspace',analytics=True)
        deadline=time.monotonic()+180
        while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
        check(not app.busy,'native_fifteen_modules_finished');check(len(app.ws.latest())==15,'native_fifteen_modules')
        check(all(r['result']['blocking']==0 for r in app.ws.latest().values()),'native_all_normal_not_blocked')
        check(len(app.ws.cross_checks())==35,'native_thirty_five_current_links')
        copied=app.copy_input_bundle(report_path.parent/'자료복사')
        check((copied/'분석원천자료/manifest.json').is_file(),'native_raw_source_bundle_copied')
        check((copied/'더미자료/통합/통합_v1.5_FIA.xlsx').read_bytes()==resource('samples','통합','통합_v1.5_FIA.xlsx').read_bytes(),'native_copy_preserves_input_bytes')
        for module in ('GLA','FIA','현금분석'):
            app.nb.select(app.tabs['결과 상세']);app.result_module.set(module);app.choose_result_module()
            preferred={'GLA':'월별집계','FIA':'전표메타대사','현금분석':'계좌잔액대사'}[module]
            available=app.ws.latest()[module]['result']['tables'];table=preferred if preferred in available else '현재원장연결'
            app.result_table.set(table);app.load_table();root.update();check(bool(app.result_tree.get_children()),module+'_native_detail_visible')
            capture_window(root,report_path.parent/(module+'_화면.png'))
        app.nb.select(app.tabs['검토후보']);root.update();check(len(app.risk_tree.get_children())==len(app.ws.risk_register())>0,'native_risk_register')
        app.risk_tree.selection_set('0');app.show_risk();capture_window(root,report_path.parent/'통합검토후보_화면.png')
        before=len(app.ws.requests);app.risk_request();root.update();check(len(app.ws.requests)==before,'request_is_only_draft_until_saved')
        check(not app.request_vars['requested_from'].get(),'request_recipient_requires_human_input')
        app.request_vars['requested_from'].set('가상 회계담당');app.save_request();check(len(app.ws.requests)==before+1,'native_request_saved_explicitly')
        capture_window(root,report_path.parent/'후보_자료요청초안.png')
        for pid in ('G01','I01','H01'):
            app.load_procedure(pid);app.save_procedure();p=app.ws.procedures[pid]
            check(not p['performed'] and not p['conclusion'] and not p['reviewer'],pid+'_human_fields_blank')
            app.nb.select(app.tabs['절차·조서']);root.update();capture_window(root,report_path.parent/(pid+'_조서.png'))
        import exporter
        exporter.export(app.ws,report_path.parent/'통합감사_미검토초안_v1.5.xlsx',CATALOG)
        result.update(ok=True,frozen=bool(getattr(sys,'frozen',False)),native_checks=checks,legacy_cases=270,total_cases=270+result['case_count'])
        atomic(report_path,json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8'));return 0
    except Exception as e:
        atomic(report_path,json.dumps({'ok':False,'error':str(e),'traceback':traceback.format_exc(),'native_checks':checks},ensure_ascii=False,indent=2).encode('utf-8'));return 1
    finally:
        if root:
            try:
                from window_capture import destroy_test_window
                destroy_test_window(root)
            except Exception:pass
