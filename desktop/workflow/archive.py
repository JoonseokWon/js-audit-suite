"""ArchiveActions; method bodies preserved from the original UI contract."""
from .shared import *
from .dialog import WorkflowDialog


class ArchiveActions:
    def open_legacy_f01(self):
            d=WorkflowDialog(self,'이전 조서번호의 실제 절차 확인');self.wf_modal=d;self._wf_actor(d)
            d.note('이전 버전에서는 후속사건 검토와 재무제표 대사에 같은 조서번호 F01을 사용했습니다. 기존 조서가 어느 절차인지 내용을 확인한 뒤 선택하세요. 과거 조서와 검토 이력은 보존하고, 현재 조서는 각 절차에 맞게 새로 작성합니다.')
            info=d.ws.workflow_status().get('legacy_f01',{})
            d.note('이전 조서의 상세 기록: '+dumps(info))
            d.entry('purpose_code','기존 F01 조서에서 실제 수행한 절차','',['subsequent_events','financial_statement_reconciliation'])
            d.text('reason','분류 근거·확인한 기록',height=4)
            def save():
                def op():
                    result=d.ws.classify_legacy_f01(d.value('purpose_code'),d.value('actor'),d.value('reason'),expected_head=d.head)
                    self.current_pid=None;return result
                return d.save(op,'이전 조서의 절차 구분을 저장했어요. 과거 작성·검토 이력은 그대로 보존해요.')
            d.button('확인한 목적 분류 저장',save);d.finish();return d

    def workflow_lock_dialog(self,reopen=False):
            d=WorkflowDialog(self,'조서 수정 다시 시작' if reopen else '검토완료본 수정 제한');self.wf_modal=d;self._wf_actor(d)
            d.note('검토를 마친 조서와 자료가 임의로 바뀌지 않도록 수정을 제한해요. 다시 수정할 때는 사유를 남겨요. 이 기능은 프로그램에 저장된 기록을 보호하며 실제 감사의견을 확정하지 않아요.')
            d.text('reason','다시 수정하는 사유' if reopen else '수정을 제한하는 사유·검토한 범위',height=4)
            def save():
                fn=d.ws.reopen_workflow if reopen else d.ws.finalize_workflow
                return d.save(lambda:fn(d.value('actor'),d.value('reason'),expected_head=d.head),'다시 수정하는 사유를 기록했어요.' if reopen else '검토완료본의 수정을 제한했어요. 감사파일을 저장할 수 있어요.')
            d.button('사유를 남기고 수정 시작' if reopen else '검토완료본 수정 제한',save);d.finish();return d

    def _wf_background(self,operation,message):
            self.guard();self.set_busy(True);self.sector_cancel.configure(state='disabled');self.status.set(message)
            def work():
                try:self.queue.put(('workflow_ok',operation()))
                except Exception as exc:self.queue.put(('workflow_error',str(exc)))
            threading.Thread(target=work,daemon=False).start()

    def finish_workflow_job(self,kind,data):
            self.set_busy(False)
            if kind=='workflow_error':self.status.set('감사파일 저장·확인 중 보완할 사항이 있어요: '+data)
            else:
                self.wf_last_archive=data
                self.status.set('감사파일 확인: '+str(data.get('path',''))+' / 원본자료 '+str(data.get('source_count',''))+'개')
                self.wf_detail.configure(state='normal');self.wf_detail.delete('1.0','end')
                self.wf_detail.insert('1.0','저장 파일의 상세 확인 결과\n'+json.dumps(data,ensure_ascii=False,indent=2))
                self.wf_detail.configure(state='disabled')
            # Creating/verifying a ZIP does not change workspace events. Keep any
            # current workpaper/request edits instead of reloading their widgets.
            self.refresh_workflow()

    def workflow_archive_dialog(self,final=False):
            self.guard()
            if not self.check_navigation():return
            ws=self.ws
            if final and not ws.workflow_status()['locked']:raise AuditError('조서 검토를 마친 뒤 검토완료본 수정 제한을 먼저 설정하세요.')
            path=filedialog.asksaveasfilename(parent=self.root,title='감사파일을 새 ZIP으로 저장',defaultextension='.zip',
                initialfile='감사파일_검토완료.zip' if final else '감사파일_검토중.zip',filetypes=[('감사파일 ZIP','*.zip')])
            if not path:return
            from audit_archive import create_archive
            self._wf_background(lambda:create_archive(ws,path,ws.engagement['작성자'],final=final),'원본자료·조서·작성 및 검토 이력을 같은 시점의 감사파일로 저장하고 있어요…')

    def workflow_verify_dialog(self):
            self.guard()
            if not self.check_navigation():return
            path=filedialog.askopenfilename(parent=self.root,title='확인할 감사파일 선택',filetypes=[('감사파일 ZIP','*.zip')])
            if not path:return
            from audit_archive import verify_archive
            self._wf_background(lambda:verify_archive(path),'저장한 자료와 조서·이력이 서로 일치하고 변경되지 않았는지 확인하고 있어요…')
