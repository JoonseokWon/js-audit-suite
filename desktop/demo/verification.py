"""Source/frozen hidden GUI checks; no model, approval, keyboard or file-dialog input."""
import tempfile
from pathlib import Path
from unittest.mock import patch


def verify(ws):
    import runtime
    runtime.configure();runtime.configure_tk_libraries()
    import tkinter as tk
    from app import App
    from common import AuditError,digest
    from demo_case import load_manifest
    from desktop.ai.evidence import open_current_evidence
    from desktop.demo.guide import DemoGuide
    from window_capture import destroy_test_window
    checks=[];before=ws.head;approval_before=digest(list(ws.ai_approvals.values()))
    drafts_before=digest(list(ws.ai_drafts.values()));tops=[]
    previous_default=tk._default_root;root=None;original=tk.Toplevel
    def check(condition,name):
        if not condition:raise AssertionError(name)
        checks.append(name)
    def hidden(*args,**kwargs):
        win=original(*args,**kwargs);win.withdraw();tops.append(win);return win
    def settle():
        import _tkinter
        count=0
        while root.tk.dooneevent(_tkinter.ALL_EVENTS|_tkinter.DONT_WAIT):
            count+=1
            if count>6000:raise AssertionError('Hidden GUI did not become idle')
    try:
        manifest=load_manifest(ws.root)
        root=tk.Tk();root.withdraw();tk._default_root=root
        with tempfile.TemporaryDirectory(prefix='audit-v22-hidden-ui-') as temp,patch.object(tk,'Toplevel',side_effect=hidden):
            app=App(root,sector_home=Path(temp)/'not-created-store')
            app.open_workspace(ws.root);app.load_procedure(manifest['target_pid']);settle()
            check(root.state()=='withdrawn','v22_ui_root_stays_hidden')
            p=ws.procedures.get(manifest['target_pid'],{})
            check(app.proc_vars['preparer'].get()==p.get('preparer',''),
                  'v22_example_creator_does_not_become_human_preparer')
            check(app.proc_vars['performed_date'].get()==p.get('performed_date',''),
                  'v22_ui_does_not_supply_human_performance_date')
            check(app.reviewer.get()==p.get('reviewer',''),'v22_ui_preserves_human_review_input')
            guide=DemoGuide(app);settle()
            check(bool(guide.status['stages']) and bool(guide.next_text.get()),'v22_case_guide_shows_saved_state_and_next_step')
            app.set_ui_zoom(150);footer=next(w for w in guide.win.winfo_children() if w is not guide.scroll)
            footer.pack_forget();guide.scroll.pack_forget()
            for _ in range(3):
                settle();height=footer.winfo_reqheight()
                footer.place(x=0,y=720-height,width=640,height=height)
                guide.scroll.place(x=0,y=0,width=640,height=720-height);settle();guide.scroll._resize()
            settle()
            controls=[w for frame in (footer,guide.actions,guide.input_actions) for w in frame.winfo_children()
                      if isinstance(w,tk.ttk.Button)]
            check(bool(controls) and all(w.winfo_width()>1 and w.winfo_x()+w.winfo_width()<=w.master.winfo_width()+1
                                        for w in controls),'v22_guide_controls_fit_narrow_150_percent_viewport')
            guide.prepare_input('sales_clean')
            check(app.file.get()==manifest['inputs']['sales_clean']['path'] and app.module.get()=='매출',
                  'v22_clean_input_is_staged_without_execution')
            evidence=open_current_evidence(app);settle()
            kinds={ref['kind'] for ref in evidence.packet['references']}
            check('raw_xlsx_row' in kinds and bool(kinds&{'calculation_row','ledger_reconciliation'}),
                  'v22_evidence_view_has_raw_and_actual_calculation_references')
            needs_exception=any(run['result']['blocking']+run['result']['review'] for run in ws.latest().values())
            check(not needs_exception or 'exception' in kinds,'v22_current_exceptions_are_visible_in_evidence')
            app.proc_text['conclusion'].insert('end','\nSYNTHETIC ONLY hidden unsaved text')
            rejected=False
            try:open_current_evidence(app)
            except AuditError:rejected=True
            check(rejected,'v22_dirty_form_requires_save_before_evidence_preview')
            app.load_procedure(manifest['target_pid']);app.refresh_ai_status()
            state=ws.ai_status(manifest['target_pid']);draft=ws.ai_drafts.get(state.get('draft_id'))
            check(not draft or draft['basis']==ws.basis() or '다시 생성' in app.ai_state.get(),
                  'v22_changed_basis_requires_new_ai_in_ui')
            check(all(win.state()=='withdrawn' for win in tops if win.winfo_exists()),'v22_ui_dialogs_stay_hidden')
            app.shutdown_ai()
        ws.refresh()
        check(ws.head==before and digest(list(ws.ai_approvals.values()))==approval_before
              and digest(list(ws.ai_drafts.values()))==drafts_before,'v22_ui_navigation_creates_no_draft_approval_or_history')
        return {'ok':True,'checks':checks,'actual_model_calls':0,'physical_keyboard_test':False,'read_only':True}
    finally:
        for win in reversed(tops):
            if win.winfo_exists():win.destroy()
        if root:destroy_test_window(root)
        tk._default_root=previous_default
