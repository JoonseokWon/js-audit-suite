"""Keep the lead schedule and independent reconciliation visually distinct."""
from desktop.shared import *
from desktop.widgets.tables import tree
from desktop.widgets.cards import BentoCard


class LeadView:
    def build_lead(self, parent):
        lead = BentoCard(parent, '원장과 리드스케줄',
                         '계정별 통제값·TB 변동과 승인한 조정을 확인해요. 차대변 균형은 기본 검사예요.')
        lead.pack(fill='both', expand=True, pady=(0, 16))
        self.lead_tree = tree(lead.body, ['계정코드', '계정명', '리드코드', '기초잔액', '차변',
                                        '대변', '조정전', '승인조정', '조정후', '원본행'], 8)
        links = BentoCard(parent, '계산 결과와 원장을 대사해요',
                          '현재 실행의 독립 계산값을 원장과 비교해요. 숫자 일치는 전체 감사완료를 뜻하지 않아요.')
        links.pack(fill='both', expand=True)
        self.cross_scope_text = tk.StringVar(value='자료의 선택 범위와 미확인 항목도 함께 확인하세요.')
        ttk.Label(links.body, textvariable=self.cross_scope_text, wraplength=1000,
                  style='Muted.TLabel').pack(anchor='w', pady=(0, 12))
        self.cross_tree = tree(links.body, ['모듈', '지표', '상태', '기대', '실제', '차이', '사유'], 7)
