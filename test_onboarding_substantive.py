"""Independent amounts and failure gates; synthetic setup, never actual approval."""
from copy import deepcopy
import threading
import unittest
from common import AuditError, digest
from onboarding.demo import CONTEXT, ledger_result
from onboarding.substantive import (APPROVAL_FIELDS, FIELD_LABELS, TABLE_FIELDS,
    analyze, sample, negative_cases, prepare_approval)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.context = dict(CONTEXT); self.ledger = ledger_result(self.context)

    def approve(self, area, payload):
        prepare_approval(area, payload, self.ledger)
        payload['approval'] = {'actor': 'SYNTHETIC ONLY test fixture',
            'reason': 'Synthetic input mapping only; no audit performance or final approval',
            'input_hash': digest({k: payload.get(k) for k in APPROVAL_FIELDS[area]})}
        return payload

    def run_case(self, area, payload=None, ledger=None):
        payload = self.approve(area, payload or sample(area, self.context))
        return analyze(area, payload, self.context, self.ledger if ledger is None else ledger)

    def codes(self, result): return {r['code'] for r in result['issues']}


class SharedContractTests(Fixture):
    def test_samples_have_no_approval_and_normal_scoped_reconciliation_passes(self):
        for area in APPROVAL_FIELDS:
            with self.subTest(area=area):
                payload = sample(area, self.context)
                self.assertEqual(payload['approval'], {})
                result = self.run_case(area, payload)
                self.assertEqual(result['blocking'], 0, result['issues'])
                self.assertEqual(result['module'], area)
                self.assertTrue(result['detail']['현재원장연결'])
                self.assertFalse(result['detail']['실제감사수행완료'])
                self.assertFalse(result['detail']['실제승인생성'])
                self.assertTrue(result['detail']['사람판단필수'])

    def test_unconfirmed_inputs_are_blocked_even_when_numbers_match(self):
        for area in APPROVAL_FIELDS:
            result = analyze(area, sample(area, self.context), self.context, self.ledger)
            self.assertIn('ONB_APPROVAL_REQUIRED', self.codes(result))
            self.assertFalse(result['detail']['현재원장연결'])

    def test_policy_or_population_change_invalidates_previous_confirmation(self):
        for area in APPROVAL_FIELDS:
            payload = self.approve(area, sample(area, self.context))
            payload['policy']['policy_version'] += '-changed'
            result = analyze(area, payload, self.context, self.ledger)
            self.assertIn('ONB_APPROVAL_REQUIRED', self.codes(result))

    def test_ledger_content_changes_are_not_silently_rebased(self):
        for area in APPROVAL_FIELDS:
            payload = self.approve(area, sample(area, self.context))
            changed = deepcopy(self.ledger)
            changed['tables']['입력_총계정원장'][0]['적요'] += ' changed'
            before = payload['policy']['ledger_basis_hash']
            prepare_approval(area, payload, changed)
            self.assertEqual(before, payload['policy']['ledger_basis_hash'])
            result = analyze(area, payload, self.context, changed)
            self.assertIn('SUB_LEDGER_BASIS_CHANGED', self.codes(result))
            self.assertFalse(result['detail']['현재원장연결'])

    def test_prepare_approval_updates_only_population_metadata(self):
        area = '유형자산증감'; payload = sample(area, self.context)
        payload['asset_movements'][0]['cost_delta'] = 79999
        before = deepcopy(payload)
        prepare_approval(area, payload)
        before['policy']['population_hash'] = payload['policy']['population_hash']
        self.assertEqual(before, payload)
        self.assertEqual(payload['approval'], {})

    def test_stale_population_hash_is_detected_even_with_a_new_input_confirmation(self):
        area='유형자산증감'; payload=sample(area,self.context)
        payload['asset_movements'][0]['source_ref']+=' changed'
        payload['approval']={'actor':'SYNTHETIC ONLY','reason':'synthetic test',
            'input_hash':digest({k:payload[k] for k in APPROVAL_FIELDS[area]})}
        result=analyze(area,payload,self.context,self.ledger)
        self.assertIn('SUB_POPULATION_CHANGED',self.codes(result))

    def test_no_ledger_context_mismatch_and_cancellation_are_rejected(self):
        area = '감사표본선정'; payload = self.approve(area, sample(area, self.context))
        result = analyze(area, payload, self.context, None)
        self.assertIn('ONB_LEDGER_REQUIRED', self.codes(result))
        self.assertFalse(result['detail']['현재원장연결'])
        wrong = dict(self.context, 회사코드='OTHER')
        with self.assertRaises(AuditError): analyze(area, payload, wrong, self.ledger)
        event = threading.Event(); event.set()
        with self.assertRaises(AuditError): analyze(area, payload, self.context, self.ledger, event)

    def test_every_empty_table_has_unique_korean_headers(self):
        for area, tables in TABLE_FIELDS.items():
            payload = sample(area, self.context)
            for table, fields in tables.items():
                labels = [FIELD_LABELS.get(f, f) for f in fields]
                self.assertEqual(len(labels), len(set(labels)), (area, table))
                self.assertTrue(all(field in FIELD_LABELS for field in fields))
                for row in payload[table]: self.assertTrue(set(row) <= set(fields))


class AssetMovementTests(Fixture):
    AREA = '유형자산증감'
    def test_gross_cost_accum_cip_and_disposal_independent_values(self):
        result = self.run_case(self.AREA)
        self.assertEqual(result['metrics'], {'기말원가':110000,'기말누계':15000,'처분손익':10000})
        pairs = result['tables']['대체취소쌍검사']
        self.assertEqual(len(pairs), 2)
        self.assertTrue(all(r['원본건수']==2 and r['원가합계']==0 for r in pairs))
        disposal = next(r for r in result['tables']['취득처분변동모집단'] if r['유형']=='disposal')
        self.assertEqual(disposal['처분대가']-(-disposal['원가변동']+disposal['누계변동']), 10000)

    def test_missing_duplicate_transfer_cancellation_and_gain_are_detected(self):
        for name, payload in negative_cases(self.AREA, self.context).items():
            with self.subTest(name=name):
                result = self.run_case(self.AREA, payload)
                self.assertGreater(result['blocking'], 0)
                self.assertFalse(result['detail']['현재원장연결'])

    def test_negative_register_amount_or_out_of_period_movement(self):
        payload = sample(self.AREA, self.context); payload['assets'][0]['opening_cost'] = -1
        with self.assertRaises(AuditError): self.run_case(self.AREA, payload)
        payload = sample(self.AREA, self.context); payload['asset_movements'][0]['date']='2025-12-31'
        self.assertIn('ASSET_PERIOD', self.codes(self.run_case(self.AREA, payload)))

    def test_cip_cannot_disappear_by_removing_its_register_and_relabeling_transfer(self):
        payload=sample(self.AREA,self.context)
        payload['assets']=[r for r in payload['assets'] if r['asset_id']!='CIP1']
        payload['asset_movements']=[r for r in payload['asset_movements'] if r['asset_id']!='CIP1']
        transfer=next(r for r in payload['asset_movements'] if r['kind']=='transfer_in')
        transfer['kind']='acquisition';transfer['pair_id']=''
        result=self.run_case(self.AREA,payload)
        self.assertIn('ASSET_DECLARED_SCOPE',self.codes(result))
        self.assertFalse(result['detail']['현재원장연결'])
        self.assertEqual(result['detail']['대상계정'],['1500','1590','1600'])
        self.assertIn('선택 계정',result['detail']['범위'])


class SamplingTests(Fixture):
    AREA = '감사표본선정'
    def test_reproducibility_is_independent_of_population_order(self):
        first = sample(self.AREA, self.context); second = deepcopy(first)
        second['population'].reverse()
        a = self.run_case(self.AREA, first); b = self.run_case(self.AREA, second)
        self.assertEqual(a['tables']['선정후보'], b['tables']['선정후보'])
        self.assertEqual(a['metrics']['모집단건수'], 12)
        self.assertEqual(a['metrics']['선정건수'], 11)

    def test_threshold_boundary_negative_stratum_and_specific_overlap(self):
        result = self.run_case(self.AREA)
        rows = result['tables']['선정후보']; by_id = {r['모집단행ID']:r for r in rows}
        self.assertEqual(by_id['POP-J09-L1']['선정층'], '고액전수')  # exactly 50,000
        negatives = [r for r in rows if r['금액'] < 0]
        self.assertEqual(len(negatives), 7)
        self.assertTrue(all(r['선정여부'] and r['선정층']=='음수별도전수' for r in negatives))
        self.assertFalse(result['detail']['MUS구현'])
        self.assertFalse(result['detail']['오류추정투영'])

    def test_duplicate_missing_sign_and_oversize_are_blocked(self):
        for name, payload in negative_cases(self.AREA, self.context).items():
            with self.subTest(name=name): self.assertGreater(self.run_case(self.AREA, payload)['blocking'], 0)

    def test_errors_are_aggregated_without_netting_away_absolute_findings(self):
        payload = sample(self.AREA, self.context)
        payload['errors'] = [dict(record_id='E1',source_ref='SYNTHETIC ONLY/E1',gl_refs=['J01/L1'],
            population_id='POP-J01-L1',book_amount=100000,audited_amount=101000,reviewer='SYNTHETIC ONLY',reason='가상 차이'),
            dict(record_id='E2',source_ref='SYNTHETIC ONLY/E2',gl_refs=['J16/L1'],population_id='POP-J16-L1',
                 book_amount=25000,audited_amount=24000,reviewer='SYNTHETIC ONLY',reason='가상 반대 차이')]
        result = self.run_case(self.AREA, payload)
        self.assertEqual(result['metrics']['발견차이순액'], 0)
        self.assertEqual(result['metrics']['발견차이절대합'], 2000)
        self.assertIn('SAMPLE_FINDING',self.codes(result))
        self.assertFalse(result['detail']['실제감사수행완료'])

    def test_error_and_specific_evidence_cannot_link_another_population_item(self):
        payload = sample(self.AREA, self.context); payload['specific_items'][0]['gl_refs']=['J01/L1']
        self.assertIn('SAMPLE_SPECIFIC_LINK', self.codes(self.run_case(self.AREA, payload)))

    def test_unsupported_mus_does_not_silently_use_another_method(self):
        payload=sample(self.AREA,self.context); payload['policy']['selection_method']='MUS'
        with self.assertRaises(AuditError): self.run_case(self.AREA,payload)

    def test_positive_and_negative_gl_lines_cannot_be_netted_into_one_sampling_unit(self):
        payload=sample(self.AREA,self.context)
        first=next(r for r in payload['population'] if r['gl_refs']==['J01/L1'])
        first['gl_refs']=['J01/L1','J04/L2'];first['amount']=20000
        payload['population']=[r for r in payload['population'] if r['gl_refs']!=['J04/L2']]
        result=self.run_case(self.AREA,payload)
        self.assertIn('SAMPLE_UNIT_NETTING',self.codes(result))
        self.assertFalse(result['detail']['현재원장연결'])


if __name__ == '__main__': unittest.main()
