"""A new 10,002-row boundary fixture with independent integer expectations."""
from openpyxl import Workbook
from ledger import SCHEMA


def create(path,journals=5001):
    if path.exists():raise FileExistsError('이전 대용량 검증 입력을 보존하세요.')
    book=Workbook(write_only=True);sheets={}
    for name,headers in SCHEMA.items():
        sheet=book.create_sheet(name);sheet.append(headers);sheets[name]=sheet
    for key,value in {'회사코드':'LARGE_DEMO','시작일':'2026-01-01','기준일':'2026-01-31',
                      '통화':'KRW','추출범위':'0001;0002'}.items():sheets['설정'].append([key,value])
    for code,name,debit,credit in [('0001','보통예금',journals,0),('0002','매출',0,journals)]:
        sheets['시산표'].append(['LARGE_DEMO',code,name,0,debit,credit,debit-credit])
        sheets['독립통제'].append(['LARGE_DEMO','2026-01-01','2026-01-31',code,journals,
            debit,credit,0,debit-credit,'독립 지정 기대값. 실제 외부 감사증거 아님.',
            '2026-02-02T09:00:00+09:00','SYNTHETIC ONLY'])
    sheets['계정매핑'].append(['0001','CASH','현금및현금성자산','BS'])
    sheets['계정매핑'].append(['0002','SALES','매출','PL'])
    for index in range(journals):
        for line,account,debit,credit in [('001','0001',1,0),('002','0002',0,1)]:
            sheets['총계정원장'].append(['LARGE_DEMO',f'L-{index:07d}',line,'2026-01-05',account,
                debit,credit,'SYNTHETIC ONLY 경계 검사','SYNTHETIC ONLY'])
    path.parent.mkdir(parents=True,exist_ok=True);book.save(path);book.close()
    return {'rows':journals*2,'total':journals}
