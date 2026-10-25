"""Inspect workbook inputs and explicitly confirm mapping and calculation policy."""
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from common import AuditError,sha
from onboarding import MODULES
from onboarding.integration import sample,read_input
from onboarding.workbooks import save_input
from onboarding.workbook_schema import descriptors,encode
from desktop_display import ScrollableFrame
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree,fill


class WorkbenchDialog:
    def __init__(self,host):
        host.guard()
        if not host.check_navigation():return
        self.host=host;self.ws=host.ws;self.head=self.ws.head;self.paths=[]
        self.win=tk.Toplevel(host.root);self.win.title('실무절차 입력·검사')
        self.win.audit_display=host.display;self.win.transient(host.root)
        px=host.display.px
        self.win.geometry(f'{min(px(1020),self.win.winfo_screenwidth()-80)}x{min(px(850),self.win.winfo_screenheight()-100)}')
        self.win.grab_set()
        footer=ttk.Frame(self.win,padding=px(16));footer.pack(side='bottom',fill='x')
        ttk.Button(footer,text='확인 기록 후 검사',style='Primary.TButton',
            command=lambda:host.call(self.execute)).pack(side='right')
        ttk.Button(footer,text='닫기',command=self.win.destroy).pack(side='right',padx=px(10))
        scroll=ScrollableFrame(self.win);scroll.pack(fill='both',expand=True)
        self.body=ttk.Frame(scroll.inner,padding=px(20));self.body.pack(fill='both',expand=True)
        ttk.Label(self.body,text='자료와 계산정책을 확인해요',style='Title.TLabel').pack(anchor='w')
        ttk.Label(self.body,text=self.ws.engagement['회사명']+' · '+self.ws.context['기준일'],style='Muted.TLabel').pack(anchor='w',pady=(5,12))
        bar=FlowFrame(self.body);bar.pack(fill='x')
        selected=host.module.get() if host.module.get() in MODULES else MODULES[0]
        self.area=tk.StringVar(value=selected)
        combo=bar.add(ttk.Combobox(bar,textvariable=self.area,values=MODULES,state='readonly',width=24))
        combo.bind('<<ComboboxSelected>>',lambda _:host.call(self.reset))
        for label,command in (('입력 양식 저장',self.save),('입력 자료 불러오기',self.load),('ERP 원본 열 연결',self.erp)):
            bar.add(ttk.Button(bar,text=label,command=lambda fn=command:host.call(fn)))
        self.notice=tk.StringVar()
        ttk.Label(self.body,textvariable=self.notice,wraplength=900,style='Muted.TLabel',justify='left').pack(fill='x',pady=(10,12))
        self.preview=tree(self.body,['자료','행수','안내'],8);self.preview.bind('<Double-1>',self.show_table)
        ttk.Label(self.body,text='행을 두 번 누르면 입력표를 볼 수 있어요. 숫자·정책은 저장한 Excel 양식에서 수정한 뒤 다시 불러오세요.',
            wraplength=900,style='Muted.TLabel').pack(fill='x',pady=(5,15))
        self.actor=tk.StringVar();self.reason=tk.StringVar();self.accept=tk.BooleanVar(value=False)
        self.aje=tk.BooleanVar(value=False)
        for label,var in (('입력 확인자',self.actor),('확인 사유',self.reason)):
            ttk.Label(self.body,text=label).pack(anchor='w');ttk.Entry(self.body,textvariable=var).pack(fill='x',pady=(3,9))
        ttk.Checkbutton(self.body,text='입력자료와 계산정책을 확인했습니다.',variable=self.accept).pack(anchor='w')
        ttk.Checkbutton(self.body,text='감사조정 별도 확인·승인',variable=self.aje).pack(anchor='w',pady=(8,0))
        ttk.Label(self.body,text='두 번째 체크는 ERP 입력에 승인 상태인 감사조정이 있을 때 그 현재 금액과 근거를 직접 확인·승인하는 항목이에요.',
            wraplength=900,style='Muted.TLabel').pack(fill='x',pady=(6,0))
        ttk.Label(self.body,text='이 확인은 감사조서의 수행·결론·최종내용 승인·검토와 별도예요. 확인자 이름은 본인인증이 아니에요.',
            wraplength=900,style='Muted.TLabel').pack(fill='x',pady=(12,0))
        self.reset()
        for child in self.body.winfo_children():
            if isinstance(child,ttk.Label):
                child.pack_configure(fill='x');child.configure(wraplength=host.display.px(640))
                child.audit_managed_wrap=True
                child.bind('<Configure>',lambda event,w=child:w.configure(wraplength=max(1,event.width)))

    def reset(self):
        self.payload=sample(self.area.get(),self.ws.context);self.paths=[];self.accept.set(False);self.aje.set(False)
        self.notice.set('가상 입력 예시예요. 실제 업무라면 회사 원본·독립 통제·계산정책으로 바꾸고 확인하세요. 예시를 실제 자료로 간주하지 않아요.')
        self.refresh()

    def refresh(self):
        self.description=descriptors(self.area.get(),self.payload)
        fill(self.preview,[{'자료':d['sheet'],'행수':len(self.payload[d['key']]),'안내':'설정 항목' if d['kind']=='dict' else '입력 행'} for d in self.description],['자료','행수','안내'])

    def save(self):
        path=filedialog.asksaveasfilename(parent=self.win,defaultextension='.xlsx',initialfile=self.area.get()+'_입력.xlsx')
        if path:save_input(self.area.get(),self.payload,path);self.notice.set('입력 양식을 저장했어요. 실제 자료로 수정한 뒤 다시 불러오세요.')

    def load(self):
        path=filedialog.askopenfilename(parent=self.win,filetypes=[('실무절차 입력','*.xlsx *.json')])
        if not path:return
        before=sha(path);self.payload=read_input(self.area.get(),path,self.ws.context)
        if sha(path)!=before:raise AuditError('불러오는 중 원본이 변경됐습니다. 다시 불러오세요.')
        self.paths=[(path,before)];self.accept.set(False);self.aje.set(False)
        self.notice.set('불러온 입력자료를 확인하세요: '+path);self.refresh()

    def erp(self):
        if self.area.get()!=MODULES[0]:raise AuditError('ERP 열 연결은 실무자료·원장에서 사용하세요.')
        from desktop.onboarding.erp_form import open_erp_mapping
        def ready(payload,path,metadata):
            self.payload=payload;self.paths=[(path,metadata['sha256'])]
            self.accept.set(False);self.aje.set(False);self.notice.set('ERP 원본을 연결했어요. 별도 TB·통제와 매핑도 확인하세요.');self.refresh()
        open_erp_mapping(self.host,self.payload,ready)

    def show_table(self,event=None):
        chosen=self.preview.selection()
        if not chosen:return
        d=self.description[int(chosen[0])];value=self.payload[d['key']]
        view=tk.Toplevel(self.win);view.title(d['sheet']);view.geometry('1050x550')
        if d['kind']=='dict':rows=[{'항목':label,'값':encode(value[key])} for key,label in zip(d['keys'],d['headers'])]
        else:rows=[{label:encode(row.get(key)) for key,label in zip(d['keys'],d['headers'])} for row in value]
        columns=list(rows[0]) if rows else d['headers'];display=tree(view,columns,15);fill(display,rows[:200],columns)
        ttk.Label(view,text=f'전체 {len(rows)}행 중 최대 200행을 표시해요. 전체 자료는 원본 Excel에서 확인하세요.').pack(anchor='w')

    def execute(self):
        if not self.accept.get():raise AuditError('입력자료와 계산정책을 확인한 뒤 체크해 주세요.')
        from desktop.onboarding.operations import execute_inputs
        execute_inputs(self,self.aje.get())


def open_workbench(host):return WorkbenchDialog(host)
