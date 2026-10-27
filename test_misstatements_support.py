"""Independent tiny JS전자 ledgers and explicitly SYNTHETIC ONLY human values."""
from pathlib import Path
import tempfile
import unittest
from openpyxl import Workbook
from common import digest, result
from workspace import Workspace
from ledger import SCHEMA

ACTOR='SYNTHETIC ONLY / 가상 상태전이 기록자'
ROOT=Path(__file__).resolve().parent


def ledger(path, corrected=False, overlay=False):
    amount=200 if corrected else 100
    config=[['회사코드','JS_ELEC'],['시작일','2026-01-01'],['기준일','2026-12-31'],
            ['통화','KRW'],['추출범위','1100;4000']]
    tables={'설정':config,
        '시산표':[['JS_ELEC','1100','매출채권',0,amount,0,amount],
                 ['JS_ELEC','4000','제품매출',0,0,amount,-amount]],
        '총계정원장':[['JS_ELEC','BASE','1','2026-12-30','1100',100,0,'가상 매출채권',ACTOR],
                     ['JS_ELEC','BASE','2','2026-12-30','4000',0,100,'가상 제품매출',ACTOR]],
        '계정매핑':[['1100','AR','매출채권','BS'],['4000','REV','제품매출','PL']],
        '독립통제':[['JS_ELEC','2026-01-01','2026-12-31',code,2 if corrected else 1,
                    amount if code=='1100' else 0,amount if code=='4000' else 0,0,
                    amount if code=='1100' else -amount,'SYNTHETIC ONLY 독립검산',
                    '2027-01-02T10:00:00+09:00',ACTOR] for code in ('1100','4000')],
        '감사조정':[],'모듈연결':[]}
    if corrected:
        tables['총계정원장'] += [['JS_ELEC','FIX','1','2026-12-31','1100',100,0,'가상 수정',ACTOR],
                              ['JS_ELEC','FIX','2','2026-12-31','4000',0,100,'가상 수정',ACTOR]]
    if overlay:
        tables['감사조정']=[['AJE','1','1100',100,0,'가상 수용','승인'],['AJE','2','4000',0,100,'가상 수용','승인']]
    book=Workbook();book.remove(book.active)
    for name,headers in SCHEMA.items():
        sheet=book.create_sheet(name);sheet.append(headers)
        for row in tables[name]:sheet.append(row)
    book.save(path);book.close();return path


def profile():
    return {'audit_framework':'KSA_200_720','audit_framework_reason':'SYNTHETIC ONLY 선택',
            'form_framework':'KIFRS','materiality':{'benchmark_name':'가상 매출',
            'benchmark_amount':100000,'materiality_rate':'0.1','performance_rate':'0.5','trivial_rate':'0.1'},
            'scope':[{'procedure_id':'F03','applicable':True,'reason':'SYNTHETIC ONLY 집계범위'}]}


class Case(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_ms_');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.ws=Workspace(self.base/'JS전자_가상업무',create={
            '회사코드':'JS_ELEC','회사명':'JS전자 / SYNTHETIC ONLY',
            '시작일':'2026-01-01','기준일':'2026-12-31','회계체계':'K-IFRS 합성',
            '감사기준':'합성 검증','작성자':'예제자료 생성기 / 실제사람아님','더미업무':True})
        self.run=self.ws.execute('원장·리드',ledger(self.base/'수정전.xlsx'))
        self.assertEqual(self.run['result']['blocking'],0)

    def record_value(self,**changes):
        return {'description':'SYNTHETIC ONLY 매출채권·매출 누락 검토',
                'assessment':'왜곡표시','classification':'사실','amount':100,
                'correction_state':'미수정','company_position':'이견있음',
                'company_note':'SYNTHETIC ONLY 회사의 이견 보존','period':'당기',
                'qualitative':'없음','tax_effect':0,'tax_basis':'SYNTHETIC ONLY 비과세 가정',
                'account_impacts':[{'account_code':'1100','fs_line':'매출채권','direction':'증가','amount':100},
                                   {'account_code':'4000','fs_line':'매출','direction':'증가','amount':100}],
                'evidence_ids':[self.run['source_id']],'procedure_ids':['F03','A04'],
                'judgment':'SYNTHETIC ONLY 독립 가상 원본 검토 후 미수정 판단',**changes}

    def check_value(self,record):
        return {'record_id':record['id'],'ledger_run_id':self.ws.latest()['원장·리드']['id'],
                'journal_ids':['FIX'],'account_checks':[{'account_code':'1100','expected_movement':100},
                {'account_code':'4000','expected_movement':-100}],
                'evidence_ids':list(self.ws.sources),'performed_date':'2027-01-02',
                'conclusion':'SYNTHETIC ONLY 선택 실제 GL 전표의 수치 비교; 실제 사람 수행 아님'}
