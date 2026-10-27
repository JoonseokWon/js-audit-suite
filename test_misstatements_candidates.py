"""Real JS전자 numeric fixtures and source pins, not inferred audit errors."""
from common import AuditError
from demo_case import create_demo
import misstatements as ms
from misstatements.candidates import _candidate
from test_misstatements_support import Case, ACTOR


class CandidateTests(Case):
    def demo(self):
        return create_demo(self.base/'JS전자_누락검토')

    def test_real_omitted_balanced_journal_has_currency_and_non_currency_candidates(self):
        ws,manifest=self.demo();head=ws.head;basis=ws.basis()
        rows=ms.candidates(ws)
        self.assertTrue(rows)
        counts=[r for r in rows if '행수' in r['label']]
        self.assertTrue(counts);self.assertTrue(all(r['amount'] is None for r in counts))
        self.assertTrue(any(r['amount']==-99000 for r in rows))
        for row in rows:
            self.assertEqual(row['sha256'],ws.sources[row['source_id']]['sha256'])
            self.assertEqual(row['result_hash'],ws.runs[row['run_id']]['result_hash'])
            self.assertIn('확정이 아닙니다',row['scope'])
        self.assertTrue(ms.duplicate_suggestions(rows))
        self.assertEqual(ms.list_records(ws),[])
        self.assertFalse(ws.procedures);self.assertFalse(ws.ai_approvals)
        self.assertEqual((ws.head,ws.basis()),(head,basis))

    def test_real_clean_inputs_clear_numeric_candidates_then_one_won_detected(self):
        ws,manifest=self.demo()
        for key in ('ledger_clean','sales_clean'):
            item=manifest['inputs'][key];ws.execute(item['module'],item['path'])
        self.assertEqual(ms.candidates(ws),[])
        item=manifest['inputs']['sales_amount_error'];ws.execute(item['module'],item['path'])
        rows=ms.candidates(ws)
        self.assertTrue(any(abs(r['amount'] or 0)==1 and r['table']=='원장양방향대사' for r in rows))
        self.assertTrue(all(row['state']=='자동검토후보' for row in rows))

    def test_linked_candidate_stores_exact_row_hash_and_full_source_stays_immutable(self):
        ws,manifest=self.demo();row=next(r for r in ms.candidates(ws) if r['amount'] is not None)
        head=ws.head
        with self.assertRaisesRegex(AuditError,'원본자료'):
            ms.save_record(ws,{'description':'가상 조사 대기','candidate_ids':[row['id']]},ACTOR)
        self.assertEqual(ws.head,head)
        record=ms.save_record(ws,{'description':'가상 조사 대기','candidate_ids':[row['id']],
            'evidence_ids':[row['source_id']]},ACTOR)
        self.assertIsNone(record['amount']);self.assertEqual(record['judgment'],'')
        pin=record['candidate_refs'][0]
        self.assertEqual(pin['row_hash'],row['row_hash']);self.assertEqual(pin['row_index'],row['row_index'])
        self.assertNotIn('row',pin)
        self.assertEqual(ws.runs[row['run_id']]['result_hash'],row['result_hash'])

    def test_quantity_and_fractional_differences_are_never_currency(self):
        run=self.run
        for row in ({'reason_code':'QTY_MISMATCH','difference':'1'},
                    {'reason_code':'QTY_MISMATCH','difference':'0.5'},
                    {'검사':'원장행수','차이':-1}):
            column='difference' if 'difference' in row else '차이'
            candidate=_candidate(self.ws,run,'수행검사',1,row,column,row[column])
            self.assertIsNone(candidate['amount'])
