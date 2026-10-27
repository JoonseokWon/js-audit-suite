"""Editable small account tables; users enter amounts without JSON syntax."""
from copy import deepcopy
from tkinter import ttk, StringVar
from desktop.widgets.flow import FlowFrame
from export_support.text import validate_structure
from common import num
from .shared import table, action


class AccountTable:
    def __init__(self,dialog,key,label,rows,*,movement=False):
        self.dialog=dialog;self.rows=deepcopy(rows);self.movement=movement
        dialog.note(label)
        columns=('account_code','expected_movement') if movement else ('account_code','fs_line','direction','amount')
        self.columns=columns
        headings={'account_code':'계정코드','fs_line':'재무제표 표시계정','direction':'영향 방향',
                  'amount':'금액(원)','expected_movement':'예상 GL 순변동(원)'}
        self.widget=table(dialog.body,tuple(headings[key] for key in columns),height=4)
        self.widget.bind('<<TreeviewSelect>>',self.select)
        form=FlowFrame(dialog.body);form.pack(fill='x',padx=10,pady=5)
        self.variables={}
        for column in columns:
            box=form.add(ttk.Frame(form));ttk.Label(box,text=headings[column]).pack(anchor='w')
            variable=StringVar();self.variables[column]=variable
            if column=='direction':widget=ttk.Combobox(box,textvariable=variable,values=('증가','감소'),state='readonly',width=10)
            else:widget=ttk.Entry(box,textvariable=variable,width=18)
            widget.pack(fill='x')
        actions=FlowFrame(dialog.body);actions.pack(fill='x',padx=10,pady=5)
        for title,call in (('계정행 추가',self.add),('선택행 변경',self.update),('선택행 제거',self.remove)):
            actions.add(ttk.Button(actions,text=title,command=lambda fn=call:action(dialog,fn)))
        dialog.fields[key]=self;self.fill()

    def get(self):return deepcopy(self.rows)

    def pending(self):
        raw={key:v.get() for key,v in self.variables.items()}
        if not any(raw.values()):return {}
        selection=self.widget.selection()
        if selection and raw=={key:str(self.rows[int(selection[0])][key]) for key in self.columns}:return {}
        return raw

    def signature(self):return {'rows':self.get(),'pending':self.pending()}

    def require_committed(self):
        from common import AuditError
        if self.pending():raise AuditError('작성 중인 계정행의 추가 또는 변경 버튼을 누른 뒤 저장하세요.')

    def fill(self):
        self.widget.delete(*self.widget.get_children())
        for index,row in enumerate(self.rows):self.widget.insert('','end',iid=str(index),values=[row[key] for key in self.columns])

    def select(self,_=None):
        selection=self.widget.selection()
        if selection:
            row=self.rows[int(selection[0])]
            for key,variable in self.variables.items():variable.set(row[key])

    def read(self):
        from misstatements.schema import impacts
        from human_input import text
        row={key:variable.get() for key,variable in self.variables.items()}
        validate_structure(row,'계정행 원문')
        if self.movement:
            return {'account_code':text(row['account_code'],'계정코드'),
                    'expected_movement':num(row['expected_movement'])}
        return impacts([row])[0]

    def add(self):
        self.rows.append(self.read());self.fill()
        for variable in self.variables.values():variable.set('')

    def update(self):
        from common import AuditError
        selection=self.widget.selection()
        if not selection:raise AuditError('변경할 계정행을 선택하세요.')
        self.rows[int(selection[0])]=self.read();self.fill()
        for variable in self.variables.values():variable.set('')

    def remove(self):
        from common import AuditError
        selection=self.widget.selection()
        if not selection:raise AuditError('제거할 계정행을 선택하세요.')
        self.rows.pop(int(selection[0]));self.fill()
        for variable in self.variables.values():variable.set('')
