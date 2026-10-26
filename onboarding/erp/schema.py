"""Explicit ERP conventions; labels are also used by the value-only Excel editor."""
from common import AuditError, digest, num, text

APPROVAL_FIELDS = ['context', 'config', 'source_rows', 'column_mapping', 'coa_mapping',
                   'trial_balance', 'independent_controls', 'adjustments',
                   'adjustment_approvals', 'presentation_mapping', 'presentation_values']
FIELD_LABELS = {
    'source_rows':'ERP 원본 행', 'column_mapping':'원본 열 매핑', 'coa_mapping':'계정 매핑',
    'trial_balance':'별도 시산표', 'independent_controls':'독립 추출 통제',
    'adjustments':'감사조정', 'adjustment_approvals':'감사조정 확인 기록',
    'presentation_mapping':'본문·주석·제조원가 매핑', 'presentation_values':'보고 금액',
    'config':'변환 설정', 'target':'표준 필드', 'source':'원본 열',
    'source_account':'원본 계정', 'account_code':'표준 계정코드', 'account_name':'계정명',
    'lead_code':'리드코드', 'lead_name':'리드명', 'statement_type':'BS·PL 구분',
    'journal_id':'전표ID', 'line_id':'행·항목ID', 'posting_date':'전기일',
    'debit':'차변', 'credit':'대변', 'amount':'금액', 'description':'적요',
    'author':'작성자', 'department':'부문', 'cancel_of':'취소 대상 원장행ID',
    'source_file':'원본 파일명', 'source_sha256':'원본 SHA256(선언)',
    'source_sheet':'원본 시트', 'source_row':'원본 행번호',
    'opening':'기초잔액', 'closing':'기말잔액', 'row_count':'원장 행수',
    'source_debit_total':'원본 부호 차변합계', 'source_credit_total':'원본 부호 대변합계',
    'debit_total':'정규화 차변합계', 'credit_total':'정규화 대변합계',
    'extract_basis':'별도 추출 근거', 'extracted_at':'추출일시', 'actor':'확인자',
    'reason':'확인 사유', 'input_hash':'확인 대상 해시', 'adjustment_id':'조정ID',
    'evidence':'조정 근거', 'status':'조정 상태', 'statement':'문서 구분',
    'basis':'잔액 기준', 'sign':'표시부호', 'unit':'보고 단위(원 배수)',
    'validation_group':'검증 그룹', 'group_policy':'개별·그룹 검증',
    'group_basis':'동일 그룹 근거', 'formula':'원본 수식(확정값 입력 시 공란)',
    'ledger_refs':'원장행ID(세미콜론 구분)',
    'amount_mode':'two_columns 또는 signed', 'signed_debit_factor':'단일금액 차변 부호',
    'source_unit':'원본 단위(원 배수)', 'currency':'통화', 'tb_state':'미마감 TB 여부',
    'reporting_basis':'재무제표 공통 기준(조정전·조정후)',
    'source_origin':'자료 가져오기 방식','source_file_sha256':'가져온 파일 SHA256',
    'source_rows_sha256':'가져온 원본 행 해시','source_filename':'가져온 파일명',
}
TABLE_FIELDS = {
    'source_rows':(),  # Original ERP headers are dynamic; use the actual row keys plus PROVENANCE.
    'column_mapping':('target','source'),
    'coa_mapping':('source_account','account_code','account_name','lead_code','lead_name','statement_type'),
    'trial_balance':('account_code','opening','debit','credit','closing'),
    'independent_controls':('account_code','row_count','source_debit_total','source_credit_total',
        'debit_total','credit_total','opening','closing','extract_basis','extracted_at','actor'),
    'adjustments':('adjustment_id','line_id','account_code','debit','credit','evidence','status'),
    'adjustment_approvals':('adjustment_id','actor','reason','input_hash'),
    'presentation_mapping':('statement','line_id','account_code','basis','sign','validation_group',
                            'group_policy','group_basis','ledger_refs'),
    'presentation_values':('statement','line_id','amount','basis','unit','formula'),
}
REQUIRED_TARGETS = {'journal_id', 'line_id', 'posting_date', 'source_account',
                    'description', 'author'}
OPTIONAL_TARGETS = {'department', 'cancel_of'}
PROVENANCE = ('source_file', 'source_sha256', 'source_sheet', 'source_row')


def rows(payload, key):
    value = payload.get(key, [])
    from input_limits import EXCEL_DATA_ROWS
    limit=EXCEL_DATA_ROWS if key=='source_rows' else 10000
    if not isinstance(value, list) or len(value) > limit:
        raise AuditError(key + f': {limit:,}행 이하 표가 필요합니다.')
    for row in value:
        if not isinstance(row, dict) or any(isinstance(v, (list, dict)) for v in row.values()):
            raise AuditError(key + ': 각 행에는 확정 단일 값만 입력하세요.')
        if any(isinstance(v, str) and v.lstrip().startswith('=') for v in row.values()):
            raise AuditError(key + ': 수식과 캐시는 계산 근거로 사용할 수 없습니다.')
    return value


def integer(value, signed=True):
    # An Excel floating point/cache boolean must not silently become a confirmed won value.
    if isinstance(value, (float, bool)):
        raise AuditError('확정된 원 단위 정수가 필요합니다.')
    return num(value, signed)


def configuration(payload):
    c = payload.get('config')
    if not isinstance(c, dict) or any(isinstance(v, (list, dict)) for v in c.values()):
        raise AuditError('변환 설정은 단일 값 사전이어야 합니다.')
    if c.get('currency') != 'KRW' or c.get('tb_state') != 'unclosed':
        raise AuditError('확정 KRW·미마감 TB만 지원합니다. 마감 분개를 임의 제외하지 않습니다.')
    if c.get('amount_mode') not in ('two_columns', 'signed'):
        raise AuditError('금액 열 규칙을 명시하세요.')
    if c.get('reporting_basis') not in ('pre_adjustment','post_adjustment'):
        raise AuditError('재무제표 전체의 공통 기준을 조정전 또는 조정후로 명시하세요.')
    if integer(c.get('source_unit'), False) not in (1, 1000):
        raise AuditError('원본 단위는 1원 또는 1000원입니다.')
    if integer(c.get('signed_debit_factor')) not in (-1, 1):
        raise AuditError('단일금액 부호는 -1 또는 1이어야 합니다.')
    return c


def adjustment_hash(group):
    fields = ('adjustment_id', 'line_id', 'account_code', 'debit', 'credit', 'evidence', 'status')
    return digest([{key:r.get(key) for key in fields} for r in group])


def rowref(row):
    return text(row.get('source_file')) + '/' + text(row.get('source_sheet')) + '!' + str(row.get('source_row'))
