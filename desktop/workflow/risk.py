"""RiskActions; method bodies preserved from the original UI contract."""
from .shared import *
from .dialog import WorkflowDialog


class RiskActions:
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
