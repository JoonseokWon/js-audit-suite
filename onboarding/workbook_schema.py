"""Declarative workbook columns; metadata describes values, never executable code."""
from common import AuditError
from onboarding import SCHEMA

GROUP_LABELS = {
    'context':'업무정보','config':'자료설정','policy':'계산정책','source_rows':'원본자료',
    'column_mapping':'열연결','coa_mapping':'계정연결','opening_balances':'기초잔액',
    'trial_balance':'시산표','independent_controls':'독립통제','adjustments':'감사조정',
    'presentation_mapping':'본문주석연결','presentation_values':'회사제시금액',
    'assets':'자산기초','asset_movements':'자산증감','population':'표본모집단',
    'specific_items':'특정항목','errors':'발견차이','institution_sources':'금융기관목록',
    'requests':'조회요청','responses':'조회회신','note_balances':'주석잔액',
    'note_movements':'주석증감','note_components':'주석구성','classification_items':'분류대상',
    'classification_evidence':'분류확인근거','accounts':'계정역할','movement_tags':'증감원인',
    'cash_allocations':'현금지급배부','depreciation_parts':'상각배부','noncash':'비현금거래',
    'cash_controls':'독립현금통제','reported_flows':'회사제시현금흐름','group_controls':'그룹검증',
}


def metadata(module):
    from onboarding.integration import engine
    provider=engine(module)
    labels=dict(getattr(provider,'FIELD_LABELS',{}))
    declared=getattr(provider,'TABLE_FIELDS',{})
    if module in declared and isinstance(declared[module],dict):declared=declared[module]
    return labels,declared


def value_type(value):
    return 'list' if isinstance(value,list) else 'bool' if isinstance(value,bool) else 'value'


def descriptors(module,payload):
    labels,declared=metadata(module)
    output=[]
    for key,value in payload.items():
        if key in ('schema','area','approval') or key.startswith('_'):continue
        if not isinstance(value,(dict,list)):raise AuditError('입력 양식은 표·항목별 값만 지원합니다: '+key)
        kind='dict' if isinstance(value,dict) else 'list'
        keys=list(value) if kind=='dict' else list(declared.get(key,()))
        if kind=='list':
            for row in value:
                if not isinstance(row,dict):raise AuditError('입력 표의 행은 항목별 값이어야 합니다.')
                keys.extend(k for k in row if k not in keys and not k.startswith('_'))
        if not keys:raise AuditError('빈 입력 표의 열 정의가 없습니다: '+key)
        sheet=GROUP_LABELS.get(key,labels.get(key,key))[:31]
        headers=[labels.get(k,k) for k in keys]
        if len(set(headers))!=len(headers):raise AuditError('입력 열 표시명이 중복입니다: '+sheet)
        types={k:value_type(value.get(k)) if kind=='dict' else
               next((value_type(r[k]) for r in value if k in r and r[k] is not None),'list' if k.endswith('_refs') else 'value') for k in keys}
        output.append({'sheet':sheet,'key':key,'kind':kind,'keys':keys,'headers':headers,'types':types})
    if len({x['sheet'] for x in output})!=len(output):raise AuditError('입력 시트 표시명 중복')
    return output


def encode(value):
    if isinstance(value,list):return '\n'.join(str(x) for x in value)
    if isinstance(value,bool):return '예' if value else '아니오'
    if isinstance(value,dict):raise AuditError('중첩 설정은 별도 표로 입력하세요.')
    return value


def decode(value,kind):
    if kind=='list':
        return [x.strip() for x in str(value).splitlines() if x.strip()] if value not in (None,'') else []
    if kind=='bool':
        if value in ('예',True):return True
        if value in ('아니오',False):return False
        raise AuditError('확인 항목은 예 또는 아니오로 입력하세요.')
    return value
