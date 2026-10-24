"""합성 현금·금융 원천자료의 고정 기대값 검증. 기존 앱을 호출하지 않는다."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTEXT = {"company_code": "SYNTH01", "start_date": "2026-01-01", "end_date": "2026-12-31", "currency": "KRW", "financial_statement_scope": "별도"}
CHECKS = ("CASH_BANK_ROLLFORWARD", "CASH_BOOK_ROLLFORWARD", "CASH_RECONCILIATION", "CASH_CONFIRMATION_BALANCE", "CASH_CONFIRMATION_CONTROL", "CASH_INTEREST")


class InputError(ValueError):
    pass


def integer(value):
    if type(value) is not int:
        raise InputError("필수 정수 원 금액이 누락되었거나 형식이 잘못됨")
    return value


def iso(value):
    if not isinstance(value, str) or len(value) != 10:
        raise InputError("ISO 날짜 누락/형식 오류")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise InputError("유효하지 않은 날짜") from exc
    if result.isoformat() != value:
        raise InputError("날짜가 ISO YYYY-MM-DD가 아님")
    return result


def index_documents(case):
    docs = {}
    identifiers = set()
    for document in case["documents"]:
        identifier = document["document_id"]
        if identifier in identifiers or not identifier.startswith("CASH-"):
            raise InputError("증빙 ID 중복/접두어 오류")
        identifiers.add(identifier)
        kind = document["document_type"]
        if kind in docs:
            raise InputError("이 소규모 규격은 문서 종류당 1건만 지원")
        if document["transaction_id"] != "CASH-CYCLE01":
            raise InputError("공통 거래 연결키 불일치")
        fields = document["fields"]
        if fields.get("company_code") != CONTEXT["company_code"] or fields.get("currency") != "KRW":
            raise InputError("회사/통화 불일치")
        if fields.get("as_of_date") != CONTEXT["end_date"]:
            raise InputError("기준일 불일치")
        docs[kind] = document
    return docs


def result(check_id, expected, actual, reason, source_paths, blocked=False):
    difference = None if expected is None or actual is None else actual - expected
    status = "INPUT_BLOCKED" if blocked else ("PASS" if difference == 0 else "EXCEPTION")
    return {"check_id": check_id, "status": status, "expected_value": expected,
            "actual_value": actual, "difference": difference, "reason": reason,
            "source_paths": source_paths}


def calculate(case):
    docs = index_documents(case)

    def fields(kind):
        if kind not in docs:
            raise InputError("필수 문서 누락: " + kind)
        return docs[kind]["fields"]

    def sources(*kinds):
        return ["document:" + docs[k]["document_id"] + "/fields" for k in kinds if k in docs]

    output = []
    for kind, check_id in (("bank_statement", CHECKS[0]), ("cash_ledger", CHECKS[1])):
        try:
            f = fields(kind)
            start = integer(f["opening_balance"])
            entries = f["entries"]
            if not isinstance(entries, list) or not entries:
                raise InputError("거래 내역 누락")
            ids = set()
            for entry in entries:
                if entry["entry_id"] in ids:
                    raise InputError("거래 ID 중복")
                ids.add(entry["entry_id"])
                d = iso(entry["date"])
                if not iso(CONTEXT["start_date"]) <= d <= iso(CONTEXT["end_date"]):
                    raise InputError("거래일이 검사 기간 밖임")
            expected = start + sum(integer(e["amount"]) for e in entries)
            output.append(result(check_id, expected, integer(f["closing_balance"]), "기초+부호 보존 거래합계=기말", sources(kind)))
        except (InputError, KeyError, TypeError) as exc:
            output.append(result(check_id, None, None, str(exc), sources(kind), True))

    try:
        bank, book, recon = fields("bank_statement"), fields("cash_ledger"), fields("bank_reconciliation")
        account_ids = {f["account_id"] for f in (bank, book, recon)}
        if len(account_ids) != 1:
            raise InputError("은행 조정 계좌 연결키 불일치")
        adjustments = recon["bank_adjustments"]
        if not adjustments or len({a["adjustment_id"] for a in adjustments}) != len(adjustments):
            raise InputError("은행 조정항목 누락/중복")
        subsequent = fields("subsequent_bank_statement")
        if subsequent["account_id"] != bank["account_id"] or subsequent["subsequent_period"] is not True:
            raise InputError("후속 은행거래의 계좌/기간 표시 불일치")
        coverage_start, coverage_end = iso(subsequent["coverage_start"]), iso(subsequent["coverage_end"])
        if not iso(CONTEXT["end_date"]) < coverage_start <= coverage_end:
            raise InputError("후속 은행거래 수록 기간 오류")
        book_references = set()
        for a in adjustments:
            if a["kind"] not in ("deposit_in_transit", "outstanding_payment"):
                raise InputError("미지원 조정항목")
            amount = integer(a["amount"])
            if (a["kind"] == "deposit_in_transit" and amount <= 0) or (a["kind"] == "outstanding_payment" and amount >= 0):
                raise InputError("조정항목 부호 오류")
            if not CONTEXT["end_date"] < a["cleared_date"] <= "2027-01-31":
                raise InputError("후속 결제일 범위 오류")
            iso(a["cleared_date"])
            if a["book_entry_id"] in book_references:
                raise InputError("같은 장부거래를 조정항목에 중복 사용")
            book_references.add(a["book_entry_id"])
            book_matching = [e for e in book["entries"] if e["entry_id"] == a["book_entry_id"]]
            if len(book_matching) != 1 or integer(book_matching[0]["amount"]) != amount:
                raise InputError("장부와 조정항목 연결 불일치")
            if a["evidence_id"] != docs["subsequent_bank_statement"]["document_id"]:
                raise InputError("후속 결제 증빙ID 불일치")
            proof = subsequent["entries"]
            matching = [e for e in proof if e["entry_id"] == a["clearing_entry_id"]]
            if len(matching) != 1 or matching[0]["date"] != a["cleared_date"] or integer(matching[0]["amount"]) != amount:
                raise InputError("후속 은행거래와 조정항목 연결 불일치")
            if not coverage_start <= iso(matching[0]["date"]) <= coverage_end:
                raise InputError("후속 결제가 은행 명세 수록 기간 밖임")
        expected = integer(bank["closing_balance"]) + sum(integer(a["amount"]) for a in adjustments)
        output.append(result(CHECKS[2], expected, integer(book["closing_balance"]), "은행 기말+미결제 항목=장부 기말; 후속결제는 합성 연결 확인", sources("bank_statement", "cash_ledger", "bank_reconciliation", "subsequent_bank_statement")))
    except (InputError, KeyError, TypeError) as exc:
        output.append(result(CHECKS[2], None, None, str(exc), sources("bank_statement", "cash_ledger", "bank_reconciliation", "subsequent_bank_statement"), True))

    try:
        bank, confirmation = fields("bank_statement"), fields("bank_confirmation")
        if bank["account_id"] != confirmation["account_id"]:
            raise InputError("조회 회신 계좌 불일치")
        output.append(result(CHECKS[3], integer(bank["closing_balance"]), integer(confirmation["confirmed_balance"]), "합성 은행잔액과 합성 회신금액 대사", sources("bank_statement", "bank_confirmation")))
    except (InputError, KeyError, TypeError) as exc:
        known = docs.get("bank_statement", {}).get("fields", {}).get("closing_balance")
        output.append(result(CHECKS[3], known, None, str(exc), sources("bank_statement", "bank_confirmation"), True))

    try:
        control = fields("confirmation_control")
        confirmed = fields("bank_confirmation")
        if not (control["sent_by_auditor"] is True and control["received_directly_by_auditor"] is True and control["response_identity_reviewed"] is True):
            raise InputError("합성 조회 통제 조건 미충족: 추가 증거/대체절차 판단 필요")
        if control["response_document_id"] != docs["bank_confirmation"]["document_id"]:
            raise InputError("조회통제대장의 회신 증빙 연결 불일치")
        if control["account_id"] != confirmed["account_id"] or iso(control["sent_date"]) > iso(control["received_date"]):
            raise InputError("조회 대상/일자 불일치")
        output.append(result(CHECKS[4], 1, 1, "합성 통제 플래그와 문서 연결 일치; 실제 감사인 통제 입증 아님", sources("confirmation_control", "bank_confirmation")))
    except (InputError, KeyError, TypeError) as exc:
        output.append(result(CHECKS[4], 1, None, str(exc), sources("confirmation_control", "bank_confirmation"), True))

    try:
        contract, ledger = fields("deposit_contract"), fields("interest_ledger")
        if contract["contract_id"] != ledger["contract_id"]:
            raise InputError("예금 계약과 이자 원장 연결 불일치")
        start, end = iso(contract["interest_start"]), iso(contract["interest_end"])
        if not iso(contract["contract_start"]) <= start <= end <= iso(contract["maturity_date"]) or end > iso(CONTEXT["end_date"]):
            raise InputError("이자 기간이 계약/보고 기간 밖임")
        if contract["day_count"] != "ACT/365F" or contract["start_included"] is not False or contract["end_included"] is not True:
            raise InputError("이 작은 검증기는 ACT/365F 초일불산입/말일산입만 지원")
        if any(contract[f] is not False for f in ("principal_changes", "compound_interest", "floating_rate", "fees_or_discount")):
            raise InputError("단리 고정원금·고정금리 외 계약은 별도 모형 필요")
        principal, rate = integer(contract["principal"]), integer(contract["annual_rate_ppm"])
        tolerance = integer(ledger["tolerance_won"])
        if principal <= 0 or not 0 <= rate <= 1000000 or not 0 <= tolerance <= 1000:
            raise InputError("원금/금리/허용오차 범위 오류")
        days = (end - start).days
        expected = int((Decimal(principal) * Decimal(rate) / 1000000 * Decimal(days) / 365).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        actual = integer(ledger["accrued_interest"])
        diff = actual - expected
        reason = f"계약 기간 {days}일, ACT/365F 단리, 원 단위 사사오입; "
        reason += "일치" if diff == 0 else ("허용오차 내 차이도 검토대상으로 유지" if abs(diff) <= tolerance else "허용오차 초과 차이")
        output.append(result(CHECKS[5], expected, actual, reason, sources("deposit_contract", "interest_ledger")))
    except (InputError, KeyError, TypeError) as exc:
        output.append(result(CHECKS[5], None, None, str(exc), sources("deposit_contract", "interest_ledger"), True))
    return output


def verify_sources(manifest):
    original = HERE.parents[2] / "2026-10-23"
    spec = json.loads((original / "spec.json").read_text("utf-8"))
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    count = 0
    for entry in manifest["existing_sources"]:
        path = original / entry["relative_path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise AssertionError("기존 원천 파일 해시 변경: " + str(path))
        book = spec["books"][entry["spec_book_index"]]
        assert book["name"] + ".xlsx" == path.name
        with zipfile.ZipFile(path) as z:
            relationships = {r.attrib["Id"]: r.attrib["Target"] for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
            sheets = {r.attrib["name"]: r.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"] for r in ET.fromstring(z.read("xl/workbook.xml")).findall("m:sheets/m:sheet", ns)}
            for loc in entry["locations"]:
                target = relationships[sheets[loc["sheet"]]]
                target = target.lstrip("/") if target.startswith("/") else "xl/" + target
                root = ET.fromstring(z.read(target))
                rows = root.findall("m:sheetData/m:row", ns)
                cells = root.findall("m:sheetData/m:row/m:c", ns)
                assert cells[0].attrib["r"] + ":" + cells[-1].attrib["r"] == loc["range"]
                assert len(rows) - 1 == loc["data_rows"]
                assert ["".join(c.itertext()) for c in rows[0].findall("m:c", ns)] == book["headers"][loc["sheet"]]
                assert len(book["tables"][loc["sheet"]]) == loc["data_rows"]
                count += 1
    return count


def verify():
    fixture = json.loads((HERE / "fixtures.json").read_text("utf-8"))
    manifest = json.loads((HERE / "manifest.json").read_text("utf-8"))
    assert fixture["schema_version"] == "pm-raw-1" and fixture["synthetic"] is True and fixture["integrated"] is False
    assert fixture["context"] == CONTEXT
    assert len(fixture["cases"]) == 5
    ids = set()
    comparisons = 0
    for case in fixture["cases"]:
        assert case["case_id"] not in ids
        ids.add(case["case_id"])
        observed = calculate(case)
        assert [r["check_id"] for r in observed] == list(CHECKS)
        assert len(case["expected"]) == len(observed)
        for actual, expected in zip(observed, case["expected"], strict=True):
            for key in ("check_id", "status", "expected_value", "actual_value", "difference"):
                assert actual[key] == expected[key], (case["case_id"], key, actual, expected)
            assert expected["reason"] and actual["reason"] and actual["source_paths"]
            comparisons += 1
    # 고정 기대값과 경계 검사. 기대값을 입력에서 다시 생성하지 않는다.
    normal = fixture["cases"][0]
    assert (date(2026, 12, 31) - date(2026, 10, 1)).days == 91
    assert calculate(normal)[5]["expected_value"] == 9100
    assert calculate(normal)[2]["expected_value"] == 1000000
    assert all(r["status"] == "PASS" for r in calculate(normal))
    missing_amount = copy.deepcopy(normal)
    next(d for d in missing_amount["documents"] if d["document_type"] == "interest_ledger")["fields"]["accrued_interest"] = None
    null_result = calculate(missing_amount)[5]
    assert null_result["status"] == "INPUT_BLOCKED" and null_result["actual_value"] is None and null_result["difference"] is None
    missing_bank = copy.deepcopy(normal)
    missing_bank["documents"] = [d for d in missing_bank["documents"] if d["document_type"] != "bank_statement"]
    assert calculate(missing_bank)[0]["status"] == "INPUT_BLOCKED"
    assert calculate(missing_bank)[2]["status"] == "INPUT_BLOCKED"
    duplicate = copy.deepcopy(normal)
    duplicate["documents"].append(copy.deepcopy(duplicate["documents"][0]))
    bad_currency = copy.deepcopy(normal)
    bad_currency["documents"][0]["fields"]["currency"] = "USD"
    for bad in (duplicate, bad_currency):
        try:
            calculate(bad)
        except InputError:
            pass
        else:
            raise AssertionError("잘못된 문서 연결/통화가 통과함")
    sources = verify_sources(manifest)
    return {"cases": len(ids), "fixed_check_comparisons": comparisons,
            "source_workbooks": len(manifest["existing_sources"]), "verified_source_locations": sources,
            "boundary_groups": 5, "synthetic": True, "integrated": False, "result": "PASS"}


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), ensure_ascii=False, indent=2))
    except (AssertionError, ValueError, KeyError, OSError) as exc:
        print("검증 실패: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
