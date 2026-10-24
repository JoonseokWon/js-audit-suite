"""Single native desktop engagement, calculation, evidence and workpaper application."""
import runtime
RESOURCE=runtime.configure()
runtime.configure_tk_libraries()
from desktop_display import enable_dpi_awareness
runtime.DPI_STATUS=enable_dpi_awareness()
from pathlib import Path
import json,sys,threading,queue,traceback,shutil
from datetime import datetime,timezone,timedelta
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog
from common import AuditError,dumps,digest
from workspace import Workspace
from adapters import MODULES
from display_schema import TABLE_COLUMNS,MODULE_TABLES
import exporter
from desktop_display import DisplayManager,ScrollableFrame,create_scrolled_text,create_editable_text
from ai_desktop import AIDesktopMixin

TITLE='JS 통합 회계감사 v1.8.1'
def resource(*parts):return RESOURCE.joinpath(*parts)
def display_time(value):return datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S KST')
CATALOG=json.loads(resource('procedure_catalog.json').read_text(encoding='utf-8'))
LIMITS={'원장·리드':'전체 계정 독립 통제·전표별 차대·조정 전후 리드. KRW 확정값, 최대 10,000행/시트.','금융상품':'기존 v2.1 단순이자·명세/원장/회신 대사. 회사는 현재 업무에 수동 귀속합니다.','매출':'기존 v2.1 주문·납품·청구·원장 대사. IFRS15 통제이전 판단은 별도 절차.','감가상각':'기존 v1.1 원가모형·유한내용연수·월할. 손상·재평가 등은 별도 절차.','확장검사':'은행 정확 1:1·채권연령/후속회수·매입 수치·기준일 재고수량. ECL·NRV·조회/입회 결론은 별도.'}
LIMITS.update({'리스':'고정 월납 임차인: 월별 현재가치·부채/사용권 롤포워드·유동분류. 변경/옵션/손상/외화는 미지원.','대손충당금':'유의적 금융요소 없는 매출채권: 전체기간 ECL 충당률표·전망 시나리오·개별평가·변동 대사. 손실률 근거는 별도 검토.'})
LIMITS.update({'재고평가':'확정 원가단가×수량·품목/로트별 NRV·평가손실/환입·원장 변동 대사. 원가 배부·실사 판단은 별도.','종업원급여':'달력일 월급·승인 수당/공제·지급·미지급·단기 누적연차·약정 DC. 세액/최저요율/DB/퇴직정산은 미지원.'})
LIMITS.update({'미기록부채·비용이연':'확정 KRW 용역: 후속송장·지급 귀속검색, 미지급 및 1회 전액지급 선급의 일할/월할 배분. 부가세·외화·재고/자산취득·환불/변경·추정충당은 별도.'})
DEMO_FILES=[('원장·리드', '통합_v1.3_원장_리드.xlsx'), ('금융상품', '통합_v1.3_금융상품.xlsx'), ('매출', '통합_v1.3_매출.xlsx'), ('감가상각', '통합_v1.3_감가상각.xlsx'), ('확장검사', '통합_v1.3_확장검사.xlsx'), ('리스', '통합_v1.3_리스.xlsx'), ('대손충당금', '통합_v1.3_대손충당금.xlsx'), ('재고평가', '통합_v1.3_재고평가.xlsx'), ('종업원급여', '통합_v1.3_종업원급여.xlsx'), ('미기록부채·비용이연', '비용이연_01_정상.xlsx')]
FULL_DEMO_FILES=DEMO_FILES+[('원천증빙','통합_v1.4_원천증빙.auditpack'),('재무제표·주석','통합_v1.4_재무제표.json')]
ANALYTIC_DEMO_FILES=FULL_DEMO_FILES+[('GLA','통합_v1.5_GLA.xlsx'),('FIA','통합_v1.5_FIA.xlsx'),('현금분석','통합_v1.5_현금분석.xlsx')]
LIMITS.update({'GLA':'현재 원장 7시트 대사 후 월·계정·작성자·복합 전표 분석. 규칙 후보와 원문·후속절차. 부정 확정 아님.',
 'FIA':'명시적 입력/승인 메타와 마감·업무시간 정책으로 분석. 없는 정보를 추정하지 않으며 미확인 규칙을 표시.',
 '현금분석':'선택 계좌의 은행 독립통제·잔액·명시적 배부·지급근거와 변경 이력 분석. 계좌 모집단과 실제 증거 진위는 별도 확인.'})
LIMITS.update({'원천증빙':'원본 엑셀·해시·행을 고정한 증빙팩. 선택한 거래의 다대다 배부와 현재 업무 원장을 대조합니다. 선택 범위 밖 완전성·증거 진위 판단은 별도입니다.',
 '재무제표·주석':'현재 업무의 조정전·미마감 TB와 합계·본문·선택 주석 대사. 입력은 확정 financial.json이며 PDF·OCR 추출은 없습니다.',
 '계정별증빙연습':'9개 계정군의 33개 독립 합성 사례를 원문에서 재계산합니다. 현재 업무 TB에 합산하지 않는 연습용이며 검토중 조서만 출력합니다.'})

def tree(parent,columns,height=12):
    frame=ttk.Frame(parent);frame.pack(fill='both',expand=True)
    t=ttk.Treeview(frame,columns=columns,show='headings',height=height,selectmode='browse')
    for c in columns:t.heading(c,text=c);t.column(c,width=145,stretch=False)
    sy=ttk.Scrollbar(frame,orient='vertical',command=t.yview);sx=ttk.Scrollbar(frame,orient='horizontal',command=t.xview);t.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
    t.grid(row=0,column=0,sticky='nsew');sy.grid(row=0,column=1,sticky='ns');sx.grid(row=1,column=0,sticky='ew');frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
    return t
def fill(t,rows,columns=None):
    t.delete(*t.get_children())
    if columns:
        t.configure(columns=columns)
        for c in columns:t.heading(c,text=c);t.column(c,width=170,stretch=False)
        manager=getattr(t.winfo_toplevel(),'audit_display',None)
        if manager:manager.register_tree(t,{c:170 for c in columns})
    cs=t['columns']
    for i,r in enumerate(rows):t.insert('', 'end',iid=str(i),values=[str(r.get(k,'')) if r.get(k) is not None else '미확인' for k in cs])

class FlowFrame(ttk.Frame):
    """Keep primary actions reachable when the window or text scale changes."""
    def __init__(self,parent,**kw):
        super().__init__(parent,**kw);self.items=[];self.pending=None;self.layout=None
        self.bind('<Configure>',lambda _:self.schedule())
        self.bind('<Destroy>',self.cleanup,add='+')
    def add(self,widget):
        self.items.append(widget);self.schedule();return widget
    def schedule(self):
        if self.pending is None:self.pending=self._root().after_idle(self.reflow)
    def cleanup(self,event):
        if event.widget is self and self.pending is not None:
            try:self._root().after_cancel(self.pending)
            except tk.TclError:pass
            self.pending=None
    def reflow(self):
        self.pending=None
        if self.winfo_width()<100:
            self.pending=self._root().after(30,self.reflow);return
        width=max(120,self.winfo_width()-20);x=0;y=4;row_height=0;positions=[]
        ordinary=[w for w in self.items if not getattr(w,'flow_compact_only',False)]
        compact=sum(w.winfo_reqwidth()+8 for w in ordinary)>width
        visible=[w for w in self.items if (not getattr(w,'flow_secondary',False) if compact else not getattr(w,'flow_compact_only',False))]
        for widget in self.items:
            if widget not in visible:widget.place_forget()
        for widget in visible:
            if isinstance(widget,ttk.Label):widget.configure(wraplength=max(100,width-12))
            w=min(width,widget.winfo_reqwidth());h=widget.winfo_reqheight();needed=w+8
            if x and x+needed>width:y+=row_height+5;x=0;row_height=0
            positions.append((widget,x+8,y,w,h));x+=needed;row_height=max(row_height,h)
        layout=tuple((str(w),x,y,width,height) for w,x,y,width,height in positions)
        if layout!=self.layout:
            for w,x,y,width,height in positions:w.place(x=x,y=y,width=width,height=height)
            self.configure(height=y+row_height+5)
            self.layout=layout

class App(AIDesktopMixin):
    def __init__(self,root,sector_home=None):
        self.root=root;root.title(TITLE);ttk.Style(root).theme_use('clam');self.display=DisplayManager(root,scale=100);root.audit_display=self.display
        if sys.platform=='win32':root.iconbitmap(default=str(resource('assets','js-audit.ico')))
        style=ttk.Style(root);style.configure('Primary.TButton',background='#2458a6',foreground='white');style.map('Primary.TButton',background=[('active','#194684')])
        self.ws=None;self.busy=False;self.cancel=threading.Event();self.queue=queue.Queue();self.current_pid=None;self.table_rows=[];self.page=0;self.closing=False
        self.init_ai(CATALOG)
        bar=FlowFrame(root,padding=(10,5));bar.pack(fill='x');self.toolbar=bar
        self.workpaper_button=bar.add(ttk.Button(bar,text='조서초안 작성',style='Primary.TButton',command=lambda:self.call(self.open_workpaper_draft)))
        secondary_actions=[]
        for label,command in [('새 업무',self.new_dialog),('업무 열기',self.open_dialog),('계정별 증빙연습',self.case_dialog),('로우데이터',lambda:self.call(self.open_raw_data)),('자료 복사',self.copy_templates),('초안 Excel 내보내기',lambda:self.export_dialog(False)),('검토완료본',lambda:self.export_dialog(True))]:
            button=bar.add(ttk.Button(bar,text=label,command=command))
            if label=='초안 Excel 내보내기':self.draft_export_button=button
            else:button.flow_secondary=True;secondary_actions.append((label,command))
        zoom_frame=ttk.Frame(bar);bar.add(zoom_frame);ttk.Label(zoom_frame,text='화면 배율').pack(side='left',padx=(8,4));self.ui_zoom=tk.StringVar(value='100%')
        self.zoom_box=ttk.Combobox(zoom_frame,textvariable=self.ui_zoom,values=['90%','100%','110%','125%','150%','175%'],state='readonly',width=6);self.zoom_box.pack(side='left');self.zoom_box.bind('<<ComboboxSelected>>',lambda _:self.call(lambda:self.set_ui_zoom(int(self.ui_zoom.get().rstrip('%')))))
        self.more_button=bar.add(ttk.Menubutton(bar,text='기타 기능 ▾'));self.more_button.flow_compact_only=True;self.more_menu=tk.Menu(self.more_button,tearoff=False);self.more_button.configure(menu=self.more_menu)
        for label,command in secondary_actions:self.more_menu.add_command(label=label,command=command)
        self.more_menu.add_command(label='AI 설정',command=lambda:self.call(self.open_ai_settings))
        from sector_demo import list_companies,default_storage_root
        self.sector_home=Path(sector_home) if sector_home is not None else default_storage_root()
        self.active_sector=None;self.sector_options=list_companies(resource('sector_resources'))
        line=FlowFrame(root,padding=(10,0,10,2));line.pack(fill='x');self.company_bar=line
        line.add(ttk.Label(line,text='모회사·자회사'));self.sector_name=tk.StringVar(value='회사를 선택하세요')
        self.sector_box=ttk.Combobox(line,textvariable=self.sector_name,values=[c['name'] for c in self.sector_options],state='readonly',width=18);line.add(self.sector_box)
        self.sector_box.bind('<<ComboboxSelected>>',lambda _:self.call(lambda:self.select_sector(self.sector_options[self.sector_box.current()]['code'])))
        self.sector_new=ttk.Button(line,text='새 연습',command=lambda:self.call(self.new_sector));line.add(self.sector_new)
        self.sector_cancel=ttk.Button(line,text='준비 취소',command=self.cancel.set,state='disabled');line.add(self.sector_cancel)
        self.sector_description=tk.StringVar(value='JS는 업종 없는 모회사, 4개 자회사는 업종별 별도 합성업무입니다.');description=line.add(ttk.Label(line,textvariable=self.sector_description));description.flow_secondary=True
        self.info=tk.StringVar(value='회사를 선택하거나 업무를 연 뒤 조서초안 작성을 누르세요.');self.info_label=ttk.Label(root,textvariable=self.info,padding=(14,4));self.info_label.pack(fill='x')
        self.status=tk.StringVar(value='준비');ttk.Label(root,textvariable=self.status,padding=(14,3)).pack(side='bottom',fill='x')
        self.nb=ttk.Notebook(root);self.nb.pack(fill='both',expand=True,padx=10,pady=5)
        tabs={name:ttk.Frame(self.nb,padding=10) for name in ('자료·검사','원장·리드','결과 상세','검토후보','절차·조서','증거·검토의견','자료요청','작업 이력')}
        for name,frame in tabs.items():self.nb.add(frame,text='조서초안·작성' if name=='절차·조서' else name)
        navigation=tk.Menu(self.more_menu,tearoff=False)
        for name,frame in tabs.items():navigation.add_command(label='조서초안·작성' if name=='절차·조서' else name,command=lambda tab=frame:self.nb.select(tab))
        self.more_menu.add_separator();self.more_menu.add_cascade(label='화면 이동',menu=navigation)
        self.tabs=tabs;self.tab_scrolls={};contents={}
        for name,frame in tabs.items():
            if name=='절차·조서':contents[name]=frame
            else:
                scroll=ScrollableFrame(frame);scroll.pack(fill='both',expand=True);self.tab_scrolls[name]=scroll;contents[name]=scroll.inner
        self.build_inputs(contents['자료·검사']);self.build_lead(contents['원장·리드']);self.build_results(contents['결과 상세']);self.build_risks(contents['검토후보']);self.build_procedures(contents['절차·조서']);self.build_evidence(contents['증거·검토의견']);self.build_requests(contents['자료요청']);self.build_history(contents['작업 이력'])
        self.request_saved=self.request_signature();self.review_saved=('', '')
        self.display.refresh_widgets();self.display.fit_window(initial=True)
        def wrap_labels(parent):
            for widget in parent.winfo_children():
                if isinstance(widget,ttk.Label) and widget.cget('wraplength'):
                    parent.bind('<Configure>',lambda e,w=widget:w.configure(wraplength=max(100,e.width-16)),add='+')
                wrap_labels(widget)
        wrap_labels(self.nb)
        root.bind('<<AuditDisplayChanged>>',lambda _:self.reflow_display(),add='+')
        root.bind('<Control-plus>',lambda _:self.step_ui_zoom(1));root.bind('<Control-equal>',lambda _:self.step_ui_zoom(1));root.bind('<Control-minus>',lambda _:self.step_ui_zoom(-1));root.bind('<Control-Key-0>',lambda _:self.set_ui_zoom(100))
        root.protocol('WM_DELETE_WINDOW',self.close);root.after(80,self.poll)
    def reflow_display(self):
        def walk(parent):
            for widget in parent.winfo_children():
                if isinstance(widget,FlowFrame):widget.schedule()
                walk(widget)
        walk(self.root)
        for scroll in self.tab_scrolls.values():scroll.refresh()
        if hasattr(self,'proc_scroll'):self.proc_scroll.refresh()
    def set_ui_zoom(self,scale):
        self.display.apply(scale=int(scale));self.ui_zoom.set(str(int(scale))+'%');self.reflow_display()
        self.status.set('화면 배율 '+str(int(scale))+'% · Ctrl + / - 로 조절, Ctrl + 0 기본 배율');return 'break'
    def step_ui_zoom(self,step):
        choices=[90,100,110,125,150,175];current=int(self.ui_zoom.get().rstrip('%'));index=choices.index(current)
        return self.set_ui_zoom(choices[max(0,min(len(choices)-1,index+step))])
    def open_workpaper_draft(self):
        if not self.ws:raise AuditError('먼저 모회사·자회사를 선택하거나 업무를 여세요. 이후 계정별 조서 초안을 작성할 수 있습니다.')
        self.guard();self.nb.select(self.tabs['절차·조서'])
        if self.current_pid:
            self.status.set('작성 중인 조서를 유지합니다. 저장·개정 후 초안 Excel로 내보내세요.');return self.current_pid
        from common import PROCEDURE_MODULES
        preferred=next((pid for pid,module in PROCEDURE_MODULES.items() if module==self.result_module.get()),'C04')
        if preferred not in {t['id'] for t in self.tasks}:preferred='C04'
        self.load_procedure(preferred)
        index=next(i for i,t in enumerate(self.tasks) if t['id']==preferred);self.proc_tree.selection_set(str(index));self.proc_tree.see(str(index))
        self.status.set('계정별 초안: 목적·범위·계산 근거를 확인하고 실제 수행·판단을 입력한 뒤 조서 저장·개정을 누르세요.');return preferred
    def sector_selection(self):
        self.sector_name.set(next((c['name'] for c in self.sector_options if c['code']==self.active_sector),'회사를 선택하세요'))
        if self.active_sector is None:self.sector_description.set('수동 업무 · 회사명·범위는 현재 업무 정보를 확인하세요.')
    def new_sector(self):
        chosen=next((c['code'] for c in self.sector_options if c['name']==self.sector_name.get()),None)
        if chosen is None:raise AuditError('먼저 모회사 또는 자회사를 선택하세요.')
        return self.select_sector(chosen,fresh=True)
    def select_sector(self,code,fresh=False):
        if self.busy:self.sector_selection();raise AuditError('준비·검사 중입니다. 완료 또는 취소 후 선택하세요.')
        if code not in [c['code'] for c in self.sector_options]:raise AuditError('지원하지 않는 업종 회사')
        if not self.check_navigation():self.sector_selection();return False
        from sector_demo import open_company
        self.set_busy(True);self.cancel.clear()
        self.status.set('모회사·자회사별 자료·저장 이력을 확인 중…')
        def worker():
            try:
                result=open_company(code,self.sector_home,resource('sector_resources'),fresh=fresh,event=self.cancel,progress=lambda s:self.queue.put(('status',s)))
                self.queue.put(('sector_ready',result))
            except Exception as e:self.queue.put(('sector_error',str(e)))
        threading.Thread(target=worker,daemon=False).start();return True
    def set_busy(self,value):
        self.busy=value
        if value:
            self.disabled_widgets=[]
            def disable(parent):
                for w in parent.winfo_children():
                    if isinstance(w,ttk.Widget):
                        previous=w.state();w.state(['disabled']);self.disabled_widgets.append((w,'ttk',previous))
                    elif isinstance(w,(tk.Text,tk.Listbox)) or getattr(w,'audit_native_text',False):
                        previous=w.cget('state');w.configure(state='disabled');self.disabled_widgets.append((w,'tk',previous))
                    disable(w)
            disable(self.nb);self.root.focus_set();self.sector_box.configure(state='disabled');self.sector_new.configure(state='disabled');self.sector_cancel.configure(state='normal')
        else:
            for w,kind,previous in getattr(self,'disabled_widgets',[]):
                if kind=='ttk':w.state(['!disabled',*previous])
                else:w.configure(state=previous)
            self.disabled_widgets=[];self.sector_box.configure(state='readonly');self.sector_new.configure(state='normal');self.sector_cancel.configure(state='disabled')
    def reset_workspace_view(self):
        self.current_pid=None;self.current_request=None;self.file.set('');self.search.set('');self.result_module.set('');self.result_table.set('');self.page=0;self.table_rows=[];self.visible_rows=[]
        for var in self.proc_vars.values():var.set('')
        for text in list(self.proc_text.values())+[self.row_text,self.risk_detail]:text.delete('1.0','end')
        self.set_history_text('')
        self.excluded.set(False);self.reviewer.set('');self.review_note.set('');self.review_saved=('', '')
        self.evidence_list.selection_clear(0,'end');self.proc_heading.set('절차를 선택하세요. 실제 수행·판단·검토는 별도로 기록합니다.')
        self.clear_request();self.saved_signature=self.form_signature()
    def request_signature(self):
        return dumps({'id':self.current_request,'vars':{k:v.get() for k,v in self.request_vars.items()},'state':self.request_state.get(),'sources':[self.request_sources[i]['id'] for i in self.request_evidence.curselection()]})
    def check_navigation(self):
        pending_request={k:v.get() for k,v in self.request_vars.items()};pending_state=self.request_state.get();pending_ids=[self.request_sources[i]['id'] for i in self.request_evidence.curselection()];pending_review=(self.reviewer.get(),self.review_note.get())
        if not self.check_draft():return False
        for k,v in self.request_vars.items():v.set(pending_request[k])
        self.request_state.set(pending_state);self.request_evidence.selection_clear(0,'end')
        for i,s in enumerate(self.request_sources):
            if s['id'] in pending_ids:self.request_evidence.selection_set(i)
        self.reviewer.set(pending_review[0]);self.review_note.set(pending_review[1])
        if self.request_signature()!=getattr(self,'request_saved',self.request_signature()):
            answer=messagebox.askyesnocancel('미저장 자료요청','자료요청 수정 내용을 저장한 뒤 이동할까요? 아니오를 선택하면 수정 내용을 버립니다.',parent=self.root)
            if answer is None:return False
            if answer:
                try:self.save_request()
                except Exception as e:messagebox.showerror('저장 필요',str(e),parent=self.root);return False
                self.reviewer.set(pending_review[0]);self.review_note.set(pending_review[1])
        if (self.reviewer.get(),self.review_note.get())!=self.review_saved:
            if not messagebox.askokcancel('미저장 검토 입력','검토자·검토내용 입력이 아직 검토기록으로 저장되지 않았습니다. 이 입력을 버리고 이동할까요?',parent=self.root):return False
        return True
    def guard(self):
        if self.busy:raise AuditError('검사가 실행 중입니다. 완료 또는 취소 후 변경하세요.')
        if not self.ws:raise AuditError('업무를 먼저 만들거나 여세요.')
    def open_raw_data(self,open_folder=True):
        self.guard()
        from sector_demo import data_folder
        folder=data_folder(self.ws)
        if open_folder:
            import os
            os.startfile(str(folder))
        self.status.set('최초 더미 입력·원천 열람 / 최신 등록사본은 업무/원본/: '+str(folder));return folder
    def build_history(self,p):
        ttk.Label(p,text='저장한 자료요청·조서 개정·검토 등의 로컬 이력입니다. 저장 전 입력과 실제 이메일 발송은 별개이며 이름 입력은 본인인증·전자서명이 아닙니다.',wraplength=1190).pack(anchor='w',pady=8)
        self.history_tree=tree(p,['순번','시각 KST','기록종류','대상','상태','작성·검토 입력값'],11)
        self.history_tree.bind('<<TreeviewSelect>>',lambda _:self.show_history())
        self.history_detail=create_scrolled_text(p,height=13,wrap='word',state='disabled');self.history_detail.audit_container.pack(fill='both',expand=True,pady=8)
        self.history_items=[]
    def set_history_text(self,value):
        self.history_detail.configure(state='normal');self.history_detail.delete('1.0','end');self.history_detail.insert('1.0',value);self.history_detail.configure(state='disabled')
    def history_rows(self):
        names={'engagement':'업무 생성','source':'자료 등록','run':'검사 실행','procedure':'조서 저장·개정·검토','note':'검토의견','evidence_request':'자료요청·상태 변경','ai_draft':'AI 초안 생성','ai_apply':'AI 초안 적용','ai_content_approval':'AI 내용 최종 승인'}
        names['sector_storage_relocation']='자료 보관 폴더 이동'
        self.history_items=list(self.ws.events) if self.ws else []
        rows=[]
        for index,event in enumerate(self.history_items,1):
            d=event['data'];state=d.get('state','')
            if event['kind']=='run':state='입력 보완 필요' if d['result']['blocking'] else '자동검사 종료 · 수동절차 필요'
            actor=' / '.join(str(d[k]) for k in ('preparer','reviewer','actor') if d.get(k))
            rows.append({'순번':index,'시각 KST':display_time(event['at']),'기록종류':names.get(event['kind'],event['kind']),'대상':d.get('title') or d.get('name') or d.get('module') or d.get('회사명') or d.get('procedure_id') or d.get('id',''),'상태':state,'작성·검토 입력값':actor or '기록 없음'})
        return rows
    def show_history(self):
        selected=self.history_tree.selection()
        if not selected:return
        text=json.dumps(self.history_items[int(selected[0])],ensure_ascii=False,indent=2)
        if len(text)>100000:text=text[:100000]+'\n[화면 미리보기 생략. 전체 이력은 업무.sqlite3 및 출력 증적JSON에 보존됩니다.]'
        self.set_history_text(text)
    def build_risks(self,p):
        ttk.Label(p,text='규칙 기반 검토 후보입니다. 우선순위는 부정 확률이 아닙니다. 원문·조건·미확인 범위를 확인하고 판단을 조서에 기록하세요.',wraplength=1150).pack(anchor='w',pady=8)
        self.risk_items=[];self.risk_tree=tree(p,['모듈','규칙ID','우선순위','사유','연결상태','조서ID'],10)
        self.risk_tree.bind('<<TreeviewSelect>>',lambda _:self.show_risk())
        self.risk_detail=create_scrolled_text(p,height=12,wrap='word');self.risk_detail.audit_container.pack(fill='both',expand=True,pady=8)
        buttons=FlowFrame(p);buttons.pack(fill='x',pady=8)
        for label,fn in [('관련 조서 열기',self.risk_workpaper),('자료요청 초안',self.risk_request),('검토맥락 저장',self.export_context)]:buttons.add(ttk.Button(buttons,text=label,command=lambda f=fn:self.call(f)))
    def selected_risk(self):
        self.guard();s=self.risk_tree.selection()
        if not s:raise AuditError('검토 후보를 선택하세요.')
        return self.risk_items[int(s[0])]
    def show_risk(self):
        s=self.risk_tree.selection()
        if not s:return
        self.risk_detail.delete('1.0','end');self.risk_detail.insert('1.0',json.dumps(self.risk_items[int(s[0])],ensure_ascii=False,indent=2))
    def risk_workpaper(self):
        r=self.selected_risk()
        if not self.check_draft():return
        self.load_procedure(r['조서ID']);self.nb.select(self.tabs['절차·조서'])
    def risk_request(self):
        r=self.selected_risk();draft=self.ws.candidate_request_draft(r['후보키']);self.clear_request()
        for k,v in self.request_vars.items():v.set(draft[k])
        for i,s in enumerate(self.request_sources):
            if s['id'] in draft['source_ids']:self.request_evidence.selection_set(i)
        self.nb.select(self.tabs['자료요청']);self.status.set('요청 초안입니다. 요청처·기한·범위를 확인한 뒤 저장하세요.')
    def export_context(self):
        self.guard();path=filedialog.asksaveasfilename(parent=self.root,title='로컬 규칙 분석의 검토맥락 저장',defaultextension='.json',filetypes=[('JSON','*.json')])
        if path:
            from review_support import save_context
            save_context(self.ws,path);self.status.set('로컬 규칙 분석의 검토맥락을 저장했습니다. AI 추론 사용 여부: 없음.')
    def build_requests(self,p):
        ttk.Label(p,text='요청자료·수령 사본·처리상태를 기록합니다. 수령/검토 상태에는 등록한 증거를 연결하세요.').pack(anchor='w',pady=8)
        self.request_tree=tree(p,['id','title','requested_from','due_date','state','note'],7)
        for key,label in [('id','요청번호'),('title','요청자료'),('requested_from','요청처'),('due_date','기한'),('state','상태'),('note','요청범위·처리내용')]:self.request_tree.heading(key,text=label)
        self.request_tree.bind('<<TreeviewSelect>>',self.select_request)
        form=ttk.Frame(p);form.pack(fill='x',pady=8);self.request_vars={}
        for key,label in [('title','요청자료'),('requested_from','요청처'),('due_date','기한'),('note','요청범위·처리내용·취소 사유')]:
            row=ttk.Frame(form);row.pack(fill='x',pady=3);ttk.Label(row,text=label,width=28).pack(side='left');v=tk.StringVar();self.request_vars[key]=v;ttk.Entry(row,textvariable=v).pack(side='left',fill='x',expand=True)
        self.request_state=tk.StringVar(value='요청');ttk.Combobox(form,textvariable=self.request_state,values=['요청','부분수령','수령','검토완료','취소'],state='readonly',width=15).pack(anchor='w',pady=6)
        ttk.Label(form,text='연결할 등록 증거 (여러 개 선택 가능)').pack(anchor='w')
        self.request_evidence=tk.Listbox(form,selectmode='extended',height=6,exportselection=False);self.request_evidence.pack(fill='x')
        self.request_sources=[];self.current_request=None
        buttons=ttk.Frame(form);buttons.pack(fill='x',pady=8)
        ttk.Button(buttons,text='새 요청',command=self.clear_request).pack(side='left');ttk.Button(buttons,text='요청·수령 기록 저장',command=lambda:self.call(self.save_request)).pack(side='left',padx=8)
    def clear_request(self):
        self.current_request=None
        for v in self.request_vars.values():v.set('')
        self.request_state.set('요청');self.request_evidence.selection_clear(0,'end')
        self.request_saved=self.request_signature()
    def select_request(self,_=None):
        if not self.ws or not self.request_tree.selection():return
        row=list(self.ws.requests.values())[int(self.request_tree.selection()[0])];self.current_request=row['id']
        for k,v in self.request_vars.items():v.set(row[k])
        self.request_state.set(row['state']);self.request_evidence.selection_clear(0,'end')
        for i,s in enumerate(self.request_sources):
            if s['id'] in row['source_ids']:self.request_evidence.selection_set(i)
        self.request_saved=self.request_signature()
    def save_request(self):
        self.guard();d={k:v.get() for k,v in self.request_vars.items()};d.update(id=self.current_request,state=self.request_state.get(),source_ids=[self.request_sources[i]['id'] for i in self.request_evidence.curselection()])
        row=self.ws.save_request(d);self.refresh();self.current_request=row['id'];self.request_saved=self.request_signature();self.status.set('자료요청·수령 기록 저장 완료')
    def call(self,fn):
        try:return fn()
        except Exception as e:self.status.set(str(e));messagebox.showerror('확인 필요',str(e),parent=self.root);return None
    def form_signature(self):
        return dumps({'id':self.current_pid,'vars':{k:v.get() for k,v in self.proc_vars.items()},'text':{k:t.get('1.0','end').strip() for k,t in self.proc_text.items()},'excluded':self.excluded.get(),'evidence':[self.evidence_sources[i]['id'] for i in self.evidence_list.curselection()]})
    def dirty(self):return bool(self.current_pid and hasattr(self,'saved_signature') and self.form_signature()!=self.saved_signature)
    def check_draft(self):
        if not self.dirty():return True
        answer=messagebox.askyesnocancel('미저장 조서','작성 중인 조서를 저장한 뒤 이동할까요? 아니오를 선택하면 수정 내용을 버립니다.',parent=self.root)
        if answer is None:return False
        if answer:
            try:self.save_procedure()
            except Exception as e:messagebox.showerror('저장 필요',str(e),parent=self.root);return False
        return True
    def new_dialog(self):
        if self.busy or not self.check_navigation():return
        win=tk.Toplevel(self.root);win.title('새 감사 업무');win.transient(self.root);frame=ttk.Frame(win,padding=15);frame.pack(fill='both',expand=True);fields={}
        defaults={'회사코드':'','회사명':'','시작일':'2026-01-01','기준일':'2026-12-31','회계체계':'K-IFRS','감사기준':'한국 회계감사기준 / 해당 보고기간 시행일 확인','작성자':''}
        for i,(k,v) in enumerate(defaults.items()):
            ttk.Label(frame,text=k).grid(row=i,column=0,sticky='w',pady=5);var=tk.StringVar(value=v);fields[k]=var;ttk.Entry(frame,textvariable=var,width=55).grid(row=i,column=1)
        def create():
            if self.busy or not self.check_navigation():return
            folder=filedialog.askdirectory(parent=win,title='새 업무를 만들 빈 폴더 선택')
            if folder:
                def op():
                    self.ws=Workspace(folder,create={k:v.get() for k,v in fields.items()});self.reset_workspace_view();self.active_sector=None;self.sector_selection();self.refresh();win.destroy()
                self.call(op)
        ttk.Button(frame,text='빈 폴더 선택 후 생성',command=create).grid(row=8,column=1,sticky='e',pady=10)
    def open_workspace(self,folder):
        if self.busy:raise AuditError('검사 중 업무를 바꿀 수 없습니다.')
        ws=Workspace(folder);self.ws=ws;self.reset_workspace_view();self.active_sector=None;self.sector_selection();self.refresh()
    def open_dialog(self):
        if self.busy or not self.check_navigation():return
        folder=filedialog.askdirectory(parent=self.root,title='업무.sqlite3가 있는 업무 폴더')
        if folder:self.call(lambda:self.open_workspace(folder))
    def start_demo(self,folder,full=False,analytics=False):
        if self.busy:raise AuditError('검사 실행 중')
        self.ws=Workspace(folder,create={'회사코드':'SYNTH01','회사명':'합성 제조회사 (SYNTHETIC ONLY)','시작일':'2026-01-01','기준일':'2026-12-31','회계체계':'K-IFRS / 합성 시나리오','감사기준':'한국 회계감사기준 / 학습용','작성자':'합성작성자','더미업무':True});self.reset_workspace_view();self.active_sector=None;self.sector_selection();self.refresh()
        self.launch([(m,resource('samples','통합',f)) for m,f in (ANALYTIC_DEMO_FILES if analytics else FULL_DEMO_FILES if full else DEMO_FILES)])
    def demo_dialog(self):
        if self.busy or not self.check_navigation():return
        folder=filedialog.askdirectory(parent=self.root,title='더미업무를 보관할 상위 폴더 선택')
        if folder:self.call(lambda:self.start_demo(Path(folder)/('더미업무_'+datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d_%H%M%S')),full=True,analytics=True))
    def case_dialog(self):
        if self.busy or not self.check_navigation():return
        data=json.loads(resource('worker_cases.json').read_text(encoding='utf-8'))
        win=tk.Toplevel(self.root);win.title('계정별 독립 증빙연습');win.transient(self.root)
        ttk.Label(win,text='현재 업무와 분리된 새 합성 업무를 만듭니다. 33개 사례는 서로 합산하지 않습니다.',padding=12).pack()
        selected=tk.StringVar(value=data[0]['worker']+' | '+data[0]['case_id'])
        box=ttk.Combobox(win,textvariable=selected,state='readonly',width=75,values=[x['worker']+' | '+x['case_id'] for x in data]);box.pack(padx=12,pady=10)
        def start():
            if self.busy or not self.check_navigation():return
            entry=data[box.current()];folder=filedialog.askdirectory(parent=win,title='새 독립 연습 업무를 만들 상위 폴더')
            if not folder:return
            def op():
                self.ws=Workspace(Path(folder)/('계정연습_'+entry['case_id']+'_'+datetime.now().strftime('%Y%m%d_%H%M%S')),create={'회사코드':'SYNTH01','회사명':'독립 계정 합성 사례','시작일':'2026-01-01','기준일':'2026-12-31','회계체계':'K-IFRS / 합성 제한 사례','감사기준':'학습용·실제 감사 수행 아님','작성자':'합성작성자','더미업무':True})
                self.reset_workspace_view();self.active_sector=None;self.sector_selection();self.refresh();win.destroy();self.launch([('계정별증빙연습',resource(entry['file']))])
            self.call(op)
        ttk.Button(win,text='새 독립 업무에서 실행',command=start).pack(pady=12)
    def copy_templates(self):
        folder=filedialog.askdirectory(parent=self.root,title='입력양식과 더미자료를 복사할 폴더')
        if folder:self.call(lambda:self.copy_input_bundle(folder))
    def copy_input_bundle(self,folder):
        target=Path(folder)/'통합감사_v1.7_입력자료'
        if target.exists():raise AuditError('동일 복사 폴더가 이미 있습니다. 다른 폴더를 선택하세요.')
        for src,dest in [('templates','입력양식'),('samples','더미자료'),('raw_analytics','분석원천자료'),('sector_resources','업종별자료'),('문서','사용안내')]:shutil.copytree(resource(src),target/dest)
        self.status.set('입력양식·더미·원천·사용안내 복사 완료: '+str(target));return target
    def build_inputs(self,p):
        ttk.Label(p,text='현재 업무에 자료를 등록하고 검사합니다. 실제 회사/기간과 추출 조건은 원본 증거로 확인하세요.').pack(anchor='w',pady=3)
        line=FlowFrame(p);line.pack(fill='x',pady=7);self.module=tk.StringVar(value=MODULES[0]);self.file=tk.StringVar();line.add(ttk.Combobox(line,textvariable=self.module,values=MODULES,state='readonly',width=24));self.module.trace_add('write',lambda *_:self.scope_text.set(LIMITS[self.module.get()]));line.add(ttk.Entry(line,textvariable=self.file,width=30))
        for label,fn in [('파일 선택',self.choose_input),('등록·검사 실행',lambda:self.call(self.run_selected)),('취소',self.cancel.set)]:line.add(ttk.Button(line,text=label,command=fn))
        self.scope_text=tk.StringVar(value=LIMITS[MODULES[0]]);ttk.Label(p,textvariable=self.scope_text,wraplength=1150).pack(anchor='w',pady=8)
        self.run_tree=tree(p,['모듈','실행상태','차단','검토','실행시각','자료명'],8)
        ttk.Label(p,text='예외를 더블클릭하면 해당 예외의 수행·검토 조서를 작성합니다. 차단 오류는 원본을 보완해 재실행해야 합니다.').pack(anchor='w',pady=7)
        self.issue_tree=tree(p,['모듈','중요도','사유','내용','원본행'],8);self.issue_tree.bind('<Double-1>',self.select_issue)
        self.issue_tree.column('내용',width=400);self.issue_tree.column('원본행',width=300);self.run_tree.column('실행시각',width=225);self.run_tree.column('실행상태',width=240)
    def choose_input(self):
        path=filedialog.askopenfilename(parent=self.root,filetypes=[('감사 입력자료','*.xlsx *.json *.auditpack'),('Excel 확정값','*.xlsx'),('재무제표·증빙 JSON','*.json'),('원천증빙 패키지','*.auditpack')]);
        if path:self.file.set(path)
    def run_selected(self):
        self.guard()
        if not self.check_draft():return
        if not Path(self.file.get()).is_file():raise AuditError('현재 모듈의 입력 파일을 선택하세요.')
        self.launch([(self.module.get(),Path(self.file.get()))])
    def launch(self,items):
        self.guard();self.set_busy(True);self.cancel.clear();self.status.set('자료 등록·검사 중…');ws=self.ws
        def worker():
            try:
                for m,p in items:
                    if self.cancel.is_set():break
                    self.queue.put(('status',m+' 검사 중'));r=ws.execute(m,p,self.cancel);self.queue.put(('run',r))
                self.queue.put(('done',None))
            except Exception as e:self.queue.put(('error',str(e)))
        threading.Thread(target=worker,daemon=False).start()
    def poll(self):
        try:
            while True:
                kind,data=self.queue.get_nowait()
                if kind=='status':self.status.set(data)
                elif kind=='run':pass
                elif kind in ('ai_ok','ai_error'):
                    self.finish_ai_job(kind,data)
                    if self.closing:return
                elif kind in ('sector_ready','sector_error'):
                    self.set_busy(False)
                    if kind=='sector_ready':
                        try:
                            ws=Workspace(data['folder']);self.ws=ws;self.reset_workspace_view();self.active_sector=data['company_code'];self.sector_selection();self.refresh()
                            c=next(c for c in self.sector_options if c['code']==self.active_sector);self.sector_description.set(('업종 없음 · 모회사 자체 원장 / 연결계산 미수행' if c.get('kind')=='parent' else c['sector']+' / 자회사 별도 합성업무 · 수동 판단·검토 필요'))
                            self.status.set('저장된 회사 연습을 열었습니다.' if data['reused'] else ('모회사 원장 1개와 조서 초안 준비 · 투자주식 평가·연결계산은 미수행' if c.get('kind')=='parent' else '15개 검사·35개 TB 숫자·실행 연결 확인 · 독립 감사증거 검증 완료를 뜻하지 않습니다.'))
                        except Exception as e:self.sector_selection();self.status.set('업무 열기 오류: '+str(e))
                    else:self.sector_selection();self.status.set('회사 준비 중단: '+data)
                    if self.closing:self.shutdown_ai();self.root.destroy();return
                else:
                    self.set_busy(False)
                    if kind=='error':self.status.set('실행 오류: '+data)
                    else:self.status.set('검사 완료. 수동 증거 확인과 조서 검토를 진행하세요.')
                    self.call(self.refresh)
                    if self.closing:self.shutdown_ai();self.root.destroy();return
        except queue.Empty:pass
        self.root.after(80,self.poll)
    def build_lead(self,p):
        ttk.Label(p,text='차대변 균형은 기본 검사입니다. 원장 행수·계정별 통제·TB 변동 및 계산값을 별도로 비교합니다. 숫자·실행 연결 일치는 전체 증빙 감사 완료를 뜻하지 않습니다.',wraplength=1180).pack(anchor='w',pady=5)
        self.lead_tree=tree(p,['계정코드','계정명','리드코드','기초잔액','차변','대변','조정전','승인조정','조정후','원본행'],10)
        self.cross_scope_text=tk.StringVar(value='계산 결과와 TB 숫자·현재 실행 연결. 원천 선택 범위와 미확인 항목은 별도 확인하세요.')
        ttk.Label(p,textvariable=self.cross_scope_text,wraplength=1180).pack(anchor='w',pady=8);self.cross_tree=tree(p,['모듈','지표','상태','기대','실제','차이','사유'],7)
    def build_results(self,p):
        bar=FlowFrame(p);bar.pack(fill='x');self.result_module=tk.StringVar();self.result_table=tk.StringVar();self.search=tk.StringVar();self.result_modules=ttk.Combobox(bar,textvariable=self.result_module,state='readonly',width=24);bar.add(self.result_modules);self.result_modules.bind('<<ComboboxSelected>>',lambda _:self.choose_result_module())
        self.result_tables=ttk.Combobox(bar,textvariable=self.result_table,state='readonly',width=27);bar.add(self.result_tables);self.result_tables.bind('<<ComboboxSelected>>',lambda _:self.load_table());bar.add(ttk.Entry(bar,textvariable=self.search,width=20))
        for label,fn in [('검색',self.load_table),('이전',lambda:self.turn_page(-1)),('다음',lambda:self.turn_page(1))]:bar.add(ttk.Button(bar,text=label,command=fn))
        self.page_label=tk.StringVar();bar.add(ttk.Label(bar,textvariable=self.page_label))
        self.result_tree=tree(p,['내용'],14);self.result_tree.bind('<<TreeviewSelect>>',self.show_row)
        self.row_text=create_scrolled_text(p,height=9,wrap='word');self.row_text.audit_container.pack(fill='both',expand=False,pady=7)
    def choose_result_module(self):
        if not self.ws:return
        latest=self.ws.latest();r=latest.get(self.result_module.get());names=list(r['result']['tables']) if r else []
        preferred=MODULE_TABLES.get(self.result_module.get(),[]);names.sort(key=lambda n:preferred.index(n) if n in preferred else len(preferred))
        self.result_tables['values']=names;self.result_table.set(names[0] if names else '');self.load_table()
    def load_table(self):
        if not self.ws:return
        r=self.ws.latest().get(self.result_module.get());self.table_rows=r['result']['tables'].get(self.result_table.get(),[]) if r else []
        q=self.search.get().strip().lower()
        if q:self.table_rows=[r for r in self.table_rows if q in dumps(r).lower()]
        self.page=0;self.render_page()
    def turn_page(self,delta):self.page=max(0,min(max(0,(len(self.table_rows)-1)//200),self.page+delta));self.render_page()
    def render_page(self):
        self.visible_rows=self.table_rows[self.page*200:(self.page+1)*200];columns=TABLE_COLUMNS.get(self.result_table.get()) or list(dict.fromkeys(k for r in self.visible_rows for k in r)) or ['내용']
        rows=self.visible_rows
        if self.result_module.get() in MODULE_TABLES:
            rows=[{k:format(v,',') if isinstance(v,int) and not isinstance(v,bool) else v for k,v in row.items()} for row in rows]
        fill(self.result_tree,rows,columns)
        if self.result_table.get() in TABLE_COLUMNS:
            widths={c:{'리스ID':95,'채권ID':110,'거래처':145,'분류군':95,'월':100,'회차':60,'연체일수':85,'측정구분':90,'가중손실률':110}.get(c,135) for c in columns}
            self.display.register_tree(self.result_tree,widths)
        self.page_label.set(f'{len(self.table_rows)}행 / {self.page+1}쪽 (전체 저장은 필터와 무관)')
    def show_row(self,_=None):
        s=self.result_tree.selection()
        if s:
            self.row_text.delete('1.0','end');self.row_text.insert('1.0',json.dumps(self.visible_rows[int(s[0])],ensure_ascii=False,indent=2))
    def build_procedures(self,p):
        self.build_ai_actions(p,FlowFrame)
        pan=ttk.Panedwindow(p,orient='horizontal');pan.pack(fill='both',expand=True);left=ttk.Frame(pan);right_outer=ttk.Frame(pan,padding=(10,0));pan.add(left,weight=2);pan.add(right_outer,weight=3)
        buttons=FlowFrame(right_outer);buttons.pack(side='bottom',fill='x',pady=5);self.workpaper_actions=buttons
        self.save_workpaper_button=buttons.add(ttk.Button(buttons,text='조서 저장·개정',command=lambda:self.call(self.save_procedure)))
        buttons.add(ttk.Button(buttons,text='검토 요청',command=lambda:self.call(self.request_review)))
        self.workpaper_export_button=buttons.add(ttk.Button(buttons,text='초안 Excel 내보내기',command=lambda:self.export_dialog(False)))
        self.workpaper_export_button.flow_secondary=True
        self.proc_scroll=ScrollableFrame(right_outer);self.proc_scroll.pack(fill='both',expand=True);right=self.proc_scroll.inner
        self.proc_paned=pan;pan.bind('<Configure>',lambda e:pan.sashpos(0,max(180,int(e.width*.38))))
        self.proc_tree=tree(left,['ID','절차','현재상태','필수'],20);self.proc_tree.column('ID',width=85);self.proc_tree.column('절차',width=240);self.proc_tree.bind('<<TreeviewSelect>>',self.on_procedure_select)
        self.proc_heading=tk.StringVar(value='왼쪽에서 계정을 선택하세요. 초안 근거를 확인한 뒤 실제 수행·판단을 작성합니다.');ttk.Label(right,textvariable=self.proc_heading,wraplength=650).pack(anchor='w',pady=3)
        self.proc_vars={}
        row=FlowFrame(right);row.pack(fill='x')
        for label,key,width in [('작성자','preparer',14),('실제 수행일','performed_date',12)]:
            group=ttk.Frame(row);row.add(group);ttk.Label(group,text=label).pack(anchor='w');v=tk.StringVar();self.proc_vars[key]=v;ttk.Entry(group,textvariable=v,width=width).pack(fill='x')
        self.excluded=tk.BooleanVar();row.add(ttk.Checkbutton(row,text='범위 제외',variable=self.excluded))
        self.proc_text={}
        for label,key,height in [('목적·주장','purpose',2),('위험·기준 / 제외 사유','risk',2),('모집단·선정/검사 범위','scope',2),('실제 수행내용·근거·예외 조사','performed',3),('판단·결론·추가절차','conclusion',3)]:
            ttk.Label(right,text=label).pack(anchor='w');t=create_editable_text(right,height=height,wrap='word');t.audit_container.pack(fill='x');self.proc_text[key]=t
        ttk.Label(right,text='연결 증거 (Ctrl로 여러 자료 선택, 실제 근거는 위 수행내용에 기록)',wraplength=650).pack(anchor='w');self.evidence_list=tk.Listbox(right,selectmode='extended',height=3,exportselection=False,font='AuditSmallFont');self.evidence_list.pack(fill='x')
        rr=ttk.Frame(right);rr.pack(fill='x');ttk.Label(rr,text='검토자').pack(anchor='w');self.reviewer=tk.StringVar();ttk.Entry(rr,textvariable=self.reviewer,width=15).pack(anchor='w');ttk.Label(rr,text='검토내용·범위').pack(anchor='w');self.review_note=tk.StringVar();ttk.Entry(rr,textvariable=self.review_note).pack(fill='x')
        rr2=FlowFrame(right);rr2.pack(fill='x',pady=5);self.review_complete_button=rr2.add(ttk.Button(rr2,text='검토기록 완료',command=lambda:self.call(lambda:self.review(True))));rr2.add(ttk.Button(rr2,text='보완 의견',command=lambda:self.call(lambda:self.review(False))))
    def task_list(self):
        from procedures import task_definitions
        return task_definitions(self.ws,CATALOG)
    def on_procedure_select(self,_=None):
        selected=self.proc_tree.selection()
        if not selected:return
        pid=self.tasks[int(selected[0])]['id']
        if pid==self.current_pid:return
        if self.check_draft():self.load_procedure(pid)
    def load_procedure(self,pid):
        task=next(x for x in self.task_list() if x['id']==pid);p=self.ws.procedures.get(pid,task) if self.ws else task;self.current_pid=pid;self.current_title=p['title'];self.proc_heading.set(p['title']+' / '+(self.ws.procedure_state(p) if self.ws and 'basis' in p else '미착수'))
        for key,var in self.proc_vars.items():var.set(p.get(key,self.ws.engagement['작성자'] if key=='preparer' and self.ws else ''))
        self.excluded.set(p.get('excluded',False))
        for key,t in self.proc_text.items():t.delete('1.0','end');t.insert('1.0',p.get('excluded_reason','') if key=='risk' and p.get('excluded') else p.get(key,''))
        self.evidence_list.selection_clear(0,'end')
        for i,s in enumerate(self.evidence_sources):
            if s['id'] in p.get('evidence_ids',[]):self.evidence_list.selection_set(i)
        self.reviewer.set(p.get('reviewer',''));self.review_note.set(p.get('review_note',''))
        self.review_saved=(self.reviewer.get(),self.review_note.get())
        self.saved_signature=self.form_signature()
        self.refresh_ai_status()
    def save_procedure(self):
        self.guard()
        if not self.current_pid:raise AuditError('절차를 선택하세요.')
        p={'id':self.current_pid,'title':self.current_title,**{k:v.get() for k,v in self.proc_vars.items()},**{k:t.get('1.0','end').strip() for k,t in self.proc_text.items()},'excluded':self.excluded.get(),'evidence_ids':[self.evidence_sources[i]['id'] for i in self.evidence_list.curselection()]}
        if p['excluded']:p['excluded_reason']=p['risk']
        self.ws.save_procedure(p);self.refresh();self.status.set('조서 개정 저장. 이전 검토는 다시 받아야 합니다.')
    def request_review(self):
        self.guard()
        if self.dirty():self.save_procedure()
        self.ws.request_review(self.current_pid);self.refresh()
    def review(self,accepted):
        self.guard()
        if self.dirty():raise AuditError('조서 수정 후 저장·검토요청을 다시 진행하세요.')
        self.ws.review(self.current_pid,self.reviewer.get(),self.review_note.get(),accepted);self.refresh()
    def select_issue(self,_=None):
        selected=self.issue_tree.selection()
        if selected and self.check_draft():
            r,i=self.issue_items[int(selected[0])];self.nb.select(self.tabs['절차·조서']);self.load_procedure('X-'+r['id']+'-'+str(i))
    def build_evidence(self,p):
        bar=FlowFrame(p);bar.pack(fill='x',pady=4)
        for label,fn in [('증거 파일 등록',self.add_evidence),('검토의견 등록',self.add_note),('선택 의견 해결 기록',self.resolve_note)]:bar.add(ttk.Button(bar,text=label,command=lambda f=fn:self.call(f)))
        self.source_tree=tree(p,['자료명','유형','원본파일','사본해시','등록시각'],9);self.note_tree=tree(p,['제목','내용','작성자','해결','시각'],8)
        ttk.Label(p,text='증거는 업무 폴더에 사본으로 보존합니다. 이름 입력은 인증된 서명이 아닙니다. DB·헤드·원본 폴더를 함께 백업하세요.').pack(anchor='w',pady=7)
        ttk.Button(bar,text='독립 ID 통제값',command=lambda:self.call(self.id_control)).pack(side='left',padx=6)
    def id_control(self):
        from estimate_controls import independent_ids
        path=filedialog.askopenfilename(parent=self.root,title='계산 입력과 별도로 ERP에서 추출한 전체 ID CSV',filetypes=[('UTF-8 CSV','*.csv')])
        if not path:return
        column=simpledialog.askstring('독립 ID 열','CSV의 식별자 열 이름 (예: 채권ID, 리스ID)',parent=self.root)
        if not column:return
        value=independent_ids(path,column);output='행수: '+str(value['행수'])+'\nID해시: '+value['ID해시']
        self.root.clipboard_clear();self.root.clipboard_append(output)
        messagebox.showinfo('독립 통제값 복사됨',output+'\n\n독립통제 시트에 입력하고 CSV·추출 근거를 증거로 등록하세요. 같은 계산 입력을 재합산한 값은 독립 증거가 아닙니다.',parent=self.root)
    def add_evidence(self):
        self.guard()
        if not self.check_draft():return
        path=filedialog.askopenfilename(parent=self.root)
        if path:
            label=simpledialog.askstring('자료명','근거를 식별할 자료명',initialvalue=Path(path).name,parent=self.root)
            if label:self.ws.add_source(path,label);self.refresh()
    def add_note(self):
        self.guard()
        if not self.check_draft():return
        title=simpledialog.askstring('검토의견','의견 제목',parent=self.root)
        if title:
            body=simpledialog.askstring('검토의견','내용·대상 조서·필요한 후속조치',parent=self.root);actor=simpledialog.askstring('검토의견','작성자',parent=self.root)
            if body and actor:self.ws.add_note(title,body,actor);self.refresh()
    def resolve_note(self):
        self.guard()
        if not self.check_draft():return
        s=self.note_tree.selection()
        if s:
            n=self.note_items[int(s[0])];body=simpledialog.askstring('해결 기록','해결 내용·근거',parent=self.root);actor=simpledialog.askstring('해결 기록','작성자',parent=self.root)
            if body and actor:self.ws.add_note(n['title'],n['body']+' / 해결: '+body,actor,True,n['id']);self.refresh()
    def refresh(self):
        if not self.ws:return
        self.ws.refresh();e=self.ws.engagement;latest=self.ws.latest();self.info.set(f"{e['회사명']} / {e['회사코드']} / {e['시작일']} ~ {e['기준일']} / "+('더미업무 / ' if e.get('더미업무') else '')+str(self.ws.root))
        fill(self.run_tree,[{'모듈':m,'실행상태':'입력 보완 필요' if r['result']['blocking'] else '자동검사 종료·수동절차 필요','차단':r['result']['blocking'],'검토':r['result']['review'],'실행시각':display_time(r['at']),'자료명':self.ws.sources[r['source_id']]['name']} for m,r in latest.items()])
        self.issue_items=[(r,i) for r in latest.values() for i,_ in enumerate(r['result']['issues'])];fill(self.issue_tree,[{'모듈':r['module'],'중요도':r['result']['issues'][i]['severity'],'사유':r['result']['issues'][i]['code'],'내용':r['result']['issues'][i]['message'],'원본행':r['result']['issues'][i]['reference']} for r,i in self.issue_items])
        fill(self.lead_tree,latest.get('원장·리드',{}).get('result',{}).get('tables',{}).get('리드스케줄',[]));fill(self.cross_tree,self.ws.cross_checks())
        raw=latest.get('원천증빙',{}).get('result')
        if self.active_sector=='JS':scope='모회사 자체 원장 · 자회사 영업자료·투자주식 평가·연결계산은 포함하지 않습니다.'
        elif raw:
            metrics=raw['metrics'];scope=('원천 검사 차단 · ' if raw['blocking'] else '')+'TB 숫자·현재 실행 연결 요약. 원천 선택 '+str(metrics.get('선택원천행수','미확인'))+'행·대상 '+str(metrics.get('선택대상행수','미확인'))+'행·배부 '+str(metrics.get('배부건수','미확인'))+'건 / 미확인 범위 '+str(metrics.get('미확인범위수','미확인'))+'개. 결과 상세 → 원천증빙 → 연결범위를 확인하세요.'
        else:scope='계산 결과와 TB 숫자·현재 실행 연결. 실제 원천 선택 범위와 미확인 항목은 결과 상세에서 확인하세요.'
        self.cross_scope_text.set(scope)
        self.result_modules['values']=list(latest)
        if self.result_module.get() not in latest:self.result_module.set(next(iter(latest),''))
        self.choose_result_module();self.tasks=self.task_list();required=self.ws.required_procedures();fill(self.proc_tree,[{'ID':t['id'] if not t['id'].startswith('X-') else '예외','절차':self.ws.procedures.get(t['id'],t)['title'],'현재상태':self.ws.procedure_state(self.ws.procedures[t['id']]) if t['id'] in self.ws.procedures else '미착수','필수':'필수' if t['id'] in required else '선택'} for t in self.tasks])
        self.evidence_sources=list(self.ws.sources.values());self.evidence_list.delete(0,'end')
        for s in self.evidence_sources:self.evidence_list.insert('end',s['name']+' / '+s['id'][:8])
        fill(self.request_tree,list(self.ws.requests.values()));self.request_sources=self.evidence_sources
        self.request_evidence.delete(0,'end')
        for s in self.request_sources:self.request_evidence.insert('end',s['name']+' / '+s['id'][:8])
        if self.current_request in self.ws.requests:
            for i,s in enumerate(self.request_sources):
                if s['id'] in self.ws.requests[self.current_request]['source_ids']:self.request_evidence.selection_set(i)
        fill(self.source_tree,[{'자료명':s['name'],'유형':s['role'],'원본파일':s['original'],'사본해시':s['sha256'],'등록시각':s['registered_at']} for s in self.evidence_sources]);self.note_items=list(self.ws.notes.values());fill(self.note_tree,[{'제목':n['title'],'내용':n['body'],'작성자':n['actor'],'해결':'해결' if n['resolved'] else '미해결','시각':n['at']} for n in self.note_items])
        self.risk_items=self.ws.risk_register();fill(self.risk_tree,self.risk_items);self.risk_detail.delete('1.0','end')
        fill(self.history_tree,self.history_rows());self.set_history_text('')
        if self.current_pid and any(t['id']==self.current_pid for t in self.tasks):self.load_procedure(self.current_pid)
    def export_dialog(self,final):
        def op():
            self.guard()
            if not self.check_draft():return
            path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.xlsx',initialfile='통합감사_검토완료.xlsx' if final else '통합감사_초안.xlsx',filetypes=[('Excel 조서','*.xlsx')])
            if path:exporter.export(self.ws,path,CATALOG,final);self.status.set('조서 저장: '+path)
        self.call(op)
    def close(self):
        if self.busy:self.closing=True;self.cancel.set();self.status.set('취소·이력 저장 후 종료 중…')
        elif self.check_navigation():self.shutdown_ai();self.root.destroy()

def main():
    if '--self-test-ime' in sys.argv:
        from verify_ime_patch import self_test
        return self_test(Path(sys.argv[sys.argv.index('--report')+1]),Path(sys.argv[sys.argv.index('--workspace')+1]))
    if '--self-test-ai-real' in sys.argv:
        from verify_ai_actual import self_test
        return self_test(Path(sys.argv[sys.argv.index('--report')+1]),Path(sys.argv[sys.argv.index('--ai-runtime')+1]))
    if '--self-test-v18' in sys.argv:
        from verify_v18 import self_test
        return self_test(Path(sys.argv[sys.argv.index('--report')+1]))
    if '--self-test-v171' in sys.argv:
        from verify_v171 import self_test
        return self_test(Path(sys.argv[sys.argv.index('--report')+1]))
    if '--self-test-v17' in sys.argv:
        from verify_v17 import self_test
        return self_test(Path(sys.argv[sys.argv.index('--report')+1]))
    if '--self-test-v16' in sys.argv:
        from verify_v16 import self_test
        return self_test(Path(sys.argv[sys.argv.index('--report')+1]))
    if '--self-test-v15' in sys.argv:
        from verify_v15 import self_test
        return self_test(Path(sys.argv[sys.argv.index('--report')+1]))
    if '--self-test-v14' in sys.argv:
        from verify_v14 import self_test
        return self_test(Path(sys.argv[sys.argv.index('--report')+1]))
    if '--self-test' in sys.argv:
        from verify import self_test
        return self_test(Path(sys.argv[sys.argv.index('--report')+1]))
    root=tk.Tk();app=App(root)
    if '--workspace' in sys.argv:app.call(lambda:app.open_workspace(sys.argv[sys.argv.index('--workspace')+1]))
    root.mainloop();return 0
if __name__=='__main__':sys.exit(main())
