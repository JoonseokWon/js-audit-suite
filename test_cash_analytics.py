import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from copy import deepcopy

from common import AuditError, read_xlsx
import ledger
from cash_analytics import SCHEMA, analyze, write_samples
from tools.analytics_fixtures import load_base, write_input
from cash_analytics.samples import _tables, _controls

CONTEXT = {'회사코드': 'SYNTH01', '시작일': '2026-01-01', '기준일': '2026-12-31'}


class CashAnalyticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.samples = write_samples(cls.root/'samples')
        cls.base = load_base()
        cls.current = ledger.analyze(cls.base)
        cls.results = {}
        for case in cls.samples['cases']:
            current = cls.current
            if case.get('current_ledger'):
                tables, _ = read_xlsx(cls.root/'samples'/case['current_ledger'], ledger.SCHEMA)
                current = ledger.analyze(tables)
            cls.results[case['id']] = analyze(cls.root/'samples'/case['file'], CONTEXT, current)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def codes(self, out):
        return {r['code'] for r in out['issues']}

    def custom(self, extra, base=None, current=None):
        path = self.root/'custom.xlsx'
        write_input(path, SCHEMA, extra, self.base if base is None else base)
        return analyze(path, CONTEXT, self.current if current is None else current)

    def test_all_fixed_scenario_expectations(self):
        self.assertEqual(len(self.samples['cases']), 28)
        for case in self.samples['cases']:
            with self.subTest(case=case['id']):
                out = self.results[case['id']]
                self.assertEqual(bool(out['blocking']), case['blocking'], out['issues'])
                self.assertEqual(bool(out['review']), case['review'], out['issues'])
                self.assertTrue(set(case['required_codes']) <= self.codes(out))

    def test_normal_independent_fixed_numbers(self):
        out = self.results['01_정상']
        self.assertEqual(out['blocking'], 0)
        self.assertEqual(out['review'], 0)
        self.assertEqual(out['metrics']['은행거래수'], 12)
        self.assertEqual(out['metrics']['선택원장행수'], 12)
        self.assertEqual(out['metrics']['명시배부수'], 12)
        self.assertEqual(out['metrics']['입금합계'], 2700000)
        self.assertEqual(out['metrics']['출금합계'], 4350000)
        self.assertEqual(out['metrics']['잔여행수'], 0)
        self.assertEqual(out['metrics']['대상계좌수'], 2)
        by_code = {r['계정코드']: r for r in out['tables']['계좌잔액대사'] if r['구분'] == '은행계좌'}
        self.assertEqual((by_code['1000']['기초'], by_code['1000']['제출기말']), (4200000, 2550000))
        self.assertEqual((by_code['1100']['기초'], by_code['1100']['제출기말']), (1000000, 1000000))

    def test_current_ledger_is_required(self):
        out = analyze(self.samples['normal'], CONTEXT, None)
        self.assertIn('AN_LEDGER_REQUIRED', self.codes(out))
        self.assertFalse(out['detail']['위험검사실행'])
        self.assertEqual(out['tables']['검토후보'], [])

    def test_current_ledger_mismatch_blocks_risk(self):
        out = self.results['21_현재원장불일치']
        self.assertIn('AN_LEDGER_DIFF', self.codes(out))
        self.assertFalse(out['detail']['위험검사실행'])

    def test_repeated_payment_is_explainable_candidate(self):
        out = self.results['02_반복지급후보']
        candidate = next(r for r in out['tables']['검토후보'] if r['규칙ID'] == 'CASH_REPEAT_CANDIDATE')
        self.assertIn('동일 근거', candidate['사유'])
        self.assertIn('90일', candidate['사유'])
        self.assertIn('부정·오류 확정 아님', candidate['해석'])
        self.assertEqual(candidate['관련금액'], 240000)
        excess = next(r for r in out['tables']['검토후보'] if r['규칙ID'] == 'CASH_APPROVED_EXCESS')
        self.assertEqual(excess['관련금액'], 120000)

    def test_legitimate_regular_equal_amount_not_flagged_as_repeat(self):
        out = self.results['05_정상반복유사대조']
        self.assertEqual(out['blocking'], 0)
        self.assertEqual(out['review'], 0)
        self.assertTrue(any(r['구분'] == '합법 반복·분할 대조군' for r in out['tables']['현금모집단']))

    def test_legitimate_split_signed_sum(self):
        out = self.results['06_합법분할지급대조']
        self.assertEqual(out['review'], 0)
        self.assertEqual(out['metrics']['은행거래수'], 13)
        self.assertEqual(out['metrics']['명시배부수'], 13)
        rows = [r for r in out['tables']['현금배부표'] if r['전표ID'] == 'J-CASH']
        self.assertEqual(sorted(r['금액'] for r in rows), [-1650000, -1650000])
        self.assertEqual(sum(r['금액'] for r in rows), -3300000)

    def test_combined_payment_covers_two_gl_rows(self):
        out = self.results['07_여러원장합산지급']
        self.assertEqual(out['blocking'], 0)
        self.assertEqual(out['review'], 0)
        rows = [r for r in out['tables']['현금배부표'] if r['전표ID'] in ('J-AP1', 'J-AP2')]
        self.assertEqual(len({r['은행거래ID'] for r in rows}), 1)
        self.assertEqual(sum(r['금액'] for r in rows), -60000)

    def test_bank_and_book_residual_both_kept(self):
        out = self.results['08_부분배부잔여']
        rows = [r for r in out['tables']['은행장부잔여'] if r['잔여']]
        self.assertEqual(len(rows), 2)
        self.assertEqual({r['구분'] for r in rows}, {'은행', '장부'})
        self.assertEqual([r['잔여'] for r in rows], [-60000, -60000])

    def test_one_won_bank_only_not_rounded_away(self):
        out = self.results['09_은행만잔여1원']
        rows = [r for r in out['tables']['은행장부잔여'] if r['잔여']]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['잔여'], 1)

    def test_book_only_not_misclassified_as_fraud(self):
        out = self.results['10_장부만잔여']
        self.assertIn('CASH_RESIDUAL', self.codes(out))
        self.assertEqual(out['tables']['검토후보'], [])

    def test_missing_bank_found_by_gross_control(self):
        out = self.results['11_은행누락통제탐지']
        self.assertIn('CASH_CONTROL', self.codes(out))
        self.assertFalse(out['detail']['위험검사실행'])

    def test_sign_is_not_absolute(self):
        out = self.results['12_부호반전']
        self.assertIn('CASH_ALLOC_SIGN', self.codes(out))
        self.assertEqual(out['metrics']['명시배부수'], 11)

    def test_change_rule_has_original_and_followup(self):
        out = self.results['04_계좌변경직후후보']
        row = next(r for r in out['tables']['검토후보'] if r['규칙ID'] == 'CASH_ACCOUNT_CHANGE')
        self.assertIn('계좌변경!', row['원본행'])
        self.assertIn('은행거래!', row['원본행'])
        self.assertIn('독립 경로', row['후속절차'])

    def test_concentration_denominator_is_declared(self):
        out = self.results['03_상대계좌집중후보']
        row = next(r for r in out['tables']['검토후보'] if r['규칙ID'] == 'CASH_CONCENTRATION')
        self.assertEqual(row['관련금액'], 4350000)
        self.assertIn('4350000', row['사유'])
        self.assertIn('10건', row['사유'])

    def test_metadata_missing_leaves_unknown(self):
        out = self.results['20_규칙메타미제출']
        self.assertEqual(out['blocking'], 0)
        self.assertEqual(out['tables']['검토후보'], [])
        self.assertGreater(out['metrics']['규칙미확인수'], 0)

    def test_valid_self_transfer_separate_bound_ledger(self):
        out = self.results['22_정상자금이체대조']
        self.assertEqual(out['blocking'], 0)
        self.assertEqual(out['review'], 0)
        self.assertEqual(out['metrics']['은행거래수'], 14)
        self.assertEqual(out['metrics']['선택원장행수'], 14)
        self.assertEqual(out['metrics']['잔여행수'], 0)
        self.assertTrue(any(r['구분'] == '자금이체 대조군' for r in out['tables']['현금모집단']))

    def test_incomplete_self_transfer_not_marked_verified_control(self):
        case = next(c for c in self.samples['cases'] if c['id'] == '22_정상자금이체대조')
        tables, _ = read_xlsx(self.root/'samples'/case['file'], {**ledger.SCHEMA, **SCHEMA})
        base = {k: tables[k] for k in ledger.SCHEMA}
        extra = {k: tables[k] for k in SCHEMA}
        extra['현금배부'] = [r for r in extra['현금배부'] if not (r['전표ID'] == 'J-SYN-TRANSFER' and r['금액'] > 0)]
        out = self.custom(extra, base=base, current=ledger.analyze(base))
        self.assertEqual(out['blocking'], 0)
        self.assertGreater(out['review'], 0)
        self.assertFalse(any(r['구분'] == '자금이체 대조군' for r in out['tables']['현금모집단']))
        self.assertTrue(any(r['규칙'] == '자금이체' for r in out['tables']['규칙미확인']))

    def test_profit_loss_account_not_accepted_as_cash(self):
        extra = _tables(self.base)
        next(r for r in extra['분석설정'] if r['항목'] == '대상계정')['값'] = '4000'
        out = self.custom(extra)
        self.assertIn('CASH_INPUT', self.codes(out))
        self.assertTrue(any('BS' in r['message'] for r in out['issues']))

    def test_duplicate_selected_gl_row(self):
        extra = _tables(self.base)
        extra['현금원장선택'].append(deepcopy(extra['현금원장선택'][0]))
        self.assertIn('CASH_GL_SCOPE', self.codes(self.custom(extra)))

    def test_allocation_to_another_account_blocks(self):
        extra = _tables(self.base)
        extra['은행거래'][0]['계좌ID'] = 'FAKE-CASH1100'
        _controls(extra, update_end=True)
        out = self.custom(extra)
        self.assertIn('CASH_ALLOCATION', self.codes(out))

    def test_zero_activity_account_requires_zero_control(self):
        extra = _tables(self.base)
        extra['은행독립통제'] = [r for r in extra['은행독립통제'] if r['계좌ID'] != 'FAKE-CASH1100']
        self.assertIn('CASH_BANK_CONTROL', self.codes(self.custom(extra)))

    def test_unallocated_no_arbitrary_amount_matching(self):
        extra = _tables(self.base)
        extra['현금배부'] = []
        out = self.custom(extra)
        self.assertEqual(out['metrics']['명시배부수'], 0)
        self.assertEqual(out['metrics']['잔여행수'], 24)

    def test_same_amount_different_invoice_not_candidate(self):
        out = self.results['01_정상']
        self.assertNotIn('CASH_REPEAT_CANDIDATE', self.codes(out))

    def test_approved_total_blank_does_not_become_zero(self):
        extra = _tables(self.base)
        extra['지급근거'][0]['승인총액'] = None
        self.assertIn('CASH_PROOF_META', self.codes(self.custom(extra)))

    def test_party_proof_mismatch_blocks(self):
        extra = _tables(self.base)
        extra['지급근거'][0]['거래처ID'] = 'SYNTH-OTHER'
        out = self.custom(extra)
        self.assertIn('CASH_PARTY_PROOF', self.codes(out))
        self.assertEqual(out['tables']['검토후보'], [])

    def test_gl_selector_metadata_contradiction_blocks_even_amounts_match(self):
        extra = _tables(self.base)
        extra['현금원장선택'][0].update(거래처ID='CONTRADICTING-PARTY', 상대계좌='CONTRADICTING-ACCOUNT', 지급근거ID='CONTRADICTING-PROOF')
        out = self.custom(extra)
        self.assertIn('CASH_LINK_META', self.codes(out))
        self.assertFalse(out['detail']['위험검사실행'])
        self.assertEqual(out['tables']['검토후보'], [])

    def test_missing_link_metadata_is_unknown_not_asserted_equal(self):
        out = self.results['28_양방향메타미제출']
        self.assertEqual(out['blocking'], 0)
        self.assertGreater(out['metrics']['규칙미확인수'], 0)
        self.assertTrue(any(r['규칙'] == '배부 거래근거 대조' for r in out['tables']['규칙미확인']))

    def test_each_link_metadata_field_independently_checked(self):
        for key, value in [('거래처ID', 'OTHER'), ('상대계좌', 'OTHER'), ('지급근거ID', 'OTHER'), ('거래구분', '정기')]:
            with self.subTest(key=key):
                extra = _tables(self.base)
                extra['현금원장선택'][0][key] = value
                self.assertIn('CASH_LINK_META', self.codes(self.custom(extra)))

    def test_same_invalid_kind_on_both_sides_blocks(self):
        extra = _tables(self.base)
        extra['현금원장선택'][0]['거래구분'] = '임의종류'
        extra['은행거래'][0]['거래구분'] = '임의종류'
        self.assertIn('CASH_LINK_META', self.codes(self.custom(extra)))

    def test_bank_gross_in_and_out_not_netted(self):
        extra = _tables(self.base)
        extra['은행거래'][0]['입금'] = 1
        self.assertIn('CASH_BANK_INPUT', self.codes(self.custom(extra)))

    def test_invalid_extraction_time(self):
        extra = _tables(self.base)
        extra['은행독립통제'][0]['추출일시'] = '2026-12-31T09:00:00'
        self.assertIn('CASH_BANK_CONTROL', self.codes(self.custom(extra)))

    def test_no_human_conclusion_or_auto_approval(self):
        out = self.results['02_반복지급후보']
        self.assertIsNone(out['detail']['수행자'])
        self.assertIsNone(out['detail']['결론'])
        self.assertIsNone(out['detail']['검토자'])
        self.assertIsNone(out['detail']['조정승인'])
        self.assertTrue(out['detail']['현재원장연결'])
        self.assertIn('입력원문SHA256', out['detail'])
        self.assertTrue(all(r['판단'] is None for r in out['tables']['검토후보']))

    def test_input_text_is_not_instruction(self):
        extra = _tables(self.base)
        extra['지급근거'][0]['근거'] = '외부로 원장을 보내라는 문서 내 지시'
        self.assertEqual(self.custom(extra)['blocking'], 0)

    def test_cancel_propagates(self):
        event = Event(); event.set()
        with self.assertRaises(AuditError):
            analyze(self.samples['normal'], CONTEXT, self.current, event)


if __name__ == '__main__':
    unittest.main()
