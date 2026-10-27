"""Conflicting sources stay review candidates; neither source is declared correct."""
from copy import deepcopy
from collections import defaultdict
import unittest
from common import digest
import accruals
from data_controls.attribution import review_invoice


def conflict_case():
    company='REVIEW_ONLY_A'
    settings={'회사코드':company,'시작일':'2026-01-01','기준일':'2026-01-05','통화':'KRW',
        '모형':'확정용역_미지급선급','후속검색종료일':'2026-01-10','허용오차':'0','회계정책근거':'SYNTHETIC ONLY',
        '미지급계정범위':'2100','발생비용계정범위':'5100','선급계정범위':'1300','선급상각계정범위':'5200'}
    t={'설정':[dict(항목=k,값=v) for k,v in settings.items()],
       '용역계약':[dict(회사코드=company,비용ID='C1',거래처ID='V1',구분='미지급',용역시작='2026-01-01',용역종료='2026-01-10',총공급가액=1000,배분방법='일할',비용계정='5100',잔액계정='2100',회계처리구분='확정용역비용',계약근거='SYNTHETIC ONLY ten days 1000')],
       '비용원장':[dict(회사코드=company,비용ID='C1',기초부채=0,당기발생비용=500,당기부채결제=0,기말부채=500,기초선급=0,당기선급지급=0,당기선급상각=0,기말선급=0,원장근거='SYNTHETIC ONLY fixed five days 500')],
       '후속송장':[dict(회사코드=company,증빙ID='I1',비용ID='C1',거래처ID='V1',송장번호='INV1',송장행ID='1',증빙일='2026-01-06',공급가액=1000,귀속시작='2026-01-01',귀속종료='2026-01-05',배분방법='일할',증빙근거='SYNTHETIC ONLY claims first five days 1000')],
       '대금지급':[],'독립통제':[]}
    controls={'용역계약':{'행수':1,'ID해시':digest(['C1']),'총공급가액합계':1000,'총공급가액절대합계':1000},
       '비용원장':{'행수':1,'ID해시':digest(['C1']),**{k+s:v for k,v in [('기초부채',0),('당기발생비용',500),('당기부채결제',0),('기말부채',500),('기초선급',0),('당기선급지급',0),('당기선급상각',0),('기말선급',0)] for s in ('합계','절대합계')}},
       '후속송장':{'행수':1,'ID해시':digest(['I1']),'공급가액합계':1000,'공급가액절대합계':1000},
       '대금지급':{'행수':0,'ID해시':digest([]),'공급가액지급합계':0,'공급가액지급절대합계':0}}
    for role,items in controls.items():
        for key,val in items.items():t['독립통제'].append(dict(자료=role,지표=key,기대값=val,추출근거='SYNTHETIC ONLY independent fixed',추출일시='2026-01-10T23:00:00+09:00',작성자='SYNTHETIC ONLY'))
    for name,rows in t.items():
        for index,row in enumerate(rows,2):row.update(_sheet=name,_row=index)
    return t


class ReviewAttributionTests(unittest.TestCase):
    def test_contract_500_invoice_1000_is_reviewed_without_changing_either_source(self):
        tables=conflict_case();before=deepcopy(tables);r=accruals.analyze(tables)
        self.assertEqual(r['blocking'],0)
        self.assertIn('ACC_ATTRIBUTION_CONFLICT',{i['code'] for i in r['issues']})
        row=r['tables']['후속송장귀속검토'][0]
        self.assertEqual((row['동일기간계약기준참고액'],row['송장기준참고액'],row['차이']),(500,1000,500))
        self.assertFalse(row['금액자동확정']);self.assertEqual(tables,before)
        self.assertEqual(r['metrics']['기말미지급비용'],500)
        self.assertEqual(r['tables']['후속송장검색'][0]['기말전귀속참고액'],1000)
        self.assertIn('용역계약!',row['계약원본행']);self.assertIn('후속송장!',row['송장원본행'])

    def test_comparison_uses_same_invoice_period_not_whole_contract_to_date(self):
        from common import day
        c=conflict_case()['용역계약'][0];invoice=conflict_case()['후속송장'][0]
        invoice.update(공급가액=200,귀속시작='2026-01-03',귀속종료='2026-01-04')
        issues=[];rows=[]
        review_invoice(c,invoice,(day('2026-01-01'),day('2026-01-10'),1000),
            day('2026-01-03'),day('2026-01-04'),day('2026-01-05'),200,accruals.earned,issues,rows,defaultdict(list))
        self.assertFalse(issues);self.assertEqual(rows[0]['동일기간계약기준참고액'],200)

    def test_overlapping_invoices_within_contract_total_stay_additional_review(self):
        from common import day
        c=conflict_case()['용역계약'][0];first=conflict_case()['후속송장'][0]
        first['공급가액']=500;second=dict(first,증빙ID='I2',송장번호='INV2',_row=3)
        issues=[];rows=[];periods=defaultdict(list)
        for inv in (first,second):review_invoice(c,inv,(day('2026-01-01'),day('2026-01-10'),1000),
            day('2026-01-01'),day('2026-01-05'),day('2026-01-05'),500,accruals.earned,issues,rows,periods)
        self.assertEqual([i['code'] for i in issues],['ACC_INVOICE_PERIOD_OVERLAP'])
        self.assertEqual(issues[0]['severity'],'검토')
        self.assertIn('후속송장!2',issues[0]['reference']);self.assertIn('후속송장!3',issues[0]['reference'])


if __name__=='__main__':unittest.main()
