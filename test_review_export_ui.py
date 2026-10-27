"""Owned hidden Tk controls only; no physical IME, DPI movement or Office UI."""
from pathlib import Path
import tempfile,unittest,sys
from unittest.mock import patch


@unittest.skipUnless(sys.platform=='win32','Native Windows hidden UI')
class ReviewHiddenUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import runtime
        runtime.configure();runtime.configure_tk_libraries()
        import tkinter as tk
        from app import App
        cls.tk=tk;cls.base=tempfile.TemporaryDirectory(prefix='review-ui-hidden-')
        cls.root=tk.Tk();cls.root.withdraw();cls.app=App(cls.root,sector_home=Path(cls.base.name)/'not-created')

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown_ai()
        from window_capture import destroy_test_window
        destroy_test_window(cls.root);cls.base.cleanup()

    def setUp(self):
        from workspace import Workspace
        self.temp=tempfile.TemporaryDirectory(prefix='review-ui-case-')
        context={'회사코드':'SYNTH01','회사명':'SYNTHETIC ONLY','시작일':'2026-01-01','기준일':'2026-12-31',
            '회계체계':'K-IFRS','감사기준':'SYNTHETIC ONLY','작성자':'SYNTHETIC ONLY','더미업무':True}
        self.ws=Workspace(Path(self.temp.name)/'SYNTHETIC_ONLY',create=context)
        self.ws.save_procedure({'id':'A04','title':'SYNTHETIC ONLY','preparer':'SYNTHETIC ONLY','conclusion':'unchanged'})
        self.app.open_workspace(self.ws.root);self.app.load_procedure('A04');self.ws=self.app.ws
        self.tops=[];original=self.tk.Toplevel
        def hidden(*args,**kwargs):
            win=original(*args,**kwargs);win.withdraw();self.tops.append(win);return win
        self.patch=patch.object(self.tk,'Toplevel',side_effect=hidden);self.patch.start()

    def tearDown(self):
        for win in reversed(self.tops):
            if win.winfo_exists():win.destroy()
        self.patch.stop();self.temp.cleanup()
        self.assertEqual(self.root.state(),'withdrawn')

    def test_new_native_control_character_is_rejected_with_no_history_change(self):
        before=self.ws.head
        with self.assertRaisesRegex(ValueError,'U\\+0001'):
            self.app.proc_text['conclusion'].insert('end','\x01')
        self.assertEqual(self.ws.head,before);self.assertEqual(self.app.proc_text['conclusion'].get('1.0','end').strip(),'unchanged')

    def test_legacy_read_escapes_display_without_editing_DB_and_unchanged_save_is_blocked(self):
        from common import AuditError
        legacy=dict(self.ws.procedures['A04']);legacy['conclusion']='SYNTHETIC ONLY old\x01record'
        # Simulate bytes previously accepted by v2.3, only in this synthetic fixture.
        with patch('workspace.validate_structure',side_effect=lambda value,label:value):
            self.ws._append('procedure',legacy)
        self.ws.refresh();before=self.ws.head
        with self.assertRaisesRegex(AuditError,'U\\+0001'):self.ws.save_procedure(legacy)
        self.app.refresh();self.app.load_procedure('A04')
        self.assertIn('⟦U+0001⟧',self.app.proc_text['conclusion'].get('1.0','end'))
        self.assertEqual(self.ws.procedures['A04']['conclusion'],legacy['conclusion'])
        self.assertEqual(self.ws.head,before)
        with self.assertRaisesRegex(AuditError,'기존 conclusion'):self.app.save_procedure()
        self.assertEqual(self.ws.head,before)
        self.app.proc_text['conclusion'].delete('1.0','end')
        self.app.proc_text['conclusion'].insert('1.0','SYNTHETIC ONLY manually corrected')
        self.app.save_procedure()
        self.assertTrue(any(event['kind']=='procedure' and event['data'].get('conclusion')==legacy['conclusion'] for event in self.ws.events))

    def test_program_facts_and_unverified_proposals_have_distinct_views_and_apply_caption(self):
        import runtime
        from test_ai_workpapers import mock_response
        self.ws.execute('원장·리드',runtime.configure()/'samples/통합/통합_01_원장정상.xlsx');self.app.refresh();self.app.load_procedure('A04')
        packet=self.ws.ai_packet('A04');response=mock_response(packet)
        did=self.ws.record_ai_draft(packet,response,'SYNTHETIC ONLY UI fixture requester')
        before=self.ws.head;self.app.open_ai_preview(did);win=self.app.ai_preview_win
        notebooks=[child for child in win.winfo_children() if isinstance(child,self.tk.ttk.Notebook)]
        titles=[notebooks[0].tab(tab,'text') for tab in notebooks[0].tabs()]
        self.assertIn('프로그램 근거 기록 · 적용 대상',titles)
        self.assertIn('미검증 AI 제안 · 자동 적용 안 함',titles)
        self.assertIn('계산표 포함·생략 범위',titles)
        self.assertEqual(win.apply_button.cget('text'),'프로그램 근거만 조서에 적용')
        self.assertEqual(self.ws.head,before);self.assertFalse(self.ws.ai_status('A04')['approved'])

    def test_module_limit_label_changes_with_selected_module(self):
        self.app.module.set('금융상품');self.assertIn('1,000행',self.app.scope_text.get())
        self.app.module.set('매출');self.assertIn('1,000행',self.app.scope_text.get())
        self.app.module.set('원장·리드');self.assertIn('1,048,575행',self.app.scope_text.get())
        self.app.module.set('실무자료·원장');self.assertIn('정형 Excel',self.app.scope_text.get())

    def test_compact_and_verbose_inventory_display_identical_counts_and_reason_labels(self):
        from ai_evidence_inventory.encoding import compact_manifest
        from desktop.ai.inventory import inventory_rows
        original={'schema':'calculation-inventory-1','runs':[{'id':'R','module':'SYNTHETIC ONLY'}],
            'tables':[{'run':0,'table':'통제','available':40,'included':2,'omitted':38,'hash':'a'*64,
                       'reasons':{'row_limit':37,'reference_or_character_budget':1}}]}
        self.assertEqual(inventory_rows({'calculation_inventory':original}),inventory_rows({'calculation_inventory':compact_manifest(original)}))
        row=inventory_rows({'calculation_inventory':original})[0]
        self.assertEqual((row['전체 결과행'],row['포함행'],row['생략행']),(40,2,38))
        self.assertIn('표별 행 한도 37행',row['생략 사유'])
