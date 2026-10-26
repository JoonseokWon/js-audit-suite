"""AIState; method bodies preserved from the original UI contract."""
from .shared import *


class AIState:
    def init_ai(self,catalog):
            self.ai_catalog=catalog; self.ai_runtime=LocalAIRuntime()
            self.ai_config={'provider':'ollama','model':DEFAULT_MODEL,'endpoint':self.ai_runtime.base_url,'num_gpu':0,'num_ctx':16384,'timeout_seconds':300}
            self.ai_api_key=''; self.ai_openai_model=''; self.ai_job_complete=None
            self.ai_state=tk.StringVar(value='AI 초안 → 근거 확인 → 사람 수정·저장 → 최종 내용 승인')
            self.ai_elapsed=tk.StringVar(value='');self._ai_elapsed_timer=None;self._ai_job_started=None

    def build_ai_actions(self,parent,flow):
            bar=flow(parent);bar.pack(fill='x',pady=(0,5));self.ai_actions=bar
            from .evidence import open_current_evidence
            for attr,label,fn in [('ai_evidence_button','생성 근거 보기',lambda:open_current_evidence(self)),('ai_generate_button','AI 초안 생성',self.start_ai_generation),('ai_preview_button','초안 보기·적용',self.open_ai_preview),('ai_approve_button','AI 내용 최종 승인',self.open_ai_approval),('ai_settings_button','AI 설정',self.open_ai_settings)]:
                setattr(self,attr,bar.add(ttk.Button(bar,text=label,command=lambda f=fn:self.call(f))))
            status=bar.add(ttk.Label(bar,textvariable=self.ai_state));status.flow_secondary=True
            self.ai_elapsed_label=bar.add(ttk.Label(bar,textvariable=self.ai_elapsed,style='Muted.TLabel'))

    def refresh_ai_status(self):
            message='AI 초안 → 근거 확인 → 사람 수정·저장 → 최종 내용 승인'
            if self.ws and self.current_pid:
                state=self.ws.ai_status(self.current_pid);message=state['state']
                draft=self.ws.ai_drafts.get(state.get('draft_id'))
                if draft and draft.get('basis')!=self.ws.basis():
                    message='근거 변경 · AI 초안을 다시 생성하고 사람이 확인하세요.'
            self.ai_state.set(message)

    def ai_actor(self):
            from desktop.demo.context import default_preparer
            return self.proc_vars['preparer'].get().strip() or default_preparer(self.ws)

    def ai_clean_form(self):
            self.guard();self.open_workpaper_draft()
            if self.dirty():
                choice=messagebox.askyesnocancel('작성 내용 보존','현재 수정 내용을 저장할까요? 아니오를 선택하면 마지막 저장 내용으로 되돌립니다.',parent=self.root)
                if choice is None:return False
                if choice:self.save_procedure()
                else:self.load_procedure(self.current_pid)
            return True

    def shutdown_ai(self):
            self.stop_ai_elapsed()
            self.ai_api_key=''
            win=getattr(self,'ai_settings_win',None)
            if win and win.winfo_exists():win.key.set('')
            self.ai_runtime.stop()
