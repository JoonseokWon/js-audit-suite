"""AIDialogs; method bodies preserved from the original UI contract."""
from .shared import *
from .evidence import build_evidence_frame,wrapping_label
from export_support.text import display_text


class AIDialogs:
    def ai_window(self,title,width=960,height=700):
            win=tk.Toplevel(self.root);win.title(title);win.transient(self.root)
            win.audit_display=getattr(self,'display',None)
            px=self.display.px if hasattr(self,'display') else int
            available_w=max(320,self.root.winfo_screenwidth()-80)
            available_h=max(320,self.root.winfo_screenheight()-130)
            win.geometry(f'{min(px(width),available_w)}x{min(px(height),available_h)}')
            win.minsize(min(px(520),available_w),min(px(380),available_h));return win

    def open_external_consent(self,packet,send):
            win=self.ai_window('OpenAI로 전송할 근거 확인');self.ai_consent_win=win
            wrapping_label(win,text='아래 선택된 원문 발췌·대사·예외·현재 조서가 OpenAI API로 전송됩니다. 실제 데이터의 외부 전송 권한을 확인하세요.',padding=10).pack(fill='x')
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
            wrapping_label(win,text=f"{draft['procedure_id']} · {draft['provider']} / {draft['model']}\n프로그램 근거 기록과 미검증 모델 제안을 구분해 보여줘요. 실제 수행·판단은 사람이 확인·작성하세요.",padding=10).pack(fill='x')
            footer=ttk.Frame(win);footer.pack(side='bottom',fill='x')
            nb=ttk.Notebook(win);nb.pack(fill='both',expand=True,padx=10)
            from .draft_sections import sections
            for label,content in sections(draft,FIELD_LABELS):
                frame=ttk.Frame(nb);nb.add(frame,text=label);text=create_scrolled_text(frame,wrap='word');text.audit_container.pack(fill='both',expand=True);text.insert('1.0',content);text.configure(state='disabled')
            evidence=build_evidence_frame(nb,draft['packet']);nb.add(evidence,text='원본·대사 근거')
            from .inventory import build_inventory_frame
            inventory=build_inventory_frame(nb,draft['packet']);nb.add(inventory,text='계산표 포함·생략 범위')
            win.inventory_body=inventory
            frame=ttk.Frame(nb);nb.add(frame,text='전체 근거 JSON')
            text=create_scrolled_text(frame,wrap='word');text.audit_container.pack(fill='both',expand=True)
            text.insert('1.0',json.dumps(draft['packet'],ensure_ascii=False,indent=2));text.configure(state='disabled')
            win.evidence_body=evidence
            def apply():
                if self.ws is not captured_ws:raise AuditError('초안 화면을 연 뒤 업무가 변경됐습니다. 현재 업무에서 다시 여세요.')
                if self.current_pid!=draft['procedure_id']:raise AuditError('이 초안의 원래 조서를 선택하세요.')
                if not self.ai_clean_form():return
                self.ws.apply_ai_draft(draft_id,self.ai_actor());self.refresh();win.destroy();self.status.set('프로그램 근거 기록만 적용했어요. 모델 자유서술은 자동 적용하지 않았어요. 실제 수행·판단은 직접 작성·저장하고 내용을 승인하세요.')
            ttk.Button(footer,text='닫기',command=win.destroy).pack(side='right',padx=10,pady=10)
            win.apply_button=ttk.Button(footer,text='현재 조서에 적용',command=lambda:self.call(apply));win.apply_button.pack(side='right',padx=5,pady=10)
            if draft.get('contract_version')!='ai-structured-2':win.apply_button.configure(state='disabled')
            else:win.apply_button.configure(text='프로그램 근거만 조서에 적용')

    def open_ai_approval(self):
            if not self.ai_clean_form():return
            ws=self.ws;pid=self.current_pid;state=ws.ai_status(pid)
            if not state['required']:raise AuditError('AI 초안을 적용한 후 최종 내용을 승인하세요.')
            if ws.ai_drafts[state['draft_id']].get('contract_version')!='ai-structured-2':
                raise AuditError('이전 형식의 AI 초안은 조회만 가능해요. 현재 근거로 새 구조화 초안을 생성하세요.')
            if ws.ai_drafts[state['draft_id']]['basis']!=ws.basis():
                raise AuditError('근거 자료·검사 결과가 바뀌었어요. 새 AI 초안을 생성·적용하고 사람이 내용을 확인하세요.')
            win=self.ai_window('AI 내용 최종 승인');self.ai_approval_win=win
            wrapping_label(win,text='사람이 수정·저장한 현재 내용과 근거 버전을 승인합니다. 별도 검토자의 검토기록과 전체 감사 완료를 대신하지 않습니다.',padding=10).pack(fill='x')
            controls=ttk.Frame(win,padding=10);controls.pack(side='bottom',fill='x')
            body=create_scrolled_text(win,wrap='word');body.audit_container.pack(fill='both',expand=True,padx=10)
            p=ws.procedures[pid];draft=ws.ai_drafts[state['draft_id']]
            citations=draft.get('verified_citations',draft.get('citations',{}))
            body.insert('1.0',display_text(pid+' · '+state['state']+'\n'+state['provider']+' / '+state['model']+'\n\n'+'\n\n'.join(FIELD_LABELS[k]+'\n'+p[k]+'\n검증된 적용 근거: '+', '.join(citations.get(k,[])) for k in FIELD_LABELS)));body.configure(state='disabled')
            win.actor=tk.StringVar(value=self.ai_actor())
            ttk.Label(controls,text='승인자').grid(row=0,column=0,sticky='w');ttk.Entry(controls,textvariable=win.actor,width=22).grid(row=0,column=1,sticky='w')
            ttk.Label(controls,text='검토·수정·판단 기록').grid(row=1,column=0,sticky='nw');win.note=create_editable_text(controls,height=3,wrap='word');win.note.audit_container.grid(row=1,column=1,sticky='ew');controls.columnconfigure(1,weight=1)
            win.confirmed=tk.BooleanVar(value=False);ttk.Checkbutton(controls,text='근거·예외·미수행 사항과 최종 내용을 검토했습니다.',variable=win.confirmed).grid(row=2,column=0,columnspan=2,sticky='w',pady=8)
            def approve():
                self.guard()
                if not win.confirmed.get():raise AuditError('최종 내용 검토 확인을 선택하세요.')
                if self.ws is not ws or self.current_pid!=pid or self.dirty():raise AuditError('승인 화면을 연 뒤 조서가 변경됐습니다. 다시 확인하세요.')
                ws.refresh();current=ws.ai_status(pid)
                if any(current.get(k)!=state.get(k) for k in ('content_hash','basis','draft_id')) or ws.procedures[pid].get('edit_revision')!=p.get('edit_revision'):raise AuditError('승인 화면을 연 뒤 저장 내용·근거가 변경됐습니다. 다시 확인하세요.')
                ws.approve_ai_content(pid,win.actor.get(),win.note.get('1.0','end').strip());self.refresh();win.destroy();self.status.set('AI 최종 내용 승인 기록 저장. 별도 검토자는 검토 요청 후 검토기록을 남기세요.')
            win.approve_button=ttk.Button(controls,text='확인한 최종 내용 승인',command=lambda:self.call(approve));win.approve_button.grid(row=3,column=1,sticky='e')
