"""Evidence registration and review notes have separate cards and actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree
from desktop.widgets.cards import BentoCard


class EvidenceView:
    def build_evidence(self, parent):
        evidence = BentoCard(parent, '등록한 증거',
                             '원본의 사본과 해시를 업무 폴더에 보존해요. DB·이력헤드·원본 폴더를 함께 백업하세요.')
        evidence.pack(fill='both', expand=True, pady=(0, 16))
        actions = FlowFrame(evidence.body)
        actions.pack(fill='x', pady=(0, 12))
        actions.add(ttk.Button(actions, text='증거 파일 등록하기', style='Primary.TButton',
                               command=lambda: self.call(self.add_evidence)))
        actions.add(ttk.Button(actions, text='독립 ID 통제값 확인', command=lambda: self.call(self.id_control)))
        self.source_tree = tree(evidence.body, ['자료명', '유형', '원본파일', '사본해시', '등록시각'], 8)
        notes = BentoCard(parent, '검토의견과 해결 기록',
                          '의견의 대상과 후속조치 근거를 기록하세요. 작성자 이름은 인증된 서명이 아니에요.')
        notes.pack(fill='both', expand=True)
        bar = FlowFrame(notes.body)
        bar.pack(fill='x', pady=(0, 12))
        bar.add(ttk.Button(bar, text='검토의견 등록하기', command=lambda: self.call(self.add_note)))
        bar.add(ttk.Button(bar, text='선택한 의견의 해결 기록', command=lambda: self.call(self.resolve_note)))
        self.note_tree = tree(notes.body, ['제목', '내용', '작성자', '해결', '시각'], 8)
