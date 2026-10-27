"""WorkflowView; method bodies preserved from the original UI contract."""
from .shared import *
from .dialog import WorkflowDialog


class WorkflowView:
    def build_workflow(self,parent,flow_type):
            self.wf_summary=tk.StringVar(value='업무를 연 뒤 감사계획을 저장하면 절차 연결 기능이 활성화됩니다.')
            self.wf_profile_summary=tk.StringVar(value='계획 미설정 · 적용 기준과 비율은 직접 결정하세요.')
            self.wf_last_archive={};self.wf_state={};self.wf_modal=None
            ttk.Label(parent,textvariable=self.wf_summary,wraplength=1150).pack(anchor='w',fill='x',pady=5)
            ttk.Label(parent,textvariable=self.wf_profile_summary,wraplength=1150).pack(anchor='w',fill='x',pady=5)
            ttk.Label(parent,text='감사계획 수립 및 위험평가').pack(anchor='w',pady=(10,2))
            bar=flow_type(parent);bar.pack(fill='x')
            for label,action in [('감사계획·중요성',self.open_workflow_profile),('감사위험 추가',lambda:self.open_workflow_risk(new=True)),
                                 ('선택 위험 수정',self.open_workflow_risk),('새 절차 연결',lambda:self.open_workflow_procedure(new=True)),
                                 ('선택 절차 연결 수정',self.open_workflow_procedure),('이전 조서번호 확인',self.open_legacy_f01),
                                 ('위험·절차 연결',self.open_audit_links),('왜곡표시 집계',self.open_misstatements),
                                 ('상태 새로고침',self.refresh_workflow)]:
                bar.add(ttk.Button(bar,text=label,command=lambda f=action:self.call(f)))
            ttk.Label(parent,text='검토완료본 수정 제한 및 감사파일 보관').pack(anchor='w',pady=(10,2))
            archives=flow_type(parent);archives.pack(fill='x')
            for label,action in [('검토중 감사파일 저장',lambda:self.workflow_archive_dialog(False)),
                                 ('검토완료본 수정 제한',lambda:self.workflow_lock_dialog(False)),
                                 ('검토완료 감사파일 저장',lambda:self.workflow_archive_dialog(True)),
                                 ('조서 수정 다시 시작',lambda:self.workflow_lock_dialog(True)),('저장 파일 확인',self.workflow_verify_dialog)]:
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
            self.wf_summary.set(('감사계획 입력함' if state['active'] else '감사계획 입력 전')+
                                (' · 검토완료본 수정 제한 중' if state['locked'] else ' · 작성·수정 가능')+
                                f" · 보완 필요 {len(state['blockers'])}건 (수행·검토 기록 미완료 {len(state['human_pending'])}건 포함)")
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
