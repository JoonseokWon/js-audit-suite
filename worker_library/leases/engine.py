"""Small, isolated lease raw-data acceptance check. Standard library only."""
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTEXT = {
    "company_code": "SYNTH01", "start_date": "2026-01-01",
    "end_date": "2026-12-31", "currency": "KRW",
    "financial_statement_scope": "별도",
}
DOCUMENT_TYPES = {"lease_contract", "discount_rate_memo", "payment_schedule",
                  "bank_payment", "lease_subledger", "general_ledger_extract"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, field, nonnegative=False):
    require(type(value) is int, f"{field}: integer KRW required, missing is not zero")
    require(abs(value) <= 10**13, f"{field}: amount outside fixture range")
    require(not nonnegative or value >= 0, f"{field}: nonnegative amount required")
    return value


def iso(value):
    require(type(value) is str, "ISO date required")
    require(date.fromisoformat(value).isoformat() == value, "ISO date required")
    return value


def blocked(reason, refs):
    return [{"check_id": "LEASE-INPUT", "status": "INPUT_BLOCKED",
             "expected_value": "SUPPORTED_COMPLETE_INPUT", "actual_value": None,
             "difference": None, "reason": reason, "source_refs": refs}]


def calculate(case):
    """Accept only the declared 2-year annual-end, no-option synthetic contract."""
    docs = case["documents"]
    require(len({d["document_id"] for d in docs}) == len(docs), "duplicate evidence ID")
    require(len(docs) == len(DOCUMENT_TYPES), "six evidence documents required")
    require({d["document_type"] for d in docs} == DOCUMENT_TYPES, "document types required")
    require(len({d["transaction_id"] for d in docs}) == 1, "transaction join mismatch")
    by_type = {}
    for i, d in enumerate(docs):
        require(d["document_id"].startswith("LEASE-"), "document prefix")
        require(d["transaction_id"].startswith("LEASE-"), "transaction prefix")
        require(d["fields"]["company_code"] == CONTEXT["company_code"], "company mismatch")
        require(d["fields"]["lease_id"] == "LEASE-L001", "lease join mismatch")
        by_type[d["document_type"]] = (d["fields"], f"/documents/{i}/fields")
    contract, cp = by_type["lease_contract"]
    rate_memo, rp = by_type["discount_rate_memo"]
    schedule, sp = by_type["payment_schedule"]
    bank, bp = by_type["bank_payment"]
    sub, lp = by_type["lease_subledger"]
    gl, gp = by_type["general_ledger_extract"]

    if contract.get("annual_effective_discount_rate") is None or rate_memo.get("annual_effective_discount_rate") is None:
        return blocked("할인율 누락: 현재가치·이자·사용권자산 계산 보류. 0%로 대체하지 않음.",
                       [cp + "/annual_effective_discount_rate", rp + "/annual_effective_discount_rate"])
    try:
        raw_rate = contract["annual_effective_discount_rate"]
        require(type(raw_rate) is str, "discount rate must be a decimal string")
        rate = Decimal(raw_rate)
        require(rate.is_finite() and 0 <= rate < 1, "unsupported discount rate")
        require(raw_rate == rate_memo["annual_effective_discount_rate"], "rate memo mismatch")
    except (InvalidOperation, ValueError) as exc:
        return blocked(str(exc), [cp + "/annual_effective_discount_rate", rp])
    supported = (
        contract["commencement_date"] == "2026-01-01"
        and contract["contract_end_date"] == "2027-12-31"
        and contract["lease_years"] == 2 and type(contract["lease_years"]) is int
        and contract["payment_timing"] == "ANNUAL_END"
        and contract["discount_rate_type"] == "ANNUAL_EFFECTIVE"
        and contract["applied_discount_rate_basis"] == "INCREMENTAL_BORROWING_RATE"
        and contract["implicit_rate_readily_determinable"] is False
        and contract["transfer_of_ownership"] is False
        and contract["extension_option"] is False
        and contract["purchase_option"] is False
        and contract["termination_option"] is False
        and contract["variable_payment"] is False
        and contract["modifications"] == []
        and contract["depreciation_method"] == "STRAIGHT_LINE_OVER_LEASE_TERM"
        and all(type(contract[k]) is int and contract[k] == 0 for k in (
            "prepayment", "initial_direct_cost", "incentive_received",
            "restoration_cost", "residual_value_guarantee"))
    )
    if not supported:
        return blocked("명시된 단순 연말 후급 계약 범위 밖 조건: 수동 검토 필요.", [cp])
    require(iso(contract["agreement_date"]) <= contract["commencement_date"], "agreement after commencement")
    require(contract["rate_document_id"] == docs[1]["document_id"], "rate evidence join mismatch")
    require(rate_memo["observation_date"] == "2026-01-01", "rate date mismatch")
    require(rate_memo["currency"] == "KRW" and rate_memo["term_years"] == 2, "rate context mismatch")
    require(sub["as_of_date"] == gl["as_of_date"] == "2026-12-31", "ledger period mismatch")
    payment = integer(contract["annual_payment"], "annual_payment", True)
    require(payment > 0, "positive payment required")
    expected_dates = ["2026-12-31", "2027-12-31"]
    payments = schedule["payments"]
    require(len(payments) == 2, "two contractual payments required")
    require([iso(p["payment_date"]) for p in payments] == expected_dates, "payment timing mismatch")
    require([p["subsequent_period"] for p in payments] == [False, True], "subsequent period label mismatch")
    require(all(type(p["subsequent_period"]) is bool for p in payments), "period flag must be boolean")
    require(all(integer(p["amount"], "scheduled payment", True) == payment for p in payments), "fixed payment mismatch")
    require(bank["payment_date"] == expected_dates[0], "bank payment date mismatch")
    require(bank["payment_id"] == payments[0]["payment_id"], "payment evidence join mismatch")
    integer(bank["cash_movement"], "bank cash movement")
    require(bank["cash_movement"] <= 0, "bank outflow sign must be preserved")
    for key, value in sub.items():
        if key.endswith("_amount"):
            integer(value, key, True)
    for key, value in gl.items():
        if key.endswith("_amount"):
            integer(value, key)
    require(gl["sign_convention"] == "DEBIT_POSITIVE_CREDIT_NEGATIVE", "GL sign convention")
    require(sub["liability_opening_amount"] == sub["rou_opening_amount"] == 0, "new lease opening balance")

    with localcontext() as ctx:
        ctx.prec = 40
        pv = sum((Decimal(payment) / (1 + rate) ** year for year in (1, 2)), Decimal(0))
        interest = pv * rate
        closing = pv + interest - payment
        depreciation = pv / 2
        rou_closing = pv - depreciation
        final_closing = closing * (1 + rate) - payment
        require(abs(final_closing) < Decimal("0.00000000000001"), "full lease must settle")
        won = lambda x: int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        pv, interest, closing, depreciation, rou_closing = map(won, (pv, interest, closing, depreciation, rou_closing))

    results = []
    def check(check_id, expected, actual, reason, refs):
        diff = actual - expected
        results.append({"check_id": check_id, "status": "PASS" if diff == 0 else "EXCEPTION",
                        "expected_value": expected, "actual_value": actual,
                        "difference": diff, "reason": reason, "source_refs": refs})

    check("LEASE-PV", pv, sub["liability_addition_amount"], "개시 부채=계약상 후급 지급액의 현재가치", [cp, rp, sp, lp + "/liability_addition_amount"])
    check("LEASE-LL-CLOSE", closing, sub["liability_closing_amount"], "독립 스케줄의 기말 리스부채와 보조원장 비교", [cp, rp, sp, lp + "/liability_closing_amount"])
    check("LEASE-LL-ROLL", sub["liability_opening_amount"] + sub["liability_addition_amount"] + sub["interest_amount"] - sub["payment_amount"], sub["liability_closing_amount"], "부채 기초+증가+이자-지급=기말", [lp])
    check("LEASE-INTEREST", interest, sub["interest_amount"], "개시 부채×명시된 연 유효 할인율", [cp, rp, lp + "/interest_amount"])
    check("LEASE-ROU-ADDITION", pv, sub["rou_addition_amount"], "추가 원가·인센티브가 모두 0인 계약의 사용권자산 증가", [cp, lp + "/rou_addition_amount"])
    check("LEASE-DEPRECIATION", depreciation, sub["depreciation_amount"], "소유권 이전·매수 옵션 없는 2년 리스기간 정액 상각", [cp, lp + "/depreciation_amount"])
    check("LEASE-ROU-CLOSE", rou_closing, sub["rou_closing_amount"], "재계산 사용권자산 순장부금액", [cp, lp + "/rou_closing_amount"])
    check("LEASE-PAYMENT", -payment, bank["cash_movement"], "2026년 약정 지급액과 은행 출금 비교; 부호 보존", [sp + "/payments/0", bp])
    check("LEASE-GL-LL", -closing, gl["lease_liability_amount"], "독립 재계산 부채와 원장 대변잔액 비교", [cp, rp, sp, gp + "/lease_liability_amount"])
    check("LEASE-GL-ROU", rou_closing, gl["rou_cost_amount"] + gl["rou_accumulated_depreciation_amount"], "사용권자산 원가·누계 원장 대사", [gp, lp])
    check("LEASE-GL-INTEREST", interest, gl["interest_expense_amount"], "이자비용 원장 대사", [gp, lp])
    check("LEASE-GL-CASH", bank["cash_movement"], gl["cash_movement_amount"], "은행 지급과 원장 현금 변동 대사", [gp, bp])
    check("LEASE-GL-DEPRECIATION", depreciation, gl["depreciation_expense_amount"], "상각비 원장 대사", [gp, lp])
    check("LEASE-PAYMENT-SUBLEDGER", payment, sub["payment_amount"], "약정 지급과 보조원장 지급 대사", [sp, lp])
    return results


def main():
    path = HERE / "fixtures.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    require(data["schema_version"] == "pm-raw-1", "schema version")
    require(data["synthetic"] is True and data["integrated"] is False, "release boundary")
    require(data["context"] == CONTEXT, "context mismatch")
    require(len(data["cases"]) == 3, "three fixed acceptance cases")
    count = 0
    status_counts = {"PASS": 0, "EXCEPTION": 0, "INPUT_BLOCKED": 0}
    for case in data["cases"]:
        require(case["case_id"].startswith("LEASE-"), "case ID prefix")
        computed = calculate(case)
        require(len(computed) == len(case["expected"]), f"{case['case_id']}: check count mismatch")
        for actual, fixed in zip(computed, case["expected"]):
            for key in ("check_id", "status", "expected_value", "actual_value", "difference"):
                require(actual[key] == fixed[key], f"{case['case_id']} {actual['check_id']} {key}: {actual[key]!r} != {fixed[key]!r}")
            require(bool(fixed["reason"]), "fixed reason required")
            require(bool(actual["source_refs"]), "traceable source required")
            status_counts[actual["status"]] += 1
            count += 1
        print(f"{case['case_id']}: {len(computed)} fixed checks matched")

    # Negative input checks prove that missing amounts and unsupported terms cannot pass as zero.
    normal = data["cases"][0]
    guards = 0
    for field, bad_value in (("annual_payment", None), ("annual_payment", True)):
        probe = deepcopy(normal)
        probe["documents"][0]["fields"][field] = bad_value
        try:
            calculate(probe)
        except ValueError:
            guards += 1
        else:
            raise AssertionError(f"did not reject {field}={bad_value!r}")
    for field, bad_value in (("modifications", [{"effective_date": "2026-07-01"}]), ("extension_option", True)):
        probe = deepcopy(normal)
        probe["documents"][0]["fields"][field] = bad_value
        require(calculate(probe)[0]["status"] == "INPUT_BLOCKED", "unsupported terms not blocked")
        guards += 1
    print(json.dumps({"cases": 3, "fixed_checks": count, "statuses": status_counts,
                      "additional_guard_checks": guards, "integrated": False,
                      "fixtures_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
