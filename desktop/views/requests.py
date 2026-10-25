"""Source requests preserve explicit receipt state and source links."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree
from desktop.widgets.cards import BentoCard


class RequestsView:
    def build_requests(self, parent):
        requests = BentoCard(parent, '자료요청 목록',
                             '요청자료와 수령 사본·처리상태를 기록해요. 수령·검토 상태에는 등록 증거를 연결하세요.')
        requests.pack(fill='both', expand=True, pady=(0, 16))
        columns = ['id', 'title', 'requested_from', 'due_date', 'state', 'note']
        self.request_tree = tree(requests.body, columns, 7)
        for key, label in [('id', '요청번호'), ('title', '요청자료'), ('requested_from', '요청처'),
                           ('due_date', '기한'), ('state', '상태'), ('note', '요청범위·처리내용')]:
            self.request_tree.heading(key, text=label)
        self.request_tree.bind('<<TreeviewSelect>>', self.select_request)
        form = BentoCard(parent, '요청·수령 내용을 작성해요',
                         '저장하면 로컬 이력이 남아요. 실제 이메일 발송은 별도예요.')
        form.pack(fill='both', expand=True)
        self.request_vars = {}
        for key, label in [('title', '요청자료'), ('requested_from', '요청처'), ('due_date', '기한'),
                           ('note', '요청범위·처리내용·취소 사유')]:
            row = ttk.Frame(form.body, style='Card.TFrame')
            row.pack(fill='x', pady=(0, 10))
            ttk.Label(row, text=label).pack(anchor='w', pady=(0, 4))
            value = tk.StringVar()
            self.request_vars[key] = value
            ttk.Entry(row, textvariable=value).pack(fill='x')
        self.request_state = tk.StringVar(value='요청')
        ttk.Label(form.body, text='처리상태').pack(anchor='w', pady=(0, 4))
        ttk.Combobox(form.body, textvariable=self.request_state,
                     values=['요청', '부분수령', '수령', '검토완료', '취소'], state='readonly', width=18).pack(anchor='w')
        ttk.Label(form.body, text='연결할 등록 증거 · Ctrl로 여러 개 선택').pack(anchor='w', pady=(12, 4))
        self.request_evidence = tk.Listbox(form.body, selectmode='extended', height=5,
                                          exportselection=False, borderwidth=1, relief='solid')
        self.request_evidence.pack(fill='x')
        self.request_sources = []
        self.current_request = None
        buttons = FlowFrame(form.body)
        buttons.pack(fill='x', pady=(12, 0))
        buttons.add(ttk.Button(buttons, text='새 요청 작성', command=self.clear_request))
        buttons.add(ttk.Button(buttons, text='요청·수령 기록 저장', style='Primary.TButton',
                               command=lambda: self.call(self.save_request)))
