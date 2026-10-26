"""Single native desktop engagement, calculation, evidence and workpaper application."""
import runtime
RESOURCE=runtime.configure()
runtime.configure_tk_libraries()
from desktop_display import enable_dpi_awareness
runtime.DPI_STATUS=enable_dpi_awareness()
from pathlib import Path
import json,sys,threading,queue,traceback,shutil
from datetime import datetime,timezone,timedelta
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog
from common import AuditError,dumps,digest
from workspace import Workspace
from adapters import MODULES
from display_schema import TABLE_COLUMNS,MODULE_TABLES
import exporter
from desktop_display import DisplayManager,ScrollableFrame,create_scrolled_text,create_editable_text
from ai_desktop import AIDesktopMixin
from workflow_desktop import WorkflowDesktopMixin

TITLE='JS 통합 회계감사 v2.2.0'

ONBOARDING_LIMITS={
 '실무자료·원장':'확인한 ERP 열·계정·부호와 독립 통제. 조정 전후 TB·본문·주석·제조원가 대사. 원본 추출 신뢰성은 별도 확인.',
 '유형자산증감':'원가·누계·CIP 취득·대체·취소·처분 모집단과 증감 대사. 자본화·사용가능일·실재성은 사람 판단.',
 '감사표본선정':'확인한 모집단·방법·규모와 고정 seed로 고액층·특정항목·무작위 표본 선정. 규모·범위·오류 평가 판단은 별도.',
 '금융기관조회':'금융기관 목록·조회항목·부분회신·미회신과 원장 대사. 실제 발송·회신 진위 확인은 사람 수행.',
 '주석구성대사':'자산·차입 증감과 담보 등 주석 구성 대사. 적용 공시요건·정성 표현의 충분성은 별도 검토.',
 '분류검토':'보유목적·만기·제한·위험 등 근거 누락과 상충 확인. 날짜만으로 현금성자산을 자동 확정하지 않음.',
 '현금흐름표연결':'현재 원장과 현금 배부·제조상각·이자·법인세·비현금·부채 증감 대사. 적용 정책·출발점은 사람 확인.',
}
def resource(*parts):return RESOURCE.joinpath(*parts)
def display_time(value):return datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S KST')
CATALOG=json.loads(resource('procedure_catalog.json').read_text(encoding='utf-8'))
LIMITS={'원장·리드':'전체 계정 독립 통제·전표별 차대·조정 전후 리드. KRW 확정값, 최대 10,000행/시트.','금융상품':'기존 v2.1 단순이자·명세/원장/회신 대사. 회사는 현재 업무에 수동 귀속합니다.','매출':'기존 v2.1 주문·납품·청구·원장 대사. IFRS15 통제이전 판단은 별도 절차.','감가상각':'기존 v1.1 원가모형·유한내용연수·월할. 손상·재평가 등은 별도 절차.','확장검사':'은행 정확 1:1·채권연령/후속회수·매입 수치·기준일 재고수량. ECL·NRV·조회/입회 결론은 별도.'}
LIMITS.update({'리스':'고정 월납 임차인: 월별 현재가치·부채/사용권 롤포워드·유동분류. 변경/옵션/손상/외화는 미지원.','대손충당금':'유의적 금융요소 없는 매출채권: 전체기간 ECL 충당률표·전망 시나리오·개별평가·변동 대사. 손실률 근거는 별도 검토.'})
LIMITS.update({'재고평가':'확정 원가단가×수량·품목/로트별 NRV·평가손실/환입·원장 변동 대사. 원가 배부·실사 판단은 별도.','종업원급여':'달력일 월급·승인 수당/공제·지급·미지급·단기 누적연차·약정 DC. 세액/최저요율/DB/퇴직정산은 미지원.'})
LIMITS.update({'미기록부채·비용이연':'확정 KRW 용역: 후속송장·지급 귀속검색, 미지급 및 1회 전액지급 선급의 일할/월할 배분. 부가세·외화·재고/자산취득·환불/변경·추정충당은 별도.'})
DEMO_FILES=[('원장·리드', '통합_v1.3_원장_리드.xlsx'), ('금융상품', '통합_v1.3_금융상품.xlsx'), ('매출', '통합_v1.3_매출.xlsx'), ('감가상각', '통합_v1.3_감가상각.xlsx'), ('확장검사', '통합_v1.3_확장검사.xlsx'), ('리스', '통합_v1.3_리스.xlsx'), ('대손충당금', '통합_v1.3_대손충당금.xlsx'), ('재고평가', '통합_v1.3_재고평가.xlsx'), ('종업원급여', '통합_v1.3_종업원급여.xlsx'), ('미기록부채·비용이연', '비용이연_01_정상.xlsx')]
FULL_DEMO_FILES=DEMO_FILES+[('원천증빙','통합_v1.4_원천증빙.auditpack'),('재무제표·주석','통합_v1.4_재무제표.json')]
ANALYTIC_DEMO_FILES=FULL_DEMO_FILES+[('GLA','통합_v1.5_GLA.xlsx'),('FIA','통합_v1.5_FIA.xlsx'),('현금분석','통합_v1.5_현금분석.xlsx')]
LIMITS.update({'GLA':'현재 원장 7시트 대사 후 월·계정·작성자·복합 전표 분석. 규칙 후보와 원문·후속절차. 부정 확정 아님.',
 'FIA':'명시적 입력/승인 메타와 마감·업무시간 정책으로 분석. 없는 정보를 추정하지 않으며 미확인 규칙을 표시.',
 '현금분석':'선택 계좌의 은행 독립통제·잔액·명시적 배부·지급근거와 변경 이력 분석. 계좌 모집단과 실제 증거 진위는 별도 확인.'})
LIMITS.update({'원천증빙':'원본 엑셀·해시·행을 고정한 증빙팩. 선택한 거래의 다대다 배부와 현재 업무 원장을 대조합니다. 선택 범위 밖 완전성·증거 진위 판단은 별도입니다.',
 '재무제표·주석':'현재 업무의 조정전·미마감 TB와 합계·본문·선택 주석 대사. 입력은 확정 financial.json이며 PDF·OCR 추출은 없습니다.',
 '계정별증빙연습':'9개 계정군의 33개 독립 합성 사례를 원문에서 재계산합니다. 현재 업무 TB에 합산하지 않는 연습용이며 검토중 조서만 출력합니다.'})

