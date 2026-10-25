"""Invented JS company transactions. No workbook answers or actual company data.

Independent reference values: profit 137000; CFO 103000; CFI -55000;
CFF 40000; cash movement 88000. These are checked separately by tests.
"""
from collections import defaultdict
from datetime import timedelta
from common import day

CONTEXT = {'회사코드': 'JS_ELEC', '시작일': '2026-01-01', '기준일': '2026-12-31'}
ACCOUNTS = {
    '1000': ('보통예금', 1000000, 'BS'), '1010': ('별도은행예금', 0, 'BS'),
    '1100': ('매출채권', 0, 'BS'), '1200': ('재고자산', 10000, 'BS'),
    '1500': ('기계장치', 50000, 'BS'), '1590': ('감가상각누계액', -10000, 'BS'),
    '1600': ('건설중인자산', 0, 'BS'), '1700': ('사용권자산', 0, 'BS'),
    '2000': ('매입채무', -20000, 'BS'), '2100': ('장기차입금', -300000, 'BS'),
    '2110': ('유동성장기차입금', 0, 'BS'), '2200': ('리스부채', 0, 'BS'),
    '2300': ('미지급이자', 0, 'BS'), '2400': ('미지급법인세', 0, 'BS'),
    '3000': ('자본', -730000, 'BS'), '4000': ('매출', 0, 'PL'),
    '4100': ('유형자산처분이익', 0, 'PL'), '5100': ('감가상각비', 0, 'PL'),
    '5200': ('이자비용', 0, 'PL'), '5300': ('법인세비용', 0, 'PL'),
}
# Account, debit, credit. Reversal J19 is retained as positive opposite sides;
# the ERP sample can represent the same rows as negative original amounts.
JOURNALS = (
    ('J01', '현금 매출', (('1000',100000,0),('4000',0,100000))),
    ('J02', '외상 매출', (('1100',40000,0),('4000',0,40000))),
    ('J03', '채권 회수', (('1000',20000,0),('1100',0,20000))),
    ('J04', '건설중인자산 외부 취득', (('1600',80000,0),('1000',0,80000))),
    ('J05', 'CIP 기계장치 대체', (('1500',60000,0),('1600',0,60000))),
    ('J06', '감가상각 배부', (('5100',4000,0),('1200',6000,0),('1590',0,10000))),
    ('J07', '외상 재고 매입', (('1200',30000,0),('2000',0,30000))),
    ('J08', '매입채무 지급', (('2000',10000,0),('1000',0,10000))),
    ('J09', '차입', (('1000',50000,0),('2100',0,50000))),
    ('J10', '신규 리스 비현금 인식', (('1700',120000,0),('2200',0,120000))),
    ('J11', '리스 원금 및 이자 지급', (('2200',10000,0),('5200',1000,0),('1000',0,11000))),
    ('J12', '이자 발생', (('5200',3000,0),('2300',0,3000))),
    ('J13', '미지급이자 지급', (('2300',2000,0),('1000',0,2000))),
    ('J14', '당기법인세 발생', (('5300',5000,0),('2400',0,5000))),
    ('J15', '법인세 지급', (('2400',4000,0),('1000',0,4000))),
    ('J16', '자산 처분', (('1000',25000,0),('1590',5000,0),('1500',0,20000),('4100',0,10000))),
    ('J17', '현금 계정간 내부이체', (('1010',20000,0),('1000',0,20000))),
    ('J18', '취득 착오 기표', (('1600',5000,0),('1000',0,5000))),
    ('J19', '취득 착오 취소', (('1600',0,5000),('1000',5000,0))),
    ('J20', '차입금 유동성 대체', (('2100',50000,0),('2110',0,50000))),
)


def ledger_tables(context=None):
    context = dict(context or CONTEXT)
    tables = {name: [] for name in ('설정','시산표','총계정원장','계정매핑','독립통제','감사조정','모듈연결')}
    config = dict(context, 통화='KRW', 추출범위=';'.join(ACCOUNTS))
    tables['설정'] = [{'항목': k, '값': v} for k, v in config.items()]
    totals = defaultdict(lambda: [0,0,0])
    start, end = day(context['시작일']), day(context['기준일'])
    for n, (journal, memo, entries) in enumerate(JOURNALS):
        dt = min(start+timedelta(days=n+1), end).isoformat()
        for i, (account, debit, credit) in enumerate(entries, 1):
            tables['총계정원장'].append({'회사코드': context['회사코드'], '전표ID': journal,
                '행ID': 'L'+str(i), '전기일': dt, '계정코드': account,
                '차변': debit, '대변': credit, '적요': memo, '작성자': '가상 입력자'})
            t=totals[account]; t[0]+=1; t[1]+=debit; t[2]+=credit
    for account, (name, opening, statement) in ACCOUNTS.items():
        count, debit, credit = totals[account]
        tables['시산표'].append({'회사코드': context['회사코드'], '계정코드': account, '계정명': name,
            '기초잔액': opening, '당기차변': debit, '당기대변': credit, '기말잔액': opening+debit-credit})
        tables['계정매핑'].append({'계정코드':account, '리드코드':account,
            '리드명':name, '표시구분':statement})
        tables['독립통제'].append(dict(context, 계정코드=account, 원장행수=count,
            차변합계=debit, 대변합계=credit, 기초잔액=opening, 기말잔액=opening+debit-credit,
            추출근거='고정된 가상 20전표 기준, 실제 ERP 추출 아님',
            추출일시='2026-12-31T23:00:00+09:00', 작성자='가상 통제 담당자'))
    for sheet, rows in tables.items():
        for n, row in enumerate(rows, 2): row.update(_sheet=sheet, _row=n)
    return tables


def ledger_result(context=None):
    from ledger import analyze
    context = dict(context or CONTEXT)
    result = analyze(ledger_tables(context))
    result['context'] = context
    return result
