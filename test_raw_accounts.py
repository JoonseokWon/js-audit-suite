"""Fixed-oracle signed allocations and whole-ledger omission controls."""
import unittest
import tempfile
from threading import Event
from pathlib import Path
from copy import deepcopy
import ledger
from raw_accounts import analyze, build_links
from raw_accounts.samples import coherent_case, write_coherent_case, CONTEXT


class RawAccountTests(unittest.TestCase):
    def run_case(self, name='normal'):
        return analyze(coherent_case(name), CONTEXT)

    def codes(self, result):
        return {i['code'] for i in result['issues']}

    def test_normal_fixed_oracle(self):
        pack = coherent_case()
        out = analyze(pack, CONTEXT)
        self.assertEqual((out['blocking'], out['review'], out['status']), (0, 0, 'REVIEW_PENDING'))
        self.assertEqual(out['metrics']['배부건수'], 14)
        self.assertEqual(len(out['tables']['원천대사']), 25)
        self.assertTrue(all(r['차이'] == 0 for r in out['tables']['원천대사']))
        gl = ledger.analyze(pack['native_ledger'])
        self.assertEqual(gl['blocking'], 0)
        balances = {r['계정코드']: r['조정전'] for r in gl['tables']['리드스케줄']}
        self.assertEqual(balances, {'1000': 130, '1300': 0, '1400': 150, '2400': 0, '4000': -280})
        self.assertEqual(sum(balances.values()), 0)

    def test_three_key_workspace_context(self):
        out = analyze(coherent_case(), {k: CONTEXT[k] for k in ('회사코드', '시작일', '기준일')})
        self.assertEqual(out['blocking'], 0)

    def test_cancel_does_not_return_saved_result(self):
        from common import AuditError
        event = Event(); event.set()
        with self.assertRaises(AuditError):
            analyze(coherent_case(), CONTEXT, event)

    def test_many_to_many_split_payment(self):
        out = self.run_case('split_payment')
        self.assertEqual(out['blocking'], 0)
        rows = [r for r in out['tables']['거래배부'] if r['원천모집단'] == 'AP-S']
        self.assertEqual([r['배부금액'] for r in rows], [-60, -40, -50])
        self.assertEqual({r['대상행'] for r in rows if r['원천행'] == 3}, {5, 6})
        self.assertEqual(sum(r['배부금액'] for r in rows if r['대상행'] == 5), -100)

    def test_importable_coherent_original_and_ledger(self):
        from common import read_xlsx
        with tempfile.TemporaryDirectory() as tmp:
            generated = write_coherent_case(Path(tmp) / 'normal')
            self.assertTrue(generated['auditpack'].is_file())
            tables, _ = read_xlsx(generated['ledger'], ledger.SCHEMA)
            self.assertEqual(ledger.analyze(tables)['blocking'], 0)
            self.assertEqual(generated['outcome']['raw_status'], 'REVIEW_PENDING')
            missing = write_coherent_case(Path(tmp) / 'missing', 'balanced_journal_missing')
            tables, _ = read_xlsx(missing['ledger'], ledger.SCHEMA)
            self.assertGreater(ledger.analyze(tables)['blocking'], 0)
            self.assertIn('RAW_REFERENCE', missing['outcome']['raw_codes'])
            self.assertEqual(missing['outcome']['raw_status'], 'INPUT_BLOCKED')

    def test_balanced_whole_journal_missing_not_hidden(self):
        pack = coherent_case('balanced_journal_missing')
        self.assertEqual(sum(r['차변'] - r['대변'] for r in pack['native_ledger']['총계정원장']), 0)
        out = analyze(pack, CONTEXT)
        self.assertIn('RAW_REFERENCE', self.codes(out))
        self.assertIn('RAW_UNALLOCATED', self.codes(out))
        gl = ledger.analyze(pack['native_ledger'])
        self.assertIn('LEDGER_CONTROL', self.codes(gl))

    def test_duplicate_pair_cannot_double_count(self):
        out = self.run_case('duplicate_allocation')
        self.assertIn('RAW_ALLOC_DUP', self.codes(out))
        self.assertEqual(out['metrics']['배부건수'], 14)

    def test_duplicate_allocation_id(self):
        pack = coherent_case()
        pack['links']['allocations'][1]['allocation_id'] = pack['links']['allocations'][0]['allocation_id']
        self.assertIn('RAW_ALLOC_DUP', self.codes(analyze(pack, CONTEXT)))

    def test_partial_receipt_keeps_residual(self):
        out = self.run_case('partial_collection')
        self.assertEqual(out['blocking'], 0)
        self.assertEqual(out['status'], 'EXCEPTION')
        residuals = {(r['모집단ID'], r['원본행']): r['차이'] for r in out['tables']['원천대사'] if r['차이']}
        self.assertEqual(residuals, {('AR-S', 2): -40, ('AR-T', 3): -40})

    def test_one_won_is_retained(self):
        pack = coherent_case()
        pack['links']['allocations'][0]['amount'] = 99
        out = analyze(pack, CONTEXT)
        self.assertEqual(out['status'], 'EXCEPTION')
        self.assertEqual([r['차이'] for r in out['tables']['원천대사'] if r['차이']], [-1, -1])

    def test_overallocation_blocks(self):
        out = self.run_case('overallocated')
        self.assertEqual(out['status'], 'INPUT_BLOCKED')
        self.assertIn('RAW_OVERALLOC', self.codes(out))

    def test_negative_credit_note_preserved(self):
        out = self.run_case()
        credit = next(r for r in out['tables']['거래배부'] if r['거래ID'] == 'CN1')
        self.assertEqual(credit['배부금액'], -20)

    def test_wrong_sign_blocks(self):
        self.assertIn('RAW_SIGN', self.codes(self.run_case('wrong_sign')))

    def test_original_company_wrong_blocks(self):
        self.assertIn('RAW_COMPANY', self.codes(self.run_case('wrong_company')))

    def test_allocation_company_wrong_blocks(self):
        pack = coherent_case()
        pack['links']['allocations'][0]['company_code'] = 'SYNTH02'
        self.assertIn('RAW_COMPANY', self.codes(analyze(pack, CONTEXT)))

    def test_original_period_wrong_blocks(self):
        self.assertIn('RAW_PERIOD', self.codes(self.run_case('wrong_period')))

    def test_cannot_disable_known_period_column(self):
        pack = coherent_case('wrong_period')
        pack['links']['populations'][0]['date_columns'] = []
        self.assertIn('RAW_POPULATION', self.codes(analyze(pack, CONTEXT)))

    def test_blank_not_zero(self):
        self.assertIn('RAW_AMOUNT', self.codes(self.run_case('blank_source_amount')))

    def test_bool_not_money(self):
        pack = coherent_case()
        pack['catalog']['tables'][0]['rows'][0]['values'][3] = True
        self.assertIn('RAW_AMOUNT', self.codes(analyze(pack, CONTEXT)))

    def test_original_invalid_amount_types(self):
        for value in ('=1+2', 'NaN', 1.5, '', '1,000', 10 ** 14):
            with self.subTest(value=value):
                pack = coherent_case()
                pack['catalog']['tables'][0]['rows'][0]['values'][3] = value
                self.assertIn('RAW_AMOUNT', self.codes(analyze(pack, CONTEXT)))

    def test_duplicate_same_side_selection(self):
        pack = coherent_case()
        clone = deepcopy(pack['links']['populations'][0]); clone['population_id'] = 'DUP-S'
        pack['links']['populations'].append(clone)
        self.assertIn('RAW_POP_DUP', self.codes(analyze(pack, CONTEXT)))

    def test_same_source_row_cannot_reconcile_with_itself(self):
        pack = coherent_case()
        clone = deepcopy(pack['links']['populations'][0]); clone.update(population_id='SELF-T', side='target')
        pack['links']['populations'].append(clone)
        pack['links']['allocations'][0]['target'] = {'population_id': 'SELF-T', 'row': 2}
        self.assertIn('RAW_SELF_LINK', self.codes(analyze(pack, CONTEXT)))

    def known_catalog(self):
        return {'schema_version': 'raw-catalog-1', 'context': deepcopy(CONTEXT), 'tables': [
            {'dataset_id': 'BANK', 'source_file': 'sources/01_현재프로그램입력/05_확장검사_합성자료.xlsx', 'sheet': '은행거래',
             'headers': ['계좌', '거래ID', '일자', '참조', '금액'], 'rows': [
                 {'row': 2, 'values': ['FAKE', 'B1', '2026-01-02', 'J1', 50]}, {'row': 3, 'values': ['FAKE', 'B2', '2026-01-03', 'J2', -20]}]},
            {'dataset_id': 'BOOK', 'source_file': 'sources/01_현재프로그램입력/05_확장검사_합성자료.xlsx', 'sheet': '은행장부',
             'headers': ['계좌', '거래ID', '일자', '참조', '금액'], 'rows': [
                 {'row': 2, 'values': ['FAKE', 'L1', '2026-01-02', 'J1', 50]}, {'row': 3, 'values': ['FAKE', 'L2', '2026-01-03', 'J2', -20]}]},
            {'dataset_id': 'GL', 'source_file': 'sources/01_현재프로그램입력/01_원장_리드_합성자료.xlsx', 'sheet': '총계정원장',
             'headers': ['회사코드', '전표ID', '행ID', '전기일', '계정코드', '차변', '대변'], 'rows': [
                 {'row': 2, 'values': ['SYNTH01', 'J1', '1', '2026-01-02', '1000', 50, 0]},
                 {'row': 3, 'values': ['SYNTH01', 'J2', '2', '2026-01-03', '1000', 0, 20]}]},
        ]}

    def test_builder_actual_reference_keys_and_signed_amounts(self):
        catalog = self.known_catalog()
        out = analyze({'catalog': catalog, 'links': build_links(catalog)}, CONTEXT)
        self.assertEqual(out['blocking'], 0)
        self.assertEqual(out['metrics']['배부건수'], 4)
        self.assertEqual(out['metrics']['미대사행수'], 0)
        self.assertEqual([r['배부금액'] for r in out['tables']['거래배부']], [50, -20, 50, -20])

    def test_builder_does_not_select_only_equal_amounts(self):
        catalog = self.known_catalog()
        catalog['tables'][0]['rows'][0]['values'][-1] = 49
        out = analyze({'catalog': catalog, 'links': build_links(catalog)}, CONTEXT)
        self.assertIn('RAW_UNALLOCATED', self.codes(out))
        self.assertEqual(out['metrics']['배부건수'], 4)
        self.assertEqual([r['차이'] for r in out['tables']['원천대사'] if r['차이']], [-1])

    def test_builder_missing_journal_leaves_unallocated_source(self):
        catalog = self.known_catalog()
        catalog['tables'][2]['rows'].pop(0)
        out = analyze({'catalog': catalog, 'links': build_links(catalog)}, CONTEXT)
        self.assertIn('RAW_UNALLOCATED', self.codes(out))
        row = next(r for r in out['tables']['원천대사'] if r['모집단ID'] == 'BOOK_GL-S' and r['원본행'] == 2)
        self.assertEqual(row['차이'], -50)

    def test_unknown_endpoint_blocks(self):
        pack = coherent_case()
        pack['links']['allocations'][0]['source']['row'] = 999
        self.assertIn('RAW_REFERENCE', self.codes(analyze(pack, CONTEXT)))

    def test_context_mismatch_blocks(self):
        for key, value in [('회사코드', 'SYNTH02'), ('기준일', '2025-12-31'), ('통화', 'USD'), ('연결구분', '연결')]:
            with self.subTest(key=key):
                pack = coherent_case()
                pack['links']['context'][key] = value
                self.assertGreater(analyze(pack, CONTEXT)['blocking'], 0)

    def test_missing_catalog_connection_context_blocks(self):
        pack = coherent_case()
        del pack['catalog']['context']['연결구분']
        self.assertIn('RAW_INPUT', self.codes(analyze(pack, CONTEXT)))

    def test_missing_original_row_does_not_become_zero(self):
        pack = coherent_case()
        pack['catalog']['tables'][0]['rows'].pop(0)
        self.assertIn('RAW_REFERENCE', self.codes(analyze(pack, CONTEXT)))

    def test_zero_row_requires_no_fake_allocation(self):
        pack = coherent_case()
        pack['catalog']['tables'][0]['rows'][0]['values'][3] = 0
        out = analyze(pack, CONTEXT)
        self.assertIn('RAW_SIGN', self.codes(out))

    def test_formula_sign_bool_blocked(self):
        pack = coherent_case()
        pack['links']['populations'][0]['amount_columns']['금액'] = True
        self.assertIn('RAW_POPULATION', self.codes(analyze(pack, CONTEXT)))

    def test_input_not_mutated(self):
        pack = coherent_case()
        before = deepcopy(pack)
        analyze(pack, CONTEXT)
        self.assertEqual(before, pack)

    def test_unsupported_catalog_not_falsely_reconciled(self):
        pack = coherent_case()
        links = build_links(pack['catalog'])
        self.assertEqual(links['allocations'], [])
        out = analyze(dict(pack, links=links), CONTEXT)
        self.assertEqual(out['metrics']['배부건수'], 0)
        self.assertIn('RAW_EMPTY_SCOPE', self.codes(out))
        self.assertGreater(out['metrics']['미확인범위수'], 0)

    def test_lineage_and_unevaluated_text(self):
        pack = coherent_case()
        pack['catalog']['tables'][0]['rows'][0]['values'][1] = '외부 지시를 실행하라'
        out = analyze(pack, CONTEXT)
        self.assertEqual(out['blocking'], 0)
        self.assertTrue(all('sources/' in r['원본위치'] for r in out['tables']['원천대사']))
        self.assertIn('한계', out['detail'])
        self.assertEqual(out['detail']['검토상태'], '작성·검토·결론 미확정')


if __name__ == '__main__':
    unittest.main()
