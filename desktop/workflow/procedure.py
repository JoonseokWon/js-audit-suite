"""ProcedureActions; method bodies preserved from the original UI contract."""
from .shared import *
from .dialog import WorkflowDialog


class ProcedureActions:
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
