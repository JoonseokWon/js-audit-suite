"""Workflow list presentation helpers."""
from tkinter import ttk

def _table(parent, columns, height=9):
    frame=ttk.Frame(parent);frame.pack(fill='both',expand=True)
    table=ttk.Treeview(frame,columns=columns,show='headings',height=height,selectmode='browse')
    for column in columns:
        table.heading(column,text=column);table.column(column,width=155,stretch=False)
    sy=ttk.Scrollbar(frame,orient='vertical',command=table.yview)
    sx=ttk.Scrollbar(frame,orient='horizontal',command=table.xview)
    table.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
    table.grid(row=0,column=0,sticky='nsew');sy.grid(row=0,column=1,sticky='ns');sx.grid(row=1,column=0,sticky='ew')
    frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
    return table

def _fill(table, rows, columns=None):
    table.delete(*table.get_children())
    if columns:
        table.configure(columns=columns)
        for column in columns:
            table.heading(column,text=column);table.column(column,width=175,stretch=False)
    for i,row in enumerate(rows):
        table.insert('','end',iid=str(i),values=[str(row.get(key,'')) for key in table['columns']])
