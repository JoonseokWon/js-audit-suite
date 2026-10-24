"""Actual source/EXE workpaper entry, zoom, scrolling and export checks."""
from pathlib import Path
import json,sys,time,traceback
from common import atomic,AuditError

def self_test(report_path):
    out=Path(report_path).parent;out.mkdir(parents=True,exist_ok=True);root=None;checks=[]
    def check(ok,name):
        if not ok:raise AssertionError(name)
        checks.append(name)
    try:
        from verify_v17 import self_test as baseline
        check(baseline(out/'baseline_v17/report.json')==0,'previous_111_native_checks_and_332_fixtures')
        old=json.loads((out/'baseline_v17/report.json').read_text(encoding='utf-8'))
        import runtime,tkinter as tk
        from tkinter import ttk,font
        from app import App,CATALOG
        from desktop_display import SCALE_OPTIONS
        from window_capture import capture_window,destroy_test_window
        from unittest.mock import patch
        import exporter
        root=tk.Tk();app=App(root,sector_home=out/'baseline_v17/회사별저장')
        def settle():
            for _ in range(10):root.update();time.sleep(.025)
        def inside(widget,parent):
            return (widget.winfo_ismapped() and widget.winfo_rootx()>=parent.winfo_rootx()-2
                    and widget.winfo_rooty()>=parent.winfo_rooty()-2
                    and widget.winfo_rootx()+widget.winfo_width()<=parent.winfo_rootx()+parent.winfo_width()+2
                    and widget.winfo_rooty()+widget.winfo_height()<=parent.winfo_rooty()+parent.winfo_height()+2)
        settle()
        check(runtime.DPI_STATUS['enabled'] and runtime.DPI_STATUS['mode']=='system','system_dpi_awareness_enabled')
        check(font.nametofont('AuditTextFont',root).actual()['size']==11,'body_font_11_point')
        check(tuple(int(s.rstrip('%')) for s in app.zoom_box['values'])==SCALE_OPTIONS,'six_explicit_zoom_choices')
        check(app.workpaper_button.cget('text')=='조서초안 작성','visible_workpaper_entry_label')
        check(app.draft_export_button.cget('text')=='초안 Excel 내보내기','explicit_draft_export_label')
        try:app.open_workpaper_draft()
        except AuditError:check(app.ws is None,'workpaper_entry_requires_company_without_creating_work')
        else:raise AssertionError('missing company accepted')
        app.sector_box.current(1);app.sector_box.event_generate('<<ComboboxSelected>>');root.update()
        deadline=time.monotonic()+180
        while app.busy and time.monotonic()<deadline:root.update();time.sleep(.02)
        check(not app.busy and app.active_sector=='JS_ELEC','existing_company_workspace_reused')
        settle();head=app.ws.head
        app.result_module.set('금융상품');app.choose_result_module();app.workpaper_button.invoke();settle()
        check(app.nb.select()==str(app.tabs['절차·조서']) and app.current_pid=='A02','toolbar_opens_selected_account_draft')
        check('자동계산 연결: 금융상품' in app.proc_text['scope'].get('1.0','end'),'draft_shows_actual_calculation_scope')
        expected={app.ws.latest()[m]['source_id'] for m in ('금융상품','원장·리드')}
        selected={app.evidence_sources[i]['id'] for i in app.evidence_list.curselection()}
        check(expected<=selected,'draft_includes_own_calculation_and_ledger')
        check(not app.proc_text['performed'].get('1.0','end').strip() and not app.proc_text['conclusion'].get('1.0','end').strip(),'draft_does_not_invent_human_performance_or_conclusion')
        check(app.ws.head==head,'opening_draft_does_not_save_or_change_history')
        capture_window(root,out/'조서초안_기본화면.png')
        app.proc_text['performed'].insert('1.0','합성 화면검증용 미저장 입력. 실제 감사 수행 아님.')
        signature=app.form_signature();app.workpaper_button.invoke();settle()
        check(app.form_signature()==signature and app.dirty(),'reopening_workpaper_preserves_unsaved_edit')
        observations=[]
        for percent in (100,125,150):
            root.geometry('1280x760')
            app.zoom_box.current(list(SCALE_OPTIONS).index(percent));app.zoom_box.event_generate('<<ComboboxSelected>>');settle()
            check(app.form_signature()==signature and app.ws.head==head,f'{percent}_zoom_preserves_unsaved_text_and_history')
            check(all(inside(w,app.toolbar) for w in app.toolbar.items if w.winfo_ismapped()),f'{percent}_toolbar_actions_within_window')
            check(inside(app.workpaper_button,app.toolbar) and inside(app.draft_export_button,app.toolbar) and inside(app.zoom_box,app.toolbar),f'{percent}_draft_export_and_zoom_remain_visible')
            check(inside(app.save_workpaper_button,app.workpaper_actions),f'{percent}_save_action_remains_visible')
            app.proc_scroll.refresh();app.proc_scroll.canvas.yview_moveto(1);settle()
            check(inside(app.review_complete_button,app.proc_scroll.canvas),f'{percent}_review_action_reachable_by_scrolling')
            capture_window(root,out/(f'조서초안_{percent}퍼센트_작은창.png'))
            observations.append({'percent':percent,'body_point_size':font.nametofont('AuditTextFont',root).actual()['size'],
                                 'linespace':font.nametofont('AuditTextFont',root).metrics('linespace'),
                                 'row_height':int(ttk.Style(root).lookup('Treeview','rowheight')),
                                 'window':[root.winfo_width(),root.winfo_height()],
                                 'draft_id':app.current_pid,'head_unchanged':app.ws.head==head})
        check(observations[0]['linespace']<observations[1]['linespace']<observations[2]['linespace'],'zoom_increases_actual_font_pixels')
        app.set_ui_zoom(100);app.display.fit_window(initial=True);app.proc_scroll.canvas.yview_moveto(0);settle()
        check(app.form_signature()==signature,'reset_zoom_keeps_draft_edit')
        menu_labels=[app.more_menu.entrycget(i,'label') for i in range(app.more_menu.index('end')+1) if app.more_menu.type(i)!='separator']
        check({'로우데이터','새 업무','업무 열기','자료 복사','검토완료본','화면 이동'}<=set(menu_labels),'compact_menu_keeps_all_secondary_actions')
        app.save_workpaper_button.invoke();settle()
        check(app.ws.procedures['A02']['performed'].startswith('합성 화면검증용') and app.ws.head!=head,'explicit_save_persists_real_form_and_adds_history')
        target=out/'조서초안_바로가기_출력.xlsx'
        with patch('app.filedialog.asksaveasfilename',return_value=str(target)):
            app.draft_export_button.invoke()
        settle();check(target.is_file(),'explicit_draft_export_button_creates_xlsx')
        from openpyxl import load_workbook
        book=load_workbook(target,read_only=True,data_only=True)
        rows=list(book['조서_A02'].values);book.close()
        check(any('합성 화면검증용' in str(v) for r in rows for v in r),'exported_workpaper_contains_saved_performance')
        check(app.ws.procedures['A02']['state']=='작성중','export_does_not_complete_review')
        try:exporter.export(app.ws,out/'미검토완료본_차단.xlsx',CATALOG,True)
        except AuditError:check(True,'unreviewed_draft_still_blocks_final_export')
        else:raise AssertionError('unreviewed final accepted')
        app.nb.select(app.tabs['절차·조서']);capture_window(root,out/'조서초안_저장후.png')
        environment={'dpi':app.display.dpi,'screen':[root.winfo_screenwidth(),root.winfo_screenheight()],
                     'tk':root.tk.call('info','patchlevel'),'awareness':runtime.DPI_STATUS}
        destroy_test_window(root);root=None;check(True,'whole_app_terminates_without_tcl_command_error')
        record={'ok':True,'version':'1.7.1','frozen':bool(getattr(sys,'frozen',False)),
                'legacy_cases':old['legacy_cases'],'observations':old['observations'],'sector_observations':old['sector_observations'],
                'native_checks':old['native_checks']+checks,'baseline_native_checks':old['native_checks'],
                'display_checks':checks,'display_observations':observations,'display_environment':environment,
                'legacy_native_checks':old['legacy_native_checks'],'resource_manifest_sha256':old['resource_manifest_sha256']}
        atomic(report_path,json.dumps(record,ensure_ascii=False,indent=2).encode());return 0
    except Exception as exc:
        atomic(report_path,json.dumps({'ok':False,'error':str(exc),'traceback':traceback.format_exc(),'display_checks':checks},ensure_ascii=False,indent=2).encode());return 1
    finally:
        if root:
            try:
                from window_capture import destroy_test_window
                destroy_test_window(root)
            except Exception:pass
