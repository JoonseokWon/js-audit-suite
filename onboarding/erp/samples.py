"""Invented fixtures. Approval fields intentionally stay empty for a person to confirm."""
from collections import defaultdict
from copy import deepcopy
from common import digest
from onboarding import SCHEMA
from onboarding.demo import ledger_tables


def sample(context):
    source=ledger_tables(context)
    payload={'schema':SCHEMA,'context':dict(context),
             'config':{'amount_mode':'two_columns','signed_debit_factor':1,'source_unit':1,
                       'currency':'KRW','tb_state':'unclosed','reporting_basis':'pre_adjustment'},
             **{key:[] for key in ('source_rows','column_mapping','coa_mapping','trial_balance',
                  'independent_controls','adjustments','adjustment_approvals',
                  'presentation_mapping','presentation_values')},
             'approval':{}}
    columns={'journal_id':'전표번호','line_id':'순번','posting_date':'전표일자','source_account':'ERP계정',
             'debit':'차변금액','credit':'대변금액','description':'거래내용','author':'입력담당',
             'department':'원가부문','cancel_of':'취소원행'}
    payload['column_mapping']=[{'target':target,'source':name} for target,name in columns.items()]
    for n,r in enumerate(source['총계정원장'],2):
        debit,credit=r['차변'],r['대변']; cancel=''
        if r['전표ID']=='J19':
            debit,credit=-credit,-debit
            cancel='J18/'+r['행ID']
        values=dict(journal_id=r['전표ID'],line_id=r['행ID'],posting_date=r['전기일'],
                    source_account='ERP_'+r['계정코드'],debit=debit,credit=credit,
                    description=r['적요'],author=r['작성자'],
                    department='제조' if r['전표ID']=='J06' and r['계정코드']=='1200' else '본사',cancel_of=cancel)
        payload['source_rows'].append({columns[key]:value for key,value in values.items()} | {
            'source_file':'가상_ERP_예제(실제추출아님).xlsx','source_sheet':'가상원장',
            'source_row':n,'source_sha256':''})
    fakehash=digest(payload['source_rows'])
    for r in payload['source_rows']:r['source_sha256']=fakehash
    totals=defaultdict(lambda:[0,0])
    for r in payload['source_rows']:
        t=totals[r['ERP계정']];t[0]+=r['차변금액'];t[1]+=r['대변금액']
    account_map={r['계정코드']:r for r in source['계정매핑']}
    for r in source['시산표']:
        code=r['계정코드'];m=account_map[code];bspl=m['표시구분']
        payload['coa_mapping'].append({'source_account':'ERP_'+code,'account_code':code,
            'account_name':r['계정명'],'lead_code':m['리드코드'],'lead_name':m['리드명'],'statement_type':bspl})
        payload['trial_balance'].append({'account_code':code,'opening':r['기초잔액'],
            'debit':r['당기차변'],'credit':r['당기대변'],'closing':r['기말잔액']})
        # These are frozen when a negative case removes/changes raw rows.
        c=next(c for c in source['독립통제'] if c['계정코드']==code)
        d,cr=totals['ERP_'+code]
        payload['independent_controls'].append({'account_code':code,'row_count':c['원장행수'],
            'source_debit_total':d,'source_credit_total':cr,'debit_total':c['차변합계'],
            'credit_total':c['대변합계'],'opening':c['기초잔액'],'closing':c['기말잔액'],
            'extract_basis':'고정 가상 20전표 원본; 파일해시는 가상 선언값이며 실제 ERP 독립추출 아님',
            'extracted_at':context['기준일']+'T23:00:00+09:00','actor':'가상 통제 담당자'})
        sign=-1 if (bspl=='PL' and r['기말잔액']<0) else 1
        mapping={'statement':bspl,'line_id':code,'account_code':code,'basis':'pre_adjustment','sign':sign,
                 'validation_group':'','group_policy':'individual','group_basis':'','ledger_refs':''}
        payload['presentation_mapping'].append(mapping)
        payload['presentation_values'].append({'statement':bspl,'line_id':code,'amount':r['기말잔액']*sign,
                                              'basis':'pre_adjustment','unit':1,'formula':''})
    # A selected manufacturing-cost component is tied to the exact allocation row, not all inventory movement.
    payload['presentation_mapping'].append({'statement':'COST','line_id':'제조감가상각','account_code':'1200',
        'basis':'movement','sign':1,'validation_group':'','group_policy':'individual',
        'group_basis':'','ledger_refs':'J06/L2'})
    payload['presentation_values'].append({'statement':'COST','line_id':'제조감가상각',
        'amount':6000,'basis':'movement','unit':1,'formula':''})
    for code in ('1500','1590'):
        payload['presentation_mapping'].append({'statement':'NOTE','line_id':'유형자산순액','account_code':code,
            'basis':'pre_adjustment','sign':1,'validation_group':'','group_policy':'individual',
            'group_basis':'','ledger_refs':''})
    payload['presentation_values'].append({'statement':'NOTE','line_id':'유형자산순액','amount':75000,
        'basis':'pre_adjustment','unit':1,'formula':''})
    return payload


def negative_cases(context):
    cases={}; base=sample(context)
    def case(name):
        p=deepcopy(base);cases[name]=p;return p
    p=case('차대맞는전표누락');p['source_rows']=[r for r in p['source_rows'] if r['전표번호']!='J01']
    p=case('열오매핑');next(r for r in p['column_mapping'] if r['target']=='posting_date')['source']='거래내용'
    p=case('원본단위착오');p['config']['source_unit']=1000
    p=case('표시부호착오');next(r for r in p['presentation_mapping'] if r['account_code']=='1590')['sign']=-1
    p=case('취소중복');copied=deepcopy(next(r for r in p['source_rows'] if r['전표번호']=='J19'))
    copied.update(전표번호='J21',source_row=100);p['source_rows'].append(copied)
    p=case('조정전후혼용');p['presentation_values'][0]['basis']='post_adjustment'
    p=case('그룹간상쇄');
    for i,delta in ((0,40000),(1,-40000)):
        p['presentation_mapping'][i].update(validation_group='서로다른그룹'+str(i),group_policy='net',group_basis='가상 검토 설정')
        p['presentation_values'][i]['amount']+=delta
    p=case('수식캐시');p['presentation_values'][0].update(formula='SUM(A1:A2)',amount=True)
    p=case('독립통제범위누락');p['independent_controls'].pop()
    return cases
