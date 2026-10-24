# v1.5 공통 계약

각 모듈 API: `analyze(path, context, ledger_result=None, event=None)` → common.result. 모듈명은 `GLA`, `FIA`, `현금분석`. 입력은 기존 ledger.SCHEMA 7개 시트에 모듈 전용 시트를 추가한 확정값 XLSX다. 통화 KRW와 회사·기간은 공통 설정·현재 업무와 일치해야 한다.

PM 제공 `analytics_support.read_bound(path, extra_schema, context, ledger_result, event=None)`는 `(tables, source, binding)`을 반환한다. extra_schema는 새 시트만 담은 dict다. binding은 `issues`, `tables`(현재원장연결), `detail`, `ledger`(현재 재계산 원장 결과), `valid`를 포함한다. 입력의 원장 통제를 재검사하고 현재 Workspace의 실제 원장 입력·리드와 대조한다. valid=False면 위험 검사를 유효한 완료로 표시하지 말고 common.result로 차단 내용을 돌려준다. 현재원장연결 표와 binding.detail은 모듈 결과에 반드시 포함한다. 공통 키 회사코드·전표ID·행ID는 복합키다.

PM 제공 `tools.analytics_fixtures.load_base()`는 정상 통합 원장 XLSX에서 읽은 7시트 dict를 반환한다. `write_input(path, extra_schema, extra_tables, base=None)`가 공통 7시트+전용 시트를 쓴다. 인자가 None이면 같은 정상 원장을 쓴다. 실제 파일·행 출처는 read_xlsx의 _row/_sheet를 사용한다.

각 패키지의 `write_samples(target)` 또는 `samples.write_samples(target)`는 정상+오류 입력을 쓰고 다음 dict를 반환한다: `normal`(Path), `cases` 리스트. cases 항목은 `{id, file, blocking:bool, review:bool, required_codes:[str]}`. file은 target 상대경로 XLSX 문자열, 기대값은 계산기 입력으로 넘기지 않는다. cases.json도 저장한다. 최소 정상·업무상 위험·정상 유사거래·누락·중복·회사/기간·현재원장불일치 8종 이상을 권장한다.

GLA는 월/계정/작성자/계정조합과 설명 가능한 검토 후보, FIA는 전표 메타(입력시각·수동자동·승인자·부서·시스템)와 마감일을 명시적으로 받아 검증, 현금분석은 은행과 장부·거래처계좌 변경 이력·기간을 검증하고 명시적 배부로 다대다/부분지급 및 잔여를 남긴다. 은행 독립통제와 계좌별 기초·입출금·기말 대사가 필요하다. 같은 금액이라는 이유만으로 임의 매칭하지 않는다. 계좌 소유자가 같거나 반복됐다는 이유만으로 부정 판정을 하지 않는다.

공통 결과에 탐지 규칙버전·설정·원문 위치·검사대상 수·미확인 수·후속 확인 제안을 남긴다. human 수행/결론/검토는 비워둔다. 위험점수는 검토 우선순위이며 확률로 표현하지 않는다. 판별할 데이터가 없으면 해당 규칙은 미확인으로 표시한다.
