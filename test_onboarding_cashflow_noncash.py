"""Noncash debt/assets, independent groups, adjustment and FX boundaries."""
from copy import deepcopy
import unittest
from onboarding.contracts import ledger_basis
from test_onboarding_cashflow_support import codes, extend_ledger, normal, run, set_flow


class CashflowNoncashTests(unittest.TestCase):
    def test_new_lease_and_reclass_are_noncash_not_borrowings(self):
        r=run(); debt={x['계정코드']:x for x in r['tables']['재무부채증감명세']}
        self.assertEqual(debt['2200']['신규리스'],120000)
        self.assertEqual(debt['2200']['현금증감'],-10000)
        self.assertEqual(debt['2200']['기말부채'],110000)
        self.assertEqual(debt['2100']['현금증감'],50000)
        self.assertEqual(debt['2100']['유동성대체'],-50000)
        self.assertEqual(debt['2110']['유동성대체'],50000)
        self.assertEqual(r['metrics']['CFF'],40000)

    def test_noncash_new_lease_omission_fails(self):
        p,_=normal();p['noncash'].pop(1)
        self.assertIn('CF_NONCASH_SCOPE',codes(run(p)))

    def test_noncash_duplicate_and_wrong_amount_fail(self):
        p,_=normal();p['noncash'][0]['amount']+=1
        self.assertIn('ONB_RECONCILIATION',codes(run(p)))
        p,_=normal();p['noncash'].append(deepcopy(p['noncash'][0]))
        self.assertIn('CF_NONCASH_DUPLICATE',codes(run(p)))

    def test_cash_purchase_cannot_be_noncash(self):
        p,_=normal();p['noncash'][0].update(gl_refs=['J04/L1','J04/L2'],
            debit_account='1600',credit_account='1000',amount=80000)
        self.assertIn('CF_NONCASH_CONTAINS_CASH',codes(run(p)))

    def test_noncash_journal_partial_is_not_complete(self):
        p,_=normal();p['noncash'][0]['gl_refs'].pop()
        self.assertIn('CF_NONCASH_JOURNAL',codes(run(p)))

    def test_cross_group_errors_cannot_cancel_globally(self):
        p,_=normal();p['group_controls'][3]['closing']+=777;p['group_controls'][4]['closing']-=777
        r=run(p);differences=[x['기말차이'] for x in r['tables']['검증그룹대사']]
        self.assertEqual(sum(differences),0)
        self.assertEqual(sorted(x for x in differences if x),[-777,777])
        self.assertGreater(r['blocking'],0)

    def test_cost_and_accumulated_keep_individual_account_traces(self):
        r=run();checks={x['검사']:x for x in r['tables']['계정증감대사']}
        self.assertEqual(checks['계정 증감 1500']['원장증감'],40000)
        self.assertEqual(checks['계정 증감 1590']['원장증감'],-5000)
        ppe=[x for x in r['tables']['검증그룹대사'] if x['검증그룹']=='ppe'][0]
        self.assertEqual(ppe['원장기말'],75000)

    def test_missing_or_duplicate_groups_are_blocked(self):
        p,_=normal();p['group_controls'].pop()
        self.assertIn('CF_GROUP_MISSING',codes(run(p)))
        p,_=normal();p['group_controls'].append(deepcopy(p['group_controls'][0]))
        self.assertIn('CF_GROUP_SCOPE',codes(run(p)))

    def test_unrelated_account_roles_cannot_be_collapsed_into_single_group(self):
        p,_=normal()
        for row in p['accounts']:
            if row['validation_group']=='cip':row['validation_group']='ppe'
        p['group_controls'][3]['closing']+=20000
        p['group_controls']=[r for r in p['group_controls'] if r['validation_group']!='cip']
        self.assertIn('CF_GROUP_ROLE',codes(run(p)))

    def test_cash_account_errors_cannot_cancel_between_banks(self):
        p,_=normal();p['cash_controls'][0]['closing']+=500;p['cash_controls'][1]['closing']-=500
        r=run(p);self.assertGreater(r['blocking'],0)
        self.assertFalse(r['detail']['현재원장연결'])

    def test_missing_cash_control_does_not_pass_on_total_cash(self):
        p,_=normal();p['cash_controls'].pop()
        self.assertIn('CF_CASH_CONTROL_MISSING',codes(run(p)))

    def test_approved_adjustment_current_lead_connected_and_visible(self):
        p,_=normal();l=extend_ledger((('5100',40,0),('1200',60,0),('1590',0,100)),adjustments=True)
        p['policy']['ledger_basis_hash']=ledger_basis(l)
        refs=['AJE:A01/L1','AJE:A01/L2','AJE:A01/L3']
        p['movement_tags'] += [{'source_ref':ref,'kind':'depreciation'} for ref in refs]
        p['depreciation_parts'] += [{'kind':'expense','amount':40,'gl_refs':[refs[0]]},
                                     {'kind':'inventory','amount':60,'gl_refs':[refs[1]]}]
        for row in p['group_controls']:
            if row['validation_group']=='inventory':row['closing']+=60
            if row['validation_group']=='ppe':row['closing']-=100
        set_flow(p,'net_profit',136960)
        r=run(p,l);self.assertEqual(r['blocking'],0,r['issues'])
        self.assertEqual(r['metrics']['CFO'],103000)
        traces=[x for x in r['tables']['연결원장행'] if x['원천']=='AJE']
        self.assertEqual(len(traces),3)
        check=[x for x in r['tables']['계정증감대사'] if x['검사']=='계정 증감 1590'][0]
        self.assertEqual(check['승인조정'],-100)

    def test_approved_adjustment_population_omission_fails(self):
        p,_=normal();l=extend_ledger((('5100',100,0),('1590',0,100)),adjustments=True)
        p['policy']['ledger_basis_hash']=ledger_basis(l)
        self.assertIn('CF_TAG_SCOPE',codes(run(p,l)))

    def test_foreign_currency_debt_effect_explicit_not_cash(self):
        p,_=normal();l=extend_ledger((('5400',1000,0),('2100',0,1000)),
            new_accounts=(('5400','가상외환손실',0,'PL'),))
        p['policy']['ledger_basis_hash']=ledger_basis(l)
        p['accounts'].append({'account_code':'5400','role':'fx_result','validation_group':'profit',
                              'profit_category':'financing'})
        p['movement_tags'] += [{'source_ref':ref,'kind':'fx'} for ref in ['J21/L1','J21/L2']]
        p['noncash'].append({'item_id':'NC04','kind':'debt_fx','debit_account':'5400',
            'credit_account':'2100','amount':1000,'gl_refs':['J21/L1','J21/L2']})
        for row in p['group_controls']:
            if row['validation_group']=='loans':row['closing']-=1000
        set_flow(p,'net_profit',136000)
        r=run(p,l);self.assertEqual(r['blocking'],0,r['issues'])
        self.assertEqual(r['metrics']['CFO'],103000)
        self.assertEqual(r['metrics']['FX'],0)
        debt=[x for x in r['tables']['재무부채증감명세'] if x['계정코드']=='2100'][0]
        self.assertEqual(debt['환율변동'],1000)

    def test_cash_fx_effect_separate_from_cash_flow_sections(self):
        p,_=normal();l=extend_ledger((('1000',1000,0),('5400',0,1000)),
            new_accounts=(('5400','가상외환이익',0,'PL'),))
        p['policy']['ledger_basis_hash']=ledger_basis(l)
        p['accounts'].append({'account_code':'5400','role':'fx_result','validation_group':'profit',
                              'profit_category':'financing'})
        p['movement_tags'] += [{'source_ref':ref,'kind':'fx'} for ref in ['J21/L1','J21/L2']]
        p['cash_allocations'].append({'allocation_id':'C15','parent_gl_ref':'J21/L1',
            'component':'cash_fx','amount':1000,'gl_refs':['J21/L1','J21/L2']})
        p['cash_controls'][0]['closing']+=1000;p['group_controls'][0]['closing']+=1000
        set_flow(p,'net_profit',138000);set_flow(p,'FX',1000);set_flow(p,'cash_closing',1089000)
        r=run(p,l);self.assertEqual(r['blocking'],0,r['issues'])
        self.assertEqual(r['metrics']['CFO'],103000);self.assertEqual(r['metrics']['FX'],1000)


if __name__=='__main__':unittest.main()
