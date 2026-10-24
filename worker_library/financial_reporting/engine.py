"""Read-only verification of isolated synthetic FS/CF fixtures; Python stdlib only."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONTEXT = {
    "company_code": "SYNTH01", "start_date": "2026-01-01",
    "end_date": "2026-12-31", "currency": "KRW",
    "financial_statement_scope": "별도",
}
DOC_IDS = (
    "FS-EXTRACT", "FS-LEDGER", "FS-TB", "FS-BODY", "FS-NOTES",
    "FS-ACCOUNTMAP", "FS-CFMAP", "FS-CFSTATEMENT", "FS-EQUITY",
    "FS-NONCASH", "FS-DEBTBRIDGE", "FS-AJEAPPROVAL",
)
# Independently stated fixed expectations; these are not generated from the fixture.
ORACLE = {
    "FS_REQUIRED_EVIDENCE": 12, "FS_EXTRACTION_CONTROL": 0,
    "FS_GL_JOURNAL_BALANCE": 0, "FS_TB_BALANCE": 0, "FS_TB_GL": 0,
    "FS_BODY_TB_MAPPING": 0, "FS_BODY_SUM": 0, "FS_BS_EQUATION": 60000,
    "FS_PL_PROFIT": 12000, "FS_NOTE_CASH": 17000, "FS_NOTE_PPE": 33000,
    "FS_CF_MAPPING": 0, "FS_CF_OPERATING": 8000, "FS_CF_INVESTING": -5000,
    "FS_CF_FINANCING": 4000, "FS_CF_ROLL": 17000, "FS_CF_BS_CASH": 17000,
    "FS_EQUITY_ROLL": 29000, "FS_RETAINED_EARNINGS_ROLL": 14000,
    "FS_NONCASH_ASSET": 4000, "FS_NONCASH_DEPN": 6000,
    "FS_DEBT_ROLL": 31000, "FS_AJE_AMOUNT": 6000,
}


class InputError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InputError(message)


def money(value):
    require(type(value) is int, "금액은 정수 원이어야 함: null/bool/float/문자열 금지")
    require(abs(value) <= 10**13, "금액 범위 초과")
    return value


def unique(rows, key):
    ids = [row[key] for row in rows]
    require(len(ids) == len(set(ids)), f"중복 키: {key}")
    return {row[key]: row for row in rows}


def evaluate(case, case_index):
    require(case["case_id"].startswith("FS-"), "사례 ID 접두어")
    documents = case["documents"]
    require(type(documents) is list, "documents 배열 필요")
    docs = unique(documents, "document_id")
    for doc in documents:
        require(set(doc) == {"document_id", "document_type", "transaction_id", "fields"}, "문서 키 규격")
        require(doc["document_id"].startswith("FS-") and doc["transaction_id"].startswith("FS-"), "문서·거래 ID 접두어")
        for key, value in CONTEXT.items():
            require(doc["fields"][key] == value, f"문서 문맥 불일치: {doc['document_id']}/{key}")
        require(doc["fields"]["version"] == "FS-DRAFT-1", "문서 버전 불일치")
    require(set(docs) <= set(DOC_IDS), "이 초기 사례가 지원하지 않는 문서")
    missing = sorted(set(DOC_IDS) - set(docs))

    def location(doc_id, path=""):
        if doc_id not in docs:
            return f"fixtures.json#/cases/{case_index}/documents (missing {doc_id})"
        ix = next(i for i, d in enumerate(documents) if d["document_id"] == doc_id)
        return f"fixtures.json#/cases/{case_index}/documents/{ix}/fields{path}"

    def result(check_id, expected_value, actual_value, refs, follow_up=None):
        blocked = actual_value is None
        return {
            "check_id": check_id,
            "status": "INPUT_BLOCKED" if blocked else ("PASS" if expected_value == actual_value else "EXCEPTION"),
            "expected_value": expected_value, "actual_value": actual_value,
            "difference": None if blocked else actual_value - expected_value,
            "source_locations": refs,
            "follow_up": follow_up or "작성자가 원천 및 수정본을 확인하고 감사인이 예외와 판단을 검토",
        }

    if missing:
        return [result("FS_REQUIRED_EVIDENCE", 12, None, [location(i) for i in missing],
                       "필수 자료 요청: " + ", ".join(missing) + "; 조정 포함·승인 근거 확인 전 금액 비교 중단")]
    f = {k: d["fields"] for k, d in docs.items()}
    results = [result("FS_REQUIRED_EVIDENCE", 12, len(docs), [location("FS-AJEAPPROVAL")])]

    def add(check_id, expected_value, actual_value, doc_id, path=""):
        results.append(result(check_id, money(expected_value), money(actual_value), [location(doc_id, path)]))

    gl = f["FS-LEDGER"]["rows"]
    gl_ids = unique(gl, "line_id")
    tb = unique(f["FS-TB"]["rows"], "account_code")
    require(f["FS-TB"]["basis"] == "adjusted_unclosed", "이 합성 사례는 조정 후 미마감 TB만 지원")
    dr, cr, journal_net = defaultdict(int), defaultdict(int), defaultdict(int)
    for row in gl:
        require(row["account_code"] in tb, "원장 계정의 TB 누락")
        require(row["transaction_id"].startswith("FS-"), "원장 거래 ID 접두어")
        require(row["posting_date"] == "2026-12-31", "이 작은 사례는 2026-12-31 전표만 지원")
        d, c = money(row["debit"]), money(row["credit"])
        require(d >= 0 and c >= 0 and ((d == 0) != (c == 0)), "차대 금액·양변 동시기재 오류")
        dr[row["account_code"]] += d
        cr[row["account_code"]] += c
        journal_net[row["journal_id"]] += d - c
    ctrl = f["FS-EXTRACT"]
    control_actual = {"journal_count": len(journal_net), "line_count": len(gl),
                      "debit_total": sum(dr.values()), "credit_total": sum(cr.values())}
    add("FS_EXTRACTION_CONTROL", 0, sum(money(ctrl[k]) != v for k, v in control_actual.items()), "FS-EXTRACT")
    add("FS_GL_JOURNAL_BALANCE", 0, sum(v != 0 for v in journal_net.values()), "FS-LEDGER", "/rows")
    add("FS_TB_BALANCE", 0, sum(money(r["closing"]) for r in tb.values()), "FS-TB", "/rows")
    tb_gaps = 0
    for a, r in tb.items():
        opening, debit, credit, closing = (money(r[k]) for k in ("opening", "period_debit", "period_credit", "closing"))
        tb_gaps += (debit != dr[a] or credit != cr[a] or closing != opening + dr[a] - cr[a])
        if a.startswith(("4", "5")):
            require(opening == 0, "미마감 손익 계정 기초잔액은 0이어야 함")
    add("FS_TB_GL", 0, tb_gaps, "FS-TB", "/rows")

    body = {k: money(v) for k, v in f["FS-BODY"]["items"].items()}
    require(f["FS-BODY"]["unit"] == f["FS-NOTES"]["unit"] == "KRW", "단위 불일치")
    maps = unique(f["FS-ACCOUNTMAP"]["rows"], "account_code")
    require(set(maps) == set(tb), "TB 계정 매핑 누락·추가")
    require(len(set(r["body_item_id"] for r in maps.values())) == len(maps), "초기 사례는 계정당 고유 본문 명세행 필요")
    mismatches = 0
    for a, row in maps.items():
        require(type(row["coefficient"]) is int and row["coefficient"] in (-1, 1), "표시 부호는 ±1")
        require(row["body_item_id"] in body, "본문 매핑 대상 부재")
        mismatches += body[row["body_item_id"]] != tb[a]["closing"] * row["coefficient"]
    add("FS_BODY_TB_MAPPING", 0, mismatches, "FS-ACCOUNTMAP", "/rows")
    sum_relations = unique(f["FS-BODY"]["sum_relations"], "total_id")
    sum_gaps = 0
    for total_id, relation in sum_relations.items():
        require(total_id in body, "합계 행 부재")
        components = unique(relation["components"], "item_id")
        value = 0
        for child_id, child in components.items():
            require(child_id in body and child_id != total_id, "합계 구성 행 부재·직접 순환")
            require(type(child["coefficient"]) is int and child["coefficient"] in (-1, 1), "합계 부호 오류")
            value += body[child_id] * child["coefficient"]
        sum_gaps += value != body[total_id]
    add("FS_BODY_SUM", 0, sum_gaps, "FS-BODY", "/sum_relations")
    add("FS_BS_EQUATION", body["BS_ASSETS"], body["BS_DEBT"] + body["BS_EQUITY"], "FS-BODY", "/items")
    add("FS_PL_PROFIT", body["PL_REVENUE"] - body["PL_WAGES"] - body["PL_DEPN"] - body["PL_TAX"], body["PL_PROFIT"], "FS-BODY", "/items/PL_PROFIT")
    notes = f["FS-NOTES"]
    require(notes["required_note_ids"] == ["FS-NOTE-CASH", "FS-NOTE-PPE", "FS-NOTE-DEBT"], "지정 주석 연결 누락")
    unique(notes["cash_components"], "component_id")
    add("FS_NOTE_CASH", body["BS_CASH"], sum(money(r["amount"]) for r in notes["cash_components"]), "FS-NOTES", "/cash_components")
    require(money(notes["ppe_gross"]) + money(notes["ppe_accumulated_depreciation"]) == money(notes["ppe_net"]), "PPE 주석 내부 계산 오류")
    require(money(notes["debt"]) == body["BS_DEBT"], "차입 주석과 본문 불일치")
    add("FS_NOTE_PPE", body["BS_PPE_NET"], money(notes["ppe_net"]), "FS-NOTES", "/ppe_net")

    cfmap = unique(f["FS-CFMAP"]["rows"], "ledger_line_id")
    cash_rows = {k: r for k, r in gl_ids.items() if r["account_code"] == "1000"}
    require(set(cfmap) == set(cash_rows), "현금행 분류표 누락·중복·추가")
    flows = {k: 0 for k in ("operating", "investing", "financing")}
    cf_gaps = 0
    for line_id, mapping in cfmap.items():
        require(mapping["activity"] in flows, "알 수 없는 현금흐름 활동")
        require(mapping["transaction_id"] == cash_rows[line_id]["transaction_id"], "현금흐름 거래ID 불일치")
        cash_change = money(mapping["cash_change"])
        cf_gaps += cash_change != cash_rows[line_id]["debit"] - cash_rows[line_id]["credit"]
        flows[mapping["activity"]] += cash_change
    add("FS_CF_MAPPING", 0, cf_gaps, "FS-CFMAP", "/rows")
    cf = f["FS-CFSTATEMENT"]
    require(money(cf["opening_cash"]) == tb["1000"]["opening"], "현금흐름 기초와 TB 불일치")
    for activity in flows:
        add("FS_CF_" + activity.upper(), flows[activity], money(cf[activity]), "FS-CFSTATEMENT", "/" + activity)
    calculated_close = money(cf["opening_cash"]) + sum(money(cf[k]) for k in flows) + money(cf["fx_effect"])
    add("FS_CF_ROLL", calculated_close, money(cf["closing_cash"]), "FS-CFSTATEMENT", "/closing_cash")
    add("FS_CF_BS_CASH", body["BS_CASH"], money(cf["closing_cash"]), "FS-CFSTATEMENT", "/closing_cash")

    eq = f["FS-EQUITY"]
    eq = {k: money(v) for k, v in eq.items() if k not in (*CONTEXT, "version", "synthetic_label")}
    require(eq["profit"] == body["PL_PROFIT"], "자본변동 당기손익과 본문 불일치")
    require(eq["closing_equity"] == body["BS_EQUITY"], "자본변동 기말자본과 본문 불일치")
    add("FS_EQUITY_ROLL", eq["opening_capital"] + eq["opening_retained_earnings"] + eq["profit"] - eq["dividends"] + eq["other_changes"], eq["closing_equity"], "FS-EQUITY")
    add("FS_RETAINED_EARNINGS_ROLL", eq["opening_retained_earnings"] + eq["profit"] - eq["dividends"] + eq["other_changes"], eq["closing_retained_earnings"], "FS-EQUITY", "/closing_retained_earnings")
    noncash = unique(f["FS-NONCASH"]["rows"], "movement_type")
    require(set(noncash) == {"depreciation", "asset_acquired_with_financing"}, "지정 비현금 변동 누락·추가")
    for row in noncash.values():
        require(money(row["cash_flow_amount"]) == 0, "비현금 거래의 현금흐름 포함")
        referenced = [gl_ids[k] for k in row["ledger_line_ids"]]
        require(len(referenced) == len({r["line_id"] for r in referenced}), "비현금 원장행 중복")
        require(all(r["transaction_id"] == row["transaction_id"] for r in referenced), "비현금 거래ID 불일치")
        require(not any(r["account_code"] == "1000" for r in referenced), "현금 거래를 비현금으로 입력")
        require(sum(r["debit"] for r in referenced) == sum(r["credit"] for r in referenced) == money(row["amount"]), "비현금 거래와 원장 불일치")
    add("FS_NONCASH_ASSET", 4000, money(noncash["asset_acquired_with_financing"]["amount"]), "FS-NONCASH", "/rows/1")
    add("FS_NONCASH_DEPN", body["PL_DEPN"], money(noncash["depreciation"]["amount"]), "FS-NONCASH", "/rows/0")
    debt = f["FS-DEBTBRIDGE"]
    require(money(debt["opening_debt"]) == -tb["2100"]["opening"], "차입 기초 불일치")
    require(money(debt["non_cash_additions"]) == noncash["asset_acquired_with_financing"]["amount"], "비현금 차입 증가 불일치")
    require(money(debt["closing_debt"]) == body["BS_DEBT"], "차입 기말 본문 불일치")
    add("FS_DEBT_ROLL", money(debt["opening_debt"]) + money(debt["cash_borrowings"]) - money(debt["cash_repayments"]) + money(debt["non_cash_additions"]) + money(debt["other_changes"]), money(debt["closing_debt"]), "FS-DEBTBRIDGE")
    aje = f["FS-AJEAPPROVAL"]
    require(aje["authorization_state"] == "SYNTHETIC_ASSUMED_APPROVED", "조정 승인 가정 근거 부재")
    require(aje["ledger_inclusion"] == "already_included_once", "조정 중복 포함 방지 표기 필요")
    aje_rows = [r for r in gl if r["adjustment_id"] == aje["adjustment_id"]]
    require(aje_rows and all(r["journal_id"] == aje["journal_id"] for r in aje_rows), "조정과 원장 연결 부재")
    add("FS_AJE_AMOUNT", sum(r["debit"] for r in aje_rows), money(aje["amount"]), "FS-AJEAPPROVAL", "/amount")
    return results


def verify_sources(manifest):
    catalog = json.loads((ROOT / manifest["catalog_file"]).read_text(encoding="utf-8-sig"))
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    count = 0
    for source in manifest["existing_sources"]:
        path = ROOT / source["file"]
        require(path.is_file(), "기존 원천 파일 없음: " + str(path))
        book = catalog["books"][int(source["catalog_json_pointer"].split("/")[-1])]
        require(path.stem == book["name"], "카탈로그·실파일 연결 불일치")
        with zipfile.ZipFile(path) as z:
            workbook = ET.fromstring(z.read("xl/workbook.xml"))
            sheets = {s.attrib["name"] for s in workbook.findall("m:sheets/m:sheet", ns)}
            for sheet in source["sheets"]:
                require(sheet in sheets and sheet in book["headers"], "기존 원천 시트 없음: " + sheet)
                count += 1
    portfolio = ROOT / manifest["portfolio_reference"]["file"]
    original = json.loads(portfolio.read_text(encoding="utf-8"))
    for pointer in manifest["portfolio_reference"]["json_pointers"]:
        require(pointer[1:] in original, "기존 v1.1 참조 위치 없음")
    return {"xlsx_files": len(manifest["existing_sources"]), "xlsx_sheets": count,
            "portfolio_json_locations": len(manifest["portfolio_reference"]["json_pointers"])}


def guards(normal):
    tests = []
    def test(name, mutation):
        data = copy.deepcopy(normal)
        mutation(data)
        try:
            evaluate(data, 0)
        except (InputError, KeyError):
            tests.append(name)
        else:
            raise AssertionError("입력 통제 실패: " + name)
    test("회사 불일치", lambda x: x["documents"][1]["fields"].update(company_code="OTHER"))
    test("bool 금액 거부", lambda x: x["documents"][1]["fields"]["rows"][0].update(debit=True))
    test("null 금액 거부", lambda x: x["documents"][4]["fields"]["cash_components"][0].update(amount=None))
    test("중복 문서 거부", lambda x: x["documents"].append(copy.deepcopy(x["documents"][0])))
    test("TB 계정 매핑 누락 거부", lambda x: x["documents"][5]["fields"]["rows"].pop())
    test("현금행 분류 누락 거부", lambda x: x["documents"][6]["fields"]["rows"].pop())
    test("알 수 없는 활동 거부", lambda x: x["documents"][6]["fields"]["rows"][0].update(activity="UNKNOWN"))
    return tests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", nargs="?", type=Path, default=ROOT / "fixtures.json")
    args = parser.parse_args()
    data = json.loads(args.fixture.read_text(encoding="utf-8"))
    contract = json.loads((ROOT.parent.parent / "DATA_CONTRACT.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    require(data["schema_version"] == "pm-raw-1" and data["synthetic"] is True and data["integrated"] is False, "합성·비통합 규격")
    require(data["context"] == CONTEXT == contract["context"] == manifest["context"], "공통 문맥 불일치")
    require([c["case_id"] for c in data["cases"]] == ["FS-01", "FS-02", "FS-03"], "고정 3개 사례 필요")
    summaries, exceptions, total = [], [], 0
    for i, case in enumerate(data["cases"]):
        actual = evaluate(case, i)
        expected = unique(case["expected"], "check_id")
        require({r["check_id"] for r in actual} == set(expected), "검사 누락·추가")
        if case["case_id"] != "FS-03":
            require(set(expected) == set(ORACLE), "완전 사례의 고정 검사 누락")
        for row in actual:
            exp = expected[row["check_id"]]
            require(exp["expected_value"] == ORACLE[row["check_id"]], "고정 수기 기대값 변경")
            for key in ("status", "expected_value", "actual_value", "difference"):
                require(row[key] == exp[key], f"{case['case_id']}/{row['check_id']}/{key}: {row[key]} != {exp[key]}")
            if row["status"] != "PASS":
                exceptions.append({"case_id": case["case_id"], **row})
        counts = Counter(r["status"] for r in actual)
        summaries.append({"case_id": case["case_id"], "checks": len(actual), "statuses": dict(counts),
                          "calculation_skipped": "INPUT_BLOCKED" in counts})
        total += len(actual)
    guard_names = guards(data["cases"][0])
    source_result = verify_sources(manifest)
    print(json.dumps({"worker": "financial_reporting", "result": "PASS", "schema_version": "pm-raw-1",
                      "synthetic": True, "integrated": False, "case_count": 3,
                      "fixed_expectation_checks": total, "guard_checks": len(guard_names),
                      "guards": guard_names, "cases": summaries, "exceptions": exceptions,
                      "source_references": source_result,
                      "fixture_sha256": hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
                      "workpaper_state": {"status": "미검토 초안", "preparer": None, "reviewer": None,
                                          "conclusion": None, "adjustment_approval": None},
                      "limits": ["EXE 입력·계정 간 통합 미구현", "분류 판단·전체 공시 완전성·연결재무제표 미구현", "합성 근거 존재 확인은 실제 증거 적합성 검토 아님"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (InputError, KeyError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"worker": "financial_reporting", "result": "FAIL", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
