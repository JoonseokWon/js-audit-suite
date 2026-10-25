"""Reject unsupported movements instead of placing them in a balancing bucket."""
from common import issue
from .schema import ASSETS, DEBT
from .sources import role

RULES = {
    'operating': {'cash', 'receivable', 'inventory', 'payable', 'revenue', 'operating_expense'},
    'asset_cash': ASSETS | {'cash'}, 'asset_transfer': ASSETS,
    'asset_disposal': ASSETS | {'cash', 'disposal_gain'},
    'depreciation': {'ppe_accum', 'inventory', 'depreciation_expense'},
    'lease_new': {'rou_asset', 'lease_liability'}, 'debt_reclass': {'loan_long', 'loan_current'},
    'debt_cash': DEBT | {'cash'},
    'interest_cash': {'cash', 'interest_payable', 'interest_receivable', 'interest_expense', 'interest_income'},
    'interest_accrual': {'interest_payable', 'interest_receivable', 'interest_expense', 'interest_income'},
    'tax_cash': {'cash', 'tax_payable', 'current_tax_expense'},
    'tax_accrual': {'tax_payable', 'current_tax_expense'},
    'internal_transfer': {'cash'}, 'mixed_cash': {'cash'},
    'fx': DEBT | {'cash', 'fx_result'},
    'dividend_cash': {'cash', 'equity', 'dividend_payable', 'dividend_income'},
    'dividend_accrual': {'equity', 'dividend_payable', 'dividend_income'},
}


def validate(source, accounts, tags, issues):
    for ref, row in source.items():
        if role(row, accounts) not in RULES.get(tags.get(ref), set()):
            issue(issues, 'CF_TAG_ROLE', '원장 증감 구분과 계정 역할이 다릅니다.', ref)
        if tags.get(ref) == 'mixed_cash':
            others = [r for r in source.values() if r['전표ID'] == row['전표ID']
                      and role(r, accounts) != 'cash']
            if len(others) < 2:
                issue(issues, 'CF_MIXED_CASH', '혼합 현금행은 구성항목별 상대계정 행이 필요합니다.', ref)
