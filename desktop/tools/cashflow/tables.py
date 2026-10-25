"""Native data tables using the application's common logical DPI metrics."""
from tkinter import ttk


def make_table(parent,display,columns,labels,widths,height=8):
    frame=ttk.Frame(parent);frame.pack(fill='both',expand=True)
    table=ttk.Treeview(frame,columns=columns,show='headings',height=height)
    vertical=ttk.Scrollbar(frame,orient='vertical',command=table.yview)
    horizontal=ttk.Scrollbar(frame,orient='horizontal',command=table.xview)
    table.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
    table.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns')
    horizontal.grid(row=1,column=0,sticky='ew')
    frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
    for column,label in zip(columns,labels):
        table.heading(column,text=label)
        table.column(column,minwidth=display.px(75),stretch=(column==columns[-1]),
                     anchor='e' if column in ('amount','diff') else 'w')
    display.register_tree(table,dict(zip(columns,widths)))
    return table
