"""Hand-specified synthetic expectations, independent of the tested calculations."""
from pathlib import Path
import sys,json,copy,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import ledger,extensions
from engines.finance.engine import SCHEMA as FS,CONDITIONS
from engines.finance.practice_engine import EXTRA_SCHEMA
from engines.sales.data_io import IMPORT_FIELDS
from engines.assets.engine import SCHEMA as AS
CTX={'회사코드':'SYNTH01','시작일':'2026-01-01','기준일':'2026-12-31'}
def settings(scope):return [['회사코드','SYNTH01'],['시작일','2026-01-01'],['기준일','2026-12-31'],['통화','KRW'],['추출범위',scope]]
def ledger_base():
    t={k:[] for k in ledger.SCHEMA}
    # Account gross amounts below are independently hand specified for three balanced journals.
    accounts=[['1100','정기예금',1000000,0,0,1000000],['1200','미수이자',0,36400,0,36400],['1300','매출채권',0,110000,0,110000],['1500','기계',1200000,0,0,1200000],['1590','상각누계',-240000,0,240000,-480000],['2100','부가세',0,0,10000,-10000],['3000','자본',-1960000,0,0,-1960000],['4000','매출',0,0,100000,-100000],['4100','이자수익',0,0,36400,-36400],['5000','감가상각비',0,240000,0,240000]]
    t['설정']=settings(';'.join(r[0] for r in accounts))
    t['시산표']=[['SYNTH01']+r for r in accounts]
    t['총계정원장']=[['SYNTH01','J-I','1','2026-12-31','1200',36400,0,'합성 이자','합성작성자'],['SYNTH01','J-I','2','2026-12-31','4100',0,36400,'합성 이자','합성작성자'],['SYNTH01','J-S','1','2026-09-21','1300',110000,0,'합성 매출','합성작성자'],['SYNTH01','J-S','2','2026-09-21','4000',0,100000,'합성 매출','합성작성자'],['SYNTH01','J-S','3','2026-09-21','2100',0,10000,'합성 세금','합성작성자'],['SYNTH01','J-D','1','2026-12-31','5000',240000,0,'합성 상각','합성작성자'],['SYNTH01','J-D','2','2026-12-31','1590',0,240000,'합성 상각','합성작성자']]
    counts={'1200':1,'4100':1,'1300':1,'4000':1,'2100':1,'5000':1,'1590':1}
    for k,name,op,d,cr,close in accounts:
        t['계정매핑'].append([k,k,name,'PL' if k in ('4000','4100','5000') else 'BS'])
        t['독립통제'].append(['SYNTH01','2026-01-01','2026-12-31',k,counts.get(k,0),d,cr,op,close,'SYNTHETIC ONLY / 별도 ERP 화면 '+k,"'2027-01-05T09:00:00+09:00",'합성추출자'])
    t['모듈연결']=[['금융상품','원금','1100','기말잔액',1],['금융상품','미수이자','1200','기말잔액',1],['매출','순매출','4000','당기순변동',-1],['감가상각','기말원가','1500','기말잔액',1],['감가상각','기말누계','1590','기말잔액',-1],['감가상각','당기상각','5000','당기순변동',1]]
    return t
def ext_base():
    t={k:[] for k in extensions.SCHEMA};t['설정']=settings('SYNTHETIC ONLY / 4종 제한 검사')
    t['은행장부']=[['BANK01','L1','2026-09-21','REF01',1000],['BANK01','L2','2026-09-22','REF02',-200]]
    t['은행거래']=[['BANK01','B1','2026-09-21','REF01',1000],['BANK01','B2','2026-09-22','REF02',-200]]
    t['채권']=[['AR1','C01','2026-09-21','2026-10-01',110000]]
    t['후속회수']=[['R1','AR1','2027-01-10',60000,'SYNTHETIC ONLY / 은행입금']]
    t['발주']=[['PO1','ITEM1',10,100]];t['입고']=[['GR1','PO1',6],['GR2','PO1',4]];t['매입송장']=[['PI1','PO1',10,1000]]
    t['장부재고']=[['WH1','ITEM1','EA',10]];t['실사']=[['WH1','ITEM1','EA',10,'2026-12-31','SYNTHETIC ONLY / 실사표']]
    hand={'은행장부':(2,800,1200),'은행거래':(2,800,1200),'채권':(1,110000,110000),'후속회수':(1,60000,60000),'발주':(1,10,10),'입고':(2,10,10),'매입송장':(1,1000,1000),'장부재고':(1,10,10),'실사':(1,10,10)}
    t['독립통제']=[[k,*v,'SYNTHETIC ONLY / 독립 통제 예시'] for k,v in hand.items()];return t
def main():
    books=[]
    def add(name,module,schema,t,expected):books.append({'name':name,'module':module,'headers':schema,'tables':t,'expected':expected})
    b=ledger_base();add('통합_01_원장정상','원장·리드',ledger.SCHEMA,copy.deepcopy(b),{'blocking':0,'lead_rows':10,'checks':83})
    changes=[('02_상계되는원장누락','LEDGER_CONTROL',lambda t:t['총계정원장'].__delitem__(slice(0,2))),('03_전표한쪽누락','JE_UNBALANCED',lambda t:t['총계정원장'].pop()),('04_전표중복','GL_DUP',lambda t:t['총계정원장'].append(copy.deepcopy(t['총계정원장'][0]))),('05_TB변동오류','LEDGER_CONTROL',lambda t:t['시산표'][0].__setitem__(6,1000001)),('06_미매핑','ACCOUNT_SCOPE',lambda t:t['계정매핑'].pop()),('07_통제누락','ACCOUNT_SCOPE',lambda t:t['독립통제'].pop()),('08_통제총액오류','LEDGER_CONTROL',lambda t:t['독립통제'][1].__setitem__(5,36401)),('09_통제중복','CONTROL_DUP',lambda t:t['독립통제'].append(copy.deepcopy(t['독립통제'][0]))),('10_추출시각오류','CONTROL_TIME',lambda t:t['독립통제'][0].__setitem__(10,'2025-01-01')),('11_회사혼합','COMPANY',lambda t:t['총계정원장'][0].__setitem__(0,'OTHER')),('12_기간밖','PERIOD',lambda t:t['총계정원장'][0].__setitem__(3,'2025-12-31')),('13_미승인조정','AJE_DRAFT',lambda t:t['감사조정'].extend([['AD1','1','1500',100,0,'SYNTHETIC ONLY','초안'],['AD1','2','3000',0,100,'SYNTHETIC ONLY','초안']])),('14_불균형조정','AJE_UNBALANCED',lambda t:t['감사조정'].append(['AD1','1','1500',100,0,'SYNTHETIC ONLY','승인'])),('15_연결설정오류','BIND_INVALID',lambda t:t['모듈연결'][0].__setitem__(1,'미지원지표')),('16_동시계정누락','EXTRACTION_SCOPE',lambda t:[t[k].__delitem__(0) for k in ('시산표','계정매핑','독립통제')])]
    for name,code,change in changes:
        t=copy.deepcopy(b);change(t);add('통합_'+name,'원장·리드',ledger.SCHEMA,t,{'code':code})
    t=copy.deepcopy(b);t['감사조정']=[['AD1','1','1500',100,0,'SYNTHETIC ONLY','승인'],['AD1','2','3000',0,100,'SYNTHETIC ONLY','승인']];add('통합_17_승인조정','원장·리드',ledger.SCHEMA,t,{'blocking':0,'adjusted_asset':1200100})
    e=ext_base();add('확장_01_정상','확장검사',extensions.SCHEMA,copy.deepcopy(e),{'blocking':0,'review':0,'ar_recovered':60000,'ar_days':91,'bank_matched':2})
    for name,code,change in [('02_양쪽은행누락','EXT_CONTROL',lambda t:[t[k].pop() for k in ('은행장부','은행거래')]),('03_은행모호성','BANK_UNMATCHED',lambda t:t['은행거래'].append(['BANK01','B3','2026-09-21','REF01',1000])),('04_입고미청구','PURCHASE_REVIEW',lambda t:t['매입송장'].clear()),('05_재고수량차이','INVENTORY_REVIEW',lambda t:t['실사'][0].__setitem__(3,9)),('06_채권없는입금','RECEIPT_ORPHAN',lambda t:t['후속회수'][0].__setitem__(1,'MISSING')),('07_실사일다름','COUNT_DATE',lambda t:t['실사'][0].__setitem__(4,'2026-12-30')),('08_은행중복ID','EXT_DUP',lambda t:t['은행거래'][1].__setitem__(1,'B1'))]:
        t=copy.deepcopy(e);change(t);add('확장_'+name,'확장검사',extensions.SCHEMA,t,{'code':code})
    f={k:[] for k in {'설정':['항목','값'],**FS,**EXTRA_SCHEMA}};f['설정']=[['기준일','2026-12-31'],['원금허용오차',0],['이자허용오차',0]]
    for k in ('명세','원장','회신'):f[k]=[['SYNBANK','D001','2026-12-31','KRW','원',1000000,36400]]
    f['조건']=[['SYNBANK','D001','2026-12-31','KRW','원','단순 정기예금',1000000,3.65,'%','2026-01-01','2026-12-31','2026-01-01','2026-12-31','ACT/365F','제외','포함','아니오','아니오','아니오','아니오']]
    f['이자기준']=[['SYNBANK','D001','2026-12-31','2026-01-01','제외','포함','SYNTHETIC ONLY / 계약']];f['이자구간']=[['SYNBANK','D001','S1','2026-01-01','2026-12-31','제외','포함']]
    add('통합업무_금융정상','금융상품',{'설정':['항목','값'],**FS,**EXTRA_SCHEMA},f,{'blocking':0,'review':0,'metric':{'원금':1000000,'미수이자':36400}})
    s={'orders':[['O1','1','P1','C1','2026-09-01',10,'EA',10000,'NET',0.1,'KRW']], 'deliveries':[['D1','1','O1','1','P1','C1','2026-09-10','2026-09-11',10,10,'EA']], 'invoices':[['I1','1','O1','1','P1','C1','2026-09-21',10,'EA',10000,'NET',0.1,'KRW',100000,10000,110000]],'ledger':[['J-S','2','SYNTH01','4000','2026-09-21','I1','1','C1','KRW',0,100000]],'control':[['SYNTH01','2026-01-01','2026-12-31','4000',1,0,100000,'SYNTHETIC ONLY / ERP',"'2027-01-05T09:00:00+09:00",'합성추출자']]}
    add('통합업무_매출정상','매출',IMPORT_FIELDS,s,{'blocking':0,'review':0,'metric':{'순매출':100000}})
    a={k:[] for k in AS};a['설정']=[[k,v] for k,v in {**CTX,'개시월':'당월','처분월':'포함','허용오차':0,'정책근거':'SYNTHETIC ONLY / 월할','모형범위':'원가모형-손상등없음'}.items()];a['자산']=[['SYNTH01','A01','합성 기계','유형','2025-01-01','2025-01-01',1200000,0,60,'정액법',None,None,None,None,1200000,240000,240000,1200000,480000,'SYNTHETIC ONLY / 검수계약']];a['원장']=[['SYNTH01','A01',1200000,240000,240000,1200000,480000,'SYNTHETIC ONLY / ERP']];a['통제']=[['SYNTH01','2026-01-01','2026-12-31','1500;1590;5000',1,1200000,240000,240000,1200000,480000,'SYNTHETIC ONLY / ERP',"'2027-01-05T09:00:00+09:00",'합성추출자']]
    add('통합업무_감가상각정상','감가상각',AS,a,{'blocking':0,'review':0,'metric':{'기말원가':1200000,'기말누계':480000,'당기상각':240000}})
    for name,module,schema,base in [('원장리드_입력양식','원장·리드',ledger.SCHEMA,b),('확장검사_입력양식','확장검사',extensions.SCHEMA,e)]:
        add(name,module,schema,{k:(settings('계정코드를 세미콜론으로 입력') if k=='설정' else []) for k in schema},{'template':True})
    (ROOT/'samples_specs.json').write_text(json.dumps({'context':CTX,'books':books},ensure_ascii=False,indent=2),encoding='utf-8')
    # Preserve existing independent expectations and original XLSX files without rewriting.
    old=ROOT.parents[1]/'감사도구 로컬패키지/v2.1_벤치마킹_2026-10-22'
    for kind in ('금융상품','매출 자동화'):shutil.copy2(old/kind/'samples/v2_cases.json',ROOT/'samples/기존'/kind/'v2_cases.json')
    print('New workbooks:',len(books))
if __name__=='__main__':main()
