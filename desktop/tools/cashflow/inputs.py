"""Cash-flow desktop actions; calculation policy remains in the copied engine."""
from .shared import *

class InputActions:

    def save_template(self):
        path = filedialog.asksaveasfilename(parent=self.root, title='새 입력 양식을 저장해요', defaultextension='.xlsx', initialfile='현금흐름표_입력양식.xlsx', filetypes=[('Excel', '*.xlsx')], confirmoverwrite=False)
        if not path:
            return
        rows = [Row('Settings', i + 2, {'key': key, 'value': ''}) for i, key in enumerate(SETTINGS)]
        book = InputBook({name: rows if name == 'Settings' else [] for name in SCHEMA}, '빈 입력 양식')
        try:
            save_input(book, path)
            self.status.set('입력 양식을 저장했어요: ' + path)
        except Exception as error:
            messagebox.showerror('입력 양식 저장', str(error), parent=self.root)

    def select_file(self):
        p = filedialog.askopenfilename(parent=self.root, title='현금흐름표 입력 선택', filetypes=[('Excel 입력', '*.xlsx')])
        if not p:
            return
        self.invalidate()
        self.clear_result()
        self.source_path = p
        self.example = None
        self.source_label.set('입력: ' + p)
        self.status.set('파일 선택 완료 · 검증 · 계산 버튼을 누르세요')

    def load_example(self):
        self.invalidate()
        self.clear_result()
        self.source_path = None
        self.example = self.cases[self.case_name.get()]
        self.source_label.set('더미 예제: ' + self.case_name.get() + ' · 실제 고객자료 아님')
        self.start()

    def reset(self):
        self.invalidate()
        self.clear_result()
        self.source_path = None
        self.example = None
        self.filter_mode.set('전체')
        self.search.set('')
        self.source_label.set('예제를 불러오거나 입력 .xlsx 파일을 선택하세요.')
        self.status.set('초기화 완료')
