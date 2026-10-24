"""Assert independent case expectations shared by unit and actual-EXE UI runs."""
def verify_result(result,expected):
    if 'counts' in expected:assert result.counts==expected['counts'],result.counts
    if 'rows' in expected:assert len(result.rows)==expected['rows']
    if 'period_error' in expected:
        assert any(f.status=='기간오류' and f.key[1]==expected['period_error'] for f in result.findings)
    if 'blocked_interest' in expected:
        fs=[f for f in result.findings if f.key and f.key[1]==expected['blocked_interest'] and f.check=='명세이자-단순이자']
        assert len(fs)==1 and fs[0].status=='계산불가',fs
    if 'rounding' in expected:
        fs=[f for f in result.findings if f.status=='반올림차이']
        assert len(fs)==expected['rounding']
        assert sum(abs(f.difference) for f in fs)==expected['rounding_abs']
        if 'rounding_net' in expected:assert sum(f.difference for f in fs)==expected['rounding_net']
        assert all(f.difference==0 for f in result.findings if f.status=='금액일치')
    return {'rows':len(result.rows),'counts':result.counts}
