from decimal import Decimal
def verify(result,expected):
    s=result['summary']
    assert s['모집단']==expected['population'],(s,expected)
    for e,k in [('matched','일치'),('review','검토'),('errors','오류건수'),('differences','차이')]:
        if e in expected:assert s.get(k,0)==expected[e],(k,s,expected)
    if 'min_errors' in expected:assert s['오류건수']>=expected['min_errors'],s
    for aid,values in expected.get('amounts',{}).items():
        g=next(g for g in result['groups'] if g['asset_id']==aid)
        assert g['calculated'] is not None,g
        for k,v in values.items():assert Decimal(g['calculated'][k])==v,(aid,k,g['calculated'],v)
    if 'disposal_gain' in expected:
        gains=[Decimal(g['calculated']['처분손익']) for g in result['groups'] if g['calculated'] and g['calculated']['처분손익'] is not None]
        assert gains==[Decimal(expected['disposal_gain'])],gains
    if 'rounding' in expected:assert sum(f['status']=='반올림차이' for f in result['findings'])==expected['rounding']
    if 'signed' in expected:
        total=next(r for r in result['difference_summary'] if r['비교']=='재계산-대장 당기상각')
        assert Decimal(total['부호합계'])==expected['signed'] and Decimal(total['절대합계'])==expected['absolute'],total
    return dict(s)
