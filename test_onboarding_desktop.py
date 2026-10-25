"""Withdrawn, isolated native UI tests. No keyboard/file-picker automation or real workspaces."""
from copy import deepcopy
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch,Mock


@unittest.skipUnless(sys.platform=='win32','Native Windows Tk UI')
class OnboardingDesktopTests(unittest.TestCase):
    def setUp(self):
        import runtime
        runtime.configure();runtime.configure_tk_libraries()
        import tkinter as tk
        from app import App
        from workspace import Workspace
        from onboarding.demo import CONTEXT
        self.tk=tk;self.temp=tempfile.TemporaryDirectory(prefix='audit-onboarding-ui-')
        base=Path(self.temp.name);self.root=tk.Tk();self.root.withdraw()
        self.app=App(self.root,sector_home=base/'not-created-store')
        ws=Workspace(base/'SYNTHETIC_ONLY',create=dict(CONTEXT,회사명='가상 UI 검증회사 · 실제 고객 아님',
            회계체계='K-IFRS',감사기준='SYNTHETIC ONLY UI test',작성자='가상 작성자',더미업무=True))
        self.app.open_workspace(ws.root);self.head=self.app.ws.head
        self.db=self.app.ws.root/'업무.sqlite3';self.db_bytes=self.db.read_bytes()
        self.tops=[];original=tk.Toplevel
        def hidden(*args,**kwargs):
            win=original(*args,**kwargs);win.withdraw();self.tops.append(win);return win
        self.patch=patch.object(tk,'Toplevel',side_effect=hidden);self.patch.start()

    def tearDown(self):
        try:
            self.assertEqual(self.root.state(),'withdrawn')
            self.assertEqual(self.app.ws.head,self.head)
            self.assertEqual(self.db.read_bytes(),self.db_bytes)
            self.assertFalse(self.app.sector_home.exists())
            for win in reversed(self.tops):
                if win.winfo_exists():win.destroy()
            self.app.shutdown_ai()
            from window_capture import destroy_test_window
            destroy_test_window(self.root)
        finally:self.patch.stop();self.temp.cleanup()

    def settle(self):
        import _tkinter
        count=0
        while self.root.tk.dooneevent(_tkinter.ALL_EVENTS|_tkinter.DONT_WAIT):
            count+=1
            if count>6000:raise AssertionError('UI geometry did not become idle')

    @staticmethod
    def descendants(parent):
        result=[]
        for child in parent.winfo_children():
            result.append(child);result.extend(OnboardingDesktopTests.descendants(child))
        return result

    def workbench(self):
        from desktop.onboarding.manager import WorkbenchDialog
        return WorkbenchDialog(self.app)

    def viewport(self,dialog,width=760,height=760,scale=100):
        """Size hidden dialog children explicitly; no toplevel is mapped to the desktop."""
        from desktop_display import ScrollableFrame
        self.app.set_ui_zoom(scale)
        children=dialog.win.winfo_children()
        footer=next(w for w in children if not isinstance(w,ScrollableFrame))
        scroll=next(w for w in children if isinstance(w,ScrollableFrame))
        footer.pack_forget();scroll.pack_forget()
        for _ in range(3):
            self.settle();fh=footer.winfo_reqheight()
            footer.place(x=0,y=height-fh,width=width,height=fh)
            scroll.place(x=0,y=0,width=width,height=max(1,height-fh))
            self.settle();scroll._resize()
        self.settle()
        return footer,scroll

    def assert_buttons_fit(self,parent):
        from tkinter import ttk
        buttons=[w for w in self.descendants(parent) if isinstance(w,(ttk.Button,ttk.Menubutton))]
        self.assertTrue(buttons)
        for button in buttons:
            x,y=button.winfo_x(),button.winfo_y();p=button.master
            self.assertGreater(button.winfo_width(),1)
            self.assertLessEqual(x+button.winfo_width(),p.winfo_width()+1)
            self.assertLessEqual(y+button.winfo_height(),p.winfo_height()+1)

    def test_all_seven_modules_preview_and_table_view_without_approval(self):
        from onboarding import MODULES
        dialog=self.workbench()
        self.assertEqual((dialog.actor.get(),dialog.reason.get()),('',''))
        for module in MODULES:
            with self.subTest(module=module):
                dialog.area.set(module);dialog.reset();self.settle()
                self.assertFalse(dialog.accept.get());self.assertFalse(dialog.aje.get())
                self.assertEqual(dialog.payload.get('approval'),{})
                self.assertTrue(dialog.notice.get());self.assertTrue(dialog.description)
                self.assertEqual(len(dialog.preview.get_children()),len(dialog.description))
                dialog.preview.selection_set('0');before=len(self.tops);dialog.show_table()
                self.assertEqual(len(self.tops),before+1)
                from tkinter import ttk
                table=next(w for w in self.descendants(self.tops[-1]) if isinstance(w,ttk.Treeview))
                self.assertGreater(len(table.get_children()),0)
                self.assertEqual(self.tops[-1].state(),'withdrawn');self.tops[-1].destroy()

    def test_unchecked_execute_and_cancelled_picker_never_register_or_launch(self):
        from common import AuditError
        dialog=self.workbench();before=deepcopy(dialog.payload)
        with patch.object(self.app,'launch') as launch,patch('desktop.onboarding.manager.filedialog.askopenfilename',return_value=''):
            dialog.load()
            with self.assertRaises(AuditError):dialog.execute()
            launch.assert_not_called()
        self.assertEqual(dialog.paths,[]);self.assertEqual(dialog.payload,before)

    def test_reset_clears_confirmation_and_adjustment_checkbox(self):
        dialog=self.workbench();dialog.accept.set(True);dialog.aje.set(True);dialog.reset()
        self.assertFalse(dialog.accept.get());self.assertFalse(dialog.aje.get())

    def test_dirty_navigation_cancel_opens_no_dialog(self):
        from desktop.onboarding.manager import WorkbenchDialog
        count=len(self.tops)
        with patch.object(self.app,'check_navigation',return_value=False):
            dialog=WorkbenchDialog(self.app)
        self.assertFalse(hasattr(dialog,'win'));self.assertEqual(len(self.tops),count)

    def test_checkbox_without_actor_never_registers_or_launches(self):
        from common import AuditError
        dialog=self.workbench();dialog.accept.set(True)
        with patch.object(self.app,'launch') as launch,patch.object(self.app.ws,'add_source') as add:
            with self.assertRaises(AuditError):dialog.execute()
            launch.assert_not_called();add.assert_not_called()

    def test_empty_erp_picker_and_apply_leave_payload_and_workspace_unchanged(self):
        from desktop.onboarding.erp_form import ErpMappingDialog
        from onboarding.erp import sample
        ready=Mock();payload=sample(self.app.ws.context)
        dialog=ErpMappingDialog(self.app,payload,ready)
        with patch('desktop.onboarding.erp_form.filedialog.askopenfilename',return_value=''),\
             patch('desktop.onboarding.erp_form.messagebox.showerror') as error:
            dialog.choose_file();dialog.apply();error.assert_called_once()
        ready.assert_not_called();self.assertEqual(dialog.path,'');self.assertEqual(dialog.payload,payload)
        self.assertFalse(dialog.variables);self.assertEqual(dialog.win.state(),'withdrawn')

    def test_erp_korean_rule_labels_keep_internal_codes_and_no_approval(self):
        from desktop.onboarding.erp_form import ErpMappingDialog,MODE_LABELS
        from onboarding.erp import sample
        from onboarding.erp.schema import REQUIRED_TARGETS
        ready=Mock();dialog=ErpMappingDialog(self.app,sample(self.app.ws.context),ready)
        self.assertEqual(dialog.mode.get(),MODE_LABELS['two_columns'])
        dialog.mode.set(MODE_LABELS['signed']);self.assertEqual(dialog.mode_code(),'signed')
        dialog.path='SYNTHETIC_ONLY_mock.xlsx'
        dialog.variables={key:self.tk.StringVar(value='가상열_'+key) for key in REQUIRED_TARGETS|{'amount'}}
        staged={'config':{'amount_mode':'signed'},'approval':{}}
        with patch('desktop.onboarding.erp_form.stage_original',return_value=staged) as stage:
            dialog.apply()
        self.assertEqual(stage.call_args.args[-1]['amount_mode'],'signed')
        ready.assert_called_once();self.assertEqual(ready.call_args.args[0]['approval'],{})

    def test_footer_buttons_reachable_at_100_and_150_percent_in_narrow_dialogs(self):
        from desktop.onboarding.erp_form import ErpMappingDialog
        from onboarding.erp import sample
        for scale in (100,150):
            with self.subTest(scale=scale):
                work=self.workbench();footer,scroll=self.viewport(work,760,720,scale)
                self.assert_buttons_fit(footer);self.assertGreater(scroll.canvas.winfo_height(),1)
                scroll.canvas.yview_moveto(1);self.settle()
                self.assertGreaterEqual(scroll.canvas.yview()[1],0.99)
                work.win.destroy()
                erp=ErpMappingDialog(self.app,sample(self.app.ws.context),Mock())
                footer,_=self.viewport(erp,720,660,scale);self.assert_buttons_fit(footer);erp.win.destroy()

    def test_new_header_commands_and_existing_toolbar_stay_available(self):
        self.app.app_shell.pack_forget();self.app.app_shell.place(x=0,y=0,width=1000,height=1000)
        self.settle()
        menu=self.app.more_menu
        labels=[menu.entrycget(i,'label') for i in range(menu.index('end')+1) if menu.type(i)!='separator']
        self.assertIn('실무절차 입력·검사',labels);self.assertIn('새 JS 실무절차 예제',labels)
        self.assertIn('현금흐름표 별도 도구',labels)
        for scale in (100,150):
            self.app.set_ui_zoom(scale);self.settle()
            for flow in (self.app.company_bar,self.app.toolbar):self.assert_buttons_fit(flow)
        self.assertEqual(self.root.state(),'withdrawn')

    def test_dialog_help_text_wraps_with_controlled_native_body_width(self):
        from tkinter import ttk
        from desktop.onboarding.erp_form import ErpMappingDialog
        from onboarding.erp import sample
        for scale in (100,150):
            for dialog in (self.workbench(),ErpMappingDialog(self.app,sample(self.app.ws.context),Mock())):
                self.viewport(dialog,720,700,scale)
                # Withdrawn canvases need not allocate embedded windows: supply
                # the intended viewport width for actual native child sizing.
                dialog.body.pack_forget();dialog.body.place(x=0,y=0,width=650,height=1600);self.settle()
                for child in dialog.body.winfo_children():
                    if isinstance(child,ttk.Label) and child.cget('wraplength'):
                        self.assertLessEqual(int(child.cget('wraplength')),child.winfo_width()+1)
                    if isinstance(child,ttk.Checkbutton):
                        self.assertLessEqual(child.winfo_reqwidth(),child.winfo_width()+1)
                dialog.win.destroy()


if __name__=='__main__':unittest.main()
