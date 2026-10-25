"""Keyboard-accessible native sidebar with explicit selected-state text and color."""
from tkinter import ttk
from desktop.design import COLORS

ROUTES = (
    ('업무 요약','업무 요약','워크스페이스'),
    ('자료·검사','자료 등록·검사','워크스페이스'),
    ('원장·리드','원장 대사·리드','워크스페이스'),
    ('결과 상세','계산 결과','워크스페이스'),
    ('검토후보','검토할 항목','워크스페이스'),
    ('절차·조서','조서 초안·작성','감사 기록'),
    ('계획·절차·취합','감사계획·완료 점검','감사 기록'),
    ('증거·검토의견','증거·검토의견','감사 기록'),
    ('자료요청','자료 요청','감사 기록'),
    ('작업 이력','작업 이력','감사 기록'),
)


class Sidebar(ttk.Frame):
    def __init__(self,parent,display,on_select):
        super().__init__(parent,style='Sidebar.TFrame',padding=display.px(17))
        self.display=display
        self.buttons={}
        self.active=None
        style=ttk.Style(self)
        for name,bg,fg in (('Nav.TButton',COLORS['surface'], '#4E5968'),
                           ('Selected.Nav.TButton',COLORS['blue_soft'],COLORS['blue'])):
            style.configure(name,background=bg,foreground=fg,borderwidth=0,
                            anchor='w',padding=(display.px(12),display.px(10)))
            style.map(name,background=[('active',COLORS['blue_soft'])],
                      foreground=[('active',COLORS['blue'])])
        brand=ttk.Frame(self)
        brand.pack(fill='x',pady=(4,22))
        ttk.Label(brand,text='JS',font='AuditBrand',foreground=COLORS['blue']).pack(anchor='w')
        ttk.Label(brand,text='통합 감사',style='Brand.TLabel').pack(anchor='w',pady=(3,0))
        ttk.Label(brand,text='로컬 워크스페이스',style='Muted.TLabel').pack(anchor='w',pady=(5,0))
        group=None
        for key,label,section in ROUTES:
            if group!=section:
                ttk.Label(self,text=section,style='Muted.TLabel',font=display.small_font).pack(
                    anchor='w',pady=(17,8),padx=display.px(12))
                group=section
            button=ttk.Button(self,text=label,style='Nav.TButton',
                              command=lambda route=key:on_select(route))
            button.pack(fill='x',pady=2)
            self.buttons[key]=button
        self.footer=ttk.Frame(self)
        self.footer.pack(side='bottom',fill='x',pady=(12,0))
        ttk.Label(self.footer,text='v2.0.0 · 로컬 저장',style='Muted.TLabel',
                  font=display.small_font).pack(anchor='w')

    def select(self,key):
        for route,button in self.buttons.items():
            button.configure(style='Selected.Nav.TButton' if key==route else 'Nav.TButton')
        self.active=key

    def refresh_layout(self):
        px=self.display.px
        self.configure(padding=px(17))
        style=ttk.Style(self)
        for name in ('Nav.TButton','Selected.Nav.TButton'):
            style.configure(name,padding=(px(12),px(10)))
