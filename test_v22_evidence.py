"""The compact sales packet must retain an actual calculation row."""
from pathlib import Path
import tempfile
import unittest


class CompactSalesEvidenceTests(unittest.TestCase):
    def test_selected_sales_run_has_protected_calculation_and_raw_evidence(self):
        from demo_case import create_demo
        with tempfile.TemporaryDirectory() as folder:
            ws,_=create_demo(Path(folder)/'JS전자')
            packet=ws.ai_packet('A04',limits={'max_chars':12000,'max_references':40,
                'rows_per_table':3,'max_tables':8,'cell_chars':300})
            run=ws.latest()['매출']
            rows=packet['references']
            self.assertTrue(any(r['kind']=='calculation_row' and r.get('run_id')==run['id']
                and r.get('result_hash')==run['result_hash'] for r in rows))
            self.assertTrue(any(r['kind']=='raw_xlsx_row' and r.get('source_id')==run['source_id'] for r in rows))
            self.assertTrue(any(r['kind']=='ledger_reconciliation' for r in rows))
            self.assertFalse(ws.ai_drafts or ws.ai_approvals or ws.procedures)


if __name__=='__main__':unittest.main()
