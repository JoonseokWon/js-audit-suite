"""Execution native desktop actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill

class ExecutionActions:

    def choose_input(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[('감사 입력자료', '*.xlsx *.json *.auditpack'), ('Excel 확정값', '*.xlsx'), ('재무제표·증빙 JSON', '*.json'), ('원천증빙 패키지', '*.auditpack')])
        if path:
            self.file.set(path)

    def run_selected(self):
        self.guard()
        if not self.check_draft():
            return
        if not Path(self.file.get()).is_file():
            raise AuditError('현재 모듈의 입력 파일을 선택하세요.')
        self.launch([(self.module.get(), Path(self.file.get()))])

    def launch(self, items):
        self.guard()
        self.set_busy(True)
        self.cancel.clear()
        self.status.set('자료 등록·검사 중…')
        ws = self.ws
        selected=list(items)

        def worker():
            from desktop.actions.execution_status import run_batch
            run_batch(ws,selected,self.cancel,lambda kind,data:self.queue.put((kind,data)))
        threading.Thread(target=worker, daemon=False).start()

    def poll(self):
        self._poll_timer = None
        try:
            while True:
                kind, data = self.queue.get_nowait()
                if kind == 'status':
                    self.status.set(data)
                elif kind == 'run':
                    pass
                elif kind == 'batch_done':
                    from desktop.actions.execution_status import batch_message
                    self.set_busy(False);self.last_batch_result=data
                    self.status.set(batch_message(data));self.call(self.refresh)
                    if self.closing:
                        self.shutdown_ai();self.root.destroy();return
                elif kind in ('ai_ok', 'ai_error'):
                    self.finish_ai_job(kind, data)
                    if self.closing:
                        return
                elif kind in ('workflow_ok', 'workflow_error'):
                    self.finish_workflow_job(kind, data)
                    if self.closing:
                        self.shutdown_ai()
                        self.root.destroy()
                        return
                elif kind in ('sector_ready', 'sector_error'):
                    self.set_busy(False)
                    if kind == 'sector_ready':
                        try:
                            ws = Workspace(data['folder'])
                            self.ws = ws
                            self.reset_workspace_view()
                            self.active_sector = data['company_code']
                            self.sector_selection()
                            self.refresh()
                            c = next((c for c in self.sector_options if c['code'] == self.active_sector))
                            self.sector_description.set('모회사 · 연결재무제표 / 현재 예제는 자체 원장이에요' if c.get('kind') == 'parent' else c['sector'] + ' / 자회사 별도 재무제표 · 예제 자료')
                            self.status.set('저장된 회사의 예제 업무를 열었어요.' if data['reused'] else '모회사 예제 원장과 조서 초안을 준비했어요. 연결조정은 별도 확인이 필요해요.' if c.get('kind') == 'parent' else '가상 회사의 예제 자료를 불러왔어요. 대사 결과와 조서의 실제 수행·판단을 확인하세요.')
                        except Exception as e:
                            self.sector_selection()
                            self.status.set('업무 열기 오류: ' + str(e))
                    else:
                        self.sector_selection()
                        self.status.set('회사 준비 중단: ' + data)
                    if self.closing:
                        self.shutdown_ai()
                        self.root.destroy()
                        return
                else:
                    self.set_busy(False)
                    if kind == 'error':
                        self.status.set('실행 오류: ' + data)
                    else:
                        self.status.set('검사 종료 알림을 받았어요. 실행 건수가 없어 완료 여부는 검사 실행 현황에서 확인하세요.')
                    self.call(self.refresh)
                    if self.closing:
                        self.shutdown_ai()
                        self.root.destroy()
                        return
        except queue.Empty:
            pass
        self._poll_timer = self.root.after(80, self.poll)
