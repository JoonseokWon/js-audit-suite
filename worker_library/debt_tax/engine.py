"""Owned DEBT fixtures only. Standard library, read only, no EXE integration."""
from __future__ import annotations

import copy
from datetime import date, timedelta
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import posixpath
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile

BASE = Path(__file__).resolve().parent
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REQUIRED = ("loan_contract", "opening_principal", "principal_movements", "interest_payment", "ledger_summary")
CONTEXT = {"company_code":"SYNTH01", "start_date":"2026-01-01", "end_date":"2026-12-31", "currency":"KRW", "financial_statement_scope":"별도"}


class InvalidInput(ValueError):
    pass


def integer(fields, key):
    value = fields.get(key)
    if type(value) is not int:
        raise InvalidInput(f"{key}: integer required; null is not zero")
    return value


def iso(fields, key):
    value = fields.get(key)
    if not isinstance(value, str):
        raise InvalidInput(f"{key}: ISO date required")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise InvalidInput(f"{key}: invalid date") from exc
    if parsed.isoformat() != value:
        raise InvalidInput(f"{key}: noncanonical date")
    return parsed


def result(check, expected, actual, refs):
    difference = actual - expected
    return {"check_id": check, "status": "PASS" if difference == 0 else "EXCEPTION", "expected_value": expected, "actual_value": actual, "difference": difference, "source_refs": refs}


def evaluate(case, context):
    case_index = {"DEBT-01":0, "DEBT-02":1, "DEBT-03":2}.get(case.get("case_id"), "unknown")
    pointer = f"fixtures.json#/cases/{case_index}/documents"
    refs = [pointer]
    document_indexes = {}
    seen, docs = set(), {}
    try:
        if context != CONTEXT:
            raise InvalidInput("context mismatch")
        if not case["case_id"].startswith("DEBT-"):
            raise InvalidInput("case prefix")
        for document_index, doc in enumerate(case["documents"]):
            did = doc["document_id"]
            if not isinstance(did, str) or not did.startswith("DEBT-") or did in seen:
                raise InvalidInput("duplicate or invalid document ID")
            seen.add(did)
            fields = doc["fields"]
            if (doc["transaction_id"] != "DEBT-TX01" or fields.get("company_code") != "SYNTH01"
                    or fields.get("loan_id") != "DEBT-LN01" or fields.get("currency") != "KRW"):
                raise InvalidInput("join/company/loan/currency mismatch")
            dtype = doc["document_type"]
            if dtype not in (*REQUIRED, "review_requests") or dtype in docs:
                raise InvalidInput("unknown or duplicate document type")
            docs[dtype] = doc
            document_indexes[dtype] = document_index
        missing = [kind for kind in REQUIRED if kind not in docs]
        if missing:
            return [{"check_id":"DEBT-INPUT", "status":"INPUT_BLOCKED", "expected_value":5, "actual_value":5-len(missing), "difference":-len(missing), "reason":"missing: " + ", ".join(missing), "source_refs":refs}]
        contract, opening, movements, payment, ledger = [docs[k]["fields"] for k in REQUIRED]
        for fields in (movements, ledger):
            if (iso(fields, "start_date").isoformat() != context["start_date"] or
                    iso(fields, "end_date").isoformat() != context["end_date"]):
                raise InvalidInput("source reporting period mismatch")
        start, end = iso(contract, "interest_start"), iso(contract, "interest_end")
        if start.isoformat() != context["start_date"] or end.isoformat() != context["end_date"]:
            raise InvalidInput("unsupported interest period")
        if iso(contract, "contract_start") > start or iso(contract, "maturity_date") < end:
            raise InvalidInput("interest period outside contract")
        if iso(opening, "as_of") != start - timedelta(days=1):
            raise InvalidInput("opening date mismatch")
        if not (start <= iso(payment, "payment_date") <= end):
            raise InvalidInput("payment date outside reporting period")
        if (contract.get("method") != "simple_fixed_rate_no_fees" or
                contract.get("end_date_inclusive") is not True or
                contract.get("principal_changes_during_interest_period") is not False or
                integer(contract, "day_basis") != 365 or integer(contract, "fees") != 0):
            raise InvalidInput("unsupported interest basis, fees or principal changes")
        if payment.get("settlement_allocation") != "interest_only" or not payment.get("bank_transaction_id", "").startswith("DEBT-"):
            raise InvalidInput("unallocated settlement")
        principal, opening_accrued = integer(opening, "principal"), integer(opening, "interest_payable")
        drawdowns, repayments, noncash = [integer(movements, k) for k in ("drawdowns", "repayments", "noncash_changes")]
        if (principal <= 0 or opening_accrued < 0 or (drawdowns, repayments, noncash) != (0, 0, 0)
                or movements.get("completeness") != "synthetic_explicit_zero_activity"):
            raise InvalidInput("this prototype accepts explicit zero principal activity only")
        rate = integer(contract, "annual_rate_basis_points")
        if rate < 0:
            raise InvalidInput("unsupported negative interest rate")
        cash = integer(payment, "cash_movement")
        principal_gl, expense_gl, accrued_gl = [integer(ledger, k) for k in ("principal_closing_signed", "interest_expense_signed", "interest_payable_closing_signed")]
        if cash > 0 or principal_gl > 0 or accrued_gl > 0:
            raise InvalidInput("unsupported GL/cash sign; no automatic absolute values")
        if tuple(ledger.get(k) for k in ("principal_account", "interest_expense_account", "interest_payable_account")) != ("2500", "5710", "2420"):
            raise InvalidInput("unapproved account mapping")
        journal_ids = ledger.get("journal_ids")
        if not isinstance(journal_ids, list) or not journal_ids or len(set(journal_ids)) != len(journal_ids) or any(not j.startswith("DEBT-") for j in journal_ids):
            raise InvalidInput("missing or duplicate journal references")
        interest = Fraction(principal * rate * ((end - start).days + 1), 10000 * 365)
        if interest.denominator != 1:
            raise InvalidInput("fractional KRW requires an explicit approved rounding policy")
        interest = interest.numerator
        source = lambda *types: [f"{pointer}/{document_indexes[t]}" for t in types]
        output = [result("DEBT-INPUT", 5, 5, refs),
                  result("DEBT-PRINCIPAL", principal + drawdowns - repayments + noncash, -principal_gl, source("opening_principal", "principal_movements", "ledger_summary")),
                  result("DEBT-INTEREST", interest, expense_gl, source("loan_contract", "opening_principal", "ledger_summary")),
                  result("DEBT-ACCRUAL", opening_accrued + interest + cash, -accrued_gl, source("loan_contract", "opening_principal", "interest_payment", "ledger_summary"))]
        for record, field, original in zip(output[1:], ("principal_closing_signed", "interest_expense_signed", "interest_payable_closing_signed"), (principal_gl, expense_gl, accrued_gl)):
            record["original_value"] = original
            record["original_location"] = f"{pointer}/{document_indexes['ledger_summary']}/fields/{field}"
            record["follow_up"] = "원계약·정산명세·원장행·후속지급을 확인하고 감사인이 수정 여부 검토" if record["status"] == "EXCEPTION" else "계산 일치 후에도 IPE·증빙 진위·약정·조회 검토 별도 필요"
            record["review_status"] = "미검토"
            if record["check_id"] in ("DEBT-INTEREST", "DEBT-ACCRUAL") and record["status"] == "EXCEPTION":
                record["exception_cause_id"] = "DEBT-MISSING-INTEREST01"
        return output
    except (InvalidInput, KeyError, TypeError) as exc:
        return [{"check_id":"DEBT-INPUT", "status":"INPUT_BLOCKED", "expected_value":None, "actual_value":None, "difference":None, "reason":str(exc), "source_refs":refs}]


def xlsx_rows(path, sheet_name):
    """Read cached cells only, never execute formulas or edit the source workbook."""
    with ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        sheets = {s.attrib["name"]: s.attrib[f"{{{REL}}}id"] for s in wb.find("s:sheets", NS)}
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = next(r.attrib["Target"] for r in rels if r.attrib["Id"] == sheets[sheet_name])
        part = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = ["".join(si.itertext()) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        rows = []
        root = ET.fromstring(z.read(part))
        for row in root.findall("s:sheetData/s:row", NS):
            cells = {}
            for cell in row:
                letters = "".join(c for c in cell.attrib["r"] if c.isalpha())
                col = 0
                for ch in letters:
                    col = col * 26 + ord(ch) - 64
                value = cell.find("s:v", NS)
                if cell.attrib.get("t") == "inlineStr":
                    value = "".join(cell.find("s:is", NS).itertext())
                elif value is None:
                    value = None
                elif cell.attrib.get("t") == "s":
                    value = shared[int(value.text)]
                elif cell.attrib.get("t") in ("str", "e"):
                    value = value.text
                else:
                    value = json.loads(value.text)
                cells[col-1] = value
            if cells:
                rows.append([cells.get(i) for i in range(max(cells)+1)])
        return rows


def verify_catalog(manifest):
    root = (BASE / manifest["existing_sources_root"]).resolve()
    catalog = json.loads((root / "spec.json").read_text(encoding="utf-8"))
    reports = []
    for source in manifest["existing_sources"]:
        index = int(source["catalog_pointer"].split("/")[-1])
        dataset = catalog["datasets"][index]
        assert dataset["id"] == source["dataset_id"]
        assert source["file"] == "배포/" + dataset["file"]
        assert source["sheet"] == dataset["name"]
        path = root / source["file"]
        observed = xlsx_rows(path, source["sheet"])
        width = len(dataset["headers"])
        blank_rows = [i + 1 for i, row in enumerate(observed) if all(v is None for v in row)]
        padded = [r + [None] * (width-len(r)) for r in observed if any(v is not None for v in r)]
        expected = [dataset["headers"], *dataset["rows"]]
        transport_notes = []
        # Known XLSX export representation only. Preserve raw observations in the report.
        if dataset["id"] == "D007":
            for row_number in (2, 3):
                raw = padded[row_number-1][6]
                plain = expected[row_number-1][6]
                assert raw == "'" + plain, "D007 timestamp representation changed"
                transport_notes.append({"cell":f"G{row_number}", "xlsx_raw":raw, "catalog_value":plain, "interpretation":"explicit leading text apostrophe, comparison only; source unchanged"})
                padded[row_number-1][6] = plain
        assert padded == expected, f"{source['dataset_id']}: XLSX/catalog mismatch"
        assert not blank_rows or (dataset["id"] == "D057" and blank_rows == [2]), "unexpected blank source row"
        reports.append({"dataset_id":dataset["id"], "rows":len(dataset["rows"]), "status":"PASS", "transport_notes":transport_notes, "formatted_empty_rows":blank_rows, "file_sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    return reports


def main():
    fixtures = json.loads((BASE / "fixtures.json").read_text(encoding="utf-8"))
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    assert fixtures["schema_version"] == "pm-raw-1" and fixtures["synthetic"] is True and fixtures["integrated"] is False
    assert manifest["synthetic"] is True and manifest["integrated"] is False
    assert fixtures["context"] == manifest["context"] == CONTEXT
    # Independent fixed hand oracles are not read from the generated expected fields.
    oracle = {
        "DEBT-01": [("DEBT-INPUT","PASS",5,5,0),("DEBT-PRINCIPAL","PASS",2000000,2000000,0),("DEBT-INTEREST","PASS",50000,50000,0),("DEBT-ACCRUAL","PASS",20000,20000,0)],
        "DEBT-02": [("DEBT-INPUT","PASS",5,5,0),("DEBT-PRINCIPAL","PASS",2000000,2000000,0),("DEBT-INTEREST","EXCEPTION",50000,30000,-20000),("DEBT-ACCRUAL","EXCEPTION",20000,0,-20000)],
        "DEBT-03": [("DEBT-INPUT","INPUT_BLOCKED",5,4,-1)]
    }
    keys = ("check_id", "status", "expected_value", "actual_value", "difference")
    assert [c["case_id"] for c in fixtures["cases"]] == list(oracle)
    results = []
    for case in fixtures["cases"]:
        actual = evaluate(case, fixtures["context"])
        for label, records in (("fixed fixture expected", case["expected"]), ("computed", actual)):
            assert [tuple(r[k] for k in keys) for r in records] == oracle[case["case_id"]], (case["case_id"], label, records)
        results.append({"case_id":case["case_id"], "status":"PASS", "checks":actual})
    base = fixtures["cases"][0]
    mutations = [
        ("null_interest_rate", 0, "annual_rate_basis_points", None),
        ("boolean_amount", 1, "principal", True),
        ("null_payment", 3, "cash_movement", None),
        ("wrong_company", 4, "company_code", "SYNTH02"),
        ("currency_mismatch", 4, "currency", "USD"),
        ("period_mismatch", 4, "end_date", "2025-12-31"),
        ("liability_sign", 4, "principal_closing_signed", 2000000),
        ("unsupported_fee", 0, "fees", 100),
        ("unapproved_principal_activity", 2, "repayments", 100),
        ("fractional_KRW_without_rounding_policy", 1, "principal", 2000001)
    ]
    controls = []
    for label, index, field, value in mutations:
        changed = copy.deepcopy(base)
        changed["documents"][index]["fields"][field] = value
        got = evaluate(changed, CONTEXT)
        assert len(got) == 1 and got[0]["status"] == "INPUT_BLOCKED", (label, got)
        controls.append({"control":label,"status":"PASS"})
    changed = copy.deepcopy(base)
    changed["documents"].append(copy.deepcopy(changed["documents"][0]))
    assert evaluate(changed, CONTEXT)[0]["status"] == "INPUT_BLOCKED"
    controls.append({"control":"duplicate_document","status":"PASS"})
    changed = copy.deepcopy(base)
    changed["documents"] = [d for d in changed["documents"] if d["document_type"] != "interest_payment"]
    assert evaluate(changed, CONTEXT)[0]["status"] == "INPUT_BLOCKED"
    controls.append({"control":"missing_payment_is_not_zero","status":"PASS"})
    sources = verify_catalog(manifest)
    report = {"worker":"debt_tax", "synthetic":True, "integrated":False, "status":"PASS", "case_count":len(results), "computed_check_count":sum(len(r["checks"]) for r in results), "input_guard_count":len(controls), "catalog_sources_verified":len(sources), "cases":results, "input_guards":controls, "catalog_sources":sources}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, ValueError, KeyError, OSError) as exc:
        print(json.dumps({"worker":"debt_tax","status":"FAIL","error":str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
