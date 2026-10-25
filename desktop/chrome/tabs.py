"""Build each screen once and keep original notebook APIs for guarded actions."""
from tkinter import ttk
from desktop_display import ScrollableFrame
from desktop.widgets.navigation import ROUTES
from desktop.widgets.cards import BentoCard
from desktop.widgets.flow import FlowFrame
from desktop.views.home import Dashboard


def build_tabs(host,parent):
    host.nb=ttk.Notebook(parent,style='Bento.TNotebook',takefocus=False)
    host.nb.pack(fill='both',expand=True,padx=host.display.px(18),pady=(0,host.display.px(8)))
    host.tabs={}
    host.tab_scrolls={}
    contents={}
    for key,label,_ in ROUTES:
        frame=ttk.Frame(host.nb,style='Page.TFrame')
        host.nb.add(frame,text=label)
        host.tabs[key]=frame
        if key=='절차·조서':
            contents[key]=frame
        else:
            scroll=ScrollableFrame(frame)
            scroll.configure(style='Page.TFrame')
            scroll.canvas.configure(background='#F4F6FA')
            scroll.inner.configure(style='Page.TFrame')
            scroll.pack(fill='both',expand=True)
            host.tab_scrolls[key]=scroll
            contents[key]=scroll.inner
    host.dashboard=Dashboard(contents['업무 요약'],host)
    for key,builder in (
        ('자료·검사',host.build_inputs),('원장·리드',host.build_lead),
        ('결과 상세',host.build_results),('검토후보',host.build_risks),
        ('절차·조서',host.build_procedures),('증거·검토의견',host.build_evidence),
        ('자료요청',host.build_requests),('작업 이력',host.build_history)):
        builder(contents[key])
    workflow=BentoCard(contents['계획·절차·취합'],'감사계획과 감사파일 관리',
             '판단·수행·승인은 사람이 기록하고, 프로그램은 누락과 근거 변경을 점검해요.')
    workflow.pack(fill='both',expand=True)
    host.build_workflow(workflow.body,FlowFrame)
    host.nb.bind('<<NotebookTabChanged>>',host.on_screen_changed)
    host.nb.bind('<Control-Tab>',lambda _:host.navigate_adjacent(1))
    host.nb.bind('<Control-Shift-Tab>',lambda _:host.navigate_adjacent(-1))
    host.nb.bind('<Left>',lambda _:host.navigate_adjacent(-1))
    host.nb.bind('<Right>',lambda _:host.navigate_adjacent(1))
    host.nb.select(host.tabs['업무 요약'])
