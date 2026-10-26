"""Independent invented-case expectations and plain Korean step descriptions."""
SCHEMA = 'js-electronics-ai-walkthrough-1'
TARGET_PID = 'A04'
INPUTS = {
    'ledger_error': ('원장·리드', '01_원장_균형전표누락.xlsx'),
    'ledger_clean': ('원장·리드', '02_원장_정상대조.xlsx'),
    'sales_error': ('매출', '03_매출_청구행누락.xlsx'),
    'sales_clean': ('매출', '04_매출_정상대조.xlsx'),
    'sales_amount_error': ('매출', '05_매출_공급가액1원차이.xlsx'),
}
BASES = {
    '원장·리드': ('companies/JS_ELEC/inputs/통합_v1.3_원장_리드.xlsx',
        '15257e3f3e26d3fb6570c8c037a4714468c18e8e971dea5136828b0a4e7e9ec5'),
    '매출': ('companies/JS_ELEC/inputs/통합_v1.3_매출.xlsx',
        'a62a84720ee3c3c01a2d0d4c308335b9f98176089521f9edf80f839eb747e0c9'),
}
EXPECTED = {
    'company_code': 'JS_ELEC', 'currency': 'KRW', 'total_revenue': 100000,
    'deleted_invoice': 'SI01', 'deleted_invoice_supply': 90000,
    'deleted_invoice_tax': 9000, 'deleted_invoice_total': 99000,
    'omitted_journal': 'J-S1', 'omitted_ledger_rows': 3,
    'omitted_ledger_debit': 99000, 'omitted_ledger_credit': 99000,
    'normal_ledger_rows': 82, 'error_ledger_rows': 79,
    'normal_invoice_rows': 2, 'error_invoice_rows': 1,
    'amount_difference': 1,
    'scope': 'SYNTHETIC ONLY / 고정 예제값이며 실제 고객 또는 독립 ERP 추출 아님',
}
STEPS = (
    ('inputs', '1. 입력자료와 자동검사 확인',
     '원장 J-S1 전체 3행과 매출 청구 SI01을 누락한 가상 자료를 자동검사했습니다. '
     '정상 대조자료도 별도 보관합니다. 자동검사는 사람의 실제 감사수행이 아닙니다.'),
    ('exceptions', '2. 누락·차이의 근거 확인',
     '원장 독립 통제의 행수·금액과 매출 청구·원장 대사를 확인하세요. '
     '차대가 맞는다는 사실만으로 누락이 없는 것은 아닙니다.'),
    ('draft', '3. A04 로컬 AI 조서 초안 생성',
     '조서 A04를 열고 근거 묶음을 확인한 뒤 로컬 AI로 초안을 생성하세요. '
     '초안의 원본 행·예외코드·원장 버전 인용을 직접 확인하세요.'),
    ('edit', '4. 초안 적용·수정·저장',
     '초안을 적용하고 사실과 맞지 않는 표현을 수정하세요. 실제로 수행한 내용과 '
     '아직 수행하지 않은 절차를 구분하세요. AI가 사람 판단이나 수행일을 대신 입력하지 않습니다.'),
    ('approve', '5. 사람의 내용 승인과 별도 조서 검토',
     '저장한 내용·근거·예외를 검토한 사용자가 승인자와 판단 기록을 직접 입력하세요. '
     '내용 승인과 별도 검토는 서로 다르며 전체 감사완료를 뜻하지 않습니다.'),
    ('export', '6. Excel 출력과 변경 후 재검사',
     '상단 초안 Excel 저장으로 현재 상태를 출력하세요. 정상 자료로 다시 검사하면 '
     '이전 AI 근거·승인은 유효한 현재 결과가 아니므로 새 초안과 사람 확인이 필요합니다.'),
)


def steps():
    return [dict(id=i, title=t, detail=d) for i, t, d in STEPS]
