"""Only synthetic data. One consistent entity with gross cash event legs."""
from copy import deepcopy
from .engine import Row, InputBook, SCHEMA


def make_book():
    settings = {
        'entity': '더미 제조 주식회사', 'currency': 'KRW', 'unit': '원',
        'period_start': '2026-01-01', 'period_end': '2026-12-31',
        'opening_date': '2025-12-31', 'closing_date': '2026-12-31',
        'opening_cash_control': 1000, 'closing_cash_control': 1095,
        'net_income': 160, 'net_income_control': 160, 'fx_cash_control': 5,
        'earnings_account_id': 'RE',
        'policy_note': '더미: 현금만 포함. 일반 영업손익 영업, 유형자산 투자, 차입·배당 재무. 사용자 최종 확인 필요.',
        'policy_confirmed': 'YES', 'mapping_confirmed': 'YES', 'cash_scope_confirmed': 'YES', 'profit_link_confirmed': 'YES',
    }
    data = {k: [] for k in SCHEMA}
    data['Settings'] = [[k, v] for k, v in settings.items()]
    data['Balances'] = [
        ['CASH', '현금및현금성자산', 'ASSET', 1000, 1095],
        ['AR', '매출채권', 'ASSET', 100, 140],
        ['PPE', '유형자산 순장부금액', 'ASSET', 500, 640],
        ['AP', '매입채무', 'LIABILITY', 80, 90],
        ['DEBT', '차입금', 'LIABILITY', 200, 350],
        ['CAP', '자본금', 'EQUITY', 1000, 1000],
        ['RE', '이익잉여금', 'EQUITY', 320, 430],
        ['FXR', '환율효과 더미 준비금', 'EQUITY', 0, 5],
    ]
    data['Mapping'] = [
        ['CASH', 'CASH', 'CASH_ACCOUNT', '포함 현금: 별도 현금명세 대사', 'YES'],
        ['AR', 'WC_ASSET', 'OP_AR', '일반 영업 매출채권', 'YES'],
        ['PPE', 'SCHEDULE', 'PPE_SCHEDULE', '취득/감가상각 사건별 명세', 'YES'],
        ['AP', 'WC_LIABILITY', 'OP_AP', '일반 영업 매입채무', 'YES'],
        ['DEBT', 'SCHEDULE', 'DEBT_SCHEDULE', '차입/상환 별도 유입·유출', 'YES'],
        ['CAP', 'EXCLUDED', 'CAP_EXCLUDED', '당기 변동 없는 자본', 'YES'],
        ['RE', 'EXCLUDED', 'PROFIT_LINK', '당기순이익 연결 및 배당명세', 'YES'],
        ['FXR', 'EXCLUDED', 'FX_RESERVE', '제한된 환율 더미 대응계정. 실제 회계정책 검토 필요', 'YES'],
    ]
    data['CashScope'] = [['CASH', 1000, 1095, '더미 보통예금: 사용제한 없음; 현금성자산 범위 사용자 확인', 'YES']]
    data['Events'] = [
        ['REV', '2026-02-01', 'ACCRUAL', 'NONE', 'REV_LINK', 'NONE', 300, '외상매출 및 이익 연결', 'YES'],
        ['COLLECT', '2026-03-01', 'CASH', 'OPERATING', 'COLLECTION', 'INFLOW', 0, '매출채권 회수', 'YES'],
        ['EXP', '2026-04-01', 'ACCRUAL', 'NONE', 'EXP_LINK', 'NONE', -100, '외상 비용 및 이익 연결', 'YES'],
        ['PAY', '2026-05-01', 'CASH', 'OPERATING', 'PAYMENT', 'OUTFLOW', 0, '매입채무 지급', 'YES'],
        ['DEP', '2026-06-01', 'NONCASH', 'NONE', 'DEP_LINK', 'NONE', -40, '감가상각 비현금 비용', 'YES'],
        ['CAPEX', '2026-07-01', 'CASH', 'INVESTING', 'INV_CAPEX', 'OUTFLOW', 0, '현금 유형자산 취득', 'YES'],
        ['LEASE', '2026-08-01', 'NONCASH', 'NONE', 'LEASE_LINK', 'NONE', 0, '비현금 자산 취득/채무 80: 현금흐름 제외', 'YES'],
        ['BORROW', '2026-09-01', 'CASH', 'FINANCING', 'FIN_BORROW', 'INFLOW', 0, '차입 유입', 'YES'],
        ['REPAY', '2026-10-01', 'CASH', 'FINANCING', 'FIN_REPAY', 'OUTFLOW', 0, '차입 상환: 유입과 상계 금지', 'YES'],
        ['DIV', '2026-11-01', 'CASH', 'FINANCING', 'FIN_DIVIDEND', 'OUTFLOW', 0, '현금배당: 이익잉여금 감소', 'YES'],
        ['FXEV', '2026-12-01', 'FX', 'NONE', 'FX_LINK', 'NONE', 0, '현금 KRW 환율영향 별도 5', 'YES'],
    ]
    legs = [
        ('REV', 'AR', 300), ('REV', 'RE', 300),
        ('COLLECT', 'CASH', 260), ('COLLECT', 'AR', -260),
        ('EXP', 'AP', 100), ('EXP', 'RE', -100),
        ('PAY', 'CASH', -90), ('PAY', 'AP', -90),
        ('DEP', 'PPE', -40), ('DEP', 'RE', -40),
        ('CAPEX', 'CASH', -100), ('CAPEX', 'PPE', 100),
        ('LEASE', 'PPE', 80), ('LEASE', 'DEBT', 80),
        ('BORROW', 'CASH', 100), ('BORROW', 'DEBT', 100),
        ('REPAY', 'CASH', -30), ('REPAY', 'DEBT', -30),
        ('DIV', 'CASH', -50), ('DIV', 'RE', -50),
        ('FXEV', 'CASH', 5), ('FXEV', 'FXR', 5),
    ]
    data['Movements'] = [[f'LEG{i:03}', *leg] for i, leg in enumerate(legs, 1)]
    data['Adjustments'] = [['ADJ_DEP', 'DEP', 'NONCASH', 'OP_DEPRECIATION', 40, '감가상각 비용 가산: 사건 손익 반대부호 1회', 'YES']]
    data['Statement'] = [
        ['NI', 'OPERATING', 160], ['OP_DEPRECIATION', 'OPERATING', 40],
        ['OP_AR', 'OPERATING', -40], ['OP_AP', 'OPERATING', 10],
        ['INV_CAPEX', 'INVESTING', -100], ['FIN_BORROW', 'FINANCING', 100],
        ['FIN_REPAY', 'FINANCING', -30], ['FIN_DIVIDEND', 'FINANCING', -50],
        ['CFO', 'TOTAL', 170], ['CFI', 'TOTAL', -100], ['CFF', 'TOTAL', 20],
        ['FX', 'NONE', 5], ['CASH_DELTA', 'TOTAL', 95], ['CASH_OPEN', 'TOTAL', 1000], ['CASH_CLOSE', 'TOTAL', 1095],
    ]
    return InputBook({name: [Row(name, i, dict(zip(SCHEMA[name], values))) for i, values in enumerate(rows, 2)] for name, rows in data.items()})


def change(book, sheet, key, column, value):
    book = deepcopy(book)
    key_col = SCHEMA[sheet][0]
    for row in book.sheets[sheet]:
        if row.values[key_col] == key:
            row.values[column] = value
            return book
    raise KeyError(key)


def sample_cases():
    normal = make_book()
    missing = deepcopy(normal)
    missing.sheets.pop('Events')
    unmapped = deepcopy(normal)
    unmapped.sheets['Mapping'] = [r for r in unmapped.sheets['Mapping'] if r.values['account_id'] != 'AR']
    missing_adjustment = deepcopy(normal)
    missing_adjustment.sheets['Adjustments'] = []
    return {
        '정상_비현금_환율': normal, '자료누락': missing,
        '미매핑': unmapped, '비현금조정누락': missing_adjustment,
        '환율통제불일치': change(normal, 'Settings', 'fx_cash_control', 'value', 0),
        '현금부호오류': change(normal, 'Events', 'CAPEX', 'direction', 'INFLOW'),
        '기말불일치': change(normal, 'Balances', 'AR', 'closing', 145),
        '정책미확인': change(normal, 'Settings', 'policy_confirmed', 'value', 'NO'),
        '초안불일치': change(normal, 'Statement', 'CFO', 'amount', 171),
        '유입유출상계': change(normal, 'Events', 'REPAY', 'line_id', 'FIN_BORROW'),
    }
