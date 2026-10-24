# AI 조서 근거·응답 계약

계약 버전은 `ai-evidence-1` / `ai-workpaper-1`이다. 실제 모델이 만든 초안을 근거와 함께 저장하고, 사람이 수정·검토·최종내용 승인하는 기능이다. AI 내용 승인은 전체 감사 완료나 감사의견 발행이 아니다.

## 실제 호출과 설정

`ai_provider.generate_draft(packet, config, cancel_event=None)`는 실제 HTTP 모델 호출만 수행한다. 모델·실행환경이 없거나 호출이 실패하면 설정 또는 오류 메시지를 반환하고 초안을 저장하지 않는다. 고정 문구를 AI 결과로 제공하는 대체 경로는 없다.

로컬 기본값:

```python
config = {
    'provider': 'ollama',
    'model': 'qwen3:4b-instruct-2507-q4_K_M',
    'endpoint': 'http://127.0.0.1:11437',
    'num_gpu': 0,
    'num_ctx': 16384,
    'timeout_seconds': 300,
}
```

로컬 주소는 HTTP의 `127.0.0.1`과 `localhost`만 허용하며 사용자 지정 포트를 지원한다. `localhost`도 실제 연결은 IPv4 `127.0.0.1`로 고정한다. 사용자정보·쿼리·fragment·다른 API 경로·IPv6·외부 호스트를 거절하고 시스템 프록시를 사용하지 않는다. HTTP 리다이렉트는 따르지 않는다. 로컬 공급자는 외부 API 키를 받지 않는다. 모델의 `:cloud` 및 `-cloud` 지정, 응답의 `remote_host`도 차단한다. 사용자가 별도로 실행한 로컬 서버 자체의 보안과 네트워크 정책까지 인증하는 기능은 아니다.

기본 모델은 [Ollama의 Qwen3-4B Instruct-2507 Q4_K_M](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M)이다. 제품 UI는 CPU 안정 모드 `num_gpu:0`, `num_ctx:16384`, 제한시간 300초를 전달한다. provider를 직접 호출하며 설정을 생략하면 문맥 8192와 제한시간 180초이며 GPU 설정은 서버에 맡긴다.

Ollama `/api/chat`에 JSON Schema를 `format`으로 전달하고 `stream:false`, `think:false`, `temperature:0`, `num_predict:2600`을 사용한다. `done:true`와 `done_reason:'stop'`인 assistant 본문만 받아 검증한다. 사고과정(thinking)은 초안으로 저장하지 않는다. [Ollama Chat API](https://docs.ollama.com/api/chat), [구조화 출력](https://docs.ollama.com/capabilities/structured-outputs), [thinking 설정](https://docs.ollama.com/capabilities/thinking)

24,000자는 토큰 수가 아니다. 한국어 근거와 시스템 규칙·응답 구조까지 합치면 기본 8192 토큰 문맥을 넘을 수 있다. 입력이나 생성 중 앞부분을 조용히 버리지 않도록 `truncate:false`, `shift:false`를 전달한다. 문맥 초과가 발생하면 자료 범위를 줄이거나 `config.num_ctx`를 8192~32768의 1024 배수로 명시한다. `config.num_gpu=0`은 CPU 호환성 진단용 선택 설정이며 기본에는 넣지 않는다. 다른 GPU 강제 옵션은 허용하지 않는다. 이 제어는 v0.40.7 공식 코드에서 확인했으며 해당 옵션을 무시하는 구버전·별도 서버의 동작까지 보장하지 않는다. [v0.40.7 요청 계약](https://github.com/ollama/ollama/blob/v0.40.7/api/types.go), [동일 버전의 chat 처리](https://github.com/ollama/ollama/blob/v0.40.7/server/routes.go)

선택 OpenAI 호출:

```python
config = {
    'provider': 'openai',
    'model': '사용자가 지정한 구조화 출력 지원 모델',
    'external_consent': True,
    'api_key': request_memory_key,
    'timeout_seconds': 180,
}
```

사용자가 OpenAI와 전송할 근거를 명시적으로 확인한 경우만 요청한다. 모델명을 추측해 자동 선택하지 않는다. 주소는 `https://api.openai.com/v1/responses`로 고정하며 다른 주소로 인증정보를 보내지 않는다. `text.format.type='json_schema'`, `strict:true`, `store:false`, `stream:false`, `max_output_tokens:4000`으로 호출한다. API 키는 요청 헤더의 메모리 값만 사용하고 응답·근거·설정 파일·이력에 넣지 않는다. 반환값에도 설정이나 키가 없다. 키가 응답에 그대로 나타나면 결과를 차단한다. Python 문자열의 물리적 메모리 삭제를 보장한다는 뜻은 아니다. 환경변수 `OPENAI_API_KEY`는 코드 호출자가 `allow_env_key=True`를 명시한 경우만 읽으며 기본값은 읽지 않는다. [Responses 생성 API](https://developers.openai.com/api/reference/resources/responses/methods/create), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

`store:false`는 Responses의 애플리케이션 상태 저장을 끄는 설정이다. 모든 보존이 없다는 의미는 아니다. OpenAI의 기본 악용 모니터링 로그는 고객 콘텐츠를 포함해 최대 30일 보존할 수 있고, 계정·승인된 데이터 제어 등에 따라 달라질 수 있다. 실제 회사 자료를 외부로 보내기 전 사용자의 전송 권한과 적용 정책을 확인해야 한다. [OpenAI 데이터 제어](https://developers.openai.com/api/docs/guides/your-data)

## 근거 패킷

```text
packet_version: ai-evidence-1
prompt_version: ai-workpaper-1
engagement: {company_code, company_name, start_date, end_date, synthetic, ...}
procedure: {id, title, ...}
basis: 현재 업무 근거 버전 SHA256
references: [{id, kind, company_code, data, 선택한 source/run/hash 참조...}]
safety_rules: 안전 규칙
limitations: 미수행·미확인 범위
truncation: 절단·누락 수량과 해시
```

전체 패킷은 24,000자 이내, 참조는 1~70개이다. `REF001`, `E001`처럼 영문 대문자 접두사 1~8자와 숫자 3~5자리의 중복 없는 ID를 사용한다. 각 참조의 회사가 업무 회사와 같아야 한다. 감사 대상 기간과 64자리 근거 해시가 있어야 한다. 키·토큰 패턴, 인증정보 필드, 절대 로컬 경로, 제어문자, 비유한 수, 과도한 중첩은 요청 전에 거절한다.

엔진은 원문을 발췌하고 누락 범위를 기록한다. AI가 절단된 자료를 전체 원장·모든 증빙으로 해석하면 안 된다. 원문 해시는 파일 동일성에 대한 참조이며 실제 수령·진위·독립성의 인증이 아니다. 패킷 안의 적요·문서·이전 조서 문구는 비신뢰 데이터로 user 메시지에만 들어가며 시스템 명령으로 승격하지 않는다.

## 모델 응답 JSON

모델이 직접 반환하는 JSON은 세 개의 최상위 항목만 허용한다.

```json
{
  "fields": {
    "purpose": "감사 목적 초안",
    "risk": "위험 초안",
    "scope": "전달된 자료와 제한된 범위",
    "performed": "실제 자동검사 결과와 사람이 미수행한 절차의 구별",
    "conclusion": "예외·한계와 사람의 추가검토·판단 필요"
  },
  "citations": {
    "purpose": ["REF001"],
    "risk": ["REF001"],
    "scope": ["REF001"],
    "performed": ["REF001"],
    "conclusion": ["REF001"]
  },
  "context": {
    "company_code": "패킷 회사 코드와 동일",
    "procedure_id": "패킷 절차 ID와 동일",
    "basis": "패킷 근거 해시와 동일"
  }
}
```

각 조서 필드는 비어 있지 않은 6,000자 이하 문자열이다. 각 인용 배열에는 현재 패킷에 있는 ID가 최소 하나 있어야 하며 중복 인용은 거절한다. 본문에 `[REF001]`을 쓰면 해당 필드의 인용 목록에도 있어야 한다. 응답 문맥의 회사·절차·근거 해시는 모두 일치해야 한다. JSON 중복 키, 코드펜스, 추가 승인 필드, 임의 키 등은 자동 교정하지 않고 거절한다.

검증된 provider 반환값은 `fields`, `citations`, `raw_response`(모델 JSON 원문), `provider`, `model`(서버가 반환한 모델 식별자), `requested_model`, `prompt_version`, `packet_hash`, `company_code`, `procedure_id`, `basis`이다. `packet_hash`는 `common.digest(packet)`이며 패킷 내부에 자기참조 해시를 넣지 않는다. 저장 직전 엔진이 원문과 적용 필드, 회사, 절차, 근거를 다시 비교한다. 작성 도중 패킷이나 업무 자료가 바뀌면 결과를 적용하지 않는다.

선택된 참조 중 `kind:'exception'`이 있으면 해당 `data.code`를 전부 `performed`에 원문 그대로 기재하고, 각 예외의 ID를 모두 `citations.performed`에 넣어야 한다. 같은 코드의 예외가 여러 개라면 코드 표기는 한 번이어도 해당 ID는 모두 필요하다. 예외가 있는데 일반적인 초안·검토 필요 문구만 쓰거나 코드·ID 중 하나를 빠뜨린 응답은 저장하지 않는다. 결론에도 예외·누락·차이 등 경고, 사람의 담당, 추가조사 또는 추가확인의 필요를 명시해야 한다. 모델이 예외를 놓쳤을 때 프로그램이 문장을 붙여 정상 응답처럼 보정하지 않는다. 오류를 표시하고 실제 모델의 새 응답을 받아야 한다.

Ollama에서 선택 예외가 있는 경우에는 생성 시점의 `format` 복사본에 추가 제약을 둔다. 수행내용은 `선택 예외(원문 고정): 코드 [ID]; ... | AI 서술: ` 뒤에 실제 모델의 자유 서술이 이어진다. 결론은 `필수 경고(선택 예외): 사람이 추가조사·확인해야 합니다. AI 제안: ` 뒤에 모델의 제안이 이어진다. 코드·ID 목록과 필수 경고는 프로그램이 제시한 원문 사실·안전 조건이며, 모델이 새로 발견하거나 회계적으로 판단한 사실이 아니다. `AI 서술`과 `AI 제안` 뒤가 모델의 별도 자연어 생성 부분이다. 최종 회계 판단은 사람이 한다.

고정 구간은 사후 붙여넣기가 아니라 로컬 문자열 `pattern`으로 생성 시 제약한다. 자유 서술은 최소 20자의 한 문단이며 따옴표·역슬래시·제어문자를 제외한다. 원문 코드에 있는 특수문자는 JSON 문자열 표현을 먼저 이스케이프해 보존하고, 코드 내부의 제어문자는 요청 전에 거절한다. 수행내용 인용 배열은 패킷 순서의 예외·실행 요약·원장 대사 ID 전체를 하나의 배열 `enum`으로 고정한다. 결론과 다른 항목의 인용은 모델이 선택한다. 공개 `response_schema`와 OpenAI 요청 스키마, 저장 전 공통 검증은 이 로컬 복사본의 변경을 받지 않는다. 지원하지 않는 서버가 오류를 반환하면 제약을 풀어 재시도하지 않고 저장을 차단한다.

적용 근거는 Ollama v0.40.7의 구조화 출력 전달 코드와 해당 버전이 지정한 llama.cpp `b11738`의 JSON Schema→grammar 변환 구현이다. 해당 변환기의 문자열 패턴·배열 `enum` 경로를 확인했으며 `\s`/`\S` 같이 지원하지 않는 문자클래스를 사용하지 않는다. 일부 미지원 기능이 조용히 무시될 수 있으므로 최종 코드·참조·경고 검증도 유지한다. [Ollama v0.40.7 전달 코드](https://github.com/ollama/ollama/blob/v0.40.7/llm/llama_server.go), [고정 llama.cpp 버전](https://github.com/ollama/ollama/blob/v0.40.7/LLAMA_CPP_VERSION), [b11738 변환 구현](https://github.com/ggml-org/llama.cpp/blob/b11738/common/json-schema-to-grammar.cpp), [공식 grammar 안내와 지원 한계](https://github.com/ggml-org/llama.cpp/blob/b11738/grammars/README.md)

## 차단과 사람 검토

`validate_draft_response(packet, fields, citations)`는 엔진 저장 경계에서도 재사용한다. 명시적인 감사 완료·검토 완료·적정의견, 부정/오류/이상 없음, 새 실사·입회·조회서 수령·회수, 전수검사 완료 같은 단정 표현을 보수적으로 차단한다. 미수행·추가확인·판단 필요와 같은 제한은 허용한다. 결론에 사람 검토·판단 또는 범위 제한이 있어야 한다.

이 검사는 구조·참조·문맥과 일부 명백한 과장 표현에 대한 방어다. 인용이 있다는 사실만으로 금액·회계 판단·모든 문장의 진실성이나 프롬프트 공격 방어가 보장되는 것은 아니다. 사람은 원문, 자동검사 결과, 제외된 자료, 예외와 계산 정책을 확인하고 필요한 추가 감사절차를 수행해야 한다. 사람의 수정·최종내용 승인은 AI의 자기 승인과 구별해 저장한다.

요청은 256KiB, HTTP 응답은 512KiB, 모델 JSON 본문은 40,000자 이내이다. 제한시간은 0.1~300초이며 기본 180초다. 취소·제한시간·잘린 출력·거절·잘못된 JSON·잘못된 인용·크기 초과·연결 실패는 저장 가능한 초안을 반환하지 않는다. 취소 시 연결을 닫고 후속 적용을 중지하지만 이미 공급자에 도달한 요청의 처리나 과금 취소를 보장하지 않는다. 오류에는 원격 응답 본문, 키, 인증 URL을 넣지 않고 자동 재시도도 하지 않는다.

## 검증 구분

`test_ai_provider.py`의 68개 검사는 고정 JSON 또는 로컬 모의 HTTP 서버로 요청 구조, 리다이렉트 차단, 시간 제한·취소, 본문 제한, 거절·잘림, 잘못된 응답 구조, 타회사, 없는 인용, 비밀값 비노출, 공개 출처 URL·내부 증거 URI와 로컬 경로의 구별, 문맥·CPU 선택 설정, 문구 과장 뒤에 붙인 검토 필요의 우회, 선택된 모든 예외의 코드·ID·결론 경고 보존, 로컬 생성 제약과 특수문자 보존·OpenAI 스키마 불변, OpenAI 외부동의·환경키 선택을 검증한다. `test_ai_desktop.py`는 모델·실행환경을 모의한 실제 Tk 검사이며 실제 매출 누락 계산의 예외를 초안에 유지하는 경로도 포함한다. 실제 모델 성능 검사가 아니다. 실제 Ollama/Qwen3-4B Instruct-2507의 추론과 UI/저장/조서 연결은 별도 실행 증적으로 기록하며 OpenAI는 실제 호출하지 않은 상태를 구별한다.
