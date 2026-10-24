# 공개 업데이트를 참고한 v1.5 개선

확인 기준일: 2026-10-23, 한국시간. 아래는 공개 자료의 개념을 참고한 자체 구현이다. EY 내부 코드·모델·알고리즘을 입수하거나 성능을 재현했다는 뜻이 아니다.

| 공개 자료 | 확인한 방향 | 이번 자체 프로그램 반영 |
|---|---|---|
| [EY 글로벌 발표, 2026-04-07](https://www.ey.com/en_us/newsroom/2026/04/ey-launches-enterprise-scale-agentic-ai-to-redefine-the-audit-experience-for-the-ai-era) | Canvas에 다중 에이전트 체계를 결합하고 감사인의 판단을 유지하는 업무 흐름 지원. 2028년까지 전 과정 지원 목표는 현재 완료 기능과 구분 | GLA·FIA·현금을 독립 모듈로 분리하고 같은 업무·원장 실행·증거 해시로 연결. 검토·결론 승인 단계는 사람의 기록으로 유지 |
| [EY한영 AI 감사 소개, 날짜 미표시](https://www.ey.com/ko_kr/services/ai/ey-ai-center/ai-audit) | Helix AI의 위험·이상 패턴 추천, 감사 에이전트의 정보·사람·절차 연결을 소개. 국내 배포 완료 범위는 이 페이지로 단정하지 않음 | 설명 가능한 검토후보·규칙·원문·후속절차를 한 표로 모으고 관련 조서·자료요청 초안으로 이동 |
| [EY 차세대 감사 도구 소개, 날짜 미표시](https://www.ey.com/en_us/digital-audit) | Financial Statement Tie Out·Intelligent Checklist·Canvas AI 등 업무 안에 통합된 검증 도구 소개 | 기존 재무제표 대사 보존, 추가 분석의 필요 원천자료 목록·입력 미확인·규칙 적용범위 표시 |
| [FRC AI 감사 지침, 2026-03-30](https://www.frc.org.uk/library/standards-codes-policy/audit-assurance-and-ethics/guidance/ai-in-audit/) | 생성형·에이전트 AI 출력에 대한 신뢰와 감사인의 판단·문서화 문제를 다룸 | 계산/규칙 버전·설정·검사범위·원문 위치·정상 대조군·실행 버전 기록. 실제 AI 실행 유무를 명시하고 후보를 부정 확정으로 표시하지 않음 |
| [PwC 감사 AI 업데이트, 2026-10](https://www.pwc.com/us/en/about-us/newsroom/expanded-audit-ai-capabilities.html) | 계획·위험평가·검사·커뮤니케이션에 AI 지원을 확대하면서 사람의 책임을 유지한다고 설명 | 후보 확인에서 증빙 요청·수행 기록·검토까지 이어지는 과정에 초점을 둠. 법인별 도구 우위나 탐지 성능 비교는 검증하지 않음 |

FRC 문서는 영국의 참고 지침이며 한국 회계감사기준 준수 인증 근거로 쓰지 않는다. 이번 앱은 오프라인 규칙 기반 분석과 서식화된 검토 지원을 실행하며, 생성형 AI·머신러닝 모델의 추론이나 외부 전송은 구현하지 않는다. 사용자가 AI를 활용해 개발한 사실과 앱 자체의 실제 AI 추론 기능을 구분한다.

입력 전체를 검사해도 ERP 추출 완전성·미제출 계좌·원문 진위까지 입증되지 않는다. 위험 후보는 부정 확정이나 발생확률이 아니며, 적용한 입력과 임계값 범위에서 추가 확인할 대상을 뜻한다. 수동/자동 전표·입력시각·계좌 소유 등 없는 정보는 추정하지 않는다.
