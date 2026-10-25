"""Cash-flow desktop actions; calculation policy remains in the copied engine."""
from .shared import *

class ResultActions:

    def render(self):
        self.save_button.configure(state='normal')
        for key, var in self.cards.items():
            var.set(f'{self.result.lines[key][1]:,.0f}' if key in self.result.lines else '계산중단')
        for lid, (cat, amount) in self.result.lines.items():
            self.line_tree.insert('', 'end', values=(lid, cat, f'{amount:,.0f}', self.result.status))
        for lid, cat, amount, refs, formula in self.result.trace:
            self.trace_tree.insert('', 'end', values=(lid, f'{amount:,.0f}', refs, formula))
        self.render_issues()
        self.status.set(f'{self.result.status} · 미해결 {len(self.result.issues)}건 · 금액 단위: 원')
        self.notebook.select(0 if self.result.issues else 1)

    def render_issues(self):
        if not hasattr(self, 'diff_tree'):
            return
        self.diff_tree.delete(*self.diff_tree.get_children())
        if self.result is None:
            return
        search = self.search.get().lower()
        mode = self.filter_mode.get()
        for idx, issue in enumerate(self.result.issues):
            if mode == '금액 차이' and issue.difference is None or (mode == '입력·확인 오류' and issue.difference is not None):
                continue
            if search and search not in ' '.join((issue.code, issue.ref, issue.key, issue.message)).lower():
                continue
            self.diff_tree.insert('', 'end', iid=str(idx), values=(issue.code, issue.ref, issue.key, f'{issue.difference:,.0f}' if issue.difference is not None else '—', issue.message))

    def show_issue(self, _event=None):
        selection = self.diff_tree.selection()
        if not selection or not self.result:
            return
        i = self.result.issues[int(selection[0])]
        messagebox.showinfo('미해결 차이 상세', f"{i.code}\n원행: {i.ref}\n키: {i.key}\n{i.message}\n차이: {(i.difference if i.difference is not None else '금액 차이 없음')}", parent=self.root)

    def save(self):
        if self.result is None or self.running:
            return
        path = filedialog.asksaveasfilename(parent=self.root, title='새 결과 Excel 파일', defaultextension='.xlsx', initialfile='현금흐름표_검증_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.xlsx', filetypes=[('Excel', '*.xlsx')], confirmoverwrite=False)
        if not path:
            return
        try:
            export_result(self.result, path)
            self.status.set('결과 저장 완료: ' + path)
        except Exception as e:
            messagebox.showerror('저장 실패', str(e), parent=self.root)
            self.status.set('저장 실패 · 새 파일명과 쓰기 권한을 확인하세요')
