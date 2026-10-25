"""Independent amounts, cash component allocation and manufacturing depreciation."""
from copy import deepcopy
import unittest
from common import AuditError
from onboarding import cashflow
from onboarding.demo import CONTEXT
from test_onboarding_cashflow_support import codes, normal, run, set_flow, stamp


class CashflowCalculationTests(unittest.TestCase):
    def test_independent_reference_numbers(self):
        result=run()
        self.assertEqual(result['blocking'],0,result['issues'])
        self.assertTrue(result['detail']['현재원장연결'])
        expected={'net_profit':137000,'CFO':103000,'CFI':-55000,'CFF':40000,
            'cash_opening':1000000,'cash_closing':1088000,'cash_movement':88000,'FX':0}
        for key,value in expected.items():self.assertEqual(result['metrics'][key],value,key)
        self.assertEqual(len(result['tables']['연결원장행']),44)
        self.assertEqual(result['detail']['실제AI호출'],0)

    def test_sample_has_no_fabricated_approval(self):
        p,l=normal(); self.assertEqual(p['approval'],{})
        r=cashflow.analyze(p,CONTEXT,l)
        self.assertIn('ONB_APPROVAL_REQUIRED',codes(r))
        self.assertFalse(r['detail']['현재원장연결'])

    def test_principal_interest_swapped_total_unchanged(self):
        p,_=normal(); a,b=p['cash_allocations'][5:7]
        a['amount'],b['amount']=b['amount'],a['amount']
        r=run(p)
        self.assertIn('ONB_RECONCILIATION',codes(r))
        self.assertTrue(any(x['검사'].startswith('배부 구성') and x['차이'] for x in r['tables']['검사결과']))

    def test_component_names_swapped_same_parent_total(self):
        p,_=normal(); a,b=p['cash_allocations'][5:7]
        a['component'],b['component']=b['component'],a['component']
        self.assertIn('CF_COMPONENT_ROLE',codes(run(p)))

    def test_duplicate_child_id_and_counterpart(self):
        p,_=normal(); p['cash_allocations'].append(deepcopy(p['cash_allocations'][5]))
        r=run(p)
        self.assertIn('CF_ALLOCATION_DUPLICATE',codes(r))
        self.assertIn('CF_COUNTERPART_DUPLICATE',codes(r))

    def test_counterpart_reuse_with_new_id(self):
        p,_=normal(); row=deepcopy(p['cash_allocations'][5]); row['allocation_id']='NEW'
        p['cash_allocations'].append(row)
        self.assertIn('CF_COUNTERPART_DUPLICATE',codes(run(p)))

    def test_unallocated_cash_is_not_omitted(self):
        p,_=normal(); p['cash_allocations'].pop(6)
        r=run(p)
        self.assertTrue(any(x['검사']=='현금행 배부 J11/L3' and x['차이']==1000
                            for x in r['tables']['검사결과']))

    def test_excess_child_and_wrong_direction(self):
        p,_=normal(); p['cash_allocations'][0]['amount']=-100001
        self.assertIn('CF_ALLOCATION_SIGN',codes(run(p)))

    def test_other_journal_is_not_evidence(self):
        p,_=normal(); p['cash_allocations'][0]['gl_refs']=['J01/L1','J02/L2']
        self.assertIn('CF_ALLOCATION_EVIDENCE',codes(run(p)))

    def test_missing_ref_remains_exception(self):
        p,_=normal(); p['cash_allocations'][0]['gl_refs'].append('ABSENT/L1')
        self.assertIn('ONB_REF_MISSING',codes(run(p)))

    def test_gross_and_net_inventory_methods_same_cash(self):
        p,_=normal(); p['policy']['inventory_method']='net_inventory_expensed_depreciation'
        r=run(p); self.assertEqual(r['blocking'],0,r['issues'])
        self.assertEqual(r['metrics']['CFO'],103000)
        self.assertEqual(r['metrics']['depreciation_addback'],4000)
        self.assertEqual(r['metrics']['inventory_adjustment'],-30000)
        dep=r['detail']['상각비조정']; self.assertEqual(dep['total'],10000)
        self.assertEqual(dep['capitalized'],6000)

    def test_manufacturing_depreciation_duplicate_rejected(self):
        p,_=normal(); p['depreciation_parts'].append(deepcopy(p['depreciation_parts'][1]))
        self.assertIn('CF_DEPRECIATION_DUPLICATE',codes(run(p)))

    def test_manufacturing_depreciation_omission_rejected(self):
        p,_=normal(); p['depreciation_parts'].pop()
        self.assertIn('CF_DEPRECIATION_SCOPE',codes(run(p)))

    def test_hardcoded_wrong_report_does_not_change_calculation(self):
        p,_=normal(); set_flow(p,'CFO',109000)
        r=run(p); self.assertEqual(r['metrics']['CFO'],103000)
        self.assertIn('ONB_RECONCILIATION',codes(r))

    def test_internal_transfer_gross_preserved_net_zero(self):
        r=run(); rows=[x for x in r['tables']['현금원장배부'] if x['구성항목']=='internal_transfer']
        self.assertEqual(sorted(x['배부금액'] for x in rows),[-20000,20000])
        self.assertEqual(r['metrics']['internal_transfer_net'],0)
        self.assertEqual(len(r['tables']['연결원장행']),44)

    def test_internal_transfer_one_leg_rejected(self):
        p,_=normal(); p['cash_allocations'].pop(10)
        self.assertIn('CF_INTERNAL_PAIR',codes(run(p)))

    def test_asset_purchase_reversal_retained_gross(self):
        rows=run()['tables']['현금원장배부']
        values=[x['배부금액'] for x in rows if x['부모현금행'] in {'J18/L2','J19/L2'}]
        self.assertEqual(sorted(values),[-5000,5000])

    def test_no_input_mutation(self):
        p,l=normal(); stamp(p); before=deepcopy((p,l))
        cashflow.analyze(p,CONTEXT,l)
        self.assertEqual((p,l),before)

    def test_boolean_formula_and_fraction_are_not_amounts(self):
        for value in (True,'=100000','100000.1',None):
            with self.subTest(value=value):
                p,_=normal(); p['cash_allocations'][0]['amount']=value
                with self.assertRaises(AuditError):run(p)

    def test_all_negative_fixtures_fail_after_explicit_test_confirmation(self):
        for name,p in cashflow.negative_cases(CONTEXT).items():
            with self.subTest(name=name):self.assertGreater(run(p)['blocking'],0)


if __name__=='__main__':unittest.main()
