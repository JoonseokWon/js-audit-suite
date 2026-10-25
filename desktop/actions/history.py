"""History native desktop actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill

class HistoryActions:

    def set_history_text(self, value):
        self.history_detail.configure(state='normal')
        self.history_detail.delete('1.0', 'end')
        self.history_detail.insert('1.0', value)
        self.history_detail.configure(state='disabled')

    def history_rows(self):
        names = {'engagement': '업무 생성', 'source': '자료 등록', 'run': '검사 실행', 'procedure': '조서 저장·개정·검토', 'note': '검토의견', 'evidence_request': '자료요청·상태 변경', 'ai_draft': 'AI 초안 생성', 'ai_apply': 'AI 초안 적용', 'ai_content_approval': 'AI 내용 최종 승인'}
        names['sector_storage_relocation'] = '자료 보관 폴더 이동'
        names.update({'workflow_profile': '감사계획·중요성', 'workflow_risk': '위험·주장 연결', 'workflow_procedure': '절차·증거 연결', 'workflow_f01_classification': '구형 F01 목적 확인', 'workflow_finalize': '검토기록 잠금', 'workflow_reopen': '수정 재개', 'workflow_risk_retire': '위험 사용 해제', 'workflow_procedure_retire': '절차 연결 사용 해제'})
        self.history_items = list(self.ws.events) if self.ws else []
        rows = []
        for index, event in enumerate(self.history_items, 1):
            d = event['data']
            state = d.get('state', '')
            if event['kind'] == 'run':
                state = '입력 보완 필요' if d['result']['blocking'] else '자동검사 종료 · 수동절차 필요'
            actor = ' / '.join((str(d[k]) for k in ('preparer', 'reviewer', 'actor') if d.get(k)))
            rows.append({'순번': index, '시각 KST': display_time(event['at']), '기록종류': names.get(event['kind'], event['kind']), '대상': d.get('title') or d.get('name') or d.get('module') or d.get('회사명') or d.get('procedure_id') or d.get('id', ''), '상태': state, '작성·검토 입력값': actor or '기록 없음'})
        return rows

    def show_history(self):
        selected = self.history_tree.selection()
        if not selected:
            return
        text = json.dumps(self.history_items[int(selected[0])], ensure_ascii=False, indent=2)
        if len(text) > 100000:
            text = text[:100000] + '\n[화면 미리보기 생략. 전체 이력은 업무.sqlite3 및 출력 증적JSON에 보존됩니다.]'
        self.set_history_text(text)
