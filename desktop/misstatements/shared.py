"""Head-pinned scrollable forms with raw text validation and responsive labels."""
from tkinter import ttk, messagebox
from desktop.workflow.dialog import WorkflowDialog
from export_support.text import require_xml_text
from common import AuditError


class Dialog(WorkflowDialog):
    def signature(self):
        from common import dumps
        return dumps({key:(field.signature() if hasattr(field,'signature') else self.value(key))
                      for key,field in self.fields.items()})

    def value(self,key):
        field=self.fields[key]
        if isinstance(field,tuple):
            box,records=field;return [records[i][0] for i in box.curselection()]
        if hasattr(field,'get') and not hasattr(field,'audit_container'):return field.get()
        return field.get('1.0','end-1c')

    def note(self,value):
        label=super().note(value)
        label.audit_managed_wrap=True
        label.bind('<Configure>',lambda event:label.configure(wraplength=max(1,event.width)))
        return label


def lines(value):
    require_xml_text(value,'목록 원문')
    return [line.strip() for line in value.splitlines() if line.strip()]


def table(parent,columns,height=7):
    frame=ttk.Frame(parent);frame.pack(fill='both',expand=True,padx=10,pady=8)
    widget=ttk.Treeview(frame,columns=columns,show='headings',height=height,selectmode='browse')
    for key in columns:
        widget.heading(key,text=key);widget.column(key,width=140,minwidth=60,stretch=True)
    widget.grid(row=0,column=0,sticky='nsew')
    sy=ttk.Scrollbar(frame,orient='vertical',command=widget.yview);sy.grid(row=0,column=1,sticky='ns')
    sx=ttk.Scrollbar(frame,orient='horizontal',command=widget.xview);sx.grid(row=1,column=0,sticky='ew')
    widget.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
    frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
    return widget


def selected(widget,rows):
    values=widget.selection()
    if not values:raise AuditError('행을 먼저 선택하세요.')
    return rows[int(values[0])]


def action(dialog,call):
    try:return call()
    except Exception as exc:
        dialog.host.status.set(str(exc));messagebox.showerror('입력 확인',str(exc),parent=dialog.win)
