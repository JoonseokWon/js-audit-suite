"""Period/framework policy, approval staleness and immutable ledger pin tests."""
from copy import deepcopy
import unittest
from common import AuditError
from onboarding import cashflow
from onboarding.contracts import ledger_basis
from onboarding.demo import CONTEXT
from test_onboarding_cashflow_support import codes, normal, run, set_flow, stamp


class CashflowPolicyTests(unittest.TestCase):
    def test_policy_change_invalidates_previous_confirmation(self):
        p,l=normal(); stamp(p); p['policy']['interest_paid']='financing'
        r=cashflow.analyze(p,CONTEXT,l)
        self.assertIn('ONB_APPROVAL_REQUIRED',codes(r))

    def test_table_change_invalidates_previous_confirmation(self):
        for key in cashflow.TABLE_FIELDS:
            with self.subTest(table=key):
                p,l=normal(); stamp(p); p[key][0]['_user_note']='changed'
                self.assertIn('ONB_APPROVAL_REQUIRED',codes(cashflow.analyze(p,CONTEXT,l)))

    def test_actor_reason_and_exact_hash_required(self):
        for field in ('actor','reason','input_hash'):
            p,l=normal(); stamp(p); p['approval'][field]=''
            self.assertIn('ONB_APPROVAL_REQUIRED',codes(cashflow.analyze(p,CONTEXT,l)))

    def test_source_filename_and_run_metadata_do_not_rebase_ledger_hash(self):
        p,l=normal(); original=ledger_basis(l)
        l.update(source={'filename':'other.xlsx','sha256':'abc'},runID=999,version='metadata-only')
        self.assertEqual(ledger_basis(l),original)
        self.assertEqual(run(p,l)['blocking'],0)

    def test_changed_ledger_amount_invalidates_basis(self):
        p,l=normal(); l['tables']['입력_총계정원장'][0]['차변']+=1
        self.assertIn('CF_LEDGER_STALE',codes(run(p,l)))

    def test_reconfirmed_changed_ledger_still_requires_independent_reconciliation(self):
        p,l=normal(); l['tables']['입력_총계정원장'][0]['차변']+=1
        p['policy']['ledger_basis_hash']=ledger_basis(l)
        r=run(p,l)
        self.assertIn('ONB_RECONCILIATION',codes(r))
        self.assertFalse(r['detail']['현재원장연결'])

    def test_ledger_population_omission_cannot_pass_on_equal_debits_credits(self):
        p,l=normal()
        l['tables']['입력_총계정원장']=[r for r in l['tables']['입력_총계정원장'] if r['전표ID']!='J17']
        p['movement_tags']=[r for r in p['movement_tags'] if not r['source_ref'].startswith('J17/')]
        p['cash_allocations']=[r for r in p['cash_allocations'] if not r['parent_gl_ref'].startswith('J17/')]
        p['policy']['ledger_basis_hash']=ledger_basis(l)
        r=run(p,l)
        self.assertIn('ONB_RECONCILIATION',codes(r))

    def test_blocked_or_absent_parent_ledger_never_connects(self):
        p,l=normal(); l['blocking']=1
        for ledger in (l,{}):
            r=run(p,ledger)
            self.assertIn('ONB_LEDGER_REQUIRED',codes(r))
            self.assertFalse(r['detail']['현재원장연결'])

    def test_interest_paid_financing_changes_two_sections_not_total_cash(self):
        p,_=normal(); p['policy']['interest_paid']='financing'
        set_flow(p,'CFO',106000);set_flow(p,'CFF',37000)
        r=run(p);self.assertEqual(r['blocking'],0,r['issues'])
        self.assertEqual(r['metrics']['cash_closing'],1088000)

    def test_modern_version_requires_operating_profit_and_explicit_classifications(self):
        p,_=normal(); q=p['policy'];q.update(standard_version='KIFRS1007_IFRS1118',
            effective_from='2027-01-01',version_end='2030-12-31',early_adoption=True,
            early_adoption_permitted=True,adoption_basis='SYNTHETIC ONLY 국내 시행·조기적용 별도 확인 예시',
            starting_point='operating_profit',interest_paid='financing',
            interest_received='investing',dividends_received='investing')
        set_flow(p,'CFO',106000);set_flow(p,'CFF',37000)
        r=run(p);self.assertEqual(r['blocking'],0,r['issues'])
        self.assertEqual(r['metrics']['starting_amount'],146000)
        self.assertFalse(r['detail']['국내시행자동추정'])

    def test_modern_version_wrong_start_and_classification_are_visible(self):
        p,_=normal();p['policy']['standard_version']='IAS7_IFRS18';p['policy']['framework']='IFRS'
        r=run(p);self.assertIn('CF_STARTING_POINT',codes(r));self.assertIn('CF_CLASSIFICATION',codes(r))

    def test_modern_operating_profit_uses_supported_account_categories(self):
        p,_=normal();p['policy']['standard_version']='KIFRS1007_IFRS1118'
        next(r for r in p['accounts'] if r['account_code']=='5300')['profit_category']='operating'
        self.assertIn('CF_OPERATING_PROFIT_SCOPE',codes(run(p)))

    def test_unknown_framework_and_special_financial_business_not_assumed(self):
        p,_=normal();p['policy']['framework']='일반기업회계기준';p['policy']['business_profile']='bank'
        r=run(p);self.assertIn('CF_VERSION',codes(r));self.assertIn('CF_PROFILE',codes(r))

    def test_no_automatic_domestic_switch_in_2027(self):
        context=dict(CONTEXT,시작일='2027-01-01',기준일='2027-12-31')
        p=cashflow.sample(context)
        self.assertEqual(p['policy']['standard_version'],'KIFRS1007_PRE1118')
        from onboarding.demo import ledger_result
        r=cashflow.analyze(stamp(p),context,ledger_result(context))
        self.assertIn('CF_POLICY_PERIOD',codes(r))

    def test_early_adoption_requires_permission_not_just_year(self):
        p,_=normal();p['policy'].update(effective_from='2027-01-01',early_adoption=True)
        self.assertIn('CF_EARLY_ADOPTION',codes(run(p)))

    def test_false_string_is_not_policy_boolean(self):
        p,_=normal();p['policy']['early_adoption']='FALSE'
        with self.assertRaises(AuditError):run(p)

    def test_context_mismatch_fails(self):
        p,l=normal();p['context']['회사코드']='OTHER'
        with self.assertRaises(AuditError):cashflow.analyze(stamp(p),CONTEXT,l)

    def test_schema_lists_and_field_labels_are_editable_and_unique(self):
        p,_=normal()
        for key,fields in cashflow.TABLE_FIELDS.items():
            self.assertIn(key,cashflow.APPROVAL_FIELDS)
            labels=[cashflow.FIELD_LABELS[f] for f in fields]
            self.assertEqual(len(labels),len(set(labels)))
            self.assertTrue(all(set(fields)<=set(r) for r in p[key]))

    def test_cancel_is_respected(self):
        from threading import Event
        event=Event();event.set();p,l=normal()
        with self.assertRaises(AuditError):cashflow.analyze(stamp(p),CONTEXT,l,event)


if __name__=='__main__':unittest.main()
