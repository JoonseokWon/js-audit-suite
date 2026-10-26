"""AIJobs; method bodies preserved from the original UI contract."""
from .shared import *


class AIJobs:
    def launch_ai_job(self,work,complete):
            if self.busy:raise AuditError('현재 작업이 끝난 뒤 실행하세요.')
            self.cancel.clear();self.ai_job_complete=complete;self.set_busy(True)
            self.start_ai_elapsed()
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
            self.stop_ai_elapsed()
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
