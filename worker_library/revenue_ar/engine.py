"""Standalone synthetic revenue/AR diagnostics. No posting, network, or app edits."""
from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
RAW_ROOT = HERE.parents[2]
CHECKS = (
    "DOC_LINKS", "INVOICE_CALC", "CUTOFF_REVENUE", "RETURN_POSTING",
    "AR_TIE", "RECEIPT_ALLOCATION", "CONFIRMATION_PROTOCOL", "AGING",
    "ECL", "ECL_ROLLFORWARD",
)
TYPES = {
    "order", "contract", "delivery", "invoice", "sales_ledger", "return_search",
    "receivable", "bank_receipt", "confirmation_control", "ecl_model",
    "allowance_ledger", "credit_note",
}


class Blocked(ValueError):
    pass


def ensure(condition, message):
    if not condition:
        raise AssertionError(message)


def integer(value, name, lower=None, upper=None):
    if type(value) is not int:
        raise Blocked(f"{name}: 정수 필요; null/문자/불리언을 0으로 대체하지 않음")
    if (lower is not None and value < lower) or (upper is not None and value > upper):
        raise Blocked(f"{name}: 허용 범위 외")
    return value


def iso(value, name):
    if type(value) is not str:
        raise Blocked(f"{name}: 날짜 누락")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise Blocked(f"{name}: ISO 날짜 필요") from exc
    if value != parsed.isoformat():
        raise Blocked(f"{name}: YYYY-MM-DD 필요")
    return parsed


def text_value(value, name):
    if type(value) is not str or not value.strip():
        raise Blocked(f"{name}: 근거/식별자 누락")
    return value


def one(case, kind):
    matched = [d for d in case["documents"] if d["document_type"] == kind]
    if len(matched) != 1:
        raise Blocked(f"{kind}: 필수 문서 누락 또는 중복 ({len(matched)}건)")
    return matched[0]["fields"]


def linked(case, kind):
    fields = one(case, kind)
    inv = one(case, "invoice")
    if fields.get("invoice_id") != inv.get("invoice_id"):
        raise Blocked(f"{kind}: 송장 연결 불일치")
    return fields


def validate_case(case, context):
    docs = case.get("documents")
    if type(docs) is not list or not docs:
        raise Blocked("증빙 배열 누락")
    identifiers = [d.get("document_id") for d in docs]
    if len(set(identifiers)) != len(identifiers):
        raise Blocked("증빙ID 중복")
    tx = docs[0].get("transaction_id")
    customer = docs[0].get("fields", {}).get("customer_id")
    text_value(tx, "거래ID")
    text_value(customer, "고객ID")
    for doc in docs:
        if doc.get("document_type") not in TYPES:
            raise Blocked("알 수 없는 문서 유형")
        if not str(doc.get("document_id", "")).startswith("REV-"):
            raise Blocked("워커 증빙ID 접두어 오류")
        fields = doc.get("fields", {})
        if (doc.get("transaction_id") != tx or
                fields.get("company_id") != context["company_id"] or
                fields.get("customer_id") != customer or
                fields.get("currency") != context["currency"]):
            raise Blocked("회사·거래·고객·통화 연결 불일치")


def compute(case, context, check_id):
    asof = iso(context["period_end"], "기준일")
    start = iso(context["period_start"], "시작일")
    if check_id == "DOC_LINKS":
        invoice = one(case, "invoice")
        text_value(invoice.get("invoice_id"), "송장ID")
        for doc in case["documents"]:
            if "invoice_id" in doc["fields"]:
                linked(case, doc["document_type"])
        return True, True, "식별자 연결 일치; 원본 진위 또는 모집단 완전성 인증 아님"
    if check_id == "INVOICE_CALC":
        order = one(case, "order")
        inv = one(case, "invoice")
        qty = integer(order.get("quantity"), "주문수량", 1)
        price = integer(order.get("unit_price"), "주문단가", 0)
        if inv.get("quantity") != qty or inv.get("unit_price") != price:
            raise Blocked("주문·송장 수량 또는 단가 불일치")
        net = qty * price
        bps = integer(inv.get("tax_rate_bps"), "세율bp", 0, 10000)
        tax = int((Decimal(net) * bps / 10000).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if inv.get("supply_amount") != net or inv.get("tax_amount") != tax:
            raise Blocked("송장 공급가 또는 세액 내역 불일치")
        return net + tax, integer(inv.get("total_amount"), "송장총액", 0), "주문 및 세율로 재계산"
    if check_id == "CUTOFF_REVENUE":
        contract = one(case, "contract")
        delivery = linked(case, "delivery")
        inv = one(case, "invoice")
        ledger = linked(case, "sales_ledger")
        if contract.get("policy_assessed") is not True or contract.get("revenue_policy") != "customer_acceptance":
            raise Blocked("계약상 고객 검수 기준이라는 사전 판단 누락")
        acceptance = iso(delivery.get("acceptance_date"), "고객검수일")
        shipment = iso(delivery.get("delivery_date"), "출고일")
        if acceptance < shipment:
            raise Blocked("고객 검수일이 출고일보다 빠름")
        if delivery.get("quantity") != inv.get("quantity") or delivery.get("accepted_quantity") != inv.get("quantity"):
            raise Blocked("일부 검수·수량차이 별도 배부 필요")
        expected = integer(inv.get("supply_amount"), "공급가액", 0) if start <= acceptance <= asof else 0
        posted = iso(ledger.get("posting_date"), "매출기장일")
        actual = integer(ledger.get("revenue_credit"), "매출대변", 0) if start <= posted <= asof else 0
        return expected, actual, "해당 합성 계약의 검수 조건만 적용; 일반 수익인식 판단을 대체하지 않음"
    if check_id == "RETURN_POSTING":
        search = linked(case, "return_search")
        ledger = linked(case, "sales_ledger")
        if search.get("complete_scope_declared") is not True:
            raise Blocked("반품 검색 모집단 범위 선언 누락")
        if iso(search.get("search_end"), "반품검색종료") < asof:
            raise Blocked("기말까지의 반품 검색 누락")
        notes = [d["fields"] for d in case["documents"] if d["document_type"] == "credit_note"]
        if integer(search.get("event_count"), "반품검색건수", 0) != len(notes):
            raise Blocked("검색 건수 대비 대변메모 원본 누락; 0으로 대체하지 않음")
        expected = 0
        net = 0
        for note in notes:
            if note.get("invoice_id") != one(case, "invoice").get("invoice_id"):
                raise Blocked("대변메모 원송장 연결 불일치")
            note_date = iso(note.get("credit_note_date"), "대변메모일")
            iso(note.get("return_receipt_date"), "반품입고일")
            supply = integer(note.get("supply_amount"), "반품공급가", 0)
            tax = integer(note.get("tax_amount"), "반품세액", 0)
            total = integer(note.get("total_amount"), "반품총액", 0)
            if total != supply + tax:
                raise Blocked("반품 대변메모 공급가·VAT 합계 오류")
            if start <= note_date <= asof:
                expected += total
                net += supply
        actual = integer(ledger.get("return_ar_credit"), "기장채권감소", 0)
        actual_net = integer(ledger.get("return_revenue_debit"), "매출반품차변", 0)
        if actual == expected and actual_net != net:
            raise Blocked("채권총액은 같으나 반품 공급가·VAT 분리 불일치")
        return expected, actual, "기장된 대변메모 총액 대사; 후속 반품의 기말 귀속은 추가 판단"
    if check_id == "AR_TIE":
        ledger = linked(case, "sales_ledger")
        ar = linked(case, "receivable")
        expected = integer(ledger.get("ar_debit"), "채권차변", 0) - integer(ledger.get("return_ar_credit"), "채권반품대변", 0)
        return expected, integer(ar.get("closing_balance"), "기말채권"), "동일 기장값끼리의 수치 대사; 누락된 반품·기간귀속 수정은 미반영"
    if check_id == "RECEIPT_ALLOCATION":
        receipt = linked(case, "bank_receipt")
        ar = linked(case, "receivable")
        if receipt.get("receivable_id") != ar.get("receivable_id"):
            raise Blocked("후속입금 채권 배부ID 불일치")
        receipt_date = iso(receipt.get("receipt_date"), "후속입금일")
        if not asof < receipt_date <= iso(context["subsequent_search_end"], "후속검색종료"):
            raise Blocked("후속입금 검색기간 외")
        allocated = integer(receipt.get("allocated_amount"), "배부금액", 0)
        if allocated > integer(ar.get("closing_balance"), "기말채권", 0):
            raise Blocked("기말채권보다 후속 배부액이 큼")
        return allocated, integer(receipt.get("bank_credit"), "은행입금", 0), "단일 송장·단일 입금 배부 예시; 다대다·중복·수수료·환율은 PM 연결 과제"
    if check_id == "CONFIRMATION_PROTOCOL":
        control = linked(case, "confirmation_control")
        if control.get("status") == "NON_RESPONSE" or control.get("reply_amount") is None:
            raise Blocked("직접 회신 미수령; 후속입금은 별도 절차이며 회신 null을 0으로 대체하지 않음")
        if control.get("balance_date") != context["period_end"]:
            raise Blocked("조회잔액 기준일 불일치")
        flags = ["request_controlled_by_auditor", "recipient_verified", "response_direct_to_auditor", "responder_authority_checked"]
        if any(control.get(flag) is not True for flag in flags):
            raise Blocked("감사인 발송·회신 통제 필드 미충족; 회사 전달 회신을 직접 회신으로 처리하지 않음")
        request = iso(control.get("request_date"), "조회발송일")
        response = iso(control.get("response_date"), "조회회신일")
        if request > response or control.get("status") != "SIMULATED_DIRECT_RESPONSE":
            raise Blocked("조회회신 상태·날짜 오류")
        if control.get("reply_amount") != linked(case, "receivable").get("closing_balance"):
            return True, False, "회신 잔액 차이 조사 필요"
        return True, True, "합성 통제 필드만 일치. authenticity_verified=false이며 실제 외부 회신 인증 아님"
    if check_id == "AGING":
        ar = linked(case, "receivable")
        due = iso(ar.get("due_date"), "약정만기일")
        issued = iso(ar.get("issue_date"), "채권발생일")
        if due < issued or issued > asof:
            raise Blocked("발생·만기·기준일 관계 오류")
        return max(0, (asof - due).days), integer(ar.get("reported_days_past_due"), "장부연체일수", 0), "약정만기 기준; 미도래는 실제 0일, 만기 누락은 차단"
    if check_id == "ECL":
        ar = linked(case, "receivable")
        model = one(case, "ecl_model")
        allowance = one(case, "allowance_ledger")
        contract = one(case, "contract")
        if contract.get("significant_financing_component") is not False or model.get("measurement") != "lifetime_simplified_trade_no_sfc":
            raise Blocked("유의적 금융요소 없는 매출채권 간편법 범위 확인 필요")
        if ar.get("group_id") != model.get("group_id") or model.get("group_id") != allowance.get("group_id"):
            raise Blocked("동질군 연결 불일치")
        for key in ("historical_basis_reference", "forward_basis_reference", "time_value_reference"):
            text_value(model.get(key), key)
        days, _, _ = compute(case, context, "AGING")
        scenarios = model.get("scenarios")
        if type(scenarios) is not list or not scenarios:
            raise Blocked("ECL 시나리오 누락")
        seen = set()
        probability = 0
        weighted = Decimal(0)
        for scenario in scenarios:
            ident = text_value(scenario.get("scenario_id"), "시나리오ID")
            if ident in seen:
                raise Blocked("시나리오ID 중복·구간 중복")
            seen.add(ident)
            low = integer(scenario.get("lower_days"), "구간하한", 0)
            high = integer(scenario.get("upper_days"), "구간상한", low)
            if not low <= days <= high:
                raise Blocked("연령 충당률 구간 미포함; 기본률 0 적용 금지")
            weight = integer(scenario.get("probability_bps"), "확률bp", 0, 10000)
            rate = integer(scenario.get("loss_rate_bps"), "손실률bp", 0, 10000)
            probability += weight
            weighted += Decimal(weight) * rate
        if probability != 10000:
            raise Blocked("확률 합계가 100% 아님")
        exposure = integer(ar.get("closing_balance"), "ECL 채권잔액", 0)
        required = int((Decimal(exposure) * weighted / Decimal(100000000)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        return required, integer(allowance.get("closing_allowance"), "장부기말충당금", 0), "입력 가정의 재계산이며 역사적 손실·전망·할인 가정의 적정성은 별도 검토"
    if check_id == "ECL_ROLLFORWARD":
        ledger = one(case, "allowance_ledger")
        expected = integer(ledger.get("opening_allowance"), "기초충당금", 0) + integer(ledger.get("expense"), "충당금비용") + integer(ledger.get("other_movement"), "비용외증감")
        return expected, integer(ledger.get("closing_allowance"), "기말충당금", 0), "내부 변동 대사; 필요한 ECL과의 차이는 별도 검사"
    raise Blocked("알 수 없는 검사ID")


def evaluate(case, context):
    results = []
    for check_id in CHECKS:
        try:
            validate_case(case, context)
            expected, actual, reason = compute(case, context, check_id)
            difference = (int(actual) - int(expected)) if type(actual) in (int, bool) and type(expected) in (int, bool) else None
            status = "PASS" if expected == actual else "EXCEPTION"
        except (Blocked, KeyError, TypeError) as exc:
            expected = True if check_id in ("DOC_LINKS", "CONFIRMATION_PROTOCOL") else None
            actual = difference = None
            status, reason = "INPUT_BLOCKED", str(exc)
        results.append({
            "check_id": check_id, "status": status, "expected_value": expected,
            "actual_value": actual, "difference": difference, "reason": reason,
            "source_references": [{"document_id": d.get("document_id"), "json_pointer": f"/cases/{case['_index']}/documents/{i}/fields", "original_values": d.get("fields")} for i, d in enumerate(case["documents"])],
            "follow_up": None if status == "PASS" else "해당 원본·연결키·기준일 및 조건을 조사하고 감사인이 후속절차·조정 여부를 결정",
            "conclusion": None, "reviewed_by": None,
        })
    return results


def validate_existing_index(manifest):
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    spec_path = RAW_ROOT / manifest["spec_source"]["path_relative_to_rawdata_root"]
    ensure(hashlib.sha256(spec_path.read_bytes()).hexdigest() == manifest["spec_source"]["sha256"], "spec.json 해시 변경")
    spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    checked_files = set()
    for entry in manifest["existing_source_index"]:
        parts = entry["spec_json_pointer"].split("/")[1:]
        book = spec[parts[0]][int(parts[1])]
        ensure(parts[2] == "tables" and parts[3] in book["tables"], "spec JSON 위치 오류")
        ensure(book["headers"][parts[3]] == entry["headers"], "spec 필드와 색인 차이")
        ensure(len(book["tables"][parts[3]]) == entry["rows"], "spec 행수와 색인 차이")
        path = (RAW_ROOT / entry["source_path_relative_to_rawdata_root"]).resolve()
        ensure(path.is_relative_to(RAW_ROOT.resolve()), "원천 경로가 프로젝트 밖을 참조함")
        ensure(path.is_file(), f"원천 누락: {path.name}")
        ensure(hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], f"원천 해시 변경: {path.name}")
        with zipfile.ZipFile(path) as z:
            strings = []
            if "xl/sharedStrings.xml" in z.namelist():
                strings = ["".join(e.itertext()) for e in ET.fromstring(z.read("xl/sharedStrings.xml"))]
            rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
            matches = [s for s in ET.fromstring(z.read("xl/workbook.xml")).findall("m:sheets/m:sheet", ns) if s.get("name") == entry["sheet"]]
            ensure(len(matches) == 1, "원천 시트 누락 또는 중복")
            target = rels[matches[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")]
            xml_path = target.lstrip("/") if target.startswith("/") else "xl/" + target
            rows = ET.fromstring(z.read(xml_path)).findall("m:sheetData/m:row", ns)
            values = []
            for cell in rows[0].findall("m:c", ns):
                value = cell.find("m:v", ns)
                value = "".join(cell.find("m:is", ns).itertext()) if cell.get("t") == "inlineStr" else (value.text if value is not None else None)
                if cell.get("t") == "s" and value is not None:
                    value = strings[int(value)]
                values.append(value)
            ensure(values == entry["headers"], f"실제 XLSX 헤더 차이: {entry['sheet']}")
            ensure(len(rows) - 1 == entry["rows"], f"실제 XLSX 행수 차이: {entry['sheet']}")
        checked_files.add(path)
    return len(checked_files), len(manifest["existing_source_index"])


def acceptance_oracle(case_id):
    values = [("PASS", True, True, 0), ("PASS", 110000, 110000, 0),
              ("PASS", 100000, 100000, 0), ("PASS", 0, 0, 0),
              ("PASS", 110000, 110000, 0), ("PASS", 60000, 60000, 0),
              ("PASS", True, True, 0), ("PASS", 1, 1, 0),
              ("PASS", 1430, 1430, 0), ("PASS", 1430, 1430, 0)]
    overrides = {
        "REV-C01": {},
        "REV-C02": {2: ("EXCEPTION", 0, 100000, 100000)},
        "REV-C03": {3: ("EXCEPTION", 11000, 0, -11000)},
        "REV-C04": {6: ("INPUT_BLOCKED", True, None, None)},
        "REV-C05": {8: ("EXCEPTION", 1430, 1000, -430), 9: ("PASS", 1000, 1000, 0)},
    }
    ensure(case_id in overrides, "고정 기대 사례 ID 미등록")
    for index, value in overrides[case_id].items():
        values[index] = value
    return dict(zip(CHECKS, values))


def defensive_tests(base, context):
    tests = []

    def mutate_test(name, edit, target, status, expected_actual=None):
        case = copy.deepcopy(base)
        edit(case)
        result = {r["check_id"]: r for r in evaluate(case, context)}[target]
        ensure(result["status"] == status, name + " 상태 오류")
        if expected_actual is not None:
            ensure(result["actual_value"] == expected_actual, name + " 값 오류")
        if status == "INPUT_BLOCKED":
            ensure(result["actual_value"] is None and result["difference"] is None, name + " 누락을 숫자로 치환함")
        tests.append(name)

    def f(case, kind):
        return next(d["fields"] for d in case["documents"] if d["document_type"] == kind)

    mutate_test("송장 원본 누락", lambda c: c["documents"].__setitem__(slice(None), [d for d in c["documents"] if d["document_type"] != "invoice"]), "INVOICE_CALC", "INPUT_BLOCKED")
    mutate_test("만기일 null", lambda c: f(c, "receivable").update(due_date=None), "AGING", "INPUT_BLOCKED")
    mutate_test("만기일 null ECL 전파", lambda c: f(c, "receivable").update(due_date=None), "ECL", "INPUT_BLOCKED")
    mutate_test("충당률 구간 공백", lambda c: f(c, "ecl_model")["scenarios"][0].update(lower_days=2), "ECL", "INPUT_BLOCKED")
    mutate_test("중복 시나리오", lambda c: f(c, "ecl_model")["scenarios"].append(copy.deepcopy(f(c, "ecl_model")["scenarios"][0])), "ECL", "INPUT_BLOCKED")
    mutate_test("확률 합계 90%", lambda c: f(c, "ecl_model")["scenarios"][0].update(probability_bps=6000), "ECL", "INPUT_BLOCKED")
    mutate_test("회사 전달 회신", lambda c: f(c, "confirmation_control").update(response_direct_to_auditor=False), "CONFIRMATION_PROTOCOL", "INPUT_BLOCKED")
    mutate_test("중복 증빙ID", lambda c: c["documents"].append(copy.deepcopy(c["documents"][0])), "DOC_LINKS", "INPUT_BLOCKED")
    mutate_test("타 송장 입금 배부", lambda c: f(c, "bank_receipt").update(invoice_id="REV-WRONG"), "RECEIPT_ALLOCATION", "INPUT_BLOCKED")
    mutate_test("반품 검색 자료 누락", lambda c: c["documents"].__setitem__(slice(None), [d for d in c["documents"] if d["document_type"] != "return_search"]), "RETURN_POSTING", "INPUT_BLOCKED")
    mutate_test("다른 회사 혼입", lambda c: f(c, "invoice").update(company_id="OTHER"), "DOC_LINKS", "INPUT_BLOCKED")
    mutate_test("음수 채권을 절대값 처리 금지", lambda c: f(c, "receivable").update(closing_balance=-110000), "ECL", "INPUT_BLOCKED")
    mutate_test("과거 손실 근거 공란", lambda c: f(c, "ecl_model").update(historical_basis_reference=""), "ECL", "INPUT_BLOCKED")
    mutate_test("잘못된 날짜", lambda c: f(c, "receivable").update(due_date="2026-02-30"), "AGING", "INPUT_BLOCKED")
    mutate_test("은행 입금 원본 누락", lambda c: c["documents"].__setitem__(slice(None), [d for d in c["documents"] if d["document_type"] != "bank_receipt"]), "RECEIPT_ALLOCATION", "INPUT_BLOCKED")

    def zero_rates(case):
        for scenario in f(case, "ecl_model")["scenarios"]:
            scenario["loss_rate_bps"] = 0
        f(case, "allowance_ledger").update(closing_allowance=0, expense=-1000)

    mutate_test("명시된 실제 0 손실률 보존", zero_rates, "ECL", "PASS", 0)
    mutate_test("음수 충당금 환입 부호 보존", zero_rates, "ECL_ROLLFORWARD", "PASS", 0)
    return tests


def main():
    fixtures = json.loads((HERE / "fixtures.json").read_text(encoding="utf-8-sig"))
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8-sig"))
    ensure(fixtures["schema_version"] == "pm-raw-1", "스키마 버전 오류")
    ensure(fixtures["synthetic"] is True and fixtures["integrated"] is False, "합성/미통합 표시 오류")
    ensure(fixtures["context"] == manifest["context"], "자료 문맥 차이")
    ensure(fixtures["workpaper_state"] == {"prepared_by": None, "reviewed_by": None, "conclusion": None, "adjustment_approved": False, "posted": False}, "자동 승인·전기 금지")
    ensure([c["case_id"] for c in fixtures["cases"]] == [f"REV-C{i:02d}" for i in range(1, 6)], "사례 구성 오류")
    counts = {"PASS": 0, "EXCEPTION": 0, "INPUT_BLOCKED": 0}
    summaries = []
    for index, original in enumerate(fixtures["cases"]):
        case = {**original, "_index": index}
        oracle = acceptance_oracle(case["case_id"])
        ensure([x["check_id"] for x in case["expected"]] == list(CHECKS), "기대 검사 목록 차이")
        actuals = evaluate(case, fixtures["context"])
        for expected, actual in zip(case["expected"], actuals):
            columns = ("status", "expected_value", "actual_value", "difference")
            ensure(tuple(expected[k] for k in columns) == oracle[expected["check_id"]], "합성 기대값이 독립 고정값과 다름")
            ensure(tuple(actual[k] for k in columns) == oracle[actual["check_id"]], f"{case['case_id']}/{actual['check_id']}: {actual}")
            counts[actual["status"]] += 1
        summaries.append({"case_id": case["case_id"], "matched_checks": len(actuals), "findings": [{k: r[k] for k in ("check_id", "status", "expected_value", "actual_value", "difference")} for r in actuals if r["status"] != "PASS"]})
    base = {**fixtures["cases"][0], "_index": 0}
    defensive = defensive_tests(base, fixtures["context"])
    files, sheets = validate_existing_index(manifest)
    print(json.dumps({"worker": "revenue_ar", "synthetic": True, "integrated": False, "cases": len(summaries), "matched_checks": sum(counts.values()), "result_counts": counts, "defensive_checks": len(defensive), "existing_files_verified": files, "existing_sheet_locations_verified": sheets, "scope": "독립 JSON 진단; EXE·TB·조서 미연결", "case_results": summaries}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"검증 실패: {error}", file=sys.stderr)
        sys.exit(1)
