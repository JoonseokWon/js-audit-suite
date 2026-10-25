"""Invented examples tied to the common 20-journal demo, with no approval."""
from copy import deepcopy
from datetime import timedelta
from common import day
from onboarding import SCHEMA
from onboarding.contracts import gl_key, ledger_basis
from onboarding.demo import ledger_result
from .shared import FIELDS, population_hash


def row(ident, refs=(), **values):
    return dict(record_id=ident, source_ref='SYNTHETIC ONLY/'+ident, gl_refs=list(refs), **values)


def asset_data(index, tb):
    def refs(journal): return [k for k in index if k.startswith(journal+'/')]
    def movement(ident, aid, kind, journal, cost=0, accum=0, pair='', proceeds=0, gain=0):
        return row(ident, refs(journal), asset_id=aid, kind=kind,
            date=index[refs(journal)[0]]['전기일'], cost_delta=cost, accum_delta=accum,
            pair_id=pair, proceeds=proceeds, gain=gain, cash_account='1000', gain_account='4100')
    return {'assets': [row('A-PPE', (), asset_id='PPE1', asset_type='PPE',
        cost_account='1500', accum_account='1590', opening_cost=50000, closing_cost=90000,
        opening_accum=10000, closing_accum=15000), row('A-CIP', (), asset_id='CIP1',
        asset_type='CIP', cost_account='1600', accum_account='', opening_cost=0,
        closing_cost=20000, opening_accum=0, closing_accum=0)], 'asset_movements': [
        movement('M1','CIP1','acquisition','J04',80000),
        movement('M2','PPE1','transfer_in','J05',60000,pair='T1'),
        movement('M3','CIP1','transfer_out','J05',-60000,pair='T1'),
        movement('M4','PPE1','depreciation','J06',accum=10000),
        movement('M5','PPE1','disposal','J16',-20000,-5000,proceeds=25000,gain=10000),
        movement('M6','CIP1','cancellation_in','J18',5000,pair='C1'),
        movement('M7','CIP1','cancellation_out','J19',-5000,pair='C1')]}


def sampling_data(index, tb):
    population = [row('POP-'+key.replace('/','-'), [key],
                      amount=r['차변']-r['대변']) for key, r in index.items() if r['계정코드']=='1000']
    return {'population': population, 'specific_items': [row('SPEC1', ['J16/L1'],
        population_id='POP-J16-L1', reason='합성 처분거래 특정항목 예시')], 'errors': []}


def confirmation_data(index, tb):
    sources = []; present = set()
    for account, institution, factor, field in (('1000','BANK-A',1,'deposits'),
        ('1010','BANK-B',1,'deposits'),('2100','BANK-A',-1,'borrowings'),('2110','BANK-A',-1,'borrowings')):
        refs = [key for key, r in index.items() if r['계정코드']==account]
        sources.append(row('CUR-'+account,refs,institution_id=institution,source_type='current',
            field=field,book_amount=tb[account]['기말잔액']*factor,account_code=account,factor=factor))
        present.add((institution,field))
    for ident, institution, kind, field, amount in (('PRIOR','BANK-CLOSED','prior','deposits',0),
        ('CLOSED','BANK-CLOSED','closed','deposits',0),('ZERO','BANK-ZERO','zero','deposits',0),
        ('GUAR','BANK-GUARANTEE','guarantee','guarantees',10000),
        ('COLL','BANK-A','collateral','collateral',60000)):
        sources.append(row(ident,(),institution_id=institution,source_type=kind,field=field,
                           book_amount=amount,account_code='',factor=1)); present.add((institution,field))
    institutions = sorted({r['institution_id'] for r in sources})
    fields = ['deposits','borrowings','guarantees','collateral','restrictions']
    for institution in institutions:
        for field in fields:
            if (institution,field) not in present:
                sources.append(row(institution+'-'+field,(),institution_id=institution,
                    source_type='zero',field=field,book_amount=0,account_code='',factor=1))
    requests=[row('REQ-'+str(n),(),institution_id=inst,request_id='Q'+str(n),
                   requested_fields=fields[:]) for n,inst in enumerate(institutions,1)]
    return dict(institution_sources=sources, requests=requests, responses=[])


def note_data(index, tb):
    balances=[]; movements=[]
    for account, factor, category in (('1500',1,'asset'),('1590',-1,'accum'),
        ('1600',1,'cip'),('2100',-1,'loan'),('2110',-1,'loan')):
        bid='NB'+account
        balances.append(row(bid,(),note_id='N-PPE' if category!='loan' else 'N-LOAN',
            account_code=account,factor=factor,category=category,
            opening_asis=tb[account]['기초잔액']*factor,closing_asis=tb[account]['기말잔액']*factor))
        for key,r in index.items():
            if r['계정코드']!=account: continue
            journal=key.split('/')[0]; refs=[k for k in index if k.startswith(journal+'/')]
            is_cash=any(index[k]['계정코드'] in ('1000','1010') for k in refs)
            movements.append(row('NM-'+account+'-'+key.replace('/','-'),refs,balance_id=bid,
                kind='cash' if is_cash else 'noncash', amount=(r['차변']-r['대변'])*factor,
                evidence_type='synthetic_transaction_support'))
    components=[row('LOAN-LT',[k for k,r in index.items() if r['계정코드']=='2100'],
        note_id='N-LOAN',component_kind='loan',account_code='2100',amount=300000,as_is_amount=300000,
        related_id='',details='합성 장기차입 계약 원금',evidence_type='contract'),
        row('LOAN-CUR',[k for k,r in index.items() if r['계정코드']=='2110'],
        note_id='N-LOAN',component_kind='loan',account_code='2110',amount=50000,as_is_amount=50000,
        related_id='',details='합성 유동성장기차입 원금',evidence_type='contract'),
        row('COLLATERAL',['J05/L1'],note_id='N-LOAN',component_kind='collateral',account_code='1500',
        amount=60000,as_is_amount=60000,related_id='LOAN-LT',details='합성 기계 담보 설정액',evidence_type='registry')]
    return dict(note_balances=balances,note_movements=movements,note_components=components)


def classification_data(index, tb, context):
    from .classification import CRITERIA
    acquired=max(day(context['시작일']),day(context['기준일'])-timedelta(days=30))
    items=[row('CLASS1',['J17/L1'],account_code='1010',amount=20000,as_is_class='financial_asset',
        proposed_class='cash_equivalent',acquisition_date=acquired.isoformat(),
        maturity_date=(acquired+timedelta(days=60)).isoformat(),proposal_actor='SYNTHETIC ONLY 제안자',
        proposal_reason='단기 지급 목적·계약 조건의 가상 제안이며 실제 판단 아님')]
    evidence=[row('CE'+str(n),(),item_id='CLASS1',criterion=criterion,status='supported',
        observation='SYNTHETIC ONLY: '+criterion+' 관련 명시된 계약·목적 관찰 예시')
        for n,criterion in enumerate(CRITERIA,1)]
    return dict(classification_items=items,classification_evidence=evidence)


def build(area, context):
    ledger=ledger_result(context); index={gl_key(r):r for r in ledger['tables']['입력_총계정원장']}
    tb={r['계정코드']:r for r in ledger['tables']['입력_시산표']}
    builders={'유형자산증감':asset_data,'감사표본선정':sampling_data,
              '금융기관조회':confirmation_data,'주석구성대사':note_data}
    data=classification_data(index,tb,context) if area=='분류검토' else builders[area](index,tb)
    policy=dict(policy_version='SYNTHETIC-1',standard_ref='IAS16/IAS7 및 ISA500/505/530 참고·국내 적용 확인 필요',
                basis='unadjusted',currency='KRW',ledger_basis_hash=ledger_basis(ledger))
    if area=='감사표본선정': policy.update(materiality=100000,performance_materiality=75000,
        high_threshold=50000,random_size=1,seed='JS-2026-SAMPLE-01',negative_policy='separate_full',
        selection_method='seeded_hash_rank',sampling_unit='gl_line',account_codes='1000',amount_basis='signed')
    if area=='유형자산증감': policy['asset_account_codes']='1500,1590,1600'
    if area=='금융기관조회': policy['financial_account_codes']='1000,1010,2100,2110'
    if area=='주석구성대사': policy['cash_account_codes']='1000,1010'
    payload=dict(schema=SCHEMA,context=dict(context),policy=policy,approval={},**data)
    policy['population_hash']=population_hash(area,payload)
    return payload


def negatives(area, context):
    original=build(area,context); cases={}
    def case(name): cases[name]=deepcopy(original); return cases[name]
    if area=='유형자산증감':
        case('CIP대체한쪽누락')['asset_movements'].pop(2)
        p=case('대체중복'); p['asset_movements'].append(dict(p['asset_movements'][1],record_id='M-DUP'))
        case('처분손익오류')['asset_movements'][4]['gain']=9999
        case('취소모집단누락')['asset_movements'].pop()
    elif area=='감사표본선정':
        p=case('모집단중복'); p['population'].append(deepcopy(p['population'][0]))
        case('모집단누락')['population'].pop()
        case('음수부호왜곡')['population'][2]['amount']=80000
        case('규모초과')['policy']['random_size']=999
    elif area=='금융기관조회':
        p=case('0잔액기관누락'); p['requests']=[r for r in p['requests'] if r['institution_id']!='BANK-ZERO']
        p=case('부분회신'); q=p['requests'][0]; p['responses']=[row('RESP1',(),institution_id=q['institution_id'],
            request_id=q['request_id'],field='deposits',amount=1068000,as_of=context['기준일'],
            details='가상 일부 항목만 회신',authenticity='unverified',reviewer='',reason='')]
        p=case('다른기준일'); q=p['requests'][0]; p['responses']=[row('RESP2',(),institution_id=q['institution_id'],
            request_id=q['request_id'],field='collateral',amount=60000,as_of=(day(context['기준일'])-timedelta(days=1)).isoformat(),
            details='가상 다른 날짜 담보 회신',authenticity='person_claimed',reviewer='SYNTHETIC ONLY',reason='가상입력')]
    elif area=='주석구성대사':
        p=case('비현금대체누락'); p['note_movements']=[r for r in p['note_movements'] if 'J20' not in r['record_id']]
        case('담보차입연결누락')['note_components'][2]['related_id']='MISSING'
        case('주석현재잔액차이')['note_balances'][0]['closing_asis']=89999
    else:
        case('정성근거누락')['classification_evidence'].pop()
        case('제한증거상충')['classification_evidence'][3]['status']='contradicted'
        case('장기상품잔존3개월')['classification_items'][0]['acquisition_date']=context['시작일']
        case('금액원장차이')['classification_items'][0]['amount']=19999
    for payload in cases.values(): payload['policy']['population_hash']=population_hash(area,payload)
    return cases
