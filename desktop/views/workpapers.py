"""Two-pane workpaper selection, native authoring and explicit human review."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree
from desktop.widgets.cards import BentoCard
from desktop.views.workpaper_fields import build_author_fields, build_review_fields


class WorkpapersView:
    def build_procedures(self, parent):
        self.build_ai_actions(parent, FlowFrame)
        pan = ttk.Panedwindow(parent, orient='horizontal')
        pan.pack(fill='both', expand=True, pady=(12, 0))
        left = BentoCard(pan, '절차별 조서', '작성할 절차를 선택하세요.')
        right_outer = BentoCard(pan, '조서를 작성하고 검토해요',
                                '초안의 근거를 확인한 뒤 실제 수행과 판단을 기록하세요.')
        pan.add(left, weight=2)
        pan.add(right_outer, weight=3)
        self.proc_paned = pan
        pan.bind('<Configure>', lambda event: pan.sashpos(0, max(180, int(event.width * .38))))
        self.proc_tree = tree(left.body, ['ID', '절차', '현재상태', '필수'], 20)
        self.proc_tree.column('ID', width=85)
        self.proc_tree.column('절차', width=240)
        self.proc_tree.bind('<<TreeviewSelect>>', self.on_procedure_select)
        buttons = FlowFrame(right_outer.body)
        buttons.pack(side='bottom', fill='x', pady=(12, 0))
        self.workpaper_actions = buttons
        self.save_workpaper_button = buttons.add(ttk.Button(buttons, text='조서 저장·개정',
            style='Primary.TButton', command=lambda: self.call(self.save_procedure)))
        buttons.add(ttk.Button(buttons, text='검토 요청', command=lambda: self.call(self.request_review)))
        self.workpaper_export_button = buttons.add(ttk.Button(buttons, text='초안 Excel 내보내기',
            command=lambda: self.export_dialog(False)))
        self.workpaper_export_button.flow_secondary = True
        self.proc_scroll = ScrollableFrame(right_outer.body)
        self.proc_scroll.pack(fill='both', expand=True)
        build_author_fields(self, self.proc_scroll.inner)
        build_review_fields(self, self.proc_scroll.inner)
