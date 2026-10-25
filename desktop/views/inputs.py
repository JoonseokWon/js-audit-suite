"""Register source data, run calculations and inspect their exceptions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree
from desktop.widgets.cards import BentoCard


class InputsView:
    def build_inputs(self, parent):
        upload = BentoCard(parent, '자료를 등록하고 검사해요',
                           '원본의 회사·기간과 추출 조건을 확인한 뒤 검사할 자료를 선택하세요.')
        upload.pack(fill='x', pady=(0, 16))
        line = FlowFrame(upload.body)
        line.pack(fill='x')
        self.module = tk.StringVar(value=MODULES[0])
        self.file = tk.StringVar()
        line.add(ttk.Combobox(line, textvariable=self.module, values=MODULES,
                             state='readonly', width=24))
        self.module.trace_add('write', lambda *_: self.scope_text.set(LIMITS[self.module.get()]))
        line.add(ttk.Entry(line, textvariable=self.file, width=34))
        line.add(ttk.Button(line, text='파일 선택', command=self.choose_input))
        line.add(ttk.Button(line, text='등록하고 검사하기', style='Primary.TButton',
                            command=lambda: self.call(self.run_selected)))
        line.add(ttk.Button(line, text='검사 중단', command=self.cancel.set))
        self.scope_text = tk.StringVar(value=LIMITS[MODULES[0]])
        ttk.Label(upload.body, textvariable=self.scope_text, wraplength=1000,
                  style='Muted.TLabel').pack(anchor='w', pady=(10, 0))
        runs = BentoCard(parent, '검사 실행 현황',
                         '자동검사가 끝나면 계산 결과와 사람의 확인이 필요한 항목을 함께 살펴보세요.')
        runs.pack(fill='both', expand=True, pady=(0, 16))
        self.run_tree = tree(runs.body, ['모듈', '실행상태', '차단', '검토', '실행시각', '자료명'], 6)
        self.run_tree.column('실행시각', width=225)
        self.run_tree.column('실행상태', width=240)
        issues = BentoCard(parent, '확인이 필요한 항목',
                           '행을 두 번 누르면 관련 조서를 열어요. 입력 오류는 원본을 보완한 뒤 다시 검사하세요.')
        issues.pack(fill='both', expand=True)
        self.issue_tree = tree(issues.body, ['모듈', '중요도', '사유', '내용', '원본행'], 7)
        self.issue_tree.bind('<Double-1>', self.select_issue)
        self.issue_tree.column('내용', width=460)
        self.issue_tree.column('원본행', width=320)
