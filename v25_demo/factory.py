"""User walkthrough: inputs and empty review forms, never human assessments."""
from pathlib import Path
import json
from common import AuditError, atomic, dumps, digest, sha

STEPS = [
    {'id': 'references', 'title': 'AI 인용과 원문 확인', 'detail': '원본 행·실행ID·해시를 확인하세요. 프로그램 근거 기록과 미검증 AI 제안은 별도로 보존하며 모델 자유서술을 자동 적용하지 않습니다.'},
    {'id': 'misstatements', 'title': '차이 조사와 왜곡표시 집계', 'detail': '자동검토후보는 오류 확정이 아닙니다. 사람이 원인·금액·분류·회사 확인·수정 여부를 기록하고, 동일오류 여부를 판단한 뒤 대표금액을 명시하세요. F03과 연결하며 세효과·정성적 영향도 따로 확인합니다.'},
    {'id': 'risk_response', 'title': '위험평가와 감사절차·조서 연결', 'detail': '더보기 또는 조서 화면의 위험·절차 연결에서 기존 위험을 선택하세요. 경영진주장 분류, 고유위험·통제위험 평가, 대응절차의 성격·시기·범위, 원본 회사·기간·위치·관련성을 직접 기록합니다.'},
    {'id': 'performance', 'title': '실제 수행기록 후 현재 조서 연결', 'detail': '자동검사 실행은 실제 수행을 뜻하지 않습니다. 직접 수행한 내용만 기록하고 현재 근거로 조서를 저장한 뒤 연결하세요. 내용 승인과 작성자와 다른 검토자의 별도 검토는 각각 필요합니다.'},
    {'id': 'changes', 'title': 'Excel 출력과 변경 후 재확인', 'detail': '검토중 Excel을 출력해 원문·집계·연결·미확인을 확인하세요. 자료·평가·수행·본문 변경 시 기존 승인과 연결은 그대로 재사용할 수 없습니다. 전체 감사완료본을 자동 생성하지 않습니다.'},
]


def _inputs(path):
    from openpyxl import Workbook
    book = Workbook(); book.remove(book.active)
    sheets = {
        '가상송장': [['더미표시', '회사코드', '송장ID', '작성일', '품목', '공급가액', '세액', '합계', '발행자'],
                    ['SYNTHETIC ONLY', 'JS_ELEC', 'SI01', '2026-12-30', '가상 전자부품', 90000, 9000, 99000, '']],
        '가상출고증': [['더미표시', '회사코드', '출고번호', '송장ID', '출고일', '품목', '수량', '수령확인자'],
                      ['SYNTHETIC ONLY', 'JS_ELEC', 'SYN-OUT01', 'SI01', '2026-12-30', '가상 전자부품', 1, '']],
        '가상입금내역': [['더미표시', '회사코드', '거래ID', '송장ID', '거래일', '입금액', '확인자'],
                        ['SYNTHETIC ONLY', 'JS_ELEC', 'SYN-RCPT01', 'SI01', '2027-01-15', 99000, '']],
        '검토표_빈양식': [['더미표시', '관련송장', '주장', '고유위험', '통제위험', '원인판단', '실제수행', '수행자', '내용승인자', '별도검토자'],
                          ['SYNTHETIC ONLY', 'SI01', '', '', '', '', '', '', '', '']],
        '범위': [['안내'], ['원장·매출 자동검사 입력은 기존 시연입력 파일을 사용합니다. 이 증빙은 별도 가상 예시이며 진위·연결·수령을 인증하지 않습니다.'],
                ['모든 확인자·평가·판단·수행·승인·검토는 비워 둡니다. 실제 절차를 수행한 사용자가 직접 기록하세요.']]}
    for title, rows in sheets.items():
        sheet = book.create_sheet(title)
        for row in rows: sheet.append(row)
    book.save(path); book.close()


def create_demo(folder):
    from demo_case import create_demo as previous
    ws, manifest = previous(folder); root = ws.root
    relative = '시연입력/06_원천증빙과_빈검토표.xlsx'; _inputs(root/relative)
    payload = {'schema': 'js-electronics-v25-guide-1', 'workspace_id': ws.engagement['id'],
               'synthetic': True, 'inputs': [{'path': relative, 'sha256': sha(root/relative), 'bytes': (root/relative).stat().st_size}],
               'steps': STEPS, 'scope': '입력자료·빈 양식만 생성. 실제 감사 판단·수행·승인·검토 기록은 자동 생성하지 않음.'}
    atomic(root/'v25_추가자료목록.json', dumps(payload).encode('utf-8'))
    ws._append('v25_demo_setup', {'schema': payload['schema'], 'workspace_id': ws.engagement['id'], 'manifest_hash': digest(payload)})
    ws.refresh()
    guide = '\n\nv2.5 추가 시연 · SYNTHETIC ONLY\n' + '\n\n'.join(s['title'] + '\n' + s['detail'] for s in STEPS)
    guide_path = root/'시연_안내.txt'; atomic(guide_path, (guide_path.read_text(encoding='utf-8') + guide).encode('utf-8'))
    return ws, {**manifest, 'v25': payload}


def load_extension(folder):
    from demo_case.manifest import checked_root
    from workspace import Workspace
    root = checked_root(folder); path = root/'v25_추가자료목록.json'
    if not path.is_file() or path.stat().st_size > 64000:
        raise AuditError('v2.5 시연 자료목록이 없습니다.')
    value = json.loads(path.read_text(encoding='utf-8')); ws = Workspace(root)
    records = [e['data'] for e in ws.events if e['kind'] == 'v25_demo_setup']
    expected = {'schema': 'js-electronics-v25-guide-1', 'workspace_id': ws.engagement['id'], 'manifest_hash': digest(value)}
    if records != [expected] or value.get('workspace_id') != ws.engagement['id'] or value.get('synthetic') is not True:
        raise AuditError('v2.5 추가 자료목록이 최초 등록과 다릅니다.')
    for entry in value['inputs']:
        file = root/entry['path']
        if not file.resolve().is_relative_to(root) or file.is_symlink() or not file.is_file() or file.stat().st_size != entry['bytes'] or sha(file) != entry['sha256']:
            raise AuditError('v2.5 추가 입력자료 변경·누락')
    return value
