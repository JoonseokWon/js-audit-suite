"""Hidden native form/layout QA; no physical IME, mouse, or human approval."""
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from common import AuditError
from test_misstatements_support import Case


@unittest.skipUnless(sys.platform=='win32','Native Windows Tk UI')
class DesktopTests(Case):
    def setUp(self):
        super().setUp()
        import runtime
        runtime.configure_tk_libraries()
        import tkinter as tk
        from desktop_display import DisplayManager
        self.tk=tk;self.root=tk.Tk();self.root.withdraw();self.addCleanup(self.root.destroy)
        self.display=DisplayManager(self.root)
        self.host=SimpleNamespace(root=self.root,ws=self.ws,display=self.display,
            guard=lambda:None,check_navigation=lambda:True,refresh=lambda:None,
            status=tk.StringVar())
        self.errors=[];self.error_patch=patch('desktop.misstatements.shared.messagebox.showerror',side_effect=lambda *a,**k:self.errors.append(a))
        self.error_patch.start();self.addCleanup(self.error_patch.stop)

    def test_open_readonly_is_hidden_and_does_not_create_judgments_or_events(self):
        from desktop.misstatements import open_dialog
        before=self.ws.head;dialog=open_dialog(self.host)
        self.assertEqual(dialog.win.state(),'withdrawn')
        self.assertEqual(self.ws.head,before);self.assertFalse(self.ws.procedures)
        dialog.close(force=True)

    def test_editor_keeps_human_fields_empty_and_raw_invalid_edges(self):
        from desktop.misstatements.editor import edit_record
        dialog=edit_record(self.host)
        for key in ('assessment','amount','actor','judgment','period','tax_effect','qualitative'):
            self.assertEqual(dialog.value(key),'')
        with self.assertRaisesRegex(AuditError,'U\\+000B'):
            dialog.fields['description'].insert('1.0','가상 받침 수정\x0b')
        dialog.fields['description'].insert('1.0','가상 받침 수정')
        dialog.fields['actor'].set('SYNTHETIC ONLY\x0b')
        self.assertTrue(dialog.value('actor').endswith('\x0b'))
        self.assertNotEqual(dialog.signature(),dialog.saved_signature)
        with patch('desktop.workflow.dialog.messagebox.askokcancel',return_value=False):
            self.assertFalse(dialog.close())
        dialog.close(force=True)

    def test_head_changed_save_rejected_and_navigation_cancel_creates_no_form(self):
        from desktop.misstatements.editor import edit_record
        dialog=edit_record(self.host);old=self.ws.head
        self.ws.add_note('가상 메모','SYNTHETIC ONLY 다른 저장','SYNTHETIC ONLY')
        invoked=[];dialog.save(lambda:invoked.append(True),'가상 저장')
        self.assertFalse(invoked);self.assertTrue(self.errors);self.assertNotEqual(self.ws.head,old)
        dialog.close(force=True)
        self.host.check_navigation=lambda:False
        before=len(self.root.winfo_children())
        with self.assertRaises(AuditError):edit_record(self.host)
        self.assertEqual(len(self.root.winfo_children()),before)

    def test_account_rows_are_explicit_and_unadded_or_invalid_edits_cannot_be_lost(self):
        from desktop.misstatements.editor import edit_record
        dialog=edit_record(self.host);accounts=dialog.fields['account_impacts']
        self.assertEqual(accounts.get(),[])
        raw={'account_code':'1100','fs_line':'매출채권','direction':'증가','amount':'100'}
        for key,value in raw.items():accounts.variables[key].set(value)
        with self.assertRaisesRegex(AuditError,'계정행'):accounts.require_committed()
        self.assertEqual(accounts.get(),[])
        accounts.add();self.assertEqual(accounts.get()[0]['amount'],100)
        accounts.require_committed()
        accounts.widget.selection_set('0');accounts.select();accounts.require_committed()
        accounts.variables['amount'].set('101');self.assertTrue(accounts.pending())
        with self.assertRaises(AuditError):accounts.require_committed()
        accounts.update();self.assertEqual(accounts.get()[0]['amount'],101)
        accounts.widget.selection_set('0');accounts.select()
        accounts.variables['fs_line'].set('매출채권\x0b')
        with self.assertRaisesRegex(AuditError,'U\\+000B'):accounts.update()
        self.assertEqual(accounts.get()[0]['fs_line'],'매출채권')
        dialog.close(force=True)
