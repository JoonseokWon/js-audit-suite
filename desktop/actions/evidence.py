"""Evidence native desktop actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill

class EvidenceActions:

    def id_control(self):
        from estimate_controls import independent_ids
        path = filedialog.askopenfilename(parent=self.root, title='계산 입력과 별도로 ERP에서 추출한 전체 ID CSV', filetypes=[('UTF-8 CSV', '*.csv')])
        if not path:
            return
        column = simpledialog.askstring('독립 ID 열', 'CSV의 식별자 열 이름 (예: 채권ID, 리스ID)', parent=self.root)
        if not column:
            return
        value = independent_ids(path, column)
        output = '행수: ' + str(value['행수']) + '\nID해시: ' + value['ID해시']
        self.root.clipboard_clear()
        self.root.clipboard_append(output)
        messagebox.showinfo('독립 통제값 복사됨', output + '\n\n독립통제 시트에 입력하고 CSV·추출 근거를 증거로 등록하세요. 같은 계산 입력을 재합산한 값은 독립 증거가 아닙니다.', parent=self.root)

    def add_evidence(self):
        self.guard()
        if not self.check_draft():
            return
        path = filedialog.askopenfilename(parent=self.root)
        if path:
            label = simpledialog.askstring('자료명', '근거를 식별할 자료명', initialvalue=Path(path).name, parent=self.root)
            if label:
                self.ws.add_source(path, label)
                self.refresh()

    def add_note(self):
        self.guard()
        if not self.check_draft():
            return
        title = simpledialog.askstring('검토의견', '의견 제목', parent=self.root)
        if title:
            body = simpledialog.askstring('검토의견', '내용·대상 조서·필요한 후속조치', parent=self.root)
            actor = simpledialog.askstring('검토의견', '작성자', parent=self.root)
            if body and actor:
                self.ws.add_note(title, body, actor)
                self.refresh()

    def resolve_note(self):
        self.guard()
        if not self.check_draft():
            return
        s = self.note_tree.selection()
        if s:
            n = self.note_items[int(s[0])]
            body = simpledialog.askstring('해결 기록', '해결 내용·근거', parent=self.root)
            actor = simpledialog.askstring('해결 기록', '작성자', parent=self.root)
            if body and actor:
                self.ws.add_note(n['title'], n['body'] + ' / 해결: ' + body, actor, True, n['id'])
                self.refresh()
