"""Original synthetic JS data. No approvals, actual customer data or model answers."""
from copy import deepcopy
from onboarding import SCHEMA
from onboarding.contracts import ledger_basis

ACCOUNT_MAP = (
    ('1000','cash','cash',''), ('1010','cash','cash',''),
    ('1100','receivable','receivable',''), ('1200','inventory','inventory',''),
    ('1500','ppe_cost','ppe',''), ('1590','ppe_accum','ppe',''),
    ('1600','cip','cip',''), ('1700','rou_asset','rou',''),
    ('2000','payable','payable',''), ('2100','loan_long','loans',''),
    ('2110','loan_current','loans',''), ('2200','lease_liability','lease',''),
    ('2300','interest_payable','interest',''), ('2400','tax_payable','tax',''),
    ('3000','equity','equity',''), ('4000','revenue','profit','operating'),
    ('4100','disposal_gain','profit','operating'),
    ('5100','depreciation_expense','profit','operating'),
    ('5200','interest_expense','profit','financing'),
    ('5300','current_tax_expense','profit','tax'),
)
GROUPS = (('cash',1000000,1088000), ('receivable',0,20000), ('inventory',10000,46000),
          ('ppe',40000,75000), ('cip',0,20000), ('rou',0,120000),
          ('payable',-20000,-40000), ('loans',-300000,-350000),
          ('lease',0,-110000), ('interest',0,-1000), ('tax',0,-1000),
          ('equity',-730000,-730000))


def sample(context):
    from onboarding.demo import ledger_result
    ledger = ledger_result(context)
    payload = {'schema': SCHEMA, 'context': dict(context), 'approval': {},
        'policy': {'framework':'K-IFRS', 'standard_version':'KIFRS1007_PRE1118',
            'effective_from':'2026-01-01', 'version_end':'2026-12-31',
            'early_adoption':False, 'early_adoption_permitted':False,
            'adoption_basis':'SYNTHETIC ONLY: 2026년 기존 제1007호 예시; 실제 적용 버전은 담당자가 확인',
            'starting_point':'net_profit', 'business_profile':'ordinary_nonfinancial',
            'interest_paid':'operating', 'interest_received':'operating',
            'dividends_paid':'financing', 'dividends_received':'operating', 'tax_paid':'operating',
            'inventory_method':'gross_inventory_total_depreciation',
            'ledger_basis_hash':ledger_basis(ledger), 'currency':'KRW',
            'classification_basis':'SYNTHETIC ONLY: 가상 현금계정·계정역할·분류를 사람이 검토하는 예시'},
        'accounts':[dict(zip(('account_code','role','validation_group','profit_category'),r)) for r in ACCOUNT_MAP],
        'movement_tags':[], 'cash_allocations':[],
        'depreciation_parts':[{'kind':'expense','amount':4000,'gl_refs':['J06/L1']},
                              {'kind':'inventory','amount':6000,'gl_refs':['J06/L2']}],
        'noncash':[
            {'item_id':'NC01','kind':'asset_transfer','debit_account':'1500','credit_account':'1600',
             'amount':60000,'gl_refs':['J05/L1','J05/L2']},
            {'item_id':'NC02','kind':'lease_new','debit_account':'1700','credit_account':'2200',
             'amount':120000,'gl_refs':['J10/L1','J10/L2']},
            {'item_id':'NC03','kind':'debt_reclass','debit_account':'2100','credit_account':'2110',
             'amount':50000,'gl_refs':['J20/L1','J20/L2']}],
        'cash_controls':[{'account_code':'1000','opening':1000000,'closing':1068000,
                          'source_ref':'SYNTHETIC ONLY 독립 은행잔액표!2'},
                         {'account_code':'1010','opening':0,'closing':20000,
                          'source_ref':'SYNTHETIC ONLY 독립 은행잔액표!3'}],
        'group_controls':[{'validation_group':g,'opening':a,'closing':b,
                           'source_ref':'SYNTHETIC ONLY 독립 잔액표!'+str(i)}
                          for i,(g,a,b) in enumerate(GROUPS,2)],
        'reported_flows':[{'line':k,'amount':v} for k,v in
            (('net_profit',137000),('CFO',103000),('CFI',-55000),('CFF',40000),
             ('FX',0),('cash_opening',1000000),('cash_closing',1088000))]}
    kinds = {'J01':'operating','J02':'operating','J03':'operating','J04':'asset_cash',
        'J05':'asset_transfer','J06':'depreciation','J07':'operating','J08':'operating',
        'J09':'debt_cash','J10':'lease_new','J11':'debt_cash','J12':'interest_accrual',
        'J13':'interest_cash','J14':'tax_accrual','J15':'tax_cash','J16':'asset_disposal',
        'J17':'internal_transfer','J18':'asset_cash','J19':'asset_cash','J20':'debt_reclass'}
    for row in ledger['tables']['입력_총계정원장']:
        ref = row['전표ID']+'/'+row['행ID']
        kind = 'interest_cash' if ref == 'J11/L2' else 'mixed_cash' if ref == 'J11/L3' else kinds[row['전표ID']]
        payload['movement_tags'].append({'source_ref':ref,'kind':kind})
    raw = (
        ('J01/L1','operating',100000,['J01/L2']),
        ('J03/L1','operating',20000,['J03/L2']),
        ('J04/L2','asset_purchase',-80000,['J04/L1']),
        ('J08/L2','operating',-10000,['J08/L1']),
        ('J09/L1','loan_borrowing',50000,['J09/L2']),
        ('J11/L3','lease_principal',-10000,['J11/L1']),
        ('J11/L3','interest_paid',-1000,['J11/L2']),
        ('J13/L2','interest_paid',-2000,['J13/L1']),
        ('J15/L2','tax_paid',-4000,['J15/L1']),
        ('J16/L1','asset_sale',25000,['J16/L2','J16/L3','J16/L4']),
        ('J17/L1','internal_transfer',20000,['J17/L2']),
        ('J17/L2','internal_transfer',-20000,['J17/L1']),
        ('J18/L2','asset_purchase',-5000,['J18/L1']),
        ('J19/L2','asset_purchase',5000,['J19/L1']))
    payload['cash_allocations'] = [{'allocation_id':'C'+str(i),'parent_gl_ref':ref,
        'component':component,'amount':amount,'gl_refs':[ref,*others]}
        for i,(ref,component,amount,others) in enumerate(raw,1)]
    return payload


def negative_cases(context):
    normal = sample(context)
    cases = {}
    def case(name):
        cases[name] = deepcopy(normal)
        return cases[name]
    p = case('원금이자구성교환'); p['cash_allocations'][5]['amount']=-1000; p['cash_allocations'][6]['amount']=-10000
    p = case('현금중복배부'); p['cash_allocations'].append(deepcopy(p['cash_allocations'][0]))
    p = case('현금미배부'); p['cash_allocations'].pop(6)
    p = case('제조상각중복'); p['depreciation_parts'].append(deepcopy(p['depreciation_parts'][1]))
    p = case('신규리스누락'); p['noncash'].pop(1)
    p = case('정책원장불일치'); p['policy']['ledger_basis_hash']='0'*64
    p = case('무관그룹차이상쇄'); p['group_controls'][3]['closing']+=100; p['group_controls'][4]['closing']-=100
    p = case('내부이체한쪽누락'); p['cash_allocations'].pop(10)
    p = case('원장분류행누락'); p['movement_tags'].pop()
    p = case('현금독립잔액오류'); p['cash_controls'][0]['closing']+=1
    p = case('이자발생현금차이'); p['cash_allocations'][6]['component']='lease_principal'
    p = case('새버전출발점오류'); p['policy']['standard_version']='KIFRS1007_IFRS1118'
    return cases
