"""Two local non-completion noun scopes; never a document-wide disclaimer.

Only the bare noun '감사 완료' can be qualified here. Finite completion verbs,
other matched assertions and other clauses must still pass their own checks.
"""
import re

_BARE_AUDIT_COMPLETION=re.compile(r'감사\s*완료')
_BEFORE_STAGE=re.compile(
    r'^\s*전\s*단계(?=\s|$|[,;]|에|에서|이며|이지만|지만|이다|입니다|임|인|였다|다)')
_UNCONFIRMED_WHETHER=re.compile(
    r'^\s*여부는\s*확인되지\s*않(?:았습니다|았다|았음|습니다|는다|음)'
    r'(?=\s|$|[,;]|만(?:\s|$))')


def local_noncompletion_scope(expression_index,matched,local_suffix):
    if expression_index!=2 or not _BARE_AUDIT_COMPLETION.fullmatch(matched):
        return False
    return bool(_BEFORE_STAGE.match(local_suffix) or _UNCONFIRMED_WHETHER.match(local_suffix))
