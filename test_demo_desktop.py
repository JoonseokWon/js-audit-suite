"""Hidden native walkthrough QA. Model/runtime are explicit mocks, never inference."""
from pathlib import Path
import copy,shutil,sys,tempfile,unittest
from unittest.mock import patch


@unittest.skipUnless(sys.platform=='win32','Native Windows Tk UI')
class DemoDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import runtime
        runtime.configure();runtime.configure_tk_libraries()
        import tkinter as tk,ai_desktop
        from app import App
        from demo_case import create_demo
        from test_ai_desktop import MockRuntime
        cls.tk=tk;cls.temp_class=tempfile.TemporaryDirectory(prefix='audit-demo-ui-')
        cls.base=Path(cls.temp_class.name)
        create_demo(cls.base/'master')
        cls.runtime_patch=patch.object(ai_desktop,'LocalAIRuntime',MockRuntime);cls.runtime_patch.start()
        cls.root=tk.Tk();cls.root.withdraw();cls.app=App(cls.root,sector_home=cls.base/'sectors')

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown_ai()
        from window_capture import destroy_test_window
        destroy_test_window(cls.root);cls.runtime_patch.stop();cls.temp_class.cleanup()

    def setUp(self):
        from demo_case import load_manifest
        self.temp=tempfile.TemporaryDirectory(prefix='audit-demo-ui-case-');self.folder=Path(self.temp.name)/'SYNTHETIC_ONLY'
        shutil.copytree(self.base/'master',self.folder);self.app.open_workspace(self.folder)
        self.app.load_procedure('A04');self.ws=self.app.ws;self.manifest=load_manifest(self.folder)
        self.head=self.ws.head;self.errors=[];self.tops=[]
        original=self.tk.Toplevel
        def hidden(*args,**kwargs):
            win=original(*args,**kwargs);win.withdraw();self.tops.append(win);return win
        self.patches=[patch.object(self.tk,'Toplevel',side_effect=hidden),
            patch('desktop.ai.shared.messagebox.showerror',side_effect=lambda *a,**k:self.errors.append(a))]
        for p in self.patches:p.start()

    def tearDown(self):
        self.app.cancel.clear();self.app.set_ui_zoom(100)
        for win in reversed(self.tops):
            if win.winfo_exists():win.destroy()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def settle(self):
        import _tkinter
        count=0
        while self.root.tk.dooneevent(_tkinter.ALL_EVENTS|_tkinter.DONT_WAIT):
            count+=1
            if count>6000:raise AssertionError('UI geometry did not become idle')

    def guide(self):
        from desktop.demo.guide import DemoGuide
        return DemoGuide(self.app)

    def install_mock(self):
        from test_ai_desktop import mock_response
        from procedures import task_definitions
        task=next(t for t in self.app.task_list() if t['id']=='A04')
        self.ws.save_procedure({**task,'preparer':'SYNTHETIC ONLY UI author',
            'performed':'','conclusion':'','performed_date':'','evidence_ids':[]})
        packet=self.ws.ai_packet('A04',self.app.ai_catalog)
        did=self.ws.record_ai_draft(packet,mock_response(packet),'SYNTHETIC ONLY UI requester')
        self.app.refresh();self.app.load_procedure('A04')
        return did

    def test_new_demo_does_not_fill_a_person_or_performance_from_creator_metadata(self):
        self.assertIn('예제 자료 생성기',self.ws.engagement['작성자'])
        self.assertEqual(self.app.proc_vars['preparer'].get(),'')
        self.assertEqual(self.app.proc_vars['performed_date'].get(),'')
        self.assertEqual(self.app.ai_actor(),'')
        self.assertEqual(self.app.reviewer.get(),'')
        for field in ('performed','conclusion'):self.assertEqual(self.app.proc_text[field].get('1.0','end').strip(),'')
        self.assertFalse(self.ws.procedures);self.assertFalse(self.ws.ai_drafts)

    def test_malformed_marker_still_does_not_fall_back_to_an_example_creator(self):
        (self.folder/'시연_자료목록.json').write_text('{}',encoding='utf-8')
        self.app.load_procedure('A04')
        self.assertEqual(self.app.ai_actor(),'');self.assertEqual(self.app.proc_vars['preparer'].get(),'')

    def test_blank_author_stops_generation_before_runtime_or_provider(self):
        with patch('ai_desktop.generate_draft') as generate,patch.object(self.app.ai_runtime,'ensure_server') as ensure:
            self.app.ai_generate_button.invoke()
        generate.assert_not_called();ensure.assert_not_called()
        self.assertTrue(self.errors);self.assertEqual(self.ws.head,self.head);self.assertFalse(self.ws.ai_drafts)

    def test_evidence_view_contains_raw_calculation_or_reconciliation_and_errors_without_writing(self):
        from desktop.ai.evidence import open_current_evidence,reference_rows
        win=open_current_evidence(self.app);self.settle()
        kinds={r['kind'] for r in win.packet['references']}
        self.assertIn('raw_xlsx_row',kinds);self.assertIn('exception',kinds)
        self.assertTrue({'calculation_row','ledger_reconciliation'} & kinds)
        self.assertEqual(len(win.evidence_body.reference_tree.get_children()),len(reference_rows(win.packet)))
        self.assertIn('REF',win.evidence_body.reference_detail.get('1.0','end'))
        self.assertEqual(self.ws.head,self.head);self.assertFalse(self.ws.ai_drafts)

    def test_dirty_evidence_preview_never_saves_or_generates(self):
        from desktop.ai.evidence import open_current_evidence
        from common import AuditError
        self.app.proc_text['conclusion'].insert('end','SYNTHETIC ONLY unsaved note')
        with self.assertRaises(AuditError):open_current_evidence(self.app)
        self.assertEqual(self.ws.head,self.head);self.assertFalse(self.ws.procedures)

    def test_guide_is_read_only_and_stages_clean_file_without_executing(self):
        guide=self.guide();self.settle();self.assertGreater(guide.status['blocking'],0)
        self.assertIn('AI',guide.next_text.get());self.assertFalse(guide.status['ai_state']['approved'])
        with patch.object(self.ws,'execute') as execute:
            guide.prepare_input('sales_clean')
        execute.assert_not_called();self.assertEqual(self.app.module.get(),'매출')
        self.assertEqual(self.app.file.get(),self.manifest['inputs']['sales_clean']['path'])
        self.assertEqual(self.ws.head,self.head);self.assertFalse(self.ws.procedures)

    def test_old_guide_rejects_new_workspace_and_tampered_input(self):
        from common import AuditError
        guide=self.guide();self.app.ws=copy.copy(self.ws)
        with self.assertRaises(AuditError):guide.prepare_input('ledger_clean')
        self.app.ws=self.ws
        Path(self.manifest['inputs']['sales_clean']['path']).write_bytes(b'SYNTHETIC ONLY changed input')
        with self.assertRaises(AuditError):guide.prepare_input('sales_clean')
        self.assertEqual(self.ws.head,self.head)

    def test_mock_preview_apply_and_explicit_confirmation_preserve_separate_review(self):
        did=self.install_mock();self.app.open_ai_preview(did);win=self.app.ai_preview_win
        self.assertTrue(win.evidence_body.reference_tree.get_children())
        win.apply_button.invoke();self.assertFalse(self.errors)
        self.assertFalse(self.ws.ai_status('A04')['approved'])
        self.app.proc_text['conclusion'].insert('end','\nSYNTHETIC ONLY: 사람이 입력하는 수정 동작 시험. 실제 감사 판단 아님.')
        self.app.save_procedure();self.app.open_ai_approval();approval=self.app.ai_approval_win
        self.assertFalse(approval.confirmed.get());self.assertEqual(approval.note.get('1.0','end').strip(),'')
        approval.approve_button.invoke();self.assertFalse(self.ws.ai_status('A04')['approved'])
        self.errors.clear();approval.actor.set('SYNTHETIC ONLY approval state test')
        approval.note.insert('1.0','SYNTHETIC ONLY: 상태전이 검증용 입력. 실제 사람 승인·감사 수행 아님.')
        approval.confirmed.set(True);approval.approve_button.invoke();self.assertFalse(self.errors)
        self.assertTrue(self.ws.ai_status('A04')['approved']);self.assertNotEqual(self.ws.procedures['A04']['state'],'검토완료')
        self.assertEqual(self.ws.procedures['A04']['performed_date'],'')
        self.ws.execute('원장·리드',self.manifest['inputs']['ledger_clean']['path']);self.app.refresh()
        self.assertFalse(self.ws.ai_status('A04')['approved']);self.assertIn('다시',self.app.ai_state.get())

    def test_mock_workpaper_excel_contains_saved_edit_and_no_audit_approval(self):
        from openpyxl import load_workbook
        did=self.install_mock();self.ws.apply_ai_draft(did,'SYNTHETIC ONLY UI author');self.app.refresh()
        marker='SYNTHETIC ONLY Excel saved edit'
        self.app.proc_text['conclusion'].insert('end','\n'+marker);self.app.save_procedure()
        target=Path(self.temp.name)/'SYNTHETIC_ONLY_draft.xlsx'
        with patch('desktop.actions.lifecycle.filedialog.asksaveasfilename',return_value=str(target)):
            self.app.export_dialog(False)
        self.assertTrue(target.is_file());self.assertFalse(self.errors)
        wb=load_workbook(target,data_only=False)
        try:
            values=[str(c.value) for s in wb for row in s for c in row if c.value is not None]
            self.assertTrue(any(marker in value for value in values))
            self.assertFalse(any(c.data_type=='f' for s in wb for row in s for c in row))
        finally:wb.close()
        self.assertFalse(self.ws.ai_status('A04')['approved'])

    def test_guide_footer_and_action_buttons_fit_a_narrow_150_percent_viewport(self):
        self.app.set_ui_zoom(150);guide=self.guide();self.settle()
        footer=next(w for w in guide.win.winfo_children() if w is not guide.scroll)
        footer.pack_forget();guide.scroll.pack_forget()
        for _ in range(3):
            self.settle();fh=footer.winfo_reqheight()
            footer.place(x=0,y=720-fh,width=640,height=fh)
            guide.scroll.place(x=0,y=0,width=640,height=720-fh);self.settle();guide.scroll._resize()
        self.settle()
        for parent in (footer,guide.actions,guide.input_actions):
            for button in parent.winfo_children():
                if isinstance(button,self.tk.ttk.Button):
                    self.assertGreater(button.winfo_width(),1)
                    self.assertLessEqual(button.winfo_x()+button.winfo_width(),parent.winfo_width()+1)
        self.assertEqual(self.root.state(),'withdrawn');self.assertEqual(guide.win.state(),'withdrawn')
        self.assertEqual(self.ws.head,self.head)

    def test_creator_prepares_a_separate_case_without_model_or_human_records(self):
        from desktop.demo.creator import open_demo_creator
        win=open_demo_creator(self.app)
        with patch.object(self.app,'launch_ai_job') as launch,patch('ai_desktop.generate_draft') as model:
            win.create_button.invoke()
            launch.assert_called_once();work,complete=launch.call_args.args
            result=work();complete(result)
            model.assert_not_called()
        self.assertIsNot(self.app.ws,self.ws);self.assertNotEqual(self.app.ws.root,self.ws.root)
        self.assertEqual(self.ws.head,self.head)
        self.assertFalse(self.app.ws.procedures);self.assertFalse(self.app.ws.ai_drafts)
        self.app.load_procedure('A04');self.assertEqual(self.app.ai_actor(),'')
        self.assertTrue(self.app.demo_guide_win.winfo_exists())

    def test_creator_cancelled_navigation_does_not_create_a_window_or_job(self):
        from desktop.demo.creator import open_demo_creator
        count=len(self.tops)
        with patch.object(self.app,'check_navigation',return_value=False),patch.object(self.app,'launch_ai_job') as launch:
            self.assertIsNone(open_demo_creator(self.app));launch.assert_not_called()
        self.assertEqual(len(self.tops),count);self.assertEqual(self.ws.head,self.head)

    def test_stale_basis_blocks_approval_dialog_before_any_confirmation(self):
        from common import AuditError
        did=self.install_mock();self.ws.apply_ai_draft(did,'SYNTHETIC ONLY UI author')
        self.ws.execute('원장·리드',self.manifest['inputs']['ledger_clean']['path']);self.app.refresh()
        count=len(self.tops)
        with self.assertRaisesRegex(AuditError,'새 AI 초안'):self.app.open_ai_approval()
        self.assertEqual(len(self.tops),count);self.assertFalse(self.ws.ai_status('A04')['approved'])

    def test_job_elapsed_time_starts_advances_and_finish_preserves_queue_status(self):
        self.app.status.set('SYNTHETIC ONLY provider progress remains visible')
        with patch('desktop.ai.jobs.threading.Thread') as thread,patch('desktop.ai.timing.monotonic',return_value=100) as clock:
            self.app.launch_ai_job(lambda:None,lambda _:None)
            thread.assert_called_once();self.assertTrue(self.app.busy)
            self.assertIn('00:00',self.app.ai_elapsed.get());self.assertIsNotNone(self.app._ai_elapsed_timer)
            clock.return_value=196;self.app.update_ai_elapsed()
            self.assertIn('01:36',self.app.ai_elapsed.get())
            self.assertEqual(self.app.status.get(),'SYNTHETIC ONLY provider progress remains visible')
            bar=self.app.ai_actions;bar.pack_forget();self.app.set_ui_zoom(150)
            try:
                bar.place(x=0,y=0,width=640);self.settle();bar.reflow();self.settle()
                label=self.app.ai_elapsed_label
                self.assertEqual(label.winfo_manager(),'place')
                self.assertGreater(label.winfo_width(),1)
                self.assertLessEqual(label.winfo_x()+label.winfo_width(),bar.winfo_width()+1)
            finally:
                bar.place_forget();bar.pack(fill='x',pady=(0,5),before=self.app.proc_paned)
            self.app.finish_ai_job('ai_ok',None)
        self.assertFalse(self.app.busy);self.assertIsNone(self.app._ai_elapsed_timer)
        self.assertEqual(self.app.ai_elapsed.get(),'');self.assertEqual(self.ws.head,self.head)

    def test_cancelled_elapsed_timer_stops_without_claiming_completion_or_callback(self):
        with patch('desktop.ai.jobs.threading.Thread'),patch('desktop.ai.timing.monotonic',return_value=100),\
             patch.object(self.app,'ai_job_complete') as complete:
            self.app.launch_ai_job(lambda:None,complete)
            self.app.cancel.set();self.app.update_ai_elapsed()
            self.assertIsNone(self.app._ai_elapsed_timer)
            self.assertIn('종료를 기다리는 중',self.app.ai_elapsed.get())
            self.assertNotIn('완료',self.app.ai_elapsed.get())
            self.app.finish_ai_job('ai_ok',None);complete.assert_not_called()
        self.assertFalse(self.app.busy);self.assertEqual(self.app.ai_elapsed.get(),'')
        self.assertEqual(self.ws.head,self.head);self.assertFalse(self.ws.ai_drafts)

    def test_shutdown_cancels_elapsed_after_callback_and_clears_display(self):
        with patch('desktop.ai.jobs.threading.Thread'):
            self.app.launch_ai_job(lambda:None,lambda _:None)
            timer=self.app._ai_elapsed_timer;self.assertIsNotNone(timer)
            self.app.shutdown_ai()
            self.assertIsNone(self.app._ai_elapsed_timer);self.assertEqual(self.app.ai_elapsed.get(),'')
            self.assertNotIn(timer,self.root.tk.splitlist(self.root.tk.call('after','info')))
            self.app.cancel.set();self.app.finish_ai_job('ai_ok',None)
        self.assertEqual(self.ws.head,self.head)


if __name__=='__main__':unittest.main()
