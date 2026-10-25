"""Results native desktop actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill

class ResultsActions:

    def choose_result_module(self):
        if not self.ws:
            return
        latest = self.ws.latest()
        r = latest.get(self.result_module.get())
        names = list(r['result']['tables']) if r else []
        preferred = MODULE_TABLES.get(self.result_module.get(), [])
        names.sort(key=lambda n: preferred.index(n) if n in preferred else len(preferred))
        self.result_tables['values'] = names
        self.result_table.set(names[0] if names else '')
        self.load_table()

    def load_table(self):
        if not self.ws:
            return
        r = self.ws.latest().get(self.result_module.get())
        self.table_rows = r['result']['tables'].get(self.result_table.get(), []) if r else []
        q = self.search.get().strip().lower()
        if q:
            self.table_rows = [r for r in self.table_rows if q in dumps(r).lower()]
        self.page = 0
        self.render_page()

    def turn_page(self, delta):
        self.page = max(0, min(max(0, (len(self.table_rows) - 1) // 200), self.page + delta))
        self.render_page()

    def render_page(self):
        self.visible_rows = self.table_rows[self.page * 200:(self.page + 1) * 200]
        columns = TABLE_COLUMNS.get(self.result_table.get()) or list(dict.fromkeys((k for r in self.visible_rows for k in r))) or ['내용']
        rows = self.visible_rows
        if self.result_module.get() in MODULE_TABLES:
            rows = [{k: format(v, ',') if isinstance(v, int) and (not isinstance(v, bool)) else v for k, v in row.items()} for row in rows]
        fill(self.result_tree, rows, columns)
        if self.result_table.get() in TABLE_COLUMNS:
            widths = {c: {'리스ID': 95, '채권ID': 110, '거래처': 145, '분류군': 95, '월': 100, '회차': 60, '연체일수': 85, '측정구분': 90, '가중손실률': 110}.get(c, 135) for c in columns}
            self.display.register_tree(self.result_tree, widths)
        self.page_label.set(f'{len(self.table_rows)}행 / {self.page + 1}쪽 (전체 저장은 필터와 무관)')

    def show_row(self, _=None):
        s = self.result_tree.selection()
        if s:
            self.row_text.delete('1.0', 'end')
            self.row_text.insert('1.0', json.dumps(self.visible_rows[int(s[0])], ensure_ascii=False, indent=2))
