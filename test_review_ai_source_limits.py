"""Minimum 10,002-row reproduction of the accepted large-ledger AI read path."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from openpyxl import Workbook
from common import AuditError
from ai_contract.source_read import read_source_tables


class AcceptedLedgerSourceLimitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.path=cls.root/'ledger.xlsx';book=Workbook(write_only=True)
        sheet=book.create_sheet('총계정원장');sheet.append(['전표ID','금액'])
        for i in range(10002):sheet.append([str(i),1])
        book.save(cls.path);book.close()
        cls.ws=SimpleNamespace(latest=lambda:{'원장·리드':{'source_id':'accepted-current-ledger'}})

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_accepted_current_ledger_exceeds_ten_thousand_without_truncation(self):
        tables,_=read_source_tables(self.ws,'accepted-current-ledger',self.path)
        self.assertEqual(len(tables['총계정원장']),10002)
        self.assertEqual(tables['총계정원장'][-1]['전표ID'],'10001')

    def test_another_module_or_source_does_not_acquire_ledger_limits(self):
        with self.assertRaises(AuditError):read_source_tables(self.ws,'sales-or-old-ledger-source',self.path)


if __name__=='__main__':unittest.main()
