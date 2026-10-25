"""Synthetic test helpers; approval here is not an actual user approval."""
from copy import deepcopy
from common import digest
from onboarding import cashflow
from onboarding.contracts import ledger_basis
from onboarding.demo import CONTEXT, ledger_result, ledger_tables


def stamp(payload):
    payload['approval'] = {'actor':'SYNTHETIC ONLY 테스트 확인자',
        'reason':'SYNTHETIC ONLY 독립 숫자·오류 검증; 실제 감사 수행·승인이 아님',
        'input_hash':digest({k:payload.get(k) for k in cashflow.APPROVAL_FIELDS})}
    return payload


def normal():
    return cashflow.sample(CONTEXT), ledger_result(CONTEXT)


def run(payload=None, ledger=None):
    p, l = normal()
    return cashflow.analyze(stamp(payload if payload is not None else p), CONTEXT,
                            ledger if ledger is not None else l)


def codes(result):
    return {i['code'] for i in result['issues']}


def set_flow(payload, line, value):
    for row in payload['reported_flows']:
        if row['line'] == line:
            row['amount'] = value
            return
    payload['reported_flows'].append({'line':line,'amount':value})


def extend_ledger(entries, *, new_accounts=(), adjustments=False):
    """Recompute source totals for explicit invented additions, not result caches."""
    from ledger import analyze
    tables = ledger_tables(CONTEXT)
    for code,name,opening,statement in new_accounts:
        tables['시산표'].append({'회사코드':CONTEXT['회사코드'],'계정코드':code,'계정명':name,
            '기초잔액':opening,'당기차변':0,'당기대변':0,'기말잔액':opening})
        tables['계정매핑'].append({'계정코드':code,'리드코드':code,'리드명':name,'표시구분':statement})
        tables['독립통제'].append(dict(CONTEXT,계정코드=code,원장행수=0,차변합계=0,대변합계=0,
            기초잔액=opening,기말잔액=opening,추출근거='SYNTHETIC ONLY 명시 추가 거래',
            추출일시='2026-12-31T23:00:00+09:00',작성자='SYNTHETIC ONLY'))
        for r in tables['설정']:
            if r['항목']=='추출범위': r['값']+=';'+code
    if adjustments:
        for i,(code,debit,credit) in enumerate(entries,1):
            tables['감사조정'].append({'조정ID':'A01','행ID':'L'+str(i),'계정코드':code,
                '차변':debit,'대변':credit,'근거':'SYNTHETIC ONLY 추가 상각','상태':'승인'})
    else:
        for i,(code,debit,credit) in enumerate(entries,1):
            tables['총계정원장'].append({'회사코드':CONTEXT['회사코드'],'전표ID':'J21',
                '행ID':'L'+str(i),'전기일':'2026-12-31','계정코드':code,
                '차변':debit,'대변':credit,'적요':'SYNTHETIC ONLY 추가 거래','작성자':'SYNTHETIC ONLY'})
            for r in tables['시산표']:
                if r['계정코드']==code:
                    r['당기차변']+=debit; r['당기대변']+=credit; r['기말잔액']+=debit-credit
            for r in tables['독립통제']:
                if r['계정코드']==code:
                    r['원장행수']+=1; r['차변합계']+=debit; r['대변합계']+=credit; r['기말잔액']+=debit-credit
    for name,rows in tables.items():
        for i,row in enumerate(rows,2):row.update(_row=i,_sheet=name)
    result=analyze(tables); result['context']=dict(CONTEXT)
    if result['blocking']:raise AssertionError(result['issues'])
    return result
