"""Native evidence-grounded AI drafting with explicit human application and approval."""
from pathlib import Path
import json, threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from common import AuditError,digest
from desktop_display import ScrollableFrame, create_scrolled_text
from ai_provider import generate_draft, DEFAULT_MODEL
from local_ai_runtime import LocalAIRuntime

FIELD_LABELS={'purpose':'목적·주장','risk':'위험·기준','scope':'모집단·검사 범위','performed':'수행내용·근거·예외','conclusion':'판단·결론·추가절차'}

class AIDesktopMixin:
    def init_ai(self,catalog):
        self.ai_catalog=catalog; self.ai_runtime=LocalAIRuntime()
        self.ai_config={'provider':'ollama','model':DEFAULT_MODEL,'endpoint':self.ai_runtime.base_url,'num_gpu':0,'num_ctx':16384,'timeout_seconds':300}
        self.ai_api_key=''; self.ai_openai_model=''; self.ai_job_complete=None
        self.ai_state=tk.StringVar(value='AI 초안 → 근거 확인 → 사람 수정·저장 → 최종 내용 승인')

    def build_ai_actions(self,parent,flow):
        bar=flow(parent);bar.pack(fill='x',pady=(0,5));self.ai_actions=bar
        for attr,label,fn in [('ai_generate_button','AI 초안 생성',self.start_ai_generation),('ai_preview_button','초안 보기·적용',self.open_ai_preview),('ai_approve_button','AI 내용 최종 승인',self.open_ai_approval),('ai_settings_button','AI 설정',self.open_ai_settings)]:
            setattr(self,attr,bar.add(ttk.Button(bar,text=label,command=lambda f=fn:self.call(f))))
        status=bar.add(ttk.Label(bar,textvariable=self.ai_state));status.flow_secondary=True

    def refresh_ai_status(self):
        self.ai_state.set(self.ws.ai_status(self.current_pid)['state'] if self.ws and self.current_pid else 'AI 초안 → 근거 확인 → 사람 수정·저장 → 최종 내용 승인')

    def ai_actor(self):
        return self.proc_vars['preparer'].get().strip() or self.ws.engagement.get('작성자','')

    def ai_clean_form(self):
        self.guard();self.open_workpaper_draft()
        if self.dirty():
            choice=messagebox.askyesnocancel('작성 내용 보존','현재 수정 내용을 저장할까요? 아니오를 선택하면 마지막 저장 내용으로 되돌립니다.',parent=self.root)
            if choice is None:return False
            if choice:self.save_procedure()
            else:self.load_procedure(self.current_pid)
        return True

    def launch_ai_job(self,work,complete):
        if self.busy:raise AuditError('현재 작업이 끝난 뒤 실행하세요.')
        self.cancel.clear();self.ai_job_complete=complete;self.set_busy(True)
        def worker():
            try:result=work();self.queue.put(('ai_ok',result))
            except Exception as exc:
                # Provider/runtime exceptions contain fixed messages, never request bodies or keys.
                from ai_provider import AIProviderError
                from local_ai_runtime import LocalAIError
                safe=str(exc) if isinstance(exc,(AIProviderError,LocalAIError,AuditError)) else 'AI 작업 내부 오류. 초안을 저장하지 않았습니다.'
                self.queue.put(('ai_error',safe))
        threading.Thread(target=worker,daemon=False).start()

    def finish_ai_job(self,kind,data):
        self.set_busy(False);complete=self.ai_job_complete;self.ai_job_complete=None
        if self.closing:self.shutdown_ai();self.root.destroy();return
        if self.cancel.is_set():self.status.set('AI 작업 취소. 새 초안·승인 기록을 저장하지 않았습니다.');return
        if kind=='ai_error':self.status.set(data);messagebox.showerror('AI 작업 중단',data,parent=self.root);return
        try:complete(data)
        except Exception as exc:
            text=str(exc) if isinstance(exc,AuditError) else '완료 결과를 반영하지 못했습니다. 근거와 설정을 확인하세요.'
            self.status.set(text);messagebox.showerror('AI 결과 확인',text,parent=self.root)

    def start_ai_generation(self):
        if not self.ai_clean_form():return
        ws=self.ws;pid=self.current_pid;actor=self.ai_actor()
        if not actor:raise AuditError('초안을 요청하는 작성자를 입력하세요.')
        packet=ws.ai_packet(pid,self.ai_catalog,limits={'max_chars':12000,'max_references':40,'rows_per_table':3,'max_tables':8,'cell_chars':300})
        config=dict(self.ai_config)
        if config['provider']=='openai':
            config.pop('endpoint',None)
            if not self.ai_api_key.strip() or not self.ai_openai_model.strip():raise AuditError('AI 설정에서 OpenAI 모델과 API 키를 입력하세요. 키는 메모리에서만 사용합니다.')
            self.open_external_consent(packet,lambda:self.run_ai_generation(ws,packet,actor,{**config,'model':self.ai_openai_model,'api_key':self.ai_api_key,'external_consent':True}));return
        self.run_ai_generation(ws,packet,actor,config)

    def run_ai_generation(self,ws,packet,actor,config):
        self.guard()
        if self.ws is not ws or self.current_pid!=packet['procedure']['id'] or self.dirty():raise AuditError('근거 확인 후 업무·조서가 변경됐습니다. 다시 생성하세요.')
        if digest(ws.ai_packet(self.current_pid,self.ai_catalog,limits=packet['limits']))!=digest(packet):raise AuditError('전송 전 근거 자료·실행·저장 내용이 변경됐습니다. 다시 확인하세요.')
        self.status.set('근거 기반 AI 조서 생성 중… 취소는 준비 취소 버튼')
        def work():
            if config['provider']=='ollama':
                state=self.ai_runtime.ensure_server(event=self.cancel,progress=lambda s:self.queue.put(('status',s)))
                if not state['ready']:raise AuditError('로컬 AI가 준비되지 않았습니다. AI 설정 → 로컬 AI 준비를 실행하세요.')
            return generate_draft(packet,config,self.cancel)
        def complete(response):
            if self.ws is not ws:raise AuditError('업무가 변경되어 초안을 반영하지 않았습니다.')
            did=ws.record_ai_draft(packet,response,actor);self.refresh()
            self.status.set('실제 AI 초안 저장. 근거를 확인한 뒤 적용·수정·승인하세요.');self.open_ai_preview(did)
        self.launch_ai_job(work,complete)

    def ai_window(self,title,width=960,height=700):
        win=tk.Toplevel(self.root);win.title(title);win.transient(self.root)
        win.geometry(f'{min(width,self.root.winfo_screenwidth()-80)}x{min(height,self.root.winfo_screenheight()-130)}')
        win.minsize(520,380);return win

    def open_external_consent(self,packet,send):
        win=self.ai_window('OpenAI로 전송할 근거 확인');self.ai_consent_win=win
        ttk.Label(win,text='아래 선택된 원문 발췌·대사·예외·현재 조서가 OpenAI API로 전송됩니다. 실제 데이터의 외부 전송 권한을 확인하세요.',wraplength=850,padding=10).pack(fill='x')
        footer=ttk.Frame(win);footer.pack(side='bottom',fill='x')
        text=create_scrolled_text(win,wrap='word');text.audit_container.pack(fill='both',expand=True,padx=10);text.insert('1.0',json.dumps(packet,ensure_ascii=False,indent=2));text.configure(state='disabled')
        approved=tk.BooleanVar(value=False);win.confirmed=approved
        ttk.Checkbutton(footer,text='전송할 근거를 확인했고 이 요청의 외부 전송에 동의합니다.',variable=approved).pack(anchor='w',padx=10,pady=10)
        def execute():
            if not approved.get():raise AuditError('이번 요청의 전송 동의를 선택하세요.')
            win.destroy();send()
        win.send_button=ttk.Button(footer,text='확인한 근거로 AI 생성',command=lambda:self.call(execute));win.send_button.pack(side='right',padx=10,pady=10)
        ttk.Button(footer,text='취소',command=win.destroy).pack(side='right',padx=5,pady=10)

    def open_ai_preview(self,draft_id=None):
        self.guard()
        captured_ws=self.ws
        drafts=[d for d in self.ws.ai_drafts.values() if d['procedure_id']==self.current_pid]
        if draft_id is None:
            if not drafts:raise AuditError('현재 조서의 저장된 AI 초안이 없습니다. AI 초안 생성을 먼저 실행하세요.')
            draft_id=drafts[-1]['id']
        draft=self.ws.ai_drafts[draft_id];win=self.ai_window('AI 초안 · 근거 확인');self.ai_preview_win=win;win.draft_id=draft_id
        ttk.Label(win,text=f"{draft['procedure_id']} · {draft['provider']} / {draft['model']}\nAI 제안입니다. 실제 미수행 사항과 예외를 확인하고 사람이 수정·승인하세요.",wraplength=850,padding=10).pack(fill='x')
        footer=ttk.Frame(win);footer.pack(side='bottom',fill='x')
        nb=ttk.Notebook(win);nb.pack(fill='both',expand=True,padx=10)
        for label,content in [('AI 초안','\n\n'.join(FIELD_LABELS[k]+'\n'+draft['fields'][k]+'\n근거: '+', '.join(draft['citations'][k]) for k in FIELD_LABELS)),('근거·대사',json.dumps(draft['packet'],ensure_ascii=False,indent=2))]:
            frame=ttk.Frame(nb);nb.add(frame,text=label);text=create_scrolled_text(frame,wrap='word');text.audit_container.pack(fill='both',expand=True);text.insert('1.0',content);text.configure(state='disabled')
        def apply():
            if self.ws is not captured_ws:raise AuditError('초안 화면을 연 뒤 업무가 변경됐습니다. 현재 업무에서 다시 여세요.')
            if self.current_pid!=draft['procedure_id']:raise AuditError('이 초안의 원래 조서를 선택하세요.')
            if not self.ai_clean_form():return
            self.ws.apply_ai_draft(draft_id,self.ai_actor());self.refresh();win.destroy();self.status.set('AI 초안 적용. 실제 수행·판단을 수정하고 저장한 뒤 최종 내용을 승인하세요.')
        ttk.Button(footer,text='닫기',command=win.destroy).pack(side='right',padx=10,pady=10)
        win.apply_button=ttk.Button(footer,text='현재 조서에 적용',command=lambda:self.call(apply));win.apply_button.pack(side='right',padx=5,pady=10)

    def open_ai_approval(self):
        if not self.ai_clean_form():return
        ws=self.ws;pid=self.current_pid;state=ws.ai_status(pid)
        if not state['required']:raise AuditError('AI 초안을 적용한 후 최종 내용을 승인하세요.')
        win=self.ai_window('AI 내용 최종 승인');self.ai_approval_win=win
        ttk.Label(win,text='사람이 수정·저장한 현재 내용과 근거 버전을 승인합니다. 별도 검토자의 검토기록과 전체 감사 완료를 대신하지 않습니다.',wraplength=850,padding=10).pack(fill='x')
        controls=ttk.Frame(win,padding=10);controls.pack(side='bottom',fill='x')
        body=create_scrolled_text(win,wrap='word');body.audit_container.pack(fill='both',expand=True,padx=10)
        p=ws.procedures[pid];draft=ws.ai_drafts[state['draft_id']]
        body.insert('1.0',pid+' · '+state['state']+'\n'+state['provider']+' / '+state['model']+'\n\n'+'\n\n'.join(FIELD_LABELS[k]+'\n'+p[k]+'\n생성 시 근거: '+', '.join(draft['citations'][k]) for k in FIELD_LABELS));body.configure(state='disabled')
        win.actor=tk.StringVar(value=self.ai_actor())
        ttk.Label(controls,text='승인자').grid(row=0,column=0,sticky='w');ttk.Entry(controls,textvariable=win.actor,width=22).grid(row=0,column=1,sticky='w')
        ttk.Label(controls,text='검토·수정·판단 기록').grid(row=1,column=0,sticky='nw');win.note=create_scrolled_text(controls,height=3,wrap='word');win.note.audit_container.grid(row=1,column=1,sticky='ew');controls.columnconfigure(1,weight=1)
        win.confirmed=tk.BooleanVar(value=False);ttk.Checkbutton(controls,text='근거·예외·미수행 사항과 최종 내용을 검토했습니다.',variable=win.confirmed).grid(row=2,column=0,columnspan=2,sticky='w',pady=8)
        def approve():
            self.guard()
            if not win.confirmed.get():raise AuditError('최종 내용 검토 확인을 선택하세요.')
            if self.ws is not ws or self.current_pid!=pid or self.dirty():raise AuditError('승인 화면을 연 뒤 조서가 변경됐습니다. 다시 확인하세요.')
            ws.refresh();current=ws.ai_status(pid)
            if any(current.get(k)!=state.get(k) for k in ('content_hash','basis','draft_id')) or ws.procedures[pid].get('edit_revision')!=p.get('edit_revision'):raise AuditError('승인 화면을 연 뒤 저장 내용·근거가 변경됐습니다. 다시 확인하세요.')
            ws.approve_ai_content(pid,win.actor.get(),win.note.get('1.0','end').strip());self.refresh();win.destroy();self.status.set('AI 최종 내용 승인 기록 저장. 별도 검토자는 검토 요청 후 검토기록을 남기세요.')
        win.approve_button=ttk.Button(controls,text='확인한 최종 내용 승인',command=lambda:self.call(approve));win.approve_button.grid(row=3,column=1,sticky='e')

    def open_ai_settings(self):
        if self.busy:raise AuditError('현재 작업이 끝난 뒤 설정하세요.')
        win=self.ai_window('AI 설정 · 로컬 기본 / OpenAI 선택',820,650);self.ai_settings_win=win
        footer=ttk.Frame(win,padding=10);footer.pack(side='bottom',fill='x');scroll=ScrollableFrame(win);scroll.pack(fill='both',expand=True);p=scroll.inner
        win.provider=tk.StringVar(value='로컬 AI (기본)' if self.ai_config['provider']=='ollama' else 'OpenAI API')
        ttk.Label(p,text='조서 생성 방식').pack(anchor='w');ttk.Combobox(p,textvariable=win.provider,values=['로컬 AI (기본)','OpenAI API'],state='readonly').pack(fill='x',pady=5)
        ttk.Label(p,text='로컬 모델: '+DEFAULT_MODEL+'\nCPU 기본 · 16,384 토큰 문맥 · 요청 제한 300초. 설치·모델은 EXE와 별도로 최초 준비합니다.',wraplength=730).pack(anchor='w',pady=8)
        win.runtime_root=tk.StringVar(value=str(self.ai_runtime.root));ttk.Label(p,text='전용 로컬 AI 폴더').pack(anchor='w');ttk.Entry(p,textvariable=win.runtime_root).pack(fill='x')
        def browse():
            selected=filedialog.askdirectory(parent=win,title='전용 로컬 AI 폴더')
            if selected:win.runtime_root.set(selected)
        ttk.Button(p,text='폴더 선택',command=browse).pack(anchor='w',pady=5)
        win.runtime_status=tk.StringVar(value='상태 확인을 누르세요. 최초 준비만 다운로드합니다.');ttk.Label(p,textvariable=win.runtime_status,wraplength=730).pack(fill='x',pady=8)
        def choose_runtime():
            root=Path(win.runtime_root.get()).resolve()
            if root!=self.ai_runtime.root.resolve():self.ai_runtime.stop();self.ai_runtime=LocalAIRuntime(root)
            self.ai_config['endpoint']=self.ai_runtime.base_url
        def status_complete(value):
            if win.winfo_exists():win.runtime_status.set(json.dumps(value,ensure_ascii=False,indent=2))
            self.status.set('로컬 AI 상태 확인 완료')
        def check():
            if self.busy:raise AuditError('현재 작업이 끝난 뒤 상태를 확인하세요.')
            choose_runtime();self.launch_ai_job(lambda:self.ai_runtime.status(),status_complete)
        def setup():
            if self.busy:raise AuditError('현재 작업이 끝난 뒤 준비하세요.')
            if not messagebox.askokcancel('로컬 AI 최초 준비','공식 Ollama 실행환경과 Qwen 모델 약 4GB를 다운로드합니다. 전용 폴더에 12GB 이상 여유 공간을 권장합니다. 준비할까요?',parent=win):return
            choose_runtime();self.launch_ai_job(lambda:self.ai_runtime.setup(event=self.cancel,progress=lambda s:self.queue.put(('status',s))),status_complete)
        line=ttk.Frame(p);line.pack(fill='x');win.check_button=ttk.Button(line,text='상태 확인',command=lambda:self.call(check));win.check_button.pack(side='left');win.setup_button=ttk.Button(line,text='로컬 AI 준비 (최초 1회)',command=lambda:self.call(setup));win.setup_button.pack(side='left',padx=8);ttk.Button(line,text='준비 취소',command=self.cancel.set).pack(side='left')
        ttk.Separator(p).pack(fill='x',pady=16);ttk.Label(p,text='선택: OpenAI API · 호출 비용 및 외부 전송 발생. 매 요청 전 근거 확인·동의 필요.',wraplength=730).pack(anchor='w')
        win.model=tk.StringVar(value=self.ai_openai_model);win.key=tk.StringVar(value=self.ai_api_key)
        ttk.Label(p,text='OpenAI 모델명 (사용 가능한 모델을 직접 지정)').pack(anchor='w');ttk.Entry(p,textvariable=win.model).pack(fill='x',pady=5)
        ttk.Label(p,text='API 키 (현재 실행 메모리에만 보관)').pack(anchor='w');win.key_entry=ttk.Entry(p,textvariable=win.key,show='●');win.key_entry.pack(fill='x',pady=5)
        def save():
            if self.busy:raise AuditError('준비 작업 완료 후 설정을 적용하세요.')
            choose_runtime();self.ai_config['provider']='ollama' if win.provider.get()=='로컬 AI (기본)' else 'openai';self.ai_openai_model=win.model.get().strip();self.ai_api_key=win.key.get().strip();win.key.set('');win.destroy();self.status.set('AI 설정 적용. 키·설정은 이번 실행에서만 사용합니다.')
        def close():
            if self.busy:self.cancel.set();self.status.set('AI 준비 취소 중…');return
            win.key.set('');win.destroy()
        win.save_button=ttk.Button(footer,text='설정 적용',command=lambda:self.call(save));win.save_button.pack(side='right');ttk.Button(footer,text='닫기',command=close).pack(side='right',padx=8);win.protocol('WM_DELETE_WINDOW',close)
        self.display.refresh_widgets()

    def shutdown_ai(self):
        self.ai_api_key=''
        win=getattr(self,'ai_settings_win',None)
        if win and win.winfo_exists():win.key.set('')
        self.ai_runtime.stop()
