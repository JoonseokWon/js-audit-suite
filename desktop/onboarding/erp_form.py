"""Stage real ERP columns with original file/row hashes; approval stays in the parent workflow."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from common import AuditError
from onboarding.erp.input_io import read_original, stage_original
from onboarding.erp.schema import FIELD_LABELS, REQUIRED_TARGETS, OPTIONAL_TARGETS
from desktop.widgets.flow import FlowFrame
from desktop_display import ScrollableFrame

MODE_LABELS={'two_columns':'차변·대변 두 열','signed':'부호 있는 한 금액열'}
MODE_CODES={label:code for code,label in MODE_LABELS.items()}


class ErpMappingDialog:
    def __init__(self, host, payload, on_ready):
        self.host=host;self.payload=deepcopy(payload);self.on_ready=on_ready
        self.tables={};self.metadata={};self.path='';self.variables={}
        self.win=tk.Toplevel(host.root);self.win.title('ERP 원본 열 매핑')
        self.win.audit_display=host.display
        px=host.display.px
        self.win.transient(host.root)
        width=min(px(820),self.win.winfo_screenwidth()-80);height=min(px(760),self.win.winfo_screenheight()-100)
        self.win.minsize(min(width,px(620)),min(height,px(480)))
        self.win.geometry(f'{width}x{height}');self.win.grab_set()
        footer=ttk.Frame(self.win,padding=px(14));footer.pack(side='bottom',fill='x')
        scroll=ScrollableFrame(self.win);scroll.pack(fill='both',expand=True)
        body=ttk.Frame(scroll.inner,padding=px(20));body.pack(fill='both',expand=True);self.body=body
        ttk.Label(body,text='원본 열을 연결해 주세요',style='Title.TLabel').pack(anchor='w')
        ttk.Label(body,text='원본 파일·시트·행번호와 실제 SHA256을 함께 보존해요. '
                  '시산표와 독립 통제는 별도로 받아야 해요. 적용 후에도 사람 확인이 필요해요.',
                  style='Muted.TLabel',wraplength=720,justify='left').pack(fill='x',pady=(8,14))
        row=FlowFrame(body);row.pack(fill='x')
        row.add(ttk.Button(row,text='ERP Excel 선택',command=self.choose_file,style='Primary.TButton'))
        self.sheet=tk.StringVar();self.sheet_box=row.add(ttk.Combobox(row,textvariable=self.sheet,state='readonly',width=24))
        self.sheet_box.bind('<<ComboboxSelected>>',lambda _:self.show_columns())
        self.file_label=ttk.Label(body,text='확정값만 있는 .xlsx를 선택하세요.',wraplength=720,style='Muted.TLabel')
        self.file_label.pack(fill='x',pady=(8,12))
        choices=FlowFrame(body);choices.pack(fill='x')
        config=payload.get('config',{})
        self.mode=tk.StringVar(value=MODE_LABELS.get(config.get('amount_mode','two_columns'),'금액 열 규칙을 선택하세요'))
        self.unit=tk.StringVar(value=str(config.get('source_unit',1)))
        self.factor=tk.StringVar(value=str(config.get('signed_debit_factor',1)))
        for col,(label,var,values) in enumerate((('금액 열 규칙',self.mode,tuple(MODE_CODES)),
                      ('원본 단위',self.unit,('1','1000')),('단일금액 차변 부호',self.factor,('1','-1')))):
            box=choices.add(ttk.Frame(choices))
            ttk.Label(box,text=label).pack(anchor='w')
            combo=ttk.Combobox(box,textvariable=var,values=values,state='readonly',width=20)
            combo.pack(pady=(4,0));combo.bind('<<ComboboxSelected>>',lambda _:self.show_columns())
        self.map_area=ttk.Frame(body);self.map_area.pack(fill='both',expand=True,pady=14)
        self.note=tk.StringVar(value='차변·대변이 각각 있으면 두 열을 연결하세요. 한 금액열만 있으면 부호 규칙을 확인하세요. '
                              '원본 단위는 원이면 1, 천원이면 1000이에요.')
        ttk.Label(body,textvariable=self.note,style='Muted.TLabel',wraplength=720,justify='left').pack(fill='x')
        buttons=FlowFrame(footer);buttons.pack(fill='x')
        buttons.add(ttk.Button(buttons,text='원본·열 매핑 적용',style='Primary.TButton',command=self.apply))
        buttons.add(ttk.Button(buttons,text='취소',command=self.win.destroy))
        for child in body.winfo_children():
            if isinstance(child,ttk.Label):
                child.pack_configure(fill='x');child.configure(wraplength=px(640))
                child.audit_managed_wrap=True
                child.bind('<Configure>',lambda event,w=child:w.configure(wraplength=max(1,event.width)))

    def mode_code(self):
        code=MODE_CODES.get(self.mode.get())
        if not code:raise AuditError('금액 열 규칙을 선택하세요.')
        return code

    def choose_file(self):
        path=filedialog.askopenfilename(parent=self.win,title='확정값 ERP 원본 선택',filetypes=[('Excel','*.xlsx')])
        if not path:return
        try:
            tables,metadata=read_original(path)
            if not any(tables.values()):raise AuditError('자료 행이 있는 시트가 없습니다.')
            self.path=path;self.tables=tables;self.metadata=metadata
            self.sheet_box.configure(values=list(tables));self.sheet.set(next(k for k,v in tables.items() if v))
            self.file_label.configure(text=metadata['filename']+' · 실제 SHA256 '+metadata['sha256'])
            self.show_columns()
        except (AuditError,OSError,ValueError) as exc:
            messagebox.showerror('원본 확인',str(exc),parent=self.win)

    def show_columns(self):
        old={key:value.get() for key,value in self.variables.items()}
        preset={r['target']:r['source'] for r in self.payload.get('column_mapping',[])}
        for child in self.map_area.winfo_children():child.destroy()
        self.variables={};sheet=self.sheet.get();source=self.tables.get(sheet,[])
        if not source:return
        columns=[key for key in source[0] if key not in ('_row','_sheet')]
        required=REQUIRED_TARGETS | ({'debit','credit'} if self.mode_code()=='two_columns' else {'amount'})
        fields=sorted(required)+sorted(OPTIONAL_TARGETS)
        for i,key in enumerate(fields):
            var=tk.StringVar(value=old.get(key,preset.get(key,'')))
            if var.get() not in columns:var.set('')
            ttk.Label(self.map_area,text=FIELD_LABELS.get(key,key)+(' *' if key in required else '')).grid(
                row=i,column=0,sticky='w',padx=(0,16),pady=3)
            ttk.Combobox(self.map_area,textvariable=var,values=['']+columns,state='readonly',width=42).grid(
                row=i,column=1,sticky='ew',pady=3)
            self.variables[key]=var
        self.map_area.columnconfigure(1,weight=1)
        self.note.set(f'{len(source)}개 원본 행을 보존해요. 계정·기간·부호·통제·보고 설정을 별도로 확인하세요. '
                      '매핑되지 않은 회사 계정은 계정 연결 양식에서 연결하세요. 승인자는 자동으로 입력되지 않아요.')

    def apply(self):
        try:
            if not self.path:raise AuditError('원본 파일을 먼저 선택하세요.')
            mapping={key:var.get() for key,var in self.variables.items()}
            mode=self.mode_code()
            required=REQUIRED_TARGETS | ({'debit','credit'} if mode=='two_columns' else {'amount'})
            if any(not mapping.get(key) for key in required):raise AuditError('* 필수 열을 모두 연결하세요.')
            selected=[value for value in mapping.values() if value]
            if len(selected)!=len(set(selected)):raise AuditError('서로 다른 표준 필드에 같은 원본 열을 연결할 수 없어요.')
            config=dict(self.payload.get('config',{}),amount_mode=mode,source_unit=int(self.unit.get()),
                        signed_debit_factor=int(self.factor.get()))
            staged=stage_original(self.payload,self.path,self.tables,self.metadata,self.sheet.get(),mapping,config)
            self.on_ready(staged,self.path,dict(self.metadata));self.win.destroy()
        except (AuditError,OSError,ValueError) as exc:
            messagebox.showerror('열 매핑 확인',str(exc),parent=self.win)


def open_erp_mapping(host,payload,on_ready):
    return ErpMappingDialog(host,payload,on_ready)
