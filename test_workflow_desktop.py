"""Owned hidden-window tests of native planning forms and real save callbacks."""
import runtime
runtime.configure();runtime.configure_tk_libraries()
import json
import sys
import tempfile
from pathlib import Path
import tkinter as tk
import unittest
from unittest.mock import patch
from app import App
from workspace import Workspace
from common import digest,result


@unittest.skipUnless(sys.platform=='win32','Windows native desktop component tests')
class WorkflowDesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='audit-v19-ui-')
        self.base=Path(self.temp.name)
        self.root=tk.Tk();self.root.withdraw()
        self.app=App(self.root,sector_home=self.base/'sectors')
        self.ws=Workspace(self.base/'work',create={'회사코드':'UI_TEST','회사명':'합성 UI 검증',
            '시작일':'2026-01-01','기준일':'2026-12-31','회계체계':'K-IFRS',
            '감사기준':'합성 검증용','작성자':'합성작성자','더미업무':True})
        raw=self.base/'synthetic.csv';raw.write_text('계정,금액\n1000,100\n',encoding='utf-8')
        self.sid=self.ws.add_source(raw,'합성 증거')
        self.app.open_workspace(self.ws.root)
        self.errors=patch('workflow_desktop.messagebox.showerror');self.error=self.errors.start()
        self.confirm=patch('workflow_desktop.messagebox.askokcancel',return_value=True);self.confirm.start()

    def tearDown(self):
        self.errors.stop();self.confirm.stop()
        try:
            modal=getattr(self.app,'wf_modal',None)
            if modal and modal.win.winfo_exists():modal.close(force=True)
            from window_capture import destroy_test_window
            self.app.shutdown_ai();destroy_test_window(self.root)
        finally:self.temp.cleanup()

    @staticmethod
    def set_value(dialog,key,value):
        widget=dialog.fields[key]
        if isinstance(widget,tk.Variable):widget.set(value)
        else:widget.delete('1.0','end');widget.insert('1.0',value)

    @staticmethod
    def click(dialog,label):
        def walk(parent):
            for child in parent.winfo_children():
                if child.winfo_class()=='TButton' and child.cget('text')==label:return child
                value=walk(child)
                if value:return value
        button=walk(dialog.win)
        if button is None:raise AssertionError('Button not found: '+label)
        return button.invoke()

    def profile(self):
        d=self.app.open_workflow_profile()
        for key,value in {'audit_framework':'KSA_200_720','audit_framework_reason':'합성 일반 감사 선택',
            'form_framework':'KIFRS','benchmark_name':'검증용 기준금액','benchmark_amount':'100000000',
            'materiality_rate':'0.05','performance_rate':'0.6','trivial_rate':'0'}.items():self.set_value(d,key,value)
        d.scope_tree.selection_set('C04');self.set_value(d,'scope_reason','검증용 원장 범위')
        self.click(d,'선택 절차 적용');self.click(d,'계획 저장·중요성 계산')
        self.assertFalse(self.error.called,self.error.call_args)
        return self.app.ws.workflow_profile

    def risk(self):
        d=self.app.open_workflow_risk()
        for key,value in {'title':'합성 원장 누락 위험','accounts':'1000, 2000','assertions':'완전성, 정확성',
            'nature':'합성 전수 대사 계획','timing':'2026-12-31 이후','extent':'선택 원장 2계정',
            'assessment':'검증용 판단 입력; 실제 감사 수행 아님'}.items():self.set_value(d,key,value)
        for key,chosen in [('procedure_ids','C04'),('evidence_ids',self.sid)]:
            box,values=d.fields[key]
            box.selection_set(next(i for i,(value,_) in enumerate(values) if value==chosen))
        self.click(d,'위험 기록 저장');self.assertFalse(self.error.called,self.error.call_args)
        return next(iter(self.app.ws.workflow_risks.values()))

    def test_empty_profile_has_no_automatic_framework_or_rate_selection(self):
        self.app.open_workflow_view();d=self.app.open_workflow_profile()
        self.assertEqual(d.value('audit_framework'),'')
        self.assertEqual(d.value('materiality_rate'),'')
        self.assertEqual(d.scope_records,{})
        self.assertEqual(self.app.ws.workflow_profile,None)
        self.assertEqual(self.root.state(),'withdrawn');self.assertEqual(d.win.state(),'withdrawn')

    def test_profile_real_save_button_preserves_human_reason_and_calculates_only_selected_rates(self):
        profile=self.profile()
        self.assertEqual(int(profile['materiality']['overall_materiality']),5000000)
        self.assertEqual(int(profile['materiality']['performance_materiality']),3000000)
        self.assertEqual(int(profile['materiality']['clearly_trivial_threshold']),0)
        self.assertEqual(profile['scope'][0]['reason'],'검증용 원장 범위')
        self.assertTrue(self.app.wf_state['active'])
        self.assertTrue(self.app.wf_form_tree.get_children())
        self.assertFalse(self.app.ws.procedures)

    def test_invalid_profile_keeps_editor_open_and_writes_no_event(self):
        before=self.app.ws.head;d=self.app.open_workflow_profile();self.click(d,'계획 저장·중요성 계산')
        self.assertTrue(self.error.called);self.assertTrue(d.win.winfo_exists())
        self.app.ws.refresh();self.assertEqual(self.app.ws.head,before)

    def test_risk_save_button_binds_account_assertions_procedures_and_registered_evidence(self):
        self.profile();risk=self.risk()
        self.assertEqual(risk['accounts'],['1000','2000'])
        self.assertEqual(risk['procedure_ids'],['C04']);self.assertEqual(risk['evidence_ids'],[self.sid])
        self.assertTrue(self.app.wf_risk_tree.get_children())
        self.assertFalse(self.app.ws.procedures)

    def test_new_risk_explicit_action_does_not_reuse_selected_record(self):
        self.profile();first=self.risk();self.app.wf_risk_tree.selection_set('0')
        d=self.app.open_workflow_risk(new=True)
        self.assertEqual(d.value('title'),'');self.assertNotIn('id',d.fields)
        self.assertEqual(list(self.app.ws.workflow_risks),[first['id']])

    def test_edit_link_keeps_its_identity_and_new_link_picker_excludes_existing_ids(self):
        self.profile();risk=self.risk()
        self.app.ws.save_workflow_procedure({'procedure_id':'C04','risk_ids':[risk['id']],
            'evidence_ids':[self.sid],'basis':self.app.ws.data_basis(),'nature':'검증 성격',
            'timing':'검증 시기','extent':'검증 범위','plan':'합성 계획'},'합성 작성자')
        self.app.refresh();self.app.wf_link_tree.selection_set('0')
        d=self.app.open_workflow_procedure()
        self.assertEqual(d.value('procedure_id'),'C04')
        choices=[]
        def collect(parent):
            for child in parent.winfo_children():
                if child.winfo_class()=='TCombobox' and child.cget('textvariable')==str(d.fields['procedure_id']):choices.extend(child.cget('values'))
                collect(child)
        collect(d.win);self.assertEqual(choices,['C04']);d.close(force=True)
        d=self.app.open_workflow_procedure(new=True)
        self.assertEqual(d.value('procedure_id'),'')
        available=[]
        def collect_new(parent):
            for child in parent.winfo_children():
                if child.winfo_class()=='TCombobox' and child.cget('textvariable')==str(d.fields['procedure_id']):available.extend(child.cget('values'))
                collect_new(child)
        collect_new(d.win);self.assertNotIn('C04',available);self.assertIn('G01',available)

    def test_profile_can_explicitly_unset_scope_without_rewriting_saved_profile(self):
        before=self.profile();d=self.app.open_workflow_profile();d.scope_tree.selection_set('C04')
        self.click(d,'선택 절차 미지정')
        self.assertEqual(d.scope_records,{})
        self.assertEqual(self.app.ws.workflow_profile,before)

    def test_completion_detail_and_workpaper_navigation_preserve_pending_state(self):
        self.profile();before=self.app.ws.head
        index=next(i for i,row in enumerate(self.app.wf_state['rows']) if row.get('procedure_id')=='C04')
        self.app.wf_check_tree.selection_set(str(index));self.app.show_workflow_detail('rows',self.app.wf_check_tree)
        self.assertIn(self.app.wf_state['rows'][index]['message'],self.app.wf_detail.get('1.0','end'))
        self.assertTrue(self.app.open_workflow_workpaper());self.assertEqual(self.app.current_pid,'C04')
        self.assertEqual(self.app.ws.head,before);self.assertFalse(self.app.ws.procedures)

    def test_plan_only_link_does_not_create_actual_performance_or_approval(self):
        self.profile();risk=self.risk();d=self.app.open_workflow_procedure()
        for key,value in {'procedure_id':'C04','nature':'합성 원장 대사','timing':'기준일 이후',
                          'extent':'검증용 범위','plan':'등록 원장과 독립 통제값 대사 계획'}.items():self.set_value(d,key,value)
        for key,chosen in [('risk_ids',risk['id']),('evidence_ids',self.sid)]:
            box,values=d.fields[key];box.selection_set(next(i for i,(value,_) in enumerate(values) if value==chosen))
        self.click(d,'절차 연결 저장');self.assertFalse(self.error.called,self.error.call_args)
        link=self.app.ws.workflow_procedure_links['C04']
        self.assertEqual(link['performed'],'');self.assertEqual(link['performed_date'],'')
        self.assertFalse(self.app.ws.procedures);self.assertFalse(self.app.ws.ai_approvals)
        self.assertTrue(any(row['code']=='PROCEDURE_NOT_PERFORMED' for row in self.app.wf_state['human_pending']))

    def test_closing_dirty_modal_can_be_cancelled_without_losing_text(self):
        d=self.app.open_workflow_profile();self.set_value(d,'benchmark_name','수정 중인 기준금액')
        with patch('workflow_desktop.messagebox.askokcancel',return_value=False):self.assertFalse(d.close())
        self.assertTrue(d.win.winfo_exists());self.assertEqual(d.value('benchmark_name'),'수정 중인 기준금액')

    def test_modal_refuses_save_if_another_workspace_process_changed_head(self):
        d=self.app.open_workflow_profile()
        other=Workspace(self.app.ws.root);other.add_note('동시 수정','합성 별도 작업','다른 작성자')
        previous=other.head;self.click(d,'계획 저장·중요성 계산')
        self.assertTrue(self.error.called);self.assertTrue(d.win.winfo_exists())
        self.app.ws.refresh();self.assertEqual(self.app.ws.head,previous)

    def test_final_archive_button_cannot_queue_unreviewed_unlocked_work(self):
        self.profile()
        with patch('workflow_desktop.filedialog.asksaveasfilename') as dialog:
            with self.assertRaisesRegex(ValueError,'잠금'):self.app.workflow_archive_dialog(True)
            dialog.assert_not_called()
        self.assertFalse(self.app.busy)

    def test_verification_navigation_cancel_never_opens_file_or_starts_job(self):
        with patch.object(self.app,'check_navigation',return_value=False),patch('workflow_desktop.filedialog.askopenfilename') as choose:
            self.app.workflow_verify_dialog();choose.assert_not_called()
        self.assertFalse(self.app.busy)

    def test_new_f01_and_fs01_editor_saves_distinct_purpose_codes(self):
        for pid,purpose in [('F01','subsequent_events'),('FS01','financial_statement_reconciliation')]:
            self.app.load_procedure(pid);self.app.save_procedure()
            self.assertEqual(self.app.ws.procedures[pid]['purpose_code'],purpose)
        self.assertNotEqual(self.app.ws.procedures['F01']['title'],self.app.ws.procedures['FS01']['title'])


if __name__=='__main__':unittest.main()
