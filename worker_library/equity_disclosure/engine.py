"""Small independent synthetic equity/disclosure checks; no EXE integration."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
CONTEXT = {
    "company_code": "SYNTH01", "start_date": "2026-01-01",
    "end_date": "2026-12-31", "currency": "KRW",
    "financial_statement_scope": "별도",
}
TYPES = (
    "share_capital_rollforward", "approval_minutes", "issue_bank_receipt",
    "synthetic_registration_summary", "related_party_list",
    "related_party_ledger", "related_party_note",
)


def integer(value, name):
    if type(value) is not int:
        raise ValueError(f"{name}: integer required; missing/bool/float is not zero")
    return value


def validate_bundle(bundle):
    if bundle.get("schema_version") != "pm-raw-1":
        raise ValueError("Unsupported schema")
    if bundle.get("synthetic") is not True or bundle.get("integrated") is not False:
        raise ValueError("Must remain synthetic and not integrated")
    if bundle.get("context") != CONTEXT:
        raise ValueError("Company/period/currency/scope mismatch")
    if not 2 <= len(bundle["cases"]) <= 3:
        raise ValueError("Initial fixtures must contain 2 or 3 cases")
    case_ids = set()
    for case in bundle["cases"]:
        case_id = case["case_id"]
        if not case_id.startswith("EQUITY-") or case_id in case_ids:
            raise ValueError("Invalid or repeated case ID")
        case_ids.add(case_id)
        seen, role_seen = set(), set()
        for doc in case["documents"]:
            if not doc["document_id"].startswith("EQUITY-") or doc["document_id"] in seen:
                raise ValueError("Invalid or duplicate document ID")
            seen.add(doc["document_id"])
            if doc["document_type"] not in TYPES or doc["document_type"] in role_seen:
                raise ValueError("Unknown or duplicate document role")
            role_seen.add(doc["document_type"])
            if not doc["transaction_id"].startswith("EQUITY-"):
                raise ValueError("Invalid transaction ID")
            fields = doc["fields"]
            if fields.get("company_code") != CONTEXT["company_code"]:
                raise ValueError("Document company mismatch")
            if fields.get("currency") != CONTEXT["currency"]:
                raise ValueError("Document currency mismatch")
            for key, value in fields.items():
                if key.endswith("_date"):
                    date.fromisoformat(value)
                    if not CONTEXT["start_date"] <= value <= CONTEXT["end_date"]:
                        raise ValueError("Unexpected period in initial fixture")
                if key.endswith(("_amount", "_shares", "_price", "_value")):
                    integer(value, f"{doc['document_id']}/{key}")
            if doc["document_type"] == "related_party_list":
                parties = fields["parties"]
                if not parties or len({p["party_id"] for p in parties}) != len(parties):
                    raise ValueError("Empty or repeated related-party IDs")
                if any(not p["party_id"].startswith("EQUITY-") or not p["relationship"] for p in parties):
                    raise ValueError("Invalid related-party classification")
            for key in ("party_id", "shareholder_id"):
                if key in fields and not fields[key].startswith("EQUITY-"):
                    raise ValueError("Invalid synthetic party ID")
        for item in case["expected"]:
            if item["status"] not in {"PASS", "EXCEPTION", "INPUT_BLOCKED"} or not item["reason"]:
                raise ValueError("Invalid expectation")


def evaluate_case(case):
    docs = {d["document_type"]: d for d in case["documents"]}
    output = []

    def check(check_id, dependencies, function, follow_up):
        missing = [name for name in dependencies if name not in docs]
        if missing:
            output.append({
                "check_id": check_id, "status": "INPUT_BLOCKED", "expected_value": None,
                "actual_value": None, "difference": None,
                "reason": "필수 합성 자료 누락: " + ", ".join(missing),
                "source_locations": [f"case:{case['case_id']}/documents"],
                "follow_up": follow_up,
            })
            return
        selected = [docs[name] for name in dependencies]
        # A transaction ID links evidence; presence alone must not link unrelated documents.
        if len({d["transaction_id"] for d in selected}) != 1:
            raise ValueError(f"{check_id}: unrelated transaction IDs")
        party_ids = {d["fields"]["party_id"] for d in selected if "party_id" in d["fields"]}
        if len(party_ids) > 1:
            raise ValueError(f"{check_id}: unrelated party IDs")
        expected, actual = function(*[d["fields"] for d in selected])
        diff = actual - expected if type(expected) is int and type(actual) is int else None
        output.append({
            "check_id": check_id, "status": "PASS" if actual == expected else "EXCEPTION",
            "expected_value": expected, "actual_value": actual, "difference": diff,
            "reason": "합성 통제 일치" if actual == expected else "합성 원천 사이 차이: 검토 필요",
            "source_locations": [f"case:{case['case_id']}/document:{d['document_id']}/fields" for d in selected],
            "follow_up": follow_up,
        })

    def presence(role, check_id):
        present = role in docs
        output.append({
            "check_id": check_id, "status": "PASS" if present else "INPUT_BLOCKED",
            "expected_value": 1, "actual_value": 1 if present else None,
            "difference": 0 if present else None,
            "reason": "합성 자료 존재" if present else "필수 자료 누락; 영(0)으로 치환 금지",
            "source_locations": [f"case:{case['case_id']}/documents"],
            "follow_up": "요청대장과 원본 발급·작성 범위를 확인하고 감사인이 증거를 평가한다.",
        })

    presence("approval_minutes", "EQUITY-MINUTES_PRESENT")
    presence("related_party_list", "EQUITY-RELATED_LIST_PRESENT")
    check("EQUITY-SHARE_COUNT", ["share_capital_rollforward"],
          lambda s: (s["opening_shares"] + s["issued_shares"], s["closing_shares"]),
          "주주명부·주식 종류·변경내역의 전체성을 검토한다.")
    check("EQUITY-CAPITAL", ["share_capital_rollforward"],
          lambda s: (s["opening_capital_amount"] + s["issued_shares"] * s["par_value"], s["closing_capital_amount"]),
          "자본금 원장 및 기초·기말 등기와 연결하고 실제 증자 효력을 검토한다.")
    check("EQUITY-PREMIUM", ["share_capital_rollforward"],
          lambda s: (s["opening_premium_amount"] + s["issued_shares"] * (s["issue_price"] - s["par_value"]), s["closing_premium_amount"]),
          "단순 보통주 현금증자 가정이다. 발행비용·복합상품·무상증자는 별도 설계한다.")
    check("EQUITY-ISSUE_TERMS", ["share_capital_rollforward", "approval_minutes"],
          lambda s, m: ([m["approved_shares"], m["approved_price"]], [s["issued_shares"], s["issue_price"]]),
          "의결기관 권한·정족수·정관 및 법적 효력은 감사인/법률전문가가 확인한다.")
    check("EQUITY-ISSUE_CASH", ["approval_minutes", "issue_bank_receipt"],
          lambda m, b: (m["approved_shares"] * m["approved_price"], b["received_amount"]),
          "은행 원본·출처·입금자·환급 여부를 확인하고 현금 워커와 배분 연결한다.")
    check("EQUITY-REGISTRATION", ["share_capital_rollforward", "synthetic_registration_summary"],
          lambda s, r: ([s["issued_shares"], s["closing_capital_amount"]], [r["registered_new_shares"], r["registered_capital_amount"]]),
          "합성 등기 요약 일치만 검사한다. 실제 등기 발급·변경일과 법적 효력을 확인한다.")
    check("EQUITY-RELATED_PARTY", ["related_party_list", "related_party_ledger"],
          lambda p, l: (True, l["party_id"] in {r["party_id"] for r in p["parties"]}),
          "제공 목록 내 식별 검사다. 미공개 관계자 전체성은 주주·임원·계약·조회·의사록 등으로 별도 검색한다.")
    check("EQUITY-RELATED_BALANCE", ["related_party_ledger"],
          lambda l: (l["opening_amount"] + l["advance_amount"] - l["repayment_amount"], l["closing_amount"]),
          "상대방 대사·계약·회수·충당금 및 무상거래·약정을 추가 검토한다.")
    check("EQUITY-RELATED_NOTE", ["related_party_ledger", "related_party_note"],
          lambda l, n: (l["closing_amount"], n["closing_amount"]),
          "표시 금액 외 관계의 성격·거래액·조건·보증·약정·손실충당금 공시를 별도 검토한다.")
    return output


def verify_source_index(manifest):
    catalog_path = (HERE / manifest["source_catalog"]).resolve()
    catalog = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
    checked = 0
    for source in manifest["existing_sources"]:
        value = catalog
        for token in source["catalog_pointer"].lstrip("/").split("/"):
            value = value[int(token)] if isinstance(value, list) else value[token]
        if value["id"] != source["dataset_id"] or value["name"] != source["sheet"]:
            raise AssertionError("Catalog identity changed")
        if len(value["rows"]) != source["data_rows"]:
            raise AssertionError("Catalog row count changed")
        path = (HERE / source["file"]).resolve()
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["xlsx_sha256"]:
            raise AssertionError("Indexed source workbook bytes changed")
        with ZipFile(path) as archive:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            sheets = {n.attrib["name"] for n in workbook.findall(".//{*}sheet")}
            if source["sheet"] not in sheets:
                raise AssertionError(f"Missing real XLSX sheet: {source['sheet']}")
        checked += 1
    return checked


def verify():
    bundle = json.loads((HERE / "fixtures.json").read_text(encoding="utf-8"))
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    validate_bundle(bundle)
    source_count = verify_source_index(manifest)
    summaries, assertion_count = [], 0
    for case in bundle["cases"]:
        results = evaluate_case(case)
        expected = {r["check_id"]: r for r in case["expected"]}
        if len(expected) != len(case["expected"]) or set(expected) != {r["check_id"] for r in results}:
            raise AssertionError("Missing, extra, or duplicated fixed expectations")
        for result in results:
            for field in ("status", "expected_value", "actual_value", "difference"):
                if result[field] != expected[result["check_id"]][field]:
                    raise AssertionError(f"{case['case_id']}/{result['check_id']}/{field}")
                assertion_count += 1
        summaries.append({"case_id": case["case_id"], "checks": len(results),
                          "statuses": dict(Counter(r["status"] for r in results))})
    # Controls that must reject malformed/mislinked data rather than producing a false PASS.
    rejected = 0
    for mutation in ("null_amount", "boolean_amount", "duplicate_id", "wrong_context", "wrong_transaction"):
        changed = copy.deepcopy(bundle)
        first = changed["cases"][0]
        if mutation == "null_amount":
            first["documents"][0]["fields"]["opening_capital_amount"] = None
        elif mutation == "boolean_amount":
            first["documents"][0]["fields"]["opening_capital_amount"] = True
        elif mutation == "duplicate_id":
            first["documents"][1]["document_id"] = first["documents"][0]["document_id"]
        elif mutation == "wrong_context":
            changed["context"]["currency"] = "USD"
        else:
            first["documents"][2]["transaction_id"] = "EQUITY-UNRELATED"
        try:
            validate_bundle(changed)
            evaluate_case(first)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError(f"Malformed control accepted: {mutation}")
    return {"worker": "equity_disclosure", "synthetic": True, "integrated": False,
            "case_count": len(summaries), "check_count": sum(c["checks"] for c in summaries),
            "fixed_value_assertions": assertion_count, "invalid_input_controls": rejected,
            "existing_source_locations_verified": source_count, "result": "PASS", "cases": summaries}


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
