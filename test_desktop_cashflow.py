"""Independent tool contract, exact legacy policy and hidden native UI checks."""
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch
import hashlib
import sys
import tempfile
import threading
import time
import unittest
from desktop.tools.cashflow import engine,excel_io,samples


class CashFlowContractTests(unittest.TestCase):
    def test_core_copy_is_exact_except_package_relative_imports(self):
        root=Path(engine.__file__).parent
        expected={'engine.py':'12004a35824a0ee6106a41f6cb4c827d26824f5b3f297e4d884caabe670ec2b2',
                  'excel_io.py':'1584cb3869d3c4404965bbe23c4635fab68f126b8e253160cdb722e35ef26970',
                  'samples.py':'0df987ff40bb45ce9befa104d2e532110abe5a90617262ebadb473bdb70c43c2'}
        for name,digest in expected.items():
            raw=(root/name).read_bytes()
            if name!='engine.py':raw=raw.replace(b'from .engine import ',b'from engine import ')
            self.assertEqual(hashlib.sha256(raw).hexdigest(),digest,name)

    def test_ten_original_scenarios_keep_exact_normal_values_and_negative_issues(self):
        cases=samples.sample_cases();self.assertEqual(len(cases),10)
        result=engine.calculate(cases['정상_비현금_환율'])
        self.assertFalse(result.issues)
        self.assertEqual([result.lines[k][1] for k in ('CFO','CFI','CFF','FX','CASH_DELTA')],
                         list(map(Decimal,(170,-100,20,5,95))))
        for name,book in cases.items():
            if name!='정상_비현금_환율':self.assertTrue(engine.calculate(book).issues,name)

    def test_cancellation_and_source_output_preservation(self):
        stop=threading.Event();stop.set()
        with self.assertRaises(engine.Cancelled):engine.calculate(samples.make_book(),stop)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.xlsx';excel_io.save_input(samples.make_book(),path)
            raw=path.read_bytes();book=excel_io.read_input(path)
            result=engine.calculate(book)
            with self.assertRaises((ValueError,FileExistsError)):excel_io.export_result(result,path)
            self.assertEqual(path.read_bytes(),raw)
            output=Path(folder)/'result.xlsx';excel_io.export_result(result,output)
            self.assertTrue(output.is_file())
            with self.assertRaises(FileExistsError):excel_io.export_result(result,output)


@unittest.skipUnless(sys.platform=='win32','Native Windows standalone tool')
class CashFlowDesktopTests(unittest.TestCase):
    def setUp(self):
        from desktop.tools.cashflow.entry import CashFlowApp
        import tkinter as tk
        self.root=tk.Tk();self.root.withdraw()
        self.errors=[]
        self.root.report_callback_exception=lambda kind,value,trace:self.errors.append(value)
        self.app=CashFlowApp(self.root)
        self.root.update_idletasks()
    def tearDown(self):
        try:
            if self.root.winfo_exists():self.app.close()
        except Exception:pass
        self.assertFalse(self.errors)

    def test_initial_view_is_hidden_independent_and_has_no_completed_work(self):
        self.assertEqual(self.root.state(),'withdrawn')
        self.assertFalse(hasattr(self.app,'ws'))
        self.assertIsNone(self.app.source_path);self.assertIsNone(self.app.example)
        self.assertIsNone(self.app.result);self.assertFalse(self.app.running)
        self.assertEqual(len(self.app.notebook.tabs()),4)
        self.assertTrue(self.app.save_button.instate(['disabled']))
        self.assertTrue(all(var.get()=='—' for var in self.app.cards.values()))

    def test_blank_template_does_not_grant_confirmations(self):
        from desktop.tools.cashflow import inputs
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'blank.xlsx'
            with patch.object(inputs.filedialog,'asksaveasfilename',return_value=str(path)):
                self.app.save_template()
            book=excel_io.read_input(path)
            settings={r.values['key']:r.values['value'] for r in book.sheets['Settings']}
            self.assertTrue(all(settings[key] in ('',None) for key in engine.SETTINGS))
            self.assertFalse(any(r.values.get('confirmed')=='YES' for rows in book.sheets.values() for r in rows))

    def test_background_example_and_zoom_preserve_original_result_scope(self):
        self.app.load_example()
        deadline=time.monotonic()+5
        while self.app.result is None and time.monotonic()<deadline:
            self.root.update();time.sleep(.01)
        self.assertIsNotNone(self.app.result)
        self.assertFalse(self.app.result.issues)
        self.assertEqual(self.app.cards['CFO'].get(),'170')
        self.app.set_zoom('125%');self.root.update_idletasks()
        self.assertEqual(self.app.display.percent,125)
        self.assertEqual(self.app.result.lines['CFO'][1],Decimal(170))
        self.assertIn('더미',self.app.source_label.get())

    def test_cancelled_generation_drops_late_worker_results(self):
        token=self.app.generation
        self.app.invalidate()
        self.app.messages.put((token,'result',engine.calculate(samples.make_book())))
        self.root.after_cancel(self.app._poll_timer)
        self.app._poll_timer=None
        self.app.poll()
        self.assertIsNone(self.app.result)
        self.assertFalse(self.app.running)


if __name__=='__main__':unittest.main()
