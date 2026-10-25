"""The authored workpaper fields keep the proven Windows inline IME editor."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame

TEXT_FIELDS = (
    ('목적·주장', 'purpose', 2),
    ('위험·기준 / 제외 사유', 'risk', 2),
    ('모집단·선정 / 검사 범위', 'scope', 3),
    ('실제 수행내용·근거·예외 조사', 'performed', 4),
    ('판단·결론·추가절차', 'conclusion', 4),
)


def build_author_fields(app, parent):
    app.proc_heading = tk.StringVar(value='왼쪽에서 절차를 선택한 뒤 근거를 확인하고 작성하세요.')
    ttk.Label(parent, textvariable=app.proc_heading, wraplength=650,
              style='Section.TLabel').pack(anchor='w', pady=(0, 12))
    app.proc_vars = {}
    row = FlowFrame(parent)
    row.pack(fill='x', pady=(0, 12))
    for label, key, width in [('작성자', 'preparer', 14), ('실제 수행일', 'performed_date', 12)]:
        group = ttk.Frame(row, style='Card.TFrame')
        row.add(group)
        ttk.Label(group, text=label).pack(anchor='w', pady=(0, 4))
        value = tk.StringVar()
        app.proc_vars[key] = value
        ttk.Entry(group, textvariable=value, width=width).pack(fill='x')
    app.excluded = tk.BooleanVar()
    row.add(ttk.Checkbutton(row, text='범위에서 제외', variable=app.excluded))
    app.proc_text = {}
    for label, key, height in TEXT_FIELDS:
        ttk.Label(parent, text=label).pack(anchor='w', pady=(8, 4))
        editor = create_editable_text(parent, height=height, wrap='word')
        editor.audit_container.pack(fill='x')
        app.proc_text[key] = editor
    ttk.Label(parent, text='연결 증거 · Ctrl로 여러 자료 선택', wraplength=650).pack(anchor='w', pady=(12, 4))
    app.evidence_list = tk.Listbox(parent, selectmode='extended', height=4,
                                  exportselection=False, font='AuditSmallFont', borderwidth=1, relief='solid')
    app.evidence_list.pack(fill='x')
    ttk.Label(parent, text='실제 근거는 수행내용에도 기록하세요.',
              style='Muted.TLabel').pack(anchor='w', pady=(4, 12))


def build_review_fields(app, parent):
    section = ttk.Frame(parent, style='Card.TFrame')
    section.pack(fill='x', pady=(12, 0))
    ttk.Label(section, text='별도 검토', style='Section.TLabel').pack(anchor='w', pady=(0, 8))
    ttk.Label(section, text='검토자').pack(anchor='w', pady=(0, 4))
    app.reviewer = tk.StringVar()
    ttk.Entry(section, textvariable=app.reviewer, width=18).pack(anchor='w')
    ttk.Label(section, text='검토내용·범위').pack(anchor='w', pady=(10, 4))
    app.review_note = tk.StringVar()
    ttk.Entry(section, textvariable=app.review_note).pack(fill='x')
    ttk.Label(section, text='이름 입력은 본인인증·전자서명이 아니에요. AI 내용 승인과 별도 검토를 구분하세요.',
              style='Muted.TLabel', wraplength=650).pack(anchor='w', pady=(8, 0))
    actions = FlowFrame(section)
    actions.pack(fill='x', pady=(10, 0))
    app.review_complete_button = actions.add(ttk.Button(actions, text='검토기록 완료',
        command=lambda: app.call(lambda: app.review(True))))
    actions.add(ttk.Button(actions, text='보완 의견 남기기',
        command=lambda: app.call(lambda: app.review(False))))
