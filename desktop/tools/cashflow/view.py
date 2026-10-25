"""Independent cash-flow Bento view, sharing the main app's design system."""
from tkinter import ttk
from desktop.design import apply_theme
from desktop.widgets.cards import BentoCard
from desktop.widgets.flow import FlowFrame
from desktop.widgets.responsive import BentoGrid
from desktop_display import ScrollableFrame
from .shared import tk,LABELS,SCOPE
from .tables import make_table
from .help import HELP_TEXT


class View:
    def build_view(self):
        root,px=self.root,self.display.px
        root.title('JS 현금흐름표 · 독립 검증 도구 v2.0.0')
        apply_theme(root,self.display)
        self.status=tk.StringVar(value='입력 양식이나 예제를 선택해 주세요.')
        footer=ttk.Frame(root,style='Page.TFrame',padding=(px(20),px(10)))
        footer.pack(side='bottom',fill='x')
        ttk.Label(footer,textvariable=self.status,style='PageMuted.TLabel',wraplength=1000).pack(side='left',fill='x',expand=True)
        self.progress=ttk.Progressbar(footer,mode='indeterminate',length=px(100))
        self.progress.pack(side='right')
        self.scroll=ScrollableFrame(root);self.scroll.pack(fill='both',expand=True)
        page=self.scroll.inner;page.configure(style='Page.TFrame',padding=px(20))
        heading=FlowFrame(page);heading.pack(fill='x')
        heading.add(ttk.Label(heading,text='현금흐름을 확인해요',style='Title.TLabel'))
        heading.add(ttk.Label(heading,text='글자 크기'))
        self.zoom=tk.StringVar(value='100%')
        zoom=heading.add(ttk.Combobox(heading,textvariable=self.zoom,values=('90%','100%','110%','125%','150%','175%'),state='readonly',width=6))
        zoom.bind('<<ComboboxSelected>>',lambda event:self.set_zoom(self.zoom.get()))
        ttk.Label(page,text=SCOPE,style='PageMuted.TLabel',wraplength=1000).pack(fill='x',pady=(px(6),px(14)))
        self._build_input(page)
        self._build_summary(page)
        self._build_tabs(page)

    def _build_input(self,page):
        card=BentoCard(page,'자료를 선택해요','KRW 원 단위·단일기업·간접법 자료를 확인해요. 예제의 YES는 사용법 설명을 위한 예시값이에요.')
        card.pack(fill='x',pady=(0,self.display.px(14)))
        actions=FlowFrame(card.body);actions.pack(fill='x')
        self.case_name=tk.StringVar(value='정상_비현금_환율')
        self.case_combo=actions.add(ttk.Combobox(actions,textvariable=self.case_name,values=list(self.cases),state='readonly',width=19))
        for attr,text,command,style in (
            ('example_button','예제 불러오기',self.load_example,'Soft.TButton'),
            ('template_button','입력 양식 저장',self.save_template,'TButton'),
            ('file_button','입력 Excel 선택',self.select_file,'TButton'),
            ('run_button','자료 검사하기',self.start,'Primary.TButton'),
            ('cancel_button','검사 중지',self.cancel_run,'TButton'),
            ('reset_button','선택 초기화',self.reset,'Quiet.TButton'),
            ('save_button','결과 Excel 저장',self.save,'TButton')):
            button=actions.add(ttk.Button(actions,text=text,command=command,style=style))
            setattr(self,attr,button)
        self.cancel_button.configure(state='disabled');self.save_button.configure(state='disabled')
        self.source_label=tk.StringVar(value='예제를 불러오거나 입력 XLSX를 선택해 주세요.')
        ttk.Label(card.body,textvariable=self.source_label,style='Muted.TLabel',wraplength=1000).pack(fill='x',pady=(self.display.px(10),0))

    def _build_summary(self,page):
        self.metrics_grid=BentoGrid(page);self.metrics_grid.pack(fill='x')
        self.cards={}
        for key in ('CFO','CFI','CFF','FX','CASH_DELTA'):
            card=BentoCard(self.metrics_grid,LABELS[key]+' (원)')
            self.cards[key]=tk.StringVar(value='—')
            ttk.Label(card.body,textvariable=self.cards[key],style='Metric.TLabel',anchor='e').pack(fill='x')
            self.metrics_grid.add(card,span=2 if key=='CFO' else 1)

    def _build_tabs(self,page):
        card=BentoCard(page,'계산 근거와 차이를 확인해요')
        card.pack(fill='both',expand=True)
        self.notebook=ttk.Notebook(card.body);self.notebook.pack(fill='both',expand=True)
        frames=[]
        for title in ('차이·입력 오류','현금흐름 명세','원행·계산 근거','입력 안내'):
            frame=ttk.Frame(self.notebook,padding=self.display.px(8))
            self.notebook.add(frame,text=title);frames.append(frame)
        self._build_filters(frames[0])
        self.diff_tree=make_table(frames[0],self.display,('code','ref','key','diff','message'),('오류코드','원행','키','차이 (원)','확인할 내용'),(170,140,130,100,540))
        self.diff_tree.bind('<Double-1>',self.show_issue)
        self.line_tree=make_table(frames[1],self.display,('line','category','amount','state'),('항목키','분류','계산금액 (원)','상태'),(260,190,220,500))
        self.trace_tree=make_table(frames[2],self.display,('line','amount','refs','formula'),('항목키','기여금액 (원)','원행 참조','수식·설명'),(200,150,400,500))
        ttk.Label(frames[3],text=HELP_TEXT,justify='left',wraplength=980).pack(fill='x',anchor='nw')

    def _build_filters(self,parent):
        bar=FlowFrame(parent);bar.pack(fill='x',pady=(0,self.display.px(8)))
        bar.add(ttk.Label(bar,text='차이 필터'))
        self.filter_mode=tk.StringVar(value='전체')
        self.filter_combo=bar.add(ttk.Combobox(bar,textvariable=self.filter_mode,values=('전체','금액 차이','입력·확인 오류'),state='readonly',width=15))
        self.filter_combo.bind('<<ComboboxSelected>>',lambda event:self.render_issues())
        self.search=tk.StringVar()
        bar.add(ttk.Label(bar,text='키·오류 검색'))
        self.search_entry=bar.add(ttk.Entry(bar,textvariable=self.search,width=24))
        self.search.trace_add('write',lambda *_:self.render_issues())
