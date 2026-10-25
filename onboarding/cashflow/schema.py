"""Flat, editable input contract for ledger-connected cash-flow support."""
TABLE_FIELDS = {
    'accounts': ('account_code', 'role', 'validation_group', 'profit_category'),
    'movement_tags': ('source_ref', 'kind'),
    'cash_allocations': ('allocation_id', 'parent_gl_ref', 'component', 'amount', 'gl_refs'),
    'depreciation_parts': ('kind', 'amount', 'gl_refs'),
    'noncash': ('item_id', 'kind', 'debit_account', 'credit_account', 'amount', 'gl_refs'),
    'cash_controls': ('account_code', 'opening', 'closing', 'source_ref'),
    'group_controls': ('validation_group', 'opening', 'closing', 'source_ref'),
    'reported_flows': ('line', 'amount'),
}
APPROVAL_FIELDS = ['schema', 'context', 'policy', *TABLE_FIELDS]
FIELD_LABELS = {
    'accounts': '계정별 연결 설정', 'movement_tags': '원장 증감 분류',
    'cash_allocations': '현금 원장행별 배부', 'depreciation_parts': '상각비 배부',
    'noncash': '비현금 증감명세', 'cash_controls': '현금 독립통제',
    'group_controls': '검증그룹 독립통제', 'reported_flows': '작성 현금흐름표',
    'account_code': '계정코드', 'role': '현금흐름 역할',
    'validation_group': '검증그룹', 'profit_category': '손익 범주',
    'source_ref': '근거자료 행', 'kind': '증감 구분', 'allocation_id': '배부번호',
    'parent_gl_ref': '부모 현금 원장행', 'component': '현금흐름 항목',
    'amount': '금액', 'gl_refs': '원장 연결행', 'item_id': '명세번호',
    'debit_account': '차변 계정', 'credit_account': '대변 계정',
    'opening': '기초잔액', 'closing': '기말잔액', 'line': '표시항목',
    'framework': '회계체계', 'standard_version': '현금흐름 적용 버전',
    'effective_from': '선택 버전 시행일', 'version_end': '선택 버전 적용종료일',
    'early_adoption': '조기적용 여부', 'early_adoption_permitted': '조기적용 허용 확인',
    'adoption_basis': '시행 및 조기적용 근거', 'starting_point': '간접법 출발점',
    'business_profile': '주된 사업활동 검토', 'interest_paid': '이자지급 분류',
    'interest_received': '이자수취 분류', 'dividends_paid': '배당지급 분류',
    'dividends_received': '배당수취 분류', 'tax_paid': '법인세지급 분류',
    'inventory_method': '재고 상각비 조정방식', 'ledger_basis_hash': '현재원장 내용 해시',
    'classification_basis': '현금 및 손익 분류 근거', 'currency': '계산 통화',
}
ROLES = {
    'cash', 'receivable', 'inventory', 'ppe_cost', 'ppe_accum', 'cip', 'rou_asset',
    'payable', 'loan_long', 'loan_current', 'lease_liability', 'interest_payable',
    'interest_receivable', 'tax_payable', 'equity', 'revenue', 'operating_expense',
    'disposal_gain', 'depreciation_expense', 'interest_expense', 'interest_income',
    'current_tax_expense', 'dividend_income', 'dividend_payable', 'fx_result',
}
DEBT = {'loan_long', 'loan_current', 'lease_liability'}
ASSETS = {'ppe_cost', 'ppe_accum', 'cip', 'rou_asset'}
KINDS = {'operating', 'asset_cash', 'asset_transfer', 'depreciation', 'lease_new',
         'debt_cash', 'debt_reclass', 'interest_cash', 'interest_accrual',
         'tax_cash', 'tax_accrual', 'asset_disposal', 'internal_transfer',
         'fx', 'dividend_cash', 'dividend_accrual', 'mixed_cash'}
PROFIT_ROLES = {'revenue', 'operating_expense', 'disposal_gain', 'depreciation_expense',
                'interest_expense', 'interest_income', 'current_tax_expense',
                'dividend_income', 'fx_result'}
REFERENCES = [
    {'기준': 'IAS 7', '범위': '간접법·비현금거래·현금 대사·재무부채 증감',
     'URL': 'https://www.ifrs.org/issued-standards/list-of-standards/ias-7-statement-of-cash-flows/'},
    {'기준': 'K-IFRS 제1007호', '범위': '국내 적용 버전·시행 및 조기적용은 사람이 확인',
     'URL': 'https://www.kasb.or.kr/front/board/ingAccountingList.do'},
]
