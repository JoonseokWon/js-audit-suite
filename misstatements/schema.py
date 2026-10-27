"""Small strict contracts for explicitly entered human assessments."""
import re
from copy import deepcopy
from common import AuditError, dumps, num
from human_input import text
from export_support.text import validate_structure

CLASSIFICATIONS = ('', '미분류', '사실', '판단', '추정투영')
ASSESSMENTS = ('', '검토중', '왜곡표시', '왜곡표시아님')
CORRECTIONS = ('', '수정', '미수정')
PERIODS = ('', '기초', '당기')
QUALITATIVE = ('', '있음', '없음')
COMPANY = ('', '검토중', '수용', '이견있음')
FIELDS = ('id', 'description', 'assessment', 'classification', 'amount',
          'correction_state', 'company_position', 'company_note', 'period',
          'qualitative', 'qualitative_note', 'tax_effect', 'tax_basis',
          'account_impacts', 'candidate_ids', 'evidence_ids', 'procedure_ids',
          'judgment', 'projection_basis')


def payload(value, allowed, required=()):
    if not isinstance(value, dict) or set(value)-set(allowed) or set(required)-set(value):
        raise AuditError('왜곡표시 입력 필드 누락/미지원')
    try:
        if len(dumps(value)) > 200000:raise AuditError('왜곡표시 입력 크기 초과')
    except (TypeError, ValueError, RecursionError) as exc:
        raise AuditError('왜곡표시 JSON/유한 숫자 오류') from exc
    validate_structure(value, '왜곡표시 원본 입력')
    return deepcopy(value)


def optional(value, label):
    if value in ('', None):return ''
    return text(value, label)


def identity(value, label='기록ID'):
    value = text(value, label)
    if not re.fullmatch(r'[A-Za-z0-9가-힣_.-]{1,100}', value):raise AuditError(label+' 형식 오류')
    return value


def ids(value, label):
    if not isinstance(value, list) or len(value)>500:raise AuditError(label+': 목록 한도 오류')
    values = [identity(item, label) for item in value]
    if len(values) != len(set(values)):raise AuditError(label+': 중복 ID')
    return values


def choice(value, allowed, label):
    if value not in allowed:raise AuditError(label+': 명시 선택값 오류')
    return value


def optional_num(value):
    return None if value in ('', None) else num(value)


def impacts(value):
    if not isinstance(value, list) or len(value)>500:raise AuditError('계정영향 목록/한도 오류')
    out=[]
    for raw in value:
        row=payload(raw, ('account_code','fs_line','direction','amount'),
                    ('account_code','fs_line','direction','amount'))
        row['account_code']=text(row['account_code'],'계정코드')
        row['fs_line']=text(row['fs_line'],'재무제표 표시계정')
        row['direction']=choice(row['direction'], ('증가','감소'), '표시계정 영향 방향')
        row['amount']=num(row['amount'],False);out.append(row)
    return out


def evidence(ws, value):
    values=ids(value,'증거ID')
    if any(item not in ws.sources for item in values):raise AuditError('현재 업무에 없는 증거ID')
    if ws.verify_sources():raise AuditError('등록한 원본 사본 변경/누락')
    return values


def procedures(ws, value):
    from audit_workflow import known_ids
    values=ids(value,'조서ID')
    if any(item not in known_ids(ws) for item in values):raise AuditError('현재 업무에 없는 조서·절차ID')
    return values
