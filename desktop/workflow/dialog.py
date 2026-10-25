"""Head-pinned planning dialog and explicit save lifecycle."""
from .shared import *

class WorkflowDialog:
    """A modal is pinned to one workspace head until explicit Save."""
    def __init__(self, host, title):
        host.guard()
        if not host.check_navigation():raise AuditError('이동을 취소했습니다.')
        self.host=host;self.ws=host.ws;self.ws.refresh();self.head=self.ws.head
        self.win=tk.Toplevel(host.root);self.hidden_test=host.root.state()=='withdrawn'
        if self.hidden_test:self.win.withdraw()
        self.win.title(title);self.win.transient(host.root)
        width=min(1040,max(680,host.root.winfo_screenwidth()-100))
        height=min(850,max(520,host.root.winfo_screenheight()-130))
        self.win.geometry(f'{width}x{height}+{max(20,host.root.winfo_x()+30)}+40')
        self.scroll=ScrollableFrame(self.win);self.scroll.pack(fill='both',expand=True)
        self.body=self.scroll.inner;self.fields={};self.buttons=ttk.Frame(self.win,padding=10)
        self.buttons.pack(fill='x',side='bottom');ttk.Button(self.buttons,text='닫기',command=self.close).pack(side='right')
        self.win.protocol('WM_DELETE_WINDOW',self.close)
        if not self.hidden_test:self.win.grab_set()
        host.wf_modal=self

    def note(self, value):
        label=ttk.Label(self.body,text=value,wraplength=900);label.pack(anchor='w',fill='x',pady=7,padx=10)
        return label

    def entry(self, key, label, value='', choices=None):
        group=ttk.Frame(self.body,padding=(10,4));group.pack(fill='x')
        ttk.Label(group,text=label).pack(anchor='w');variable=tk.StringVar(value=str(value))
        if choices is None:widget=ttk.Entry(group,textvariable=variable)
        else:widget=ttk.Combobox(group,textvariable=variable,values=choices,state='readonly')
        widget.pack(fill='x');self.fields[key]=variable;return variable

    def text(self, key, label, value='', height=2):
        group=ttk.Frame(self.body,padding=(10,4));group.pack(fill='x')
        ttk.Label(group,text=label).pack(anchor='w');widget=create_editable_text(group,height=height,wrap='word')
        widget.audit_container.pack(fill='x');widget.insert('1.0',str(value));self.fields[key]=widget;return widget

    def selection(self, key, label, records, selected=(), height=5):
        group=ttk.Frame(self.body,padding=(10,4));group.pack(fill='x')
        ttk.Label(group,text=label).pack(anchor='w');box=tk.Listbox(group,selectmode='extended',exportselection=False,height=height)
        box.pack(fill='x');values=list(records)
        for i,(value,name) in enumerate(values):
            box.insert('end',name)
            if value in selected:box.selection_set(i)
        self.fields[key]=(box,values);return box

    def value(self,key):
        field=self.fields[key]
        if isinstance(field,tuple):
            box,records=field;return [records[i][0] for i in box.curselection()]
        if isinstance(field,tk.Variable):return field.get().strip()
        return field.get('1.0','end').strip()

    def button(self,label,action):
        ttk.Button(self.buttons,text=label,command=action).pack(side='left',padx=5)

    def save(self, action, message):
        try:
            if self.host.ws is not self.ws:raise AuditError('업무가 변경되었습니다. 이 창을 닫고 다시 여세요.')
            self.ws.refresh()
            if self.ws.head!=self.head:raise AuditError('다른 작업으로 업무 이력이 변경됐습니다. 입력을 확인한 뒤 다시 여세요.')
            record=action();self.close(force=True);self.host.refresh();self.host.status.set(message);return record
        except Exception as exc:
            self.host.status.set(str(exc));messagebox.showerror('저장 확인',str(exc),parent=self.win)
            return None

    def finish(self):
        self.host.display.refresh_widgets();self.scroll.refresh();self.win.update_idletasks()
        if not hasattr(self,'saved_signature'):self.saved_signature=self.signature()

    def signature(self):
        return dumps({'fields':{key:self.value(key) for key in self.fields},'scope':getattr(self,'scope_records',{})})

    def close(self,force=False):
        if not force and hasattr(self,'saved_signature') and self.signature()!=self.saved_signature:
            if not messagebox.askokcancel('미저장 계획 입력','저장하지 않은 입력을 버리고 닫을까요?',parent=self.win):return False
        try:self.win.grab_release()
        except tk.TclError:pass
        self.win.destroy()
        if getattr(self.host,'wf_modal',None) is self:self.host.wf_modal=None
        return True
