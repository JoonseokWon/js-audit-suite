"""Independent frozen/source regression expectations."""
def verify_result(result,expected):
    s=result['summary']
    for key in ('MATCHED','source_rows'):
        if key in expected:assert s[key]==expected[key],s
    if 'population' in expected:assert s['population_status']==expected['population'],s
    if 'code' in expected:assert any(x['reason_code']==expected['code'] for x in result['issues']),(expected,result['issues'])
    if 'amount_differences' in expected:assert sum(x['reason_code']=='LEDGER_AMOUNT_MISMATCH' for x in result['issues'])==expected['amount_differences']
    if 'tieouts_pass' in expected:assert sum(x['status']=='PASS' for x in result['ledger_reconciliation'])==expected['tieouts_pass']
    if s['population_status']=='FAIL':assert s['MATCHED']==0,s
    return {'summary':s,'reason_codes':list(dict.fromkeys(x['reason_code'] for x in result['issues']))}
