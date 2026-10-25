"""Browse calculation tables and the original selected row."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree
from desktop.widgets.cards import BentoCard


class ResultsView:
    def build_results(self, parent):
        result = BentoCard(parent, '계산 결과를 살펴봐요',
                           '모듈과 계산표를 선택하고 검색어로 필요한 행을 찾으세요.')
        result.pack(fill='both', expand=True, pady=(0, 16))
        bar = FlowFrame(result.body)
        bar.pack(fill='x', pady=(0, 12))
        self.result_module = tk.StringVar()
        self.result_table = tk.StringVar()
        self.search = tk.StringVar()
        self.result_modules = ttk.Combobox(bar, textvariable=self.result_module, state='readonly', width=24)
        bar.add(self.result_modules)
        self.result_modules.bind('<<ComboboxSelected>>', lambda _: self.choose_result_module())
        self.result_tables = ttk.Combobox(bar, textvariable=self.result_table, state='readonly', width=27)
        bar.add(self.result_tables)
        self.result_tables.bind('<<ComboboxSelected>>', lambda _: self.load_table())
        search = ttk.Entry(bar, textvariable=self.search, width=22)
        search.bind('<Return>', lambda _: self.load_table())
        bar.add(search)
        for label, action in [('검색하기', self.load_table), ('이전', lambda: self.turn_page(-1)),
                              ('다음', lambda: self.turn_page(1))]:
            bar.add(ttk.Button(bar, text=label, command=action))
        self.page_label = tk.StringVar()
        bar.add(ttk.Label(bar, textvariable=self.page_label, style='Muted.TLabel'))
        self.result_tree = tree(result.body, ['내용'], 12)
        self.result_tree.bind('<<TreeviewSelect>>', self.show_row)
        detail = BentoCard(parent, '선택한 행의 원문',
                           '전체 Excel 내보내기에는 검색 필터와 관계없이 모든 결과를 담아요.')
        detail.pack(fill='both', expand=True)
        self.row_text = create_scrolled_text(detail.body, height=8, wrap='word')
        self.row_text.audit_container.pack(fill='both', expand=True)
