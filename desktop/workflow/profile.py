"""ProfileActions; method bodies preserved from the original UI contract."""
from .shared import *
from .dialog import WorkflowDialog


class ProfileActions:
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
