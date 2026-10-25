"""Saved event history and a read-only selected-event detail card."""
from desktop.shared import *
from desktop.widgets.tables import tree
from desktop.widgets.cards import BentoCard


class HistoryView:
    def build_history(self, parent):
        timeline = BentoCard(parent, '업무 변경 이력을 확인해요',
                             '자료요청·조서 개정·검토를 저장하면 이력이 남아요. 이름 입력은 본인인증·전자서명이 아니에요.')
        timeline.pack(fill='both', expand=True, pady=(0, 16))
        self.history_tree = tree(timeline.body, ['순번', '시각 KST', '기록종류', '대상', '상태', '작성·검토 입력값'], 10)
        self.history_tree.bind('<<TreeviewSelect>>', lambda _: self.show_history())
        detail = BentoCard(parent, '선택한 기록의 원문',
                           '저장 전 입력이나 실제 이메일 발송 여부는 저장 이력과 구분해서 확인하세요.')
        detail.pack(fill='both', expand=True)
        self.history_detail = create_scrolled_text(detail.body, height=10, wrap='word', state='disabled')
        self.history_detail.audit_container.pack(fill='both', expand=True)
        self.history_items = []
