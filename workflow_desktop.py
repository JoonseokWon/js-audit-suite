"""Native planning, evidence links and archive actions; no automatic judgments."""
from pathlib import Path
from decimal import Decimal
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from common import AuditError, dumps
from desktop_display import ScrollableFrame, create_editable_text, create_scrolled_text


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


class WorkflowDesktopMixin:
    def build_workflow(self,parent,flow_type):
        self.wf_summary=tk.StringVar(value='업무를 연 뒤 감사계획을 저장하면 절차 연결 기능이 활성화됩니다.')
        self.wf_profile_summary=tk.StringVar(value='계획 미설정 · 적용 기준과 비율은 직접 결정하세요.')
        self.wf_last_archive={};self.wf_state={};self.wf_modal=None
        ttk.Label(parent,textvariable=self.wf_summary,wraplength=1150).pack(anchor='w',fill='x',pady=5)
        ttk.Label(parent,textvariable=self.wf_profile_summary,wraplength=1150).pack(anchor='w',fill='x',pady=5)
        ttk.Label(parent,text='계획·위험·절차 연결').pack(anchor='w',pady=(10,2))
        bar=flow_type(parent);bar.pack(fill='x')
        for label,action in [('감사계획·중요성',self.open_workflow_profile),('새 위험',lambda:self.open_workflow_risk(new=True)),
                             ('선택 위험 수정',self.open_workflow_risk),('새 절차 연결',lambda:self.open_workflow_procedure(new=True)),
                             ('선택 절차 연결 수정',self.open_workflow_procedure),('구형 F01 분류',self.open_legacy_f01),
                             ('상태 새로고침',self.refresh_workflow)]:
            bar.add(ttk.Button(bar,text=label,command=lambda f=action:self.call(f)))
        ttk.Label(parent,text='검토 기록·취합').pack(anchor='w',pady=(10,2))
        archives=flow_type(parent);archives.pack(fill='x')
        for label,action in [('검토중 취합 ZIP',lambda:self.workflow_archive_dialog(False)),
                             ('검토기록 잠금',lambda:self.workflow_lock_dialog(False)),
                             ('검토완료 취합 ZIP',lambda:self.workflow_archive_dialog(True)),
                             ('수정 재개',lambda:self.workflow_lock_dialog(True)),('취합 ZIP 검증',self.workflow_verify_dialog)]:
            archives.add(ttk.Button(archives,text=label,command=lambda f=action:self.call(f)))
        self.wf_notebook=ttk.Notebook(parent);self.wf_notebook.pack(fill='both',expand=True,pady=10)
        pages={name:ttk.Frame(self.wf_notebook,padding=5) for name in ('완료점검','위험·주장·대응','절차·증거','기준·서식')}
        for name,frame in pages.items():self.wf_notebook.add(frame,text=name)
        self.wf_check_tree=_table(pages['완료점검'],['구분','절차ID','위험ID','확인사항'],11)
        for column,width in [('구분',110),('절차ID',100),('위험ID',145)]:self.wf_check_tree.column(column,width=width)
        self.wf_check_tree.column('확인사항',width=850,minwidth=380,stretch=True)
        self.wf_risk_tree=_table(pages['위험·주장·대응'],['위험ID','위험','계정','주장','절차ID','증거수'],11)
        self.wf_link_tree=_table(pages['절차·증거'],['절차ID','위험ID','증거수','성격','시기','범위','수행기록'],11)
        ttk.Label(pages['기준·서식'],text='감사계획에서 선택한 참고 계열과 절차의 연결을 표시합니다. 연결 범위·제외사항을 함께 확인하세요.',wraplength=1050).pack(anchor='w',pady=5)
        self.wf_form_tree=_table(pages['기준·서식'],['절차ID','서식'],11)
        self.wf_detail=create_scrolled_text(parent,height=7,wrap='word',state='disabled')
        self.wf_detail.audit_container.pack(fill='both',expand=True,pady=5)
        self.wf_check_tree.bind('<<TreeviewSelect>>',lambda _:self.show_workflow_detail('rows',self.wf_check_tree))
        self.wf_check_tree.bind('<Double-1>',lambda _:self.call(self.open_workflow_workpaper))
        self.wf_risk_tree.bind('<<TreeviewSelect>>',lambda _:self.show_workflow_detail('risks',self.wf_risk_tree))
        self.wf_link_tree.bind('<<TreeviewSelect>>',lambda _:self.show_workflow_detail('procedure_links',self.wf_link_tree))
        self.wf_form_tree.bind('<<TreeviewSelect>>',lambda _:self.show_workflow_detail('form_rows',self.wf_form_tree))
        ttk.Label(parent,text='완료점검은 입력·연결·현재 버전을 확인합니다. 실제 수행·판단·내용 승인·별도 검토는 해당 조서에서 기록하세요.',wraplength=1150).pack(anchor='w',fill='x',pady=5)

    def refresh_workflow(self):
        if not hasattr(self,'wf_summary'):return
        if not self.ws:
            self.wf_state={};self.wf_summary.set('업무를 먼저 여세요.');return
        state=self.ws.workflow_status();self.wf_state=state
        self.wf_summary.set(('계획 연결 활성' if state['active'] else '계획 미설정')+
                            (' · 검토기록 잠김' if state['locked'] else ' · 편집 가능')+
                            f" · 기계적 차단 {len(state['blockers'])}건 · 사람 확인 대기 {len(state['human_pending'])}건")
        profile=state.get('profile')
        if profile:
            materiality=profile['materiality']
            self.wf_profile_summary.set(f"감사체계: {profile['audit_framework']} · 회계체계: {self.ws.engagement['회계체계']} · 서식계열: {profile['form_framework']} · "
                f"전체 중요성 {materiality.get('overall_materiality','')}원 / 수행 중요성 {materiality.get('performance_materiality','')}원 / "
                f"선택한 사소금액 {materiality.get('clearly_trivial_threshold','')}원 · 선택한 비율로 재계산한 값")
        else:self.wf_profile_summary.set('적용 기준·중요성 비율·적용 절차를 직접 정한 뒤 감사계획을 저장하세요.')
        blockers={(r.get('code'),r.get('procedure_id'),r.get('risk_id'),r.get('message')) for r in state['blockers']}
        _fill(self.wf_check_tree,[{'구분':'차단' if (r.get('code'),r.get('procedure_id'),r.get('risk_id'),r.get('message')) in blockers else r.get('status','확인'),
            '절차ID':r.get('procedure_id',''),'위험ID':r.get('risk_id',''),'확인사항':r.get('message','')} for r in state['rows']])
        _fill(self.wf_risk_tree,[{'위험ID':r['id'],'위험':r['title'],'계정':', '.join(r['accounts']),
            '주장':', '.join(r['assertions']),'절차ID':', '.join(r['procedure_ids']),'증거수':len(r['evidence_ids'])} for r in state['risks']])
        _fill(self.wf_link_tree,[{'절차ID':r['procedure_id'],'위험ID':', '.join(r['risk_ids']),'증거수':len(r['evidence_ids']),
            '성격':r['nature'],'시기':r['timing'],'범위':r['extent'],'수행기록':'입력 있음' if r.get('performed') else '미기록'} for r in state['procedure_links']])
        from audit_forms import registry_rows,load_registry
        selected=[s['procedure_id'] for s in profile['scope']] if profile else []
        static_ids={row['app_id'] for row in load_registry()['procedures']}
        self.wf_state['form_rows']=registry_rows(profile['form_framework'],[pid for pid in selected if pid in static_ids]) if profile else []
        if profile:
            self.wf_state['form_rows'].extend({'절차ID':pid,'절차명':'현재 업무의 검토 예외',
                '서식계열':profile['form_framework'],'연결상태':'공식참고미지정',
                '대응범위':'동적 예외·대사차이의 후속 검토. 원래 검사·증거와 연결하세요.'}
                for pid in selected if pid not in static_ids)
        rows=self.wf_state['form_rows'];columns=list(rows[0]) if rows else ['절차ID','서식']
        _fill(self.wf_form_tree,rows,columns)

    def _wf_actor(self,dialog):
        dialog.text('actor','기록자',self.ws.engagement['작성자'],height=1)

    def open_workflow_workpaper(self):
        self.guard();selected=self.wf_check_tree.selection()
        if not selected:raise AuditError('조서 ID가 있는 완료점검 행을 선택하세요.')
        row=self.wf_state['rows'][int(selected[0])];pid=row.get('procedure_id')
        if pid not in {task['id'] for task in self.task_list()}:raise AuditError('이 항목은 개별 조서 대신 자료·계획·요청 화면에서 확인하세요.')
        if not self.check_navigation():return False
        self.load_procedure(pid);self.nb.select(self.tabs['절차·조서']);return True

    def _wf_evidence(self,dialog,selected=()):
        return dialog.selection('evidence_ids','연결할 현재 업무의 등록 증거 (Ctrl로 여러 개 선택)',
            [(s['id'],s['name']+' / '+s['id'][:8]) for s in self.ws.sources.values()],selected)

    def _wf_tasks(self):
        from audit_forms import load_registry
        tasks={row['app_id']:row['title'] for row in load_registry()['procedures']}
        tasks.update({task['id']:task['title'] for task in self.task_list()})
        return [(pid,pid+' · '+title) for pid,title in tasks.items()]

    def open_workflow_profile(self):
        d=WorkflowDialog(self,'감사계획·중요성');self.wf_modal=d
        profile=self.ws.workflow_profile or {};materiality=profile.get('materiality',{})
        d.note('기준 적용과 비율·범위는 사용자가 판단합니다. 비율은 소수로 입력하세요(예: 5%는 0.05). 저장하면 조서와 AI 내용의 현재 버전을 다시 확인해야 합니다.')
        self._wf_actor(d)
        d.entry('audit_framework','적용 감사체계',profile.get('audit_framework',''),['KSA_200_720','KSA_1200'])
        d.text('audit_framework_reason','적용 감사체계의 선택 근거',profile.get('audit_framework_reason',''))
        d.note('업무의 실제 회계체계: '+d.ws.engagement['회계체계']+' · 아래 서식계열 선택은 감사기준의 적용 가능성 판단을 대신하지 않습니다.')
        d.entry('form_framework','예시 서식 참고 계열',profile.get('form_framework',''),['KIFRS','일반기업','소규모기업'])
        d.text('benchmark_name','중요성 기준 지표명',materiality.get('benchmark_name',''),height=1)
        for key,label in [('benchmark_amount','기준 금액 (원 단위 정수)'),('materiality_rate','전체 중요성 비율'),
                          ('performance_rate','전체 중요성 대비 수행 중요성 비율'),('trivial_rate','전체 중요성 대비 사소금액 비율 (0 가능)')]:
            d.entry(key,label,materiality.get(key,''))
        d.note('아래 목록에서 절차를 선택하고 적용 여부와 사유를 직접 기록하세요. 지정하지 않은 절차를 자동 적용하지 않습니다.')
        d.scope_records={r['procedure_id']:dict(r) for r in profile.get('scope',[])}
        d.scope_tree=_table(d.body,['절차ID','절차','적용 여부','사유'],9)
        for pid,name in self._wf_tasks():
            row=d.scope_records.get(pid,{})
            d.scope_tree.insert('','end',iid=pid,values=[pid,name,'적용' if row.get('applicable') is True else '제외' if row.get('applicable') is False else '미지정',row.get('reason','')])
        d.text('scope_reason','선택 절차의 적용·제외 사유')
        def scope_set(applicable):
            chosen=d.scope_tree.selection();reason=d.value('scope_reason')
            if not chosen or not reason:
                messagebox.showerror('범위 확인','절차와 적용·제외 사유를 입력하세요.',parent=d.win);return
            for pid in chosen:
                d.scope_records[pid]={'procedure_id':pid,'applicable':applicable,'reason':reason}
                old=d.scope_tree.item(pid,'values');d.scope_tree.item(pid,values=[pid,old[1],'적용' if applicable else '제외',reason])
        scope_buttons=ttk.Frame(d.body,padding=10);scope_buttons.pack(fill='x')
        ttk.Button(scope_buttons,text='선택 절차 적용',command=lambda:scope_set(True)).pack(side='left')
        ttk.Button(scope_buttons,text='선택 절차 제외',command=lambda:scope_set(False)).pack(side='left',padx=8)
        def scope_unset():
            for pid in d.scope_tree.selection():
                d.scope_records.pop(pid,None);old=d.scope_tree.item(pid,'values')
                d.scope_tree.item(pid,values=[pid,old[1],'미지정',''])
        ttk.Button(scope_buttons,text='선택 절차 미지정',command=scope_unset).pack(side='left',padx=8)
        def save():
            payload={key:d.value(key) for key in ('audit_framework','audit_framework_reason','form_framework')}
            payload['materiality']={key:d.value(key) for key in ('benchmark_name','benchmark_amount','materiality_rate','performance_rate','trivial_rate')}
            payload['scope']=list(d.scope_records.values())
            return d.save(lambda:d.ws.save_workflow_profile(payload,d.value('actor'),expected_head=d.head),'감사계획 저장 · 중요성 계산과 현재 버전을 확인하세요.')
        d.button('계획 저장·중요성 계산',save);d.finish();return d

    def open_workflow_risk(self,new=False):
        self.guard();selected=self.wf_risk_tree.selection()
        selected_id=self.wf_state.get('risks',[])[int(selected[0])]['id'] if selected and not new else None
        d=WorkflowDialog(self,'위험·주장·대응 기록');self.wf_modal=d;self._wf_actor(d)
        existing=d.ws.workflow_risks.get(selected_id,{}) if selected_id else {}
        if selected_id and not existing:d.close(force=True);raise AuditError('위험 목록이 변경되었습니다. 새로고침 후 다시 선택하세요.')
        d.note('위험과 주장은 직접 평가해 입력하세요. 연결한 현재 자료와 실행 버전을 기록하며 자료가 바뀌면 재확인 대상으로 표시합니다.')
        d.text('title','위험 제목',existing.get('title',''),height=1)
        d.text('accounts','관련 계정 (쉼표 구분)',', '.join(existing.get('accounts',[])),height=1)
        d.text('assertions','경영진 주장 (쉼표 구분)',', '.join(existing.get('assertions',[])),height=1)
        d.selection('procedure_ids','대응 절차 (Ctrl로 여러 개 선택)',self._wf_tasks(),existing.get('procedure_ids',[]))
        self._wf_evidence(d,existing.get('evidence_ids',[]))
        for key,label in [('nature','대응절차의 성격'),('timing','대응절차의 시기'),('extent','대응절차의 범위'),('assessment','위험 평가와 판단 근거')]:
            d.text(key,label,existing.get(key,''))
        def save():
            payload={key:d.value(key) for key in ('title','nature','timing','extent','assessment','procedure_ids','evidence_ids')}
            payload.update(accounts=[x.strip() for x in d.value('accounts').split(',') if x.strip()],
                           assertions=[x.strip() for x in d.value('assertions').split(',') if x.strip()],basis=d.ws.data_basis())
            if existing:payload['id']=existing['id']
            return d.save(lambda:d.ws.save_workflow_risk(payload,d.value('actor'),expected_head=d.head),'위험·주장·대응 연결을 저장했습니다.')
        d.button('위험 기록 저장',save)
        if existing:d.button('이 위험 사용 해제',lambda:self._wf_retire(d,'risk',existing['id']))
        d.finish();return d

    def open_workflow_procedure(self,new=False):
        self.guard();selected=self.wf_link_tree.selection()
        selected_id=self.wf_state.get('procedure_links',[])[int(selected[0])]['procedure_id'] if selected and not new else None
        d=WorkflowDialog(self,'절차·증거·수행 연결');self.wf_modal=d;self._wf_actor(d)
        existing=d.ws.workflow_procedure_links.get(selected_id,{}) if selected_id else {}
        if selected_id and not existing:d.close(force=True);raise AuditError('절차 연결이 변경되었습니다. 새로고침 후 다시 선택하세요.')
        d.note('계획과 실제 수행은 구분해서 기록합니다. 이 기록이 조서의 수행·결론·사람 승인·별도 검토를 대신 완료하지 않습니다.')
        choices=[existing['procedure_id']] if existing else [pid for pid,_ in self._wf_tasks() if pid not in d.ws.workflow_procedure_links]
        d.entry('procedure_id','연결할 절차 ID',existing.get('procedure_id',''),choices)
        risks=list(self.ws.workflow_risks.values())
        d.selection('risk_ids','연결 위험 (Ctrl로 여러 개 선택)',[(r['id'],r['title']+' / '+r['id'][:8]) for r in risks],existing.get('risk_ids',[]))
        self._wf_evidence(d,existing.get('evidence_ids',[]))
        for key,label in [('nature','절차 성격'),('timing','절차 시기'),('extent','절차 범위'),('plan','구체적 수행 계획'),('performed','실제 수행내용 (수행 후 직접 입력)')]:
            d.text(key,label,existing.get(key,''),height=3 if key in ('plan','performed') else 2)
        d.entry('performed_date','실제 수행일 YYYY-MM-DD (수행 후 입력)',existing.get('performed_date',''))
        d.text('performer','실제 수행자 (수행 후 입력)',existing.get('performer',''),height=1)
        def save():
            payload={key:d.value(key) for key in ('procedure_id','risk_ids','evidence_ids','nature','timing','extent','plan','performed','performed_date','performer')}
            payload['basis']=d.ws.data_basis()
            return d.save(lambda:d.ws.save_workflow_procedure(payload,d.value('actor'),expected_head=d.head),'절차·증거 연결을 저장했습니다. 조서 수행·판단도 확인하세요.')
        d.button('절차 연결 저장',save)
        if existing:d.button('이 연결 사용 해제',lambda:self._wf_retire(d,'procedure',existing['procedure_id']))
        d.finish();return d

    def _wf_retire(self,d,kind,identifier):
        if 'retire_reason' in d.fields:return
        d.note('사용 해제는 마지막 저장본을 대상으로 합니다. 이 창에서 바꾼 다른 내용은 저장하지 않습니다.')
        d.text('retire_reason','사용 해제 사유 (아래 확인 버튼으로 기록)',height=2)
        def commit():
            fn=d.ws.retire_workflow_risk if kind=='risk' else d.ws.retire_workflow_procedure
            return d.save(lambda:fn(identifier,d.value('actor'),d.value('retire_reason'),expected_head=d.head),'사용 해제 이력을 저장했습니다.')
        d.button('사용 해제 확인',commit);d.finish()

    def open_legacy_f01(self):
        d=WorkflowDialog(self,'구형 F01 목적 분류');self.wf_modal=d;self._wf_actor(d)
        d.note('기존 F01은 후속사건과 재무제표 대사에 같은 번호가 쓰였습니다. 당시 실제 목적을 확인하고 분류하세요. 원래 조서·AI·승인 이벤트는 보존하며 새 F01/FS01 조서는 각각 작성합니다.')
        info=d.ws.workflow_status().get('legacy_f01',{})
        d.note('현재 구형 기록: '+dumps(info))
        d.entry('purpose_code','확인한 구형 F01의 목적','',['subsequent_events','financial_statement_reconciliation'])
        d.text('reason','분류 근거·확인한 기록',height=4)
        def save():
            def op():
                result=d.ws.classify_legacy_f01(d.value('purpose_code'),d.value('actor'),d.value('reason'),expected_head=d.head)
                self.current_pid=None;return result
            return d.save(op,'구형 F01 분류 기록을 저장했습니다. 원래 이벤트는 보존됩니다.')
        d.button('확인한 목적 분류 저장',save);d.finish();return d

    def workflow_lock_dialog(self,reopen=False):
        d=WorkflowDialog(self,'수정 재개' if reopen else '검토기록 잠금');self.wf_modal=d;self._wf_actor(d)
        d.note('검토기록을 잠그면 입력·분석·조서 수정을 막습니다. 재개하면 사유가 이력에 남습니다. 잠금은 실제 감사 완료나 감사의견을 표시하는 기능이 아닙니다.')
        d.text('reason','재개 사유' if reopen else '잠금 사유·확인 범위',height=4)
        def save():
            fn=d.ws.reopen_workflow if reopen else d.ws.finalize_workflow
            return d.save(lambda:fn(d.value('actor'),d.value('reason'),expected_head=d.head),'수정 재개 이력을 저장했습니다.' if reopen else '현재 검토기록을 잠갔습니다. 검토완료 취합 ZIP을 만들 수 있습니다.')
        d.button('재개 사유 기록' if reopen else '현재 검토기록 잠금',save);d.finish();return d

    def _wf_background(self,operation,message):
        self.guard();self.set_busy(True);self.sector_cancel.configure(state='disabled');self.status.set(message)
        def work():
            try:self.queue.put(('workflow_ok',operation()))
            except Exception as exc:self.queue.put(('workflow_error',str(exc)))
        threading.Thread(target=work,daemon=False).start()

    def finish_workflow_job(self,kind,data):
        self.set_busy(False)
        if kind=='workflow_error':self.status.set('취합·검증 확인 필요: '+data)
        else:
            self.wf_last_archive=data
            self.status.set('취합 파일 확인: '+str(data.get('path',''))+' / '+str(data.get('mode',''))+' / 원본 '+str(data.get('source_count',''))+'개')
            self.wf_detail.configure(state='normal');self.wf_detail.delete('1.0','end')
            self.wf_detail.insert('1.0','취합 검증 결과\n'+json.dumps(data,ensure_ascii=False,indent=2))
            self.wf_detail.configure(state='disabled')
        # Creating/verifying a ZIP does not change workspace events. Keep any
        # current workpaper/request edits instead of reloading their widgets.
        self.refresh_workflow()

    def workflow_archive_dialog(self,final=False):
        self.guard()
        if not self.check_navigation():return
        ws=self.ws
        if final and not ws.workflow_status()['locked']:raise AuditError('사람의 조서 검토를 마친 뒤 검토기록 잠금을 먼저 진행하세요.')
        path=filedialog.asksaveasfilename(parent=self.root,title='새 취합 ZIP 저장',defaultextension='.zip',
            initialfile='감사_검토완료취합.zip' if final else '감사_검토중취합.zip',filetypes=[('취합 ZIP','*.zip')])
        if not path:return
        from audit_archive import create_archive
        self._wf_background(lambda:create_archive(ws,path,ws.engagement['작성자'],final=final),'원본·DB·헤드·조서의 동일 버전을 확인하고 취합 중…')

    def workflow_verify_dialog(self):
        self.guard()
        if not self.check_navigation():return
        path=filedialog.askopenfilename(parent=self.root,title='검증할 취합 ZIP',filetypes=[('취합 ZIP','*.zip')])
        if not path:return
        from audit_archive import verify_archive
        self._wf_background(lambda:verify_archive(path),'취합 ZIP의 파일·해시·DB·조서 연결 검증 중…')

    def show_workflow_detail(self,key,table):
        selected=table.selection();records=self.wf_state.get(key,[])
        if not selected or int(selected[0])>=len(records):return
        labels={'title':'위험 제목','accounts':'관련 계정','assertions':'주장','procedure_ids':'대응 절차','procedure_id':'절차 ID',
                'risk_ids':'위험 ID','evidence_ids':'등록 증거 ID','nature':'성격','timing':'시기','extent':'범위','assessment':'판단 근거',
                'plan':'수행 계획','performed':'실제 수행내용','performer':'수행자','performed_date':'실제 수행일','actor':'기록자',
                'basis':'자료·실행 버전','updated_at':'저장 시각','id':'위험 ID','code':'확인 코드','risk_id':'위험 ID',
                'message':'확인사항','status':'상태'}
        record=records[int(selected[0])]
        body='\n\n'.join(labels.get(k,k)+': '+(', '.join(str(x) for x in v) if isinstance(v,list) else str(v)) for k,v in record.items())
        self.wf_detail.configure(state='normal');self.wf_detail.delete('1.0','end');self.wf_detail.insert('1.0',body);self.wf_detail.configure(state='disabled')
