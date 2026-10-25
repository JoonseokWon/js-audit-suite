"""AISettings; method bodies preserved from the original UI contract."""
from .shared import *


class AISettings:
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
