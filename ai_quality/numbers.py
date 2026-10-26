"""Check number tokens against each field's cited data, without deriving facts.

Presence of a token does not prove its meaning, account, timing, or correctness.
Unsupported numbers are rejected; there is no response repair or auto-calculation.
"""
from decimal import Decimal, InvalidOperation
import re
import unicodedata

_REFERENCE = re.compile(r'\[[A-Z]{1,8}[0-9]{3,5}\]')
_NUMBER = re.compile(r'(?<![A-Za-z0-9_])[-+]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)'
                     r'(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?(?![A-Za-z0-9_])')
_UNIT = re.compile(r'^\s*(천만원|백만원|억원|만원|천원|조원|%|퍼센트)')
_DATE = re.compile(r'(?<![0-9])(?:19|20)[0-9]{2}(?:-[0-9]{1,2}-[0-9]{1,2}'
                   r'|/[0-9]{1,2}/[0-9]{1,2}|년(?:\s*[0-9]{1,2}월(?:\s*[0-9]{1,2}일)?)?)(?![0-9])')
_SCALE = {'원':1, '천원':1000, '만원':10000, '백만원':1000000,
          '천만원':10000000, '억원':100000000, '조원':1000000000000,
          '%':Decimal('0.01'), '퍼센트':Decimal('0.01')}


def _tokens(value):
    text = unicodedata.normalize('NFKC', str(value))
    text = _REFERENCE.sub('', text)
    dates=list(_DATE.finditer(text))
    for match in dates:
        for component in re.findall(r'[0-9]+',match.group()):yield Decimal(component),'date'
    for match in _NUMBER.finditer(text):
        if any(match.start()<date.end() and match.end()>date.start() for date in dates):continue
        try:
            number = Decimal(match.group().replace(',', ''))
            if not number.is_finite():continue
            unit = _UNIT.match(text[match.end():])
            if unit:number *= _SCALE[unit.group(1)]
            yield number,'fact'
        except (InvalidOperation, OverflowError):continue


def _values(value):
    if isinstance(value, dict):
        for item in value.values():yield from _values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:yield from _values(item)
    elif type(value) in (int, float, str, Decimal):
        yield from _tokens(value)


def numeric_support_report(packet, fields, citations):
    """Only cited reference data plus explicit company/period context count."""
    refs = {ref['id']:ref for ref in packet.get('references', [])}
    engagement=packet.get('engagement', {})
    context_dates={number for number,kind in _values({
        key:engagement.get(key,'') for key in ('start_date','end_date')}) if kind=='date'}
    fields_report = {}
    unsupported = []
    for field, text in fields.items():
        allowed_facts=set();allowed_dates=set(context_dates)
        for ref_id in citations.get(field, []):
            if ref_id in refs:
                for number,kind in _values(refs[ref_id].get('data')):
                    (allowed_dates if kind=='date' else allowed_facts).add(number)
        observed = list(_tokens(text))
        missing = [number for number,kind in observed
                   if number not in (allowed_dates if kind=='date' else allowed_facts)]
        fields_report[field] = {'checked_tokens':len(observed), 'unsupported_tokens':len(missing)}
        if missing:unsupported.append(field)
    return {'schema':'ai-numeric-support-1', 'passed':not unsupported,
            'fields':fields_report, 'unsupported_fields':unsupported,
            'scope':'Cited numeric token presence only; semantic correctness and final judgement require human review.'}


def validate_numeric_support(packet, fields, citations):
    report = numeric_support_report(packet, fields, citations)
    if not report['passed']:
        raise ValueError('AI 초안에 인용한 근거에서 확인되지 않는 수치가 있습니다. 초안을 저장하지 않았습니다.')
    return report
