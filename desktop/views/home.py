"""Read-only engagement summary. Numbers describe saved records, never audit opinion."""
import tkinter as tk
from tkinter import ttk
from adapters import MODULES
from desktop.design import COLORS
from desktop.widgets.cards import BentoCard
from desktop.widgets.flow import FlowFrame
from desktop.widgets.responsive import BentoGrid
from desktop.progress import workspace_progress


class Dashboard:
    def __init__(self,parent,host):
        self.host=host
        self.values={}
        self.module_states={}
        self.grid=BentoGrid(parent)
        self.grid.pack(fill='both',expand=True)
        self.build_metrics()
        self.build_welcome()
        self.build_next_steps()
        self.build_modules()
        self.refresh()

    def build_metrics(self):
        specs=(('sources','등록 자료','업무에 등록한 원본 사본'),
               ('runs','자동검사','현재 자료의 최신 검사'),
               ('cross','일치한 대사','계산값과 원장의 연결'),
               ('pending','현재 프로세스','지금 이어서 할 감사 단계'))
        for key,title,description in specs:
            card=self.grid.add(BentoCard(self.grid,title))
            value=tk.StringVar(value='—')
            ttk.Label(card.body,textvariable=value,
                      style='Section.TLabel' if key=='pending' else 'Metric.TLabel',
                      wraplength=220,justify='left').pack(anchor='w',fill='x',pady=(1,8))
            ttk.Label(card.body,text=description,style='Muted.TLabel',
                      font=self.host.display.small_font,wraplength=220,justify='left').pack(anchor='w',fill='x')
            self.values[key]=value

    def build_welcome(self):
        card=self.grid.add(BentoCard(self.grid,'현재 업무'),span=2)
        self.company=tk.StringVar()
        self.period=tk.StringVar()
        self.scope=tk.StringVar()
        ttk.Label(card.body,textvariable=self.company,style='Title.TLabel',
                  wraplength=460,justify='left').pack(anchor='w',fill='x',pady=(0,8))
        ttk.Label(card.body,textvariable=self.period,style='Muted.TLabel',wraplength=480).pack(anchor='w')
        ttk.Label(card.body,textvariable=self.scope,style='Muted.TLabel',wraplength=480).pack(anchor='w',pady=(10,15))
        actions=FlowFrame(card.body)
        actions.pack(fill='x')
        actions.add(ttk.Button(actions,text='자료 등록하기',style='Primary.TButton',
                               command=lambda:self.host.navigate('자료·검사')))
        actions.add(ttk.Button(actions,text='조서 초안 열기',style='Soft.TButton',
                               command=lambda:self.host.call(self.host.open_workpaper_draft)))

    def build_next_steps(self):
        card=self.grid.add(BentoCard(self.grid,'다음에 할 일',
                       '현재 자료와 작성·검토 기록에 따라 필요한 일이 바뀌어요.'),span=2)
        self.next_rows=[]
        self.next_routes=[]
        for index in range(3):
            row=ttk.Frame(card.body)
            title=tk.StringVar()
            description=tk.StringVar()
            ttk.Label(row,text=f'{index+1:02}',foreground=COLORS['blue']).pack(side='left',padx=(0,12))
            ttk.Button(row,text='열기',style='Quiet.TButton',
                       command=lambda i=index:self.open_next_step(i)).pack(side='right')
            text=ttk.Frame(row)
            text.pack(side='left',fill='x',expand=True)
            ttk.Label(text,textvariable=title,font=self.host.display.heading_font,
                      wraplength=310,justify='left').pack(anchor='w',fill='x')
            ttk.Label(text,textvariable=description,style='Muted.TLabel',
                      font=self.host.display.small_font,wraplength=310,
                      justify='left').pack(anchor='w',fill='x',pady=(3,0))
            for child in text.winfo_children():child.audit_managed_wrap=True
            text.bind('<Configure>',lambda event,t=text:[
                child.configure(wraplength=max(80,event.width-4)) for child in t.winfo_children()])
            self.next_rows.append((row,title,description))
        self.next_empty=ttk.Label(card.body,
            text='현재 기록에서 남은 항목이 없어요. 추가 감사절차는 검토자가 확인하세요.',
            style='Muted.TLabel',wraplength=440,justify='left')

    def open_next_step(self,index):
        if index>=len(self.next_routes):return False
        stage=self.next_routes[index]
        result=self.host.navigate(stage['route'])
        if result and stage['id']=='company':self.host.sector_box.focus_set()
        return result

    def refresh_next_steps(self,progress):
        self.next_routes=progress['next_steps']
        for index,(row,title,description) in enumerate(self.next_rows):
            if index<len(self.next_routes):
                stage=self.next_routes[index]
                title.set(stage['title']);description.set(stage['description'])
                row.pack(fill='x',pady=(0,12))
            else:row.pack_forget()
        if self.next_routes:self.next_empty.pack_forget()
        else:self.next_empty.pack(anchor='w',fill='x')

    def build_modules(self):
        card=self.grid.add(BentoCard(self.grid,'계정별 분석',
                '분석할 계정을 선택해요. 자료 등록·원장 연결·조서 작성은 같은 업무에 이어져요.'),span=4)
        self.module_grid=BentoGrid(card.body,gap=8)
        self.module_grid.pack(fill='x')
        for module in MODULES:
            tile=ttk.Frame(self.module_grid,style='Card.TFrame',padding=8)
            self.module_grid.add(tile)
            label='재고자산 평가' if module=='재고평가' else module
            ttk.Button(tile,text=label,style='Soft.TButton',
                       command=lambda name=module:self.host.route_module(name)).pack(fill='x')
            status=tk.StringVar(value='자료 등록 전')
            ttk.Label(tile,textvariable=status,style='Muted.TLabel',
                      font=self.host.display.small_font).pack(anchor='w',pady=(6,2),padx=3)
            self.module_states[module]=status

    def refresh(self):
        ws=self.host.ws
        progress=workspace_progress(ws,getattr(self.host,'wf_last_archive',None))
        self.values['pending'].set(progress['current']['title'])
        self.refresh_next_steps(progress)
        if ws is None:
            self.company.set('시작할 업무를 선택해요')
            self.period.set('상단에서 회사를 선택하거나 저장된 업무를 열 수 있어요.')
            self.scope.set('예제는 가상 회사의 자료예요. 실제 고객 자료가 아니에요.')
            for key,value in self.values.items():
                if key!='pending':value.set('—')
            for value in self.module_states.values():value.set('자료 등록 전')
            return
        eng=ws.engagement
        latest=ws.latest()
        cross=ws.cross_checks()
        parent=eng.get('회사코드')=='JS'
        self.company.set(eng['회사명']+(' · 모회사 · 연결재무제표' if parent else ''))
        self.period.set(eng['시작일']+' ~ '+eng['기준일']+' · '+eng['회계체계'])
        scope=('가상 회사의 예제 자료예요. 실제 고객 자료가 아니에요.'
               if eng.get('더미업무') else '현재 저장된 자료와 기록을 기준으로 표시해요.')
        if parent:
            scope+=('\n현재 예제는 모회사 자체 원장이고, 자회사 합산·내부거래 제거 전이에요.'
                    if eng.get('더미업무') else '\n이 화면은 모회사 자체 원장 기준이에요. 자회사 합산·내부거래 제거는 별도예요.')
        self.scope.set(scope)
        self.values['sources'].set(str(len(ws.sources)))
        self.values['runs'].set(str(len(latest)))
        self.values['cross'].set(f"{sum(row.get('상태')=='일치' for row in cross)} / {len(cross)}" if cross else '—')
        for module,value in self.module_states.items():
            result=latest.get(module,{}).get('result')
            value.set('자료 등록 전' if result is None else
                      f"입력 보완 {result['blocking']}건" if result['blocking'] else
                      f"확인할 항목 {result['review']}건" if result['review'] else '검사 결과 있음')
