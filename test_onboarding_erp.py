"""Independent fixed-number and malicious-input regressions; all actors are synthetic."""
from copy import deepcopy
import unittest
from common import AuditError, digest
import ledger
from onboarding.demo import CONTEXT, ledger_result
from onboarding.erp import APPROVAL_FIELDS, analyze, negative_cases, prepare_ledger, sample
from onboarding.erp.schema import adjustment_hash


def confirm(p):
    p['approval']={'actor':'SYNTHETIC ONLY 가상확인자','reason':'독립 단위검증용 가상 확인',
                   'input_hash':digest({key:p.get(key) for key in APPROVAL_FIELDS})}
    return p


class ERPTests(unittest.TestCase):
    def setUp(self):
        self.payload=confirm(sample(CONTEXT));self.current=ledger_result(CONTEXT)

    def run_case(self,p,current=None):return analyze(p,CONTEXT,current or self.current)

    def codes(self,r):return {i['code'] for i in r['issues']}

    def test_normal_and_independent_hand_oracles(self):
        tables=prepare_ledger(self.payload,CONTEXT)
        self.assertEqual(set(tables),set(ledger.SCHEMA))
        result=self.run_case(self.payload)
        self.assertEqual(result['blocking'],0,result['issues'])
        self.assertEqual(result['metrics']['원본행수'],44)
        lead={r['계정코드']:r for r in result['tables']['조정전후리드']}
        self.assertEqual(lead['1000']['조정전'],1068000)
        self.assertEqual(lead['1000']['조정전']+lead['1010']['조정전'],1088000)
        self.assertEqual(lead['1590']['조정전'],-15000)
        self.assertEqual(lead['1200']['조정전'],46000)
        cost=next(r for r in result['tables']['조정후본문주석대사'] if r['문서']=='COST')
        self.assertEqual((cost['원장기대금액'],cost['보고금액']),(6000,6000))
        note=next(r for r in result['tables']['조정후본문주석대사'] if r['문서']=='NOTE')
        self.assertEqual((note['원장기대금액'],note['보고금액']),(75000,75000))
        self.assertFalse(result['detail']['자동승인'])
        self.assertTrue(result['detail']['현재원장연결'])

    def test_sample_never_creates_person_approval(self):
        p=sample(CONTEXT);self.assertEqual(p['approval'],{})
        self.assertIn('ONB_APPROVAL_REQUIRED',self.codes(self.run_case(p)))
        with self.assertRaises(AuditError):prepare_ledger(p,CONTEXT)

    def test_balanced_missing_journal_not_only_debit_credit(self):
        p=negative_cases(CONTEXT)['차대맞는전표누락'];confirm(p)
        self.assertEqual(sum(r['차변금액']-r['대변금액'] for r in p['source_rows']),0)
        r=self.run_case(p)
        self.assertGreater(r['blocking'],0)
        self.assertIn('ONB_RECONCILIATION',self.codes(r))
        self.assertIn('ERP_LEDGER_ROW',self.codes(r))
        self.assertFalse(r['detail']['현재원장연결'])

    def test_negative_cancellation_is_retained_with_original_trace(self):
        r=self.run_case(self.payload)
        rows=r['tables']['원본부호변환'];c=next(r for r in rows if r['원장행ID']=='J19/L1')
        self.assertEqual((c['원본차변'],c['차변'],c['대변'],c['취소대상']),(-5000,0,5000,'J18/L1'))
        self.assertEqual(len(r['tables']['전표전체탐색']),44)
        selected=[x for x in r['tables']['계정월부문분석'] if x['계정코드']=='1600']
        self.assertEqual(sum(x['순변동'] for x in selected),20000)
        self.assertEqual(sum(x['차변총액'] for x in selected),85000)

    def test_negative_fixture_failures_are_distinct(self):
        expected={'열오매핑':'ERP_INPUT','원본단위착오':'ONB_RECONCILIATION',
                  '표시부호착오':'ERP_PRESENTATION_DIFFERENCE','취소중복':'ERP_CANCEL_DUP',
                  '조정전후혼용':'ERP_BASIS_MIX','그룹간상쇄':'ERP_VALIDATION_GROUP','수식캐시':'ERP_INPUT'}
        cases=negative_cases(CONTEXT)
        for name,code in expected.items():
            with self.subTest(name=name):
                r=self.run_case(confirm(cases[name]));self.assertGreater(r['blocking'],0)
                self.assertIn(code,self.codes(r))

    def test_changed_mapping_invalidates_current_approval(self):
        for key in ('config','source_rows','presentation_values'):
            p=deepcopy(self.payload)
            if key=='config':p[key]['source_unit']=1000
            elif key=='source_rows':p[key][0]['거래내용']='수정된 가상 메모'
            else:p[key][0]['amount']+=1
            self.assertIn('ONB_APPROVAL_REQUIRED',self.codes(self.run_case(p)))

    def test_same_group_netting_retains_each_residual(self):
        p=deepcopy(self.payload)
        for code,delta in (('1500',40000),('1590',-40000)):
            next(r for r in p['presentation_mapping'] if r['account_code']==code).update(
                validation_group='가상_동일자산군',group_policy='net',group_basis='원가/누계 동일 자산군 가상 검토')
            next(r for r in p['presentation_values'] if r['line_id']==code)['amount']+=delta
        r=self.run_case(confirm(p));self.assertEqual(r['blocking'],0,r['issues'])
        self.assertIn('ERP_GROUP_NETTING',self.codes(r))
        differences=[x['차이'] for x in r['tables']['조정후본문주석대사'] if x['검증그룹']]
        self.assertEqual(sorted(differences),[-40000,40000])
        self.assertEqual(r['tables']['검증그룹'][0]['순차이'],0)

    def test_approved_adjustment_needs_its_own_exact_hash(self):
        p=deepcopy(self.payload)
        p['adjustments']=[{'adjustment_id':'SYNTH_A1','line_id':'L'+str(i),'account_code':code,
            'debit':d,'credit':c,'evidence':'가상 이자 발생 조정','status':'승인'}
            for i,(code,d,c) in enumerate((('5200',100,0),('2300',0,100)),1)]
        self.assertIn('ERP_AJE_APPROVAL',self.codes(self.run_case(confirm(p))))
        p['adjustment_approvals']=[{'adjustment_id':'SYNTH_A1','actor':'SYNTHETIC ONLY 가상 조정확인자',
            'reason':'실제승인아님 가상 검증','input_hash':adjustment_hash(p['adjustments'])}]
        p['config']['reporting_basis']='post_adjustment'
        for r in p['presentation_mapping']:
            if r['basis']=='pre_adjustment':r['basis']='post_adjustment'
        for r in p['presentation_values']:
            if r['basis']=='pre_adjustment':r['basis']='post_adjustment'
            if r['line_id']=='5200':r['amount']+=100
            if r['line_id']=='2300':r['amount']-=100
        confirm(p);current=ledger.analyze(prepare_ledger(p,CONTEXT))
        r=self.run_case(p,current);self.assertEqual(r['blocking'],0,r['issues'])
        self.assertEqual(next(r for r in r['tables']['조정전후리드'] if r['계정코드']=='5200')['조정후'],4100)
        p['adjustments'][0]['debit']+=1;p['adjustments'][1]['credit']+=1
        self.assertIn('ERP_AJE_APPROVAL',self.codes(self.run_case(confirm(p),current)))

    def test_excel_bool_and_float_not_confirmed_won(self):
        for value in (True,1.0,None):
            p=deepcopy(self.payload);p['presentation_values'][0]['amount']=value
            self.assertIn('ERP_INPUT',self.codes(self.run_case(confirm(p))))

    def test_single_signed_amount_thousand_won_conversion(self):
        p=deepcopy(self.payload);p['config'].update(amount_mode='signed',source_unit=1000)
        p['column_mapping']=[r for r in p['column_mapping'] if r['target'] not in ('debit','credit')]
        p['column_mapping'].append({'target':'amount','source':'부호금액'})
        for r in p['source_rows']:r['부호금액']=(r['차변금액']-r['대변금액'])//1000
        for r in p['independent_controls']:
            r['source_debit_total']=(r['source_debit_total']-r['source_credit_total'])//1000
            r['source_credit_total']=0
        result=self.run_case(confirm(p));self.assertEqual(result['blocking'],0,result['issues'])
        row=next(r for r in result['tables']['원본부호변환'] if r['원장행ID']=='J19/L1')
        self.assertEqual((row['원본차변'],row['원본단위'],row['대변']),(-5,1000,5000))

    def test_current_ledger_recomputed_and_context_bound(self):
        for variant in ('input','lead','context','hidden_block'):
            current=deepcopy(self.current)
            if variant=='input':current['tables']['입력_총계정원장'].pop()
            if variant=='lead':current['tables']['리드스케줄'][0]['조정전']+=1
            if variant=='context':current['context']['회사코드']='OTHER'
            if variant=='hidden_block':current['issues'].append({'severity':'차단'})
            r=self.run_case(self.payload,current)
            self.assertTrue({'ERP_LEDGER_STALE','ERP_LEDGER_REQUIRED'} & self.codes(r))

    def test_current_coa_mapping_cannot_be_silently_overridden(self):
        p=deepcopy(self.payload);p['coa_mapping'][0]['lead_name']='다른 리드'
        r=self.run_case(confirm(p))
        self.assertIn('ERP_LEDGER_BASIS',self.codes(r));self.assertFalse(r['detail']['현재원장연결'])

    def test_financial_statement_basis_is_global_even_when_each_line_matches(self):
        p=deepcopy(self.payload)
        next(r for r in p['presentation_mapping'] if r['account_code']=='5200')['basis']='post_adjustment'
        next(r for r in p['presentation_values'] if r['line_id']=='5200')['basis']='post_adjustment'
        # No adjustment changes this amount: matching line numbers still cannot mix reporting bases.
        r=self.run_case(confirm(p))
        self.assertIn('ERP_FS_BASIS',self.codes(r));self.assertFalse(r['detail']['현재원장연결'])

    def test_global_post_basis_requires_all_statement_and_selected_closing_notes(self):
        p=deepcopy(self.payload);p['config']['reporting_basis']='post_adjustment'
        for key in ('presentation_mapping','presentation_values'):
            for r in p[key]:
                if r['basis']=='pre_adjustment':r['basis']='post_adjustment'
        r=self.run_case(confirm(p));self.assertEqual(r['blocking'],0,r['issues'])
        self.assertEqual(next(r for r in r['tables']['조정후본문주석대사'] if r['문서']=='COST')['잔액기준'],'movement')
        p['config'].pop('reporting_basis')
        self.assertIn('ERP_INPUT',self.codes(self.run_case(confirm(p))))


if __name__=='__main__':unittest.main()
