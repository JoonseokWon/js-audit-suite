"""Risks native desktop actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill

class RisksActions:

    def selected_risk(self):
        self.guard()
        s = self.risk_tree.selection()
        if not s:
            raise AuditError('검토 후보를 선택하세요.')
        return self.risk_items[int(s[0])]

    def show_risk(self):
        s = self.risk_tree.selection()
        if not s:
            return
        self.risk_detail.delete('1.0', 'end')
        self.risk_detail.insert('1.0', json.dumps(self.risk_items[int(s[0])], ensure_ascii=False, indent=2))

    def risk_workpaper(self):
        r = self.selected_risk()
        if not self.check_navigation():
            return
        self.load_procedure(r['조서ID'])
        self.nb.select(self.tabs['절차·조서'])

    def risk_request(self):
        r = self.selected_risk()
        if not self.check_navigation():
            return False
        draft = self.ws.candidate_request_draft(r['후보키'])
        self.clear_request()
        for k, v in self.request_vars.items():
            v.set(draft[k])
        for i, s in enumerate(self.request_sources):
            if s['id'] in draft['source_ids']:
                self.request_evidence.selection_set(i)
        self.nb.select(self.tabs['자료요청'])
        self.status.set('요청 초안입니다. 요청처·기한·범위를 확인한 뒤 저장하세요.')

    def export_context(self):
        self.guard()
        path = filedialog.asksaveasfilename(parent=self.root, title='로컬 규칙 분석의 검토맥락 저장', defaultextension='.json', filetypes=[('JSON', '*.json')])
        if path:
            from review_support import save_context
            save_context(self.ws, path)
            self.status.set('로컬 규칙 분석의 검토맥락을 저장했습니다. AI 추론 사용 여부: 없음.')
