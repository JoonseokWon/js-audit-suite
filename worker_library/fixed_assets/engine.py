"""Small isolated asset evidence tests. Standard library only; never posts entries."""
from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONTEXT = {"company_code": "SYNTH01", "start_date": "2026-01-01",
           "end_date": "2026-12-31", "currency": "KRW",
           "financial_statement_scope": "별도"}


class MissingEvidence(ValueError):
    pass


def integer(value):
    if type(value) is not int:
        raise MissingEvidence("Amount/month count must be an integer; null is not zero")
    return value


def document(case, doc_type, asset_id=None, optional=False):
    matches = [d for d in case["documents"] if d["document_type"] == doc_type
               and (asset_id is None or d["fields"].get("asset_id") == asset_id)]
    if optional and not matches:
        return None
    if len(matches) != 1:
        raise MissingEvidence(f"Expected one {doc_type}/{asset_id}, found {len(matches)}")
    return matches[0]["fields"]


def expected_charge(register, available_on):
    """Explicit fixture assumption: full months July-Dec, no disposals/changes."""
    cost, residual = integer(register["cost_krw"]), integer(register["residual_value_krw"])
    if cost < 0 or residual < 0 or residual > cost:
        raise MissingEvidence("Invalid cost/residual")
    if register["asset_class"] == "land":
        if register["ordinary_unlimited_life_land"] is not True:
            raise MissingEvidence("Land with a limited life requires separate assessment")
        return 0
    life = integer(register["useful_life_months"])
    if life <= 0 or register["method"] != "straight_line_monthly":
        raise MissingEvidence("Unsupported method/life")
    ready = date.fromisoformat(available_on)
    if ready.day != 1:
        raise MissingEvidence("This initial fixture supports first-of-month availability only")
    end = date.fromisoformat(CONTEXT["end_date"])
    start = max(ready, date.fromisoformat(CONTEXT["start_date"]))
    months = max(0, min(life, (end.year-start.year)*12 + end.month-start.month+1))
    numerator = (cost-residual)*months
    quotient, remainder = divmod(numerator, life)
    if remainder:
        raise MissingEvidence("Fixture does not specify fractional-won rounding")
    return min(cost-residual, quotient)


def outcome(check_id, expected_value, actual_value, blocked=False):
    difference = actual_value-expected_value if type(expected_value) is int and type(actual_value) is int else None
    return {"check_id": check_id,
            "status": "INPUT_BLOCKED" if blocked else "PASS" if expected_value == actual_value else "EXCEPTION",
            "expected_value": expected_value, "actual_value": actual_value, "difference": difference}


def evaluate(case):
    machine = document(case, "asset_register", "ASSET-MACHINE-01")
    software = document(case, "asset_register", "ASSET-SOFTWARE-01")
    land = document(case, "asset_register", "ASSET-LAND-01")
    invoice = document(case, "purchase_invoice", "ASSET-MACHINE-01")
    payment = document(case, "payment", "ASSET-MACHINE-01")
    commission = document(case, "available_for_use_acceptance", "ASSET-MACHINE-01")
    activation = document(case, "available_for_use_acceptance", "ASSET-SOFTWARE-01")
    cadastral = document(case, "cadastral_abstract", "ASSET-LAND-01")
    title = document(case, "title_registry_abstract", "ASSET-LAND-01", optional=True)
    gl = document(case, "isolated_gl_asset_summary")
    machine_charge = expected_charge(machine, commission["available_for_use_date"])
    software_charge = expected_charge(software, activation["available_for_use_date"])
    land_charge = expected_charge(land, land["available_for_use_date"])
    register_net = sum(integer(r["cost_krw"])-integer(r["book_accumulated_charge_krw"])
                       for r in (machine, software, land))
    gl_net = sum(integer(x["cost_debit_balance_krw"])+integer(x["accumulated_credit_signed_krw"])
                 for x in gl["balances"])
    recalculated_net = sum(integer(r["cost_krw"]) for r in (machine,software,land))-machine_charge-software_charge-land_charge
    if title is None:
        title_actual = None
    elif (title["parcel_id"] != cadastral["parcel_id"] or title["parcel_id"] != land["parcel_id"]
          or title["as_of_date"] != CONTEXT["end_date"]):
        title_actual = "IDENTITY_OR_DATE_MISMATCH"
    else:
        title_actual = title["registered_owner_company_code"]
    return [
        outcome("ASSET-ACQUISITION", integer(invoice["capitalizable_cost_krw"]), integer(machine["cost_krw"])),
        outcome("ASSET-PAYMENT", integer(invoice["gross_payable_krw"]), -integer(payment["signed_bank_amount_krw"])),
        outcome("ASSET-READY-DATE", commission["available_for_use_date"], machine["available_for_use_date"]),
        outcome("ASSET-DEPRECIATION", machine_charge, integer(machine["book_current_charge_krw"])),
        outcome("ASSET-AMORTIZATION", software_charge, integer(software["book_current_charge_krw"])),
        outcome("ASSET-LAND-DEPRECIATION", land_charge, integer(land["book_current_charge_krw"])),
        outcome("ASSET-TITLE", CONTEXT["company_code"], title_actual, blocked=title is None),
        outcome("ASSET-REGISTER-GL", register_net, gl_net),
        outcome("ASSET-LEAD-RECALC", recalculated_net, gl_net),
    ]


def validate_structure(data):
    assert data["schema_version"] == "pm-raw-1"
    assert data["synthetic"] is True and data["integrated"] is False
    assert data["context"] == CONTEXT
    assert len(data["cases"]) == 3
    case_ids = set()
    for case in data["cases"]:
        assert set(("case_id", "description", "documents", "expected")) <= set(case)
        assert case["case_id"].startswith("ASSET-") and case["case_id"] not in case_ids
        case_ids.add(case["case_id"])
        ids = set()
        for doc in case["documents"]:
            assert doc["document_id"].startswith("ASSET-") and doc["document_id"] not in ids
            ids.add(doc["document_id"])
            assert doc["transaction_id"].startswith("ASSET-")
            assert doc["fields"]["company_code"] == CONTEXT["company_code"]
            assert doc["fields"]["synthetic_notice"] == "합성 테스트 자료 / 법적 효력 없음"
        expected_ids = [e["check_id"] for e in case["expected"]]
        assert len(set(expected_ids)) == len(expected_ids) == 9
        for e in case["expected"]:
            assert e["reason"] and e["source_locations"] and e["follow_up"]
            assert e["status"] in ("PASS", "EXCEPTION", "INPUT_BLOCKED")
            for loc in e["source_locations"]:
                assert loc["document_id"] in ids
                assert loc["json_pointer"].startswith("/cases/")


def main():
    data = json.loads((ROOT/"fixtures.json").read_text(encoding="utf-8"))
    validate_structure(data)
    count = 0
    for case in data["cases"]:
        actual = evaluate(case)
        expected = [{k: x[k] for k in ("check_id", "status", "expected_value", "actual_value", "difference")}
                    for x in case["expected"]]
        assert actual == expected, f"{case['case_id']}: {actual!r} != {expected!r}"
        count += len(actual)
        print(case["case_id"], "OK", ", ".join(f"{x['check_id']}={x['status']}" for x in actual if x["status"] != "PASS") or "all PASS")
    # Ensure missing numeric evidence and a missing mandatory document cannot masquerade as zero.
    for field in ("cost_krw", "book_current_charge_krw"):
        case = copy.deepcopy(data["cases"][0])
        document(case, "asset_register", "ASSET-MACHINE-01")[field] = None
        try:
            evaluate(case)
        except MissingEvidence:
            pass
        else:
            raise AssertionError(f"Missing {field} silently accepted")
    case = copy.deepcopy(data["cases"][0])
    case["documents"] = [d for d in case["documents"] if d["document_type"] != "purchase_invoice"]
    try:
        evaluate(case)
    except MissingEvidence:
        pass
    else:
        raise AssertionError("Missing invoice silently accepted")
    print(f"PASS: 3 cases, {count} fixed expected comparisons, 3 missing-input guard probes; no app integration")


if __name__ == "__main__":
    main()
