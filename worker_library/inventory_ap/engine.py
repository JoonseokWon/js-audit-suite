"""Independent worker fixture checks. Standard library only; does not import EXE code.

Run: python -B verify_fixtures.py
No files are written. Existing source workbooks are read only.
"""
from __future__ import annotations

import copy
import hashlib
import json
import posixpath
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
NUMBER_FIELDS = {
    "quantity", "unit_cost", "net_amount", "tax_amount", "gross_amount", "amount",
    "payable_signed", "inventory_debit", "input_vat_debit", "ap_credit",
    "closing_payable_signed", "opening_quantity", "issued_quantity",
    "closing_quantity", "recorded_allowance", "estimated_sale_price",
    "completion_cost", "selling_cost", "receipt_count",
}
CHECK_IDS = ["RECEIPT_QTY", "INVOICE_QTY", "INVOICE_NET", "TAX_GROSS", "CUTOFF",
             "AP_RECORD", "AP_BALANCE", "FOLLOWUP_PAYMENT", "SUPPLIER_TIE",
             "STOCK_ROLL", "STOCK_COUNT", "NRV_ALLOWANCE"]
FIXED_STATUS_ORACLE = {
    "INV-01-NORMAL": {},
    "INV-02-MISSING-AP": {"CUTOFF": "INPUT_BLOCKED", "AP_RECORD": "EXCEPTION",
                           "AP_BALANCE": "INPUT_BLOCKED", "SUPPLIER_TIE": "INPUT_BLOCKED"},
    "INV-03-CUTOFF": dict.fromkeys(
        ["CUTOFF", "AP_RECORD", "AP_BALANCE", "SUPPLIER_TIE", "STOCK_ROLL", "STOCK_COUNT"],
        "EXCEPTION"),
    "INV-04-COUNT-NRV": {"STOCK_COUNT": "EXCEPTION", "NRV_ALLOWANCE": "EXCEPTION"},
    "INV-05-NULL-NRV": {"NRV_ALLOWANCE": "INPUT_BLOCKED"},
}


class InputProblem(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputProblem(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def require(condition, message):
    if not condition:
        raise InputProblem(message)


def parse_date(value):
    require(isinstance(value, str), "Date must be ISO text")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise InputProblem(f"Invalid date: {value}") from exc
    require(parsed.isoformat() == value, "Date must be YYYY-MM-DD")
    return parsed


def evaluate(case, context):
    """Small, declared single-order model; deliberately not a production adapter."""
    by_type, by_id = {}, {}
    for document in case["documents"]:
        doc_id, kind = document["document_id"], document["document_type"]
        require(doc_id.startswith("INV-") and doc_id not in by_id, "Duplicate/bad evidence ID")
        require(kind not in by_type, "One document per type in this limited fixture")
        require(document["transaction_id"] == "INV-TXN-001", "Transaction link mismatch")
        fields = document["fields"]
        require(fields["company_code"] == context["회사코드"], "Company mismatch")
        for name, value in fields.items():
            if name in NUMBER_FIELDS:
                if value is None and name == "estimated_sale_price":
                    continue
                require(type(value) is int and abs(value) <= 10**13, f"Invalid integer: {name}")
            if name.endswith("_date") or name in {"scope_start", "scope_end"}:
                parse_date(value)
        by_type[kind], by_id[doc_id] = document, document

    required = {"purchase_order", "purchase_terms", "goods_receipt", "purchase_invoice",
                "tax_invoice", "bank_payment", "supplier_statement", "stock_ledger",
                "physical_count", "nrv_evidence", "warehouse_receipt_register"}
    require(required <= by_type.keys(), "Required non-ledger source document missing")
    def doc(kind):
        return by_type[kind]["fields"]

    po, terms, gr, inv = (doc(x) for x in
                          ("purchase_order", "purchase_terms", "goods_receipt", "purchase_invoice"))
    tax, bank, supplier = (doc(x) for x in ("tax_invoice", "bank_payment", "supplier_statement"))
    stock, count, nrv, register = (doc(x) for x in
                                  ("stock_ledger", "physical_count", "nrv_evidence", "warehouse_receipt_register"))
    gl = doc("gl_ap_record") if "gl_ap_record" in by_type else None
    for kind in required | ({"gl_ap_record"} if gl else set()):
        fields = doc(kind)
        for key, reference in [("purchase_order_id", "INV-PO-001"), ("receipt_id", "INV-GR-001"),
                               ("invoice_id", "INV-PI-001"), ("terms_evidence", "INV-TERM-001")]:
            if key in fields:
                require(fields[key] == reference and reference in by_id, "Broken evidence join")
        if "product_id" in fields:
            require(fields["product_id"] == po["product_id"], "Product mismatch")
        if "vendor_id" in fields:
            require(fields["vendor_id"] == po["vendor_id"], "Vendor mismatch")
        if "unit" in fields:
            require(fields["unit"] == po["unit"] == "EA", "Unsupported/mismatched unit")
        if "warehouse_id" in fields:
            require(fields["warehouse_id"] == gr["warehouse_id"], "Warehouse mismatch")
    require(terms["control_transfer_basis"] == po["control_transfer_basis"] ==
            "accepted_at_destination", "Contract condition requires auditor interpretation")
    require(terms["approval_status"] == "synthetic_declared", "Terms evidence not declared")
    require(gr["owner_id"] == context["회사코드"], "Third party ownership outside fixture")
    require(register["receipt_ids"] == ["INV-GR-001"] and register["receipt_count"] == 1,
            "Receipt population register mismatch")
    require(register["cancelled_receipts"] == [], "Cancelled receipt outside fixture")
    require(parse_date(register["scope_start"]) <= parse_date(gr["accepted_date"]) <=
            parse_date(register["scope_end"]), "Receipt outside source population")
    year_end = parse_date(context["기준일"])
    for fields, key in [(stock, "balance_date"), (count, "count_date"), (supplier, "balance_date")]:
        require(parse_date(fields[key]) == year_end, "Count/balance date needs roll-forward adapter")
    require(year_end < parse_date(bank["payment_date"]) <= parse_date(context["후속검색종료"]),
            "Payment outside declared subsequent population")
    require(bool(nrv["year_end_condition_basis"]), "NRV year-end condition evidence absent")
    require(all(value >= 0 for fields in (po, gr, inv, stock, count, nrv)
                for key, value in fields.items() if key in NUMBER_FIELDS and value is not None),
            "Negative quantities/costs outside limited fixture")
    require(inv["net_amount"] + inv["tax_amount"] == inv["gross_amount"], "Invoice total invalid")
    require(tax["net_amount"] == inv["net_amount"] and tax["tax_amount"] == inv["tax_amount"],
            "Tax/invoice component mismatch requires separate exception")
    if gl:
        require(gl["inventory_debit"] + gl["input_vat_debit"] == gl["ap_credit"],
                "Journal not balanced")

    results = []
    def check(check_id, target, actual, *, same_period=False):
        if target is None or actual is None:
            status = "INPUT_BLOCKED"
        elif same_period:
            status = "PASS" if (parse_date(target) <= year_end) == (parse_date(actual) <= year_end) else "EXCEPTION"
        else:
            status = "PASS" if target == actual else "EXCEPTION"
        difference = actual - target if type(actual) is int and type(target) is int else None
        results.append({"check_id": check_id, "status": status, "expected_value": target,
                        "actual_value": actual, "difference": difference})

    current_receipt = parse_date(context["시작일"]) <= parse_date(gr["accepted_date"]) <= year_end
    check("RECEIPT_QTY", po["quantity"], gr["quantity"])
    check("INVOICE_QTY", gr["quantity"], inv["quantity"])
    check("INVOICE_NET", inv["quantity"] * po["unit_cost"], inv["net_amount"])
    check("TAX_GROSS", inv["gross_amount"], tax["gross_amount"])
    check("CUTOFF", gr["accepted_date"], gl["posting_date"] if gl else None, same_period=True)
    check("AP_RECORD", int(current_receipt), int(gl is not None and parse_date(gl["posting_date"]) <= year_end))
    check("AP_BALANCE", -inv["gross_amount"] if current_receipt else 0,
          gl["closing_payable_signed"] if gl else None)
    check("FOLLOWUP_PAYMENT", -inv["gross_amount"], bank["amount"])
    check("SUPPLIER_TIE", supplier["payable_signed"], gl["closing_payable_signed"] if gl else None)
    check("STOCK_ROLL", stock["opening_quantity"] + (gr["quantity"] if current_receipt else 0)
          - stock["issued_quantity"], stock["closing_quantity"])
    check("STOCK_COUNT", count["quantity"], stock["closing_quantity"])
    price = nrv["estimated_sale_price"]
    allowance = None
    if price is not None:
        nrv_per_unit = price - nrv["completion_cost"] - nrv["selling_cost"]
        require(nrv_per_unit >= 0, "Negative NRV requires separate liability judgment")
        allowance = stock["closing_quantity"] * max(stock["unit_cost"] - nrv_per_unit, 0)
    check("NRV_ALLOWANCE", allowance, stock["recorded_allowance"])
    return results


def workbook_cells(path):
    """Read actual XLSX cells using the ZIP/XML format, without modifying files."""
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(item.itertext()) for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        relations = {item.attrib["Id"]: item.attrib["Target"] for item in
                     ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        result = {}
        for sheet in ET.fromstring(archive.read("xl/workbook.xml")).find("s:sheets", NS):
            target = relations[sheet.attrib[f"{{{NS['r']}}}id"]]
            member = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            cells = {}
            for cell in ET.fromstring(archive.read(member)).findall("s:sheetData/s:row/s:c", NS):
                value = cell.find("s:v", NS)
                if cell.attrib.get("t") == "s":
                    value = strings[int(value.text)]
                elif cell.attrib.get("t") == "inlineStr":
                    value = "".join(cell.find("s:is", NS).itertext())
                else:
                    value = value.text if value is not None else None
                    if value is not None and cell.attrib.get("t") not in {"str", "e"}:
                        value = Decimal(value)
                if value is not None:
                    require(cell.find("s:f", NS) is None, "Source raw table contains unexpected formula")
                    cells[cell.attrib["r"]] = value
            result[sheet.attrib["name"]] = cells
        return result


def column_name(number):
    value = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        value = chr(65 + remainder) + value
    return value


def verify_sources(manifest):
    root = (HERE / manifest["source_root_relative_to_manifest"]).resolve()
    require(root.name == "2026-10-23" and (root / "spec.json").is_file(), "Wrong resolved source root")
    spec = load_json(root / "spec.json")
    files = {}
    for item in manifest["source_files"]:
        path = root / item["path"]
        require(path.is_file(), f"Source does not exist: {item['path']}")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], "Source file SHA256 changed")
        actual = workbook_cells(path)
        book = spec["books"][item["spec_book_index"]]
        require(list(actual) == list(book["headers"]), "Actual workbook sheet inventory differs from spec")
        files[item["file_id"]] = (actual, book)
    cell_count = 0
    for source in manifest["source_tables"]:
        actual, book = files[source["file_id"]]
        sheet = source["sheet"]
        pointer = source["spec_pointer"]
        require(pointer == f"/books/{next(f['spec_book_index'] for f in manifest['source_files'] if f['file_id'] == source['file_id'])}/tables/{sheet}",
                "Wrong spec pointer")
        rows, headers = book["tables"][sheet], book["headers"][sheet]
        require(len(rows) == source["rows"], "Row count changed")
        require(source["range"] == f"A1:{column_name(len(headers))}{len(rows) + 1}", f"Wrong source cell range: {sheet}")
        for row_no, row in enumerate([headers] + rows, 1):
            for col_no, expected in enumerate(row, 1):
                address = f"{column_name(col_no)}{row_no}"
                observed = actual[sheet].get(address)
                if type(expected) in {int, float}:
                    expected = Decimal(str(expected))
                require(observed == expected, f"Actual source differs: {sheet}!{address}")
                cell_count += 1
        if "dataset_id" in source:
            matches = [item for item in spec["datasets"] if item["id"] == source["dataset_id"]]
            require(len(matches) == 1 and matches[0]["name"] == sheet and matches[0]["rows"] == rows,
                    "Current dataset ID/spec mismatch")
    return {"file_hashes_verified": len(files), "tables_verified": len(manifest["source_tables"]),
            "cells_compared_to_spec": cell_count, "actual_source_root_exists": True}


def main():
    manifest, fixtures = load_json(HERE / "manifest.json"), load_json(HERE / "fixtures.json")
    require(fixtures["schema_version"] == "pm-raw-1" and fixtures["synthetic"] is True and
            fixtures["integrated"] is False, "Fixture status invalid")
    context = fixtures["context"]
    require({key: context[key] for key in manifest["context"]} == manifest["context"], "Context mismatch")
    require(fixtures["workpaper_state"] == {"status":"미검토 초안", "preparer":None,
            "reviewer":None,"conclusion":None,"journal_approval":None}, "Workpaper cannot auto-finalize")
    cases = fixtures["cases"]
    require([case["case_id"] for case in cases] == list(FIXED_STATUS_ORACLE), "Fixed cases changed")
    totals = Counter()
    case_summary = []
    for case in cases:
        calculated = evaluate(case, context)
        require([item["check_id"] for item in case["expected"]] == CHECK_IDS, "Check inventory changed")
        counts = Counter()
        for actual, expected in zip(calculated, case["expected"], strict=True):
            require(bool(expected["reason"]), "Expected result needs a reason")
            require(bool(expected["follow_up"]) and bool(expected["unit"]), "Follow-up/unit absent")
            require(bool(expected["source_refs"]), "Source references absent")
            for reference in expected["source_refs"]:
                target = fixtures
                for token in reference["json_pointer"].lstrip("/").split("/"):
                    target = target[int(token)] if isinstance(target, list) else target[token]
                if "missing_document_type" in reference:
                    require(isinstance(target, list) and not any(d["document_type"] ==
                            reference["missing_document_type"] for d in target), "Missing document ref invalid")
                else:
                    require(target == reference["original_value"], "Source pointer/raw value mismatch")
            require(actual == {key: expected[key] for key in actual},
                    f"Fixed expected values failed: {case['case_id']} {actual}")
            require(actual["status"] == FIXED_STATUS_ORACLE[case["case_id"]].get(actual["check_id"], "PASS"),
                    "Fixed status oracle failed")
            totals[actual["status"]] += 1
            counts[actual["status"]] += 1
        case_summary.append({"case_id": case["case_id"], "checks": len(calculated), "results": dict(counts)})
    # Literal financial oracle, independent of the JSON expected arrays.
    observed = {item["check_id"]: item for item in evaluate(cases[3], context)}
    require(observed["NRV_ALLOWANCE"]["expected_value"] == 40000, "40000 won NRV hand oracle failed")
    require(observed["STOCK_COUNT"]["difference"] == 5, "5 EA hand oracle failed")
    missing = {item["check_id"]: item for item in evaluate(cases[1], context)}
    require(missing["AP_BALANCE"]["actual_value"] is None and missing["AP_BALANCE"]["difference"] is None,
            "Missing ledger amount must remain null")

    # Corrupt single inputs in disposable memory; the fixture file remains untouched.
    mutations = [
        ("duplicate evidence ID", lambda c: c["documents"].append(copy.deepcopy(c["documents"][0]))),
        ("company mismatch", lambda c: c["documents"][0]["fields"].update(company_code="WRONG")),
        ("float amount", lambda c: c["documents"][3]["fields"].update(net_amount=100000.0)),
        ("missing receipt", lambda c: c["documents"].__setitem__(slice(None),
            [d for d in c["documents"] if d["document_type"] != "goods_receipt"])),
        ("invalid date", lambda c: next(d for d in c["documents"] if d["document_type"] == "goods_receipt")["fields"].update(accepted_date="2026-02-30")),
        ("receipt register omission", lambda c: next(d for d in c["documents"] if d["document_type"] == "warehouse_receipt_register")["fields"].update(receipt_ids=[])),
        ("unit mismatch", lambda c: next(d for d in c["documents"] if d["document_type"] == "physical_count")["fields"].update(unit="KG")),
    ]
    for label, mutate in mutations:
        candidate = copy.deepcopy(cases[0])
        mutate(candidate)
        try:
            evaluate(candidate, context)
        except InputProblem:
            continue
        raise AssertionError(f"Corruption was not rejected: {label}")
    source_results = verify_sources(manifest)
    print(json.dumps({"status":"PASS", "synthetic":True,"integrated":False,
        "fixture_validation":{"cases":len(cases),"fixed_result_checks":sum(totals.values()),
                              "results":dict(totals),"input_guard_mutations":len(mutations),
                              "case_summary":case_summary},
        "source_index_validation":source_results,
        "limit":"Worker JSON only; existing EXE import, accounting judgment and final workpaper approval are not implemented."},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
