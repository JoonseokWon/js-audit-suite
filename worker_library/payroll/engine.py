"""PAY initial fixture checks. Standard library only; no tax, legal or actuarial model."""
from __future__ import annotations

import copy
import calendar
import datetime as dt
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
CORE = ("check_id", "status", "expected_value", "actual_value", "difference")
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
EXPECTED_CONTEXT = {"company_code": "SYNTH01", "start_date": "2026-01-01", "end_date": "2026-12-31", "currency": "KRW", "financial_statement_scope": "별도"}
REQUIRED = {
    "employment_contract": ("employee_id", "start_date", "pay_period_start", "pay_period_end", "base_monthly_amount", "pay_basis"),
    "attendance_approval": ("employee_id", "overtime_hours", "approved_overtime_unit_amount", "approved_bonus_amount", "approved_other_amount"),
    "payroll_statement": ("employee_id", "payroll_id", "pay_period_start", "pay_period_end", "gross_amount", "deduction_amount", "net_amount"),
    "withholding_approval": ("employee_id", "approved_amount"),
    "social_insurance_approval": ("employee_id", "approved_amount"),
    "bank_payment": ("employee_id", "payroll_id", "payment_date", "amount"),
    "payroll_ledger": ("employee_id", "payroll_id", "period_end", "recorded_unpaid_net_amount"),
}
MONEY = {"base_monthly_amount", "approved_overtime_unit_amount", "approved_bonus_amount", "approved_other_amount", "gross_amount", "deduction_amount", "net_amount", "approved_amount", "amount", "recorded_unpaid_net_amount"}


def result(check_id, expected, actual, reason, refs, *, blocked=False):
    numeric = type(expected) is int and type(actual) is int
    return {"check_id": check_id, "status": "INPUT_BLOCKED" if blocked else ("PASS" if expected == actual else "EXCEPTION"), "expected_value": expected, "actual_value": actual, "difference": actual - expected if numeric else None, "reason": reason, "source_locations": refs}


def evaluate(case, context):
    docs = case["documents"]
    problems = []
    by_type = {}
    ids = set()
    transaction_ids = set()
    employees = set()
    for i, doc in enumerate(docs):
        pointer = f"/documents/{i}"
        if not isinstance(doc, dict):
            problems.append(pointer)
            continue
        bad_keys = False
        for key in ("document_id", "document_type", "transaction_id", "fields"):
            if key not in doc or doc[key] is None:
                problems.append(f"{pointer}/{key}")
                bad_keys = True
        if bad_keys:
            continue
        if not isinstance(doc["fields"], dict):
            problems.append(pointer + "/fields")
            continue
        if not all(isinstance(doc[k], str) and doc[k].startswith("PAY-") for k in ("document_id", "transaction_id")):
            problems.append(pointer + "/identifiers")
        if doc["document_id"] in ids:
            problems.append(pointer + "/document_id")
        ids.add(doc["document_id"])
        transaction_ids.add(doc["transaction_id"])
        kind = doc["document_type"]
        by_type.setdefault(kind, []).append((i, doc["fields"]))
        fields = doc["fields"]
        if fields.get("company_code") != context["company_code"]:
            problems.append(pointer + "/fields/company_code")
        if fields.get("synthetic_notice") != "SYNTHETIC ONLY / 테스트 전용 / 법적 효력 없음":
            problems.append(pointer + "/fields/synthetic_notice")
        for key in REQUIRED.get(kind, ()):
            if key not in fields or fields[key] is None:
                problems.append(f"{pointer}/fields/{key}")
        for key, value in fields.items():
            if key in MONEY and value is not None and type(value) is not int:
                problems.append(f"{pointer}/fields/{key}")
            if key in ("employee_id", "payroll_id") and value is not None and (not isinstance(value, str) or not value.startswith("PAY-")):
                problems.append(f"{pointer}/fields/{key}")
            if key.endswith("_date") or key in ("pay_period_start", "pay_period_end", "period_end"):
                if value is None and key == "termination_date":
                    continue
                try:
                    if not isinstance(value, str) or dt.date.fromisoformat(value).isoformat() != value:
                        raise ValueError
                except (ValueError, TypeError):
                    problems.append(f"{pointer}/fields/{key}")
        if "employee_id" in fields:
            employees.add(fields["employee_id"])
    for kind in REQUIRED:
        if kind not in by_type:
            problems.append(f"/documents/missing/{kind}")
    if len(transaction_ids) != 1:
        problems.append("/documents/transaction_id_consistency")
    if len(employees) != 1:
        problems.append("/documents/employee_id_consistency")
    for kind, entries in by_type.items():
        if kind != "payroll_statement" and kind in REQUIRED and len(entries) != 1:
            problems.append(f"/documents/duplicate/{kind}")
    if problems:
        return [result("PAY-REQUIRED", "complete valid required fields", sorted(set(problems)), "필수 자료나 필드가 누락·오형식이면 계산을 중단한다. null을 0으로 바꾸지 않는다.", sorted(set(problems)), blocked=True)]
    contract = by_type["employment_contract"][0][1]
    attendance = by_type["attendance_approval"][0][1]
    if contract["pay_basis"] != "SYNTHETIC_FULL_MONTH_FIXED" or type(attendance["overtime_hours"]) is not int or attendance["overtime_hours"] < 0:
        return [result("PAY-REQUIRED", "supported fixed full-month policy", "unsupported policy or hours", "이번 검증기는 명시된 합성 전월 고정급 산식만 지원한다.", ["/documents"], blocked=True)]
    payrolls = by_type["payroll_statement"]
    out = [result("PAY-REQUIRED", "complete valid required fields", "complete valid required fields", "필수 자료·정수 금액·ISO 날짜·연결키 검사를 통과했다.", ["/documents"])]
    out.append(result("PAY-UNIQUE", 1, len(payrolls), "동일 사번·귀속기간의 급여명세는 1개여야 한다. 복수 명세는 금액을 합산하지 않는다.", [f"/documents/{i}" for i, _ in payrolls]))
    if len(payrolls) != 1:
        return out
    pi, payroll = payrolls[0]
    payment = by_type["bank_payment"][0][1]
    ledger = by_type["payroll_ledger"][0][1]
    for kind in ("bank_payment", "payroll_ledger"):
        if by_type[kind][0][1]["payroll_id"] != payroll["payroll_id"]:
            return [result("PAY-REQUIRED", "matching payroll_id", kind, "급여ID가 일치하지 않아 계산을 중단한다.", ["/documents"], blocked=True)]
    dates_match = payroll["pay_period_start"] == contract["pay_period_start"] and payroll["pay_period_end"] == contract["pay_period_end"]
    period_start = dt.date.fromisoformat(contract["pay_period_start"])
    period_end = dt.date.fromisoformat(contract["pay_period_end"])
    termination = contract.get("termination_date")
    full_month = period_start.day == 1 and period_end.year == period_start.year and period_end.month == period_start.month and period_end.day == calendar.monthrange(period_start.year, period_start.month)[1]
    active = dates_match and full_month and period_start <= period_end and dt.date.fromisoformat(contract["start_date"]) <= period_start and (termination is None or dt.date.fromisoformat(termination) >= period_end)
    active = active and dt.date.fromisoformat(context["start_date"]) <= period_start <= period_end <= dt.date.fromisoformat(context["end_date"])
    if ledger["period_end"] != contract["pay_period_end"] or not contract["pay_period_start"] <= payment["payment_date"] <= ledger["period_end"]:
        return [result("PAY-REQUIRED", "same-period payment and ledger cutoff", "unsupported timing", "후속지급·분할지급 대사는 다음 연결 단계다. 이번 계산에 당기 지급으로 섞지 않는다.", ["/documents"], blocked=True)]
    out.append(result("PAY-EMPLOYMENT", 1, int(active), "계약·명세 기간과 입퇴사일을 비교한다. 일할·무급휴직 산식은 지원하지 않는다.", ["/documents/0/fields", f"/documents/{pi}/fields"]))
    if not active:
        return out
    gross = contract["base_monthly_amount"] + attendance["overtime_hours"] * attendance["approved_overtime_unit_amount"] + attendance["approved_bonus_amount"] + attendance["approved_other_amount"]
    deductions = by_type["withholding_approval"][0][1]["approved_amount"] + by_type["social_insurance_approval"][0][1]["approved_amount"]
    net = gross - deductions
    out.append(result("PAY-GROSS", gross, payroll["gross_amount"], "고정 합성 산식: 기본월급 + 승인 시간×승인 시간당금액 + 승인 상여 + 기타수당.", ["/documents/0/fields/base_monthly_amount", "/documents/1/fields", f"/documents/{pi}/fields/gross_amount"]))
    out.append(result("PAY-DEDUCTION", deductions, payroll["deduction_amount"], "승인 원천세·사회보험 금액을 더한다. 법정 세액·요율을 계산하지 않는다.", ["/documents/3/fields/approved_amount", "/documents/4/fields/approved_amount", f"/documents/{pi}/fields/deduction_amount"]))
    out.append(result("PAY-NET", net, payroll["net_amount"], "재계산 총급여에서 승인 공제금액을 차감한다.", [f"/documents/{pi}/fields/net_amount"]))
    out.append(result("PAY-PAYMENT", net - ledger["recorded_unpaid_net_amount"], payment["amount"], "명시된 당기 단일 지급액과 순급여-원장 미지급잔액을 비교한다. 차이는 자동 수정분개로 확정하지 않는다.", ["/documents/5/fields/amount", "/documents/6/fields/recorded_unpaid_net_amount"]))
    return out


def workbook_headers(path):
    with zipfile.ZipFile(path) as z:
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = ["".join(si.itertext()) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        relationships = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {e.attrib["Id"]: e.attrib["Target"] for e in relationships}
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        output = {}
        for sheet in wb.findall("m:sheets/m:sheet", NS):
            rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = targets[rid].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            row = ET.fromstring(z.read(target)).find("m:sheetData/m:row", NS)
            cells = []
            for cell in row:
                if cell.attrib.get("t") == "s":
                    cells.append(strings[int(cell.find("m:v", NS).text)])
                elif cell.attrib.get("t") == "inlineStr":
                    cells.append("".join(cell.find("m:is", NS).itertext()))
                else:
                    v = cell.find("m:v", NS)
                    cells.append(v.text if v is not None else None)
            output[sheet.attrib["name"]] = cells
        return output


def validate_sources(manifest):
    base = (HERE / manifest["legacy_base"]).resolve()
    spec = json.loads((base / "spec.json").read_text(encoding="utf-8-sig"))
    total = 0
    for source in manifest["existing_sources"]:
        path = base / source["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"], path.name
        headers = workbook_headers(path)
        book = spec["books"][source["spec_book_index"]]
        assert book["name"] + ".xlsx" == path.name
        for sheet in source["sheets"]:
            assert headers[sheet["sheet"]] == sheet["headers"], sheet["sheet"]
            assert book["headers"][sheet["sheet"]] == sheet["headers"]
            assert len(book["tables"][sheet["sheet"]]) == sheet["catalog_row_count"]
            total += 1
    return total


def main():
    fixture = json.loads((HERE / "fixtures.json").read_text(encoding="utf-8"))
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    assert fixture["schema_version"] == "pm-raw-1"
    assert fixture["synthetic"] is True and fixture["integrated"] is False
    assert {k: fixture["context"][k] for k in EXPECTED_CONTEXT} == EXPECTED_CONTEXT
    results = []
    checks = 0
    for case in fixture["cases"]:
        assert case["case_id"].startswith("PAY-")
        actual = evaluate(case, fixture["context"])
        assert len(actual) == len(case["expected"]), case["case_id"]
        for got, expected in zip(actual, case["expected"]):
            assert {k: got[k] for k in CORE} == {k: expected[k] for k in CORE}, (case["case_id"], got, expected)
            assert got["source_locations"]
            checks += 1
        results.append({"case_id": case["case_id"], "matched_fixed_expectations": True, "checks": actual})
    baseline = fixture["cases"][0]
    probes = []
    probe = copy.deepcopy(baseline)
    duplicate = copy.deepcopy(probe["documents"][2])
    duplicate["document_id"] += "-DUP"
    duplicate["fields"]["payroll_id"] += "-DUP"
    probe["documents"].append(duplicate)
    assert any(x["check_id"] == "PAY-UNIQUE" and x["status"] == "EXCEPTION" for x in evaluate(probe, fixture["context"]))
    probes.append("duplicate_employee_period_payroll_detected_without_summing")
    probe = copy.deepcopy(baseline)
    probe["documents"][0]["fields"]["start_date"] = "2026-12-16"
    assert any(x["check_id"] == "PAY-EMPLOYMENT" and x["status"] == "EXCEPTION" for x in evaluate(probe, fixture["context"]))
    probes.append("midmonth_hire_not_treated_as_fullmonth")
    probe = copy.deepcopy(baseline)
    probe["documents"][0]["fields"]["base_monthly_amount"] = True
    assert evaluate(probe, fixture["context"])[0]["status"] == "INPUT_BLOCKED"
    probes.append("boolean_amount_blocked")
    probe = copy.deepcopy(baseline)
    probe["documents"] = [d for d in probe["documents"] if d["document_type"] != "bank_payment"]
    assert evaluate(probe, fixture["context"])[0]["status"] == "INPUT_BLOCKED"
    probes.append("missing_bank_document_not_zero")
    source_count = validate_sources(manifest)
    print(json.dumps({"worker": "payroll", "passed": True, "fixture_cases": len(results), "fixed_expectation_checks": checks, "guard_probes": probes, "verified_legacy_sheet_anchors": source_count, "integrated": False, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
