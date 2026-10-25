"""Rule candidates are review inputs, never fraud conclusions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree
from desktop.widgets.cards import BentoCard


class RisksView:
    def build_risks(self, parent):
        candidates = BentoCard(parent, '검토할 후보를 살펴봐요',
                               '규칙으로 찾은 후보예요. 우선순위는 부정 확률이 아니며, 원문을 확인하고 사람이 판단해요.')
        candidates.pack(fill='both', expand=True, pady=(0, 16))
        self.risk_items = []
        self.risk_tree = tree(candidates.body, ['모듈', '규칙ID', '우선순위', '사유', '연결상태', '조서ID'], 9)
        self.risk_tree.bind('<<TreeviewSelect>>', lambda _: self.show_risk())
        detail = BentoCard(parent, '후보의 근거와 다음 절차',
                           '선택한 후보의 원문·조건·미확인 범위를 확인하고 관련 조서나 자료요청으로 이어가세요.')
        detail.pack(fill='both', expand=True)
        self.risk_detail = create_scrolled_text(detail.body, height=10, wrap='word')
        self.risk_detail.audit_container.pack(fill='both', expand=True, pady=(0, 12))
        actions = FlowFrame(detail.body)
        actions.pack(fill='x')
        for label, action in [('관련 조서 열기', self.risk_workpaper),
                              ('자료요청 초안 만들기', self.risk_request),
                              ('검토맥락 저장하기', self.export_context)]:
            actions.add(ttk.Button(actions, text=label, command=lambda fn=action: self.call(fn)))
