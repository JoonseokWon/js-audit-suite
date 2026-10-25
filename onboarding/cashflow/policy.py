"""Validate an explicit accounting policy; never infer Korean adoption by year."""
from common import AuditError, day, issue, text
from onboarding.contracts import ledger_basis

VERSIONS = {'KIFRS1007_PRE1118': ('K-IFRS', False),
            'KIFRS1007_IFRS1118': ('K-IFRS', True),
            'IAS7_PRE_IFRS18': ('IFRS', False), 'IAS7_IFRS18': ('IFRS', True)}
POLICY_FIELDS = ('framework', 'standard_version', 'effective_from', 'version_end',
    'early_adoption', 'early_adoption_permitted', 'adoption_basis', 'starting_point',
    'business_profile', 'interest_paid', 'interest_received', 'dividends_paid',
    'dividends_received', 'tax_paid', 'inventory_method', 'ledger_basis_hash',
    'classification_basis', 'currency')


def validate(payload, context, ledger, issues):
    policy = payload.get('policy')
    if not isinstance(policy, dict):
        raise AuditError('현금흐름 회계정책을 입력하세요.')
    for field in POLICY_FIELDS:
        if field not in policy:
            raise AuditError('현금흐름 회계정책 누락: ' + field)
    for key in ('adoption_basis', 'classification_basis'):
        text(policy[key], key)
    if policy['currency'] != 'KRW':
        issue(issues, 'CF_CURRENCY', '확정된 원화 정수 금액만 지원합니다.')
    if policy['ledger_basis_hash'] != ledger_basis(ledger):
        issue(issues, 'CF_LEDGER_STALE', '연결 원장이 변경되었습니다. 정책·분류·금액을 다시 확인하세요.')
    version = VERSIONS.get(policy['standard_version'])
    if not version or policy['framework'] != version[0]:
        issue(issues, 'CF_VERSION', '선택 회계체계·버전은 현재 지원 범위가 아닙니다.')
        modern = None
    else:
        modern = version[1]
    for field in ('early_adoption', 'early_adoption_permitted'):
        if not isinstance(policy[field], bool):
            raise AuditError(field + ': 참/거짓 확정값이 필요합니다.')
    start, end = day(context['시작일']), day(context['기준일'])
    effective, expiry = day(policy['effective_from']), day(policy['version_end'])
    if start > end or effective > expiry or end > expiry:
        issue(issues, 'CF_POLICY_PERIOD', '업무기간 또는 선택 버전 적용기간이 맞지 않습니다.')
    if start < effective:
        if not (policy['early_adoption'] and policy['early_adoption_permitted']):
            issue(issues, 'CF_EARLY_ADOPTION', '시행일 전 적용은 허용 근거와 명시적인 조기적용 확인이 필요합니다.')
    elif policy['early_adoption']:
        issue(issues, 'CF_EARLY_ADOPTION', '이미 시행된 기간인데 조기적용으로 표시되어 있습니다.')
    if policy['business_profile'] != 'ordinary_nonfinancial':
        issue(issues, 'CF_PROFILE', '주된 사업활동이 금융·투자인 경우의 특별 분류는 별도 검토가 필요합니다.')
    if policy['inventory_method'] not in {'gross_inventory_total_depreciation',
                                          'net_inventory_expensed_depreciation'}:
        issue(issues, 'CF_INVENTORY_METHOD', '재고 총액·상각비 전체 조정 또는 재고 순액·비용상각 조정을 선택하세요.')
    allowed = {'interest_paid': {'operating', 'financing'},
               'interest_received': {'operating', 'investing'},
               'dividends_received': {'operating', 'investing'},
               'dividends_paid': {'operating', 'financing'}}
    if modern is True:
        allowed = {'interest_paid': {'financing'}, 'interest_received': {'investing'},
                   'dividends_received': {'investing'}, 'dividends_paid': {'financing'}}
    for field, choices in allowed.items():
        if policy[field] not in choices:
            issue(issues, 'CF_CLASSIFICATION', field + ': 선택 버전의 지원 분류와 다릅니다.')
    required_start = 'operating_profit' if modern else 'net_profit'
    if modern is not None and policy['starting_point'] != required_start:
        issue(issues, 'CF_STARTING_POINT', '선택 버전의 간접법 출발점을 확인하세요.')
    if policy['tax_paid'] != 'operating':
        issue(issues, 'CF_TAX_CLASSIFICATION', '법인세를 투자·재무 현금에 직접 귀속하는 경우는 별도 계산·검토가 필요합니다.')
    return policy


def account_categories(accounts, policy, issues):
    """Only the ordinary non-financial profile is supported for the new version."""
    if not VERSIONS.get(policy.get('standard_version'), (None,False))[1]:
        return
    expected = {'revenue':'operating', 'operating_expense':'operating',
                'depreciation_expense':'operating', 'disposal_gain':'operating',
                'interest_expense':'financing', 'interest_income':'investing',
                'dividend_income':'investing', 'current_tax_expense':'tax'}
    for code, row in accounts.items():
        category = expected.get(row.get('role'))
        if category and row.get('profit_category') != category:
            issue(issues, 'CF_OPERATING_PROFIT_SCOPE',
                  '선택한 일반 비금융업 새 버전의 손익 범주·영업손익 출발점을 확인하세요.', code)
