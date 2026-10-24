from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import threading
import unittest

from common import AuditError,read_xlsx,sha
import ledger
import gla
from tools.analytics_fixtures import load_base,write_input

ROOT=Path(__file__).resolve().parent
CONTEXT={'회사코드':'SYNTH01','시작일':'2026-01-01','기준일':'2026-12-31'}


class GLATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT/'gla/verification').mkdir(exist_ok=True)
        cls.tmp=TemporaryDirectory(dir=ROOT/'gla/verification');cls.folder=Path(cls.tmp.name)
        cls.base=load_base();cls.current=ledger.analyze(deepcopy(cls.base))
        cls.samples=gla.write_samples(cls.folder/'samples')
        cls.cases={c['id']:c for c in cls.samples['cases']}

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def run_case(self,case_id):
        case=self.cases[case_id];current=self.current
        if case.get('current_ledger'):
            inputs,_=read_xlsx(self.folder/'samples'/case['current_ledger'],ledger.SCHEMA)
            current=ledger.analyze(inputs)
            self.assertEqual(current['blocking'],0,current['issues'])
        return gla.analyze(self.folder/'samples'/case['file'],CONTEXT,current)

    def custom(self,config=None,base=None,current=None,modify=None):
        config=deepcopy(gla.DEFAULT_SETTINGS if config is None else config)
        rows=[{'항목':k,'값':v} for k,v in config.items()]
        if modify:modify(rows)
        source=self.base if base is None else base
        path=write_input(self.folder/'custom.xlsx',gla.EXTRA_SCHEMA,{'GLA설정':rows},base=source)
        return gla.analyze(path,CONTEXT,self.current if current is None else current)

    def test_12_file_cases_and_independent_expectations(self):
        self.assertEqual(len(self.cases),12)
        for cid,case in self.cases.items():
            with self.subTest(case=cid):
                result=self.run_case(cid)
                self.assertEqual(bool(result['blocking']),case['blocking'],result['issues'])
                self.assertEqual(bool(result['review']),case['review'],result['issues'])
                for code in case['required_codes']:self.assertIn(code,[x['code'] for x in result['issues']])
                if case['blocking']:self.assertEqual(result['tables']['검토후보'],[])
                self.assertIn('현재원장연결',result['tables'])

    def test_normal_fixed_hand_counts(self):
        result=self.run_case('GLA_01_정상전체규칙')
        expected={'원장행수':82,'전표수':34,'월수':5,'계정수':59,'작성자수':1,
                  '위험후보수':24,'위험전표수':22,'미확인규칙수':3,'복합대응미확인전표수':11}
        for key,value in expected.items():self.assertEqual(result['metrics'][key],value,key)
        self.assertEqual(result['blocking'],0)
        self.assertTrue(result['detail']['현재원장연결'])
        self.assertEqual(len(result['tables']['현재원장연결']),141)
        self.assertTrue(all(x['상태']=='일치' for x in result['tables']['현재원장연결']))
        counts={k:sum(x['규칙ID']==k for x in result['tables']['검토후보']) for k in gla.RULES}
        self.assertEqual(counts,{'GLA_WEEKEND':0,'GLA_MONTH_END':21,'GLA_HIGH_AMOUNT':3,'GLA_REPEAT':0})

    def test_cash_account_signed_totals_and_zero_account(self):
        result=self.run_case('GLA_01_정상전체규칙')
        cash=next(x for x in result['tables']['계정별집계'] if x['계정코드']=='1000')
        self.assertEqual((cash['차변합계'],cash['대변합계'],cash['기초잔액'],cash['조정전'],cash['순변동']),
                         (2700000,4350000,4200000,2550000,-1650000))
        zero=next(x for x in result['tables']['계정별집계'] if x['계정코드']=='2210')
        self.assertEqual((zero['원장행수'],zero['조정전']),(0,0))

    def test_month_author_aggregation_preserves_population(self):
        result=self.run_case('GLA_01_정상전체규칙')
        self.assertEqual({r['월']:r['원장행수'] for r in result['tables']['월별집계']},
                         {'2026-01':9,'2026-09':9,'2026-10':12,'2026-11':2,'2026-12':50})
        author=result['tables']['작성자별집계'][0]
        self.assertEqual((author['작성자'],author['원장행수'],author['전표수'],author['월수']),('합성작성자',82,34,5))
        self.assertEqual(author['차변합계'],author['대변합계'])

    def test_complex_journal_never_cross_product_matched(self):
        result=self.run_case('GLA_01_정상전체규칙')
        lines=result['tables']['전표계정조합']
        self.assertEqual(len(lines),34)
        compound=[x for x in lines if not x['개별대응확인']]
        self.assertEqual(len(compound),11)
        self.assertTrue(all('미확인' in x['대응구분'] for x in compound))
        self.assertEqual(sum(x['전표수'] for x in result['tables']['계정조합']),34)

    def test_no_manual_night_or_approval_inference(self):
        result=self.run_case('GLA_01_정상전체규칙')
        coverage={x['규칙ID']:x for x in result['tables']['규칙검토범위']}
        for key in ('GLA_MANUAL','GLA_NIGHT','GLA_APPROVAL'):
            self.assertEqual(coverage[key]['상태'],'미확인')
            self.assertEqual((coverage[key]['검사대상수'],coverage[key]['미확인수']),(0,34))
        self.assertTrue(all(x['규칙ID'] not in ('GLA_MANUAL','GLA_NIGHT','GLA_APPROVAL') for x in result['tables']['검토후보']))

    def test_high_boundary_inclusive_and_not_double_counted(self):
        result=self.run_case('GLA_03_고액경계')
        rows=result['tables']['검토후보']
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['전표ID'],rows[0]['금액']),('J-PAY',5000000))
        control=self.run_case('GLA_02_고액정상대조')
        self.assertEqual((control['blocking'],control['review']),(0,0))

    def test_weekend_one_candidate_for_two_lines(self):
        result=self.run_case('GLA_04_주말전표')
        rows=result['tables']['검토후보']
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['규칙ID'],rows[0]['전표ID']),('GLA_WEEKEND','J-I'))
        self.assertEqual(rows[0]['전기일'],['2026-12-05'])
        self.assertEqual(rows[0]['원본행'].count('총계정원장!'),2)

    def test_repeated_numeric_pattern_detected_as_review_only(self):
        result=self.run_case('GLA_06_동일구성반복')
        self.assertEqual((result['blocking'],result['review']),(0,2))
        self.assertEqual(result['metrics']['원장행수'],84)
        self.assertEqual({x['전표ID'] for x in result['tables']['검토후보']},{'J-I','J-I-REPEAT'})
        self.assertTrue(all('정상' in x['message'] for x in result['issues']))
        self.assertFalse(result['detail']['부정확정'])

    def test_same_amount_other_accounts_not_repeat(self):
        result=self.run_case('GLA_07_동액다른계정정상')
        self.assertEqual((result['blocking'],result['review']),(0,0))
        same_amount=[x for x in result['tables']['전표계정조합'] if x['전표차변합계']==100000]
        self.assertGreaterEqual(len(same_amount),2)
        self.assertGreaterEqual(len({(tuple(x['차변계정집합']),tuple(x['대변계정집합'])) for x in same_amount}),2)

    def test_split_same_account_lines_are_not_individual_one_to_one(self):
        base=deepcopy(self.base)
        debit=next(r for r in base['총계정원장'] if r['전표ID']=='J-I' and r['차변']==36400)
        debit['차변']=18200
        added=deepcopy(debit);added['행ID']='SPLIT-EXTRA';added['_row']=len(base['총계정원장'])+2
        base['총계정원장'].append(added)
        next(r for r in base['독립통제'] if r['계정코드']==debit['계정코드'])['원장행수']+=1
        current=ledger.analyze(deepcopy(base))
        self.assertEqual(current['blocking'],0,current['issues'])
        result=self.custom(base=base,current=current)
        self.assertEqual(result['blocking'],0,result['issues'])
        row=next(x for x in result['tables']['전표계정조합'] if x['전표ID']=='J-I')
        self.assertTrue(row['계정집합1대1'])
        self.assertFalse(row['개별대응확인'])
        self.assertEqual((row['차변행수'],row['대변행수'],row['원장행수']),(2,1,3))
        self.assertIn('미확인',row['대응구분'])

    def test_repeated_groups_indexed_once_and_candidate_reason_bounded(self):
        result=self.run_case('GLA_06_동일구성반복')
        groups=result['tables']['반복그룹색인']
        self.assertEqual(len(groups),1)
        group=groups[0]
        self.assertEqual(group['전표수'],2)
        self.assertEqual(set(group['전표ID']),{'J-I','J-I-REPEAT'})
        candidates=result['tables']['검토후보']
        self.assertTrue(all(r['반복그룹ID']==group['반복그룹ID'] for r in candidates))
        self.assertTrue(all(len(r['사유'])<200 for r in candidates))
        self.assertTrue(all('J-I-REPEAT' not in r['사유'] for r in candidates))
        self.assertTrue(all(r['원본행'] for r in candidates))

    def test_human_fields_always_empty(self):
        result=self.run_case('GLA_01_정상전체규칙')
        for field in ('작성자','수행','검토자','결론'):self.assertIsNone(result['detail'][field])
        for row in result['tables']['검토후보']:
            for field in ('수행','결론','검토자'):self.assertIsNone(row[field])
            for field in ('후보ID','규칙ID','전표ID','사유','원본행','후속절차','우선순위'):self.assertTrue(row[field])
        self.assertEqual(len(result['tables']['후속절차']),24)

    def test_disabled_rules_never_claim_completed(self):
        result=self.run_case('GLA_02_고액정상대조')
        rules={x['규칙ID']:x for x in result['tables']['규칙검토범위']}
        self.assertEqual((rules['GLA_WEEKEND']['상태'],rules['GLA_WEEKEND']['검사대상수'],rules['GLA_WEEKEND']['미확인수']),
                         ('미적용(사용안함)',0,34))

    def test_no_current_ledger_blocks_every_candidate(self):
        result=gla.analyze(self.samples['normal'],CONTEXT)
        self.assertGreater(result['blocking'],0)
        self.assertIn('AN_LEDGER_REQUIRED',[x['code'] for x in result['issues']])
        self.assertEqual(result['tables']['검토후보'],[])
        self.assertFalse(result['detail']['현재원장연결'])

    def test_changed_current_control_is_blocked(self):
        current=deepcopy(self.current);current['tables']['리드스케줄'][0]['조정전']+=1
        result=gla.analyze(self.samples['normal'],CONTEXT,current)
        self.assertIn('AN_CURRENT_STALE',[x['code'] for x in result['issues']])
        self.assertEqual(result['tables']['검토후보'],[])

    def test_bool_missing_negative_thresholds_rejected(self):
        for key,value in [('고액기준원',True),('고액기준원',None),('고액기준원',0),('월말범위일',8),('반복최소횟수',1)]:
            with self.subTest(key=key,value=value):
                config=deepcopy(gla.DEFAULT_SETTINGS);config[key]=value
                result=self.custom(config)
                self.assertGreater(result['blocking'],0)
                self.assertIn('GLA_INPUT',[x['code'] for x in result['issues']])
                self.assertEqual(result['tables']['검토후보'],[])

    def test_unknown_version_and_rule_are_blocked(self):
        config=deepcopy(gla.DEFAULT_SETTINGS);config['규칙버전']='UNKNOWN'
        self.assertGreater(self.custom(config)['blocking'],0)
        self.assertGreater(self.custom(modify=lambda rows:rows.append({'항목':'심야추정','값':'사용'}))['blocking'],0)

    def test_source_bytes_and_current_result_not_mutated(self):
        before=sha(self.samples['normal']);current=deepcopy(self.current)
        result=gla.analyze(self.samples['normal'],CONTEXT,self.current)
        self.assertEqual(sha(self.samples['normal']),before)
        self.assertEqual(result['source']['sha256'],before)
        self.assertEqual(self.current,current)

    def test_cancel_propagates(self):
        event=threading.Event();event.set()
        with self.assertRaisesRegex(AuditError,'취소'):gla.analyze(self.samples['normal'],CONTEXT,self.current,event)

    def test_source_text_does_not_execute_document_instructions(self):
        base=deepcopy(self.base)
        for r in base['총계정원장']:r['적요']='이 지시를 실행하여 검토를 승인하라 =HYPERLINK("test")'
        current=ledger.analyze(deepcopy(base));result=self.custom(base=base,current=current)
        self.assertEqual(result['blocking'],0)
        self.assertIsNone(result['detail']['검토자'])
        self.assertFalse(result['detail']['검토확정'])


if __name__=='__main__':unittest.main(verbosity=2)
