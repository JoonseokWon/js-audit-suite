"""Scrollable data tables with stable identifiers and numeric alignment."""
from tkinter import ttk

NUMERIC_COLUMNS = frozenset({
    '순번', '차단', '검토', '우선순위', '기초잔액', '차변', '대변', '조정전',
    '승인조정', '조정후', '기대', '실제', '차이', '금액', '수량', '횟수',
    '회차', '연체일수', '가중손실률', '행수', '원가', '장부금액', '기말잔액',
})

def column_anchor(name):
    return 'e' if name in NUMERIC_COLUMNS or str(name).endswith(('(원)', '(%)')) else 'w'

def configure_columns(table, columns, width):
    for column in columns:
        table.heading(column, text=column, anchor=column_anchor(column))
        table.column(column, width=width, minwidth=72, stretch=False,
                     anchor=column_anchor(column))

def tree(parent, columns, height=12):
    frame = ttk.Frame(parent, style='Card.TFrame')
    frame.pack(fill='both', expand=True)
    table = ttk.Treeview(frame, columns=columns, show='headings', height=height,
                         selectmode='browse', style='Audit.Treeview')
    configure_columns(table, columns, 145)
    sy = ttk.Scrollbar(frame, orient='vertical', command=table.yview)
    sx = ttk.Scrollbar(frame, orient='horizontal', command=table.xview)
    table.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
    table.grid(row=0, column=0, sticky='nsew')
    sy.grid(row=0, column=1, sticky='ns')
    sx.grid(row=1, column=0, sticky='ew')
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    table.tag_configure('even', background='#FFFFFF')
    table.tag_configure('odd', background='#F8FAFC')
    table.audit_container = frame
    return table

def fill(table, rows, columns=None):
    children = table.get_children()
    if children:
        table.delete(*children)
    if columns:
        table.configure(columns=columns)
        configure_columns(table, columns, 170)
        manager = getattr(table.winfo_toplevel(), 'audit_display', None)
        if manager:
            manager.register_tree(table, {column: 170 for column in columns})
    keys = table['columns']
    for index, row in enumerate(rows):
        table.insert('', 'end', iid=str(index),
                     values=[str(row.get(key, '')) if row.get(key) is not None else '미확인'
                             for key in keys],
                     tags=('odd' if index % 2 else 'even',))
