"""Native desktop composition; state, navigation and each screen live separately."""
import tkinter as tk
from tkinter import ttk
from pathlib import Path
import sys,threading,queue
from desktop.shared import resource,CATALOG,TITLE
from desktop.design import COLORS,apply_theme
from desktop_display import DisplayManager,ScrollableFrame
from desktop.widgets.navigation import Sidebar
from desktop.chrome.header import build_header
from desktop.chrome.tabs import build_tabs
from desktop.chrome.routing import ShellRouting


class DesktopShellMixin(ShellRouting):
    def __init__(self,root,sector_home=None):
        self.root=root
        root.title(TITLE)
        ttk.Style(root).theme_use('clam')
        self.display=DisplayManager(root,scale=100)
        root.audit_display=self.display
        apply_theme(root,self.display)
        if sys.platform=='win32':root.iconbitmap(default=str(resource('assets','js-audit.ico')))
        self.ws=None
        self.busy=False
        self.cancel=threading.Event()
        self.queue=queue.Queue()
        self.current_pid=None
        self.table_rows=[]
        self.page=0
        self.closing=False
        self.init_ai(CATALOG)
        from sector_demo import list_companies,default_storage_root
        self.sector_home=Path(sector_home) if sector_home is not None else default_storage_root()
        self.active_sector=None
        self.sector_options=list_companies(resource('sector_resources'))
        self.info=tk.StringVar(value='회사를 선택하거나 저장된 업무를 여세요.')
        self.status=tk.StringVar(value='업무를 선택하면 자료와 조서를 이어서 열 수 있어요.')
        self.app_shell=ttk.Frame(root,style='Page.TFrame')
        self.app_shell.pack(fill='both',expand=True)
        self.app_shell.rowconfigure(0,weight=1)
        self.app_shell.columnconfigure(1,weight=1)
        side=ScrollableFrame(self.app_shell)
        side.grid(row=0,column=0,sticky='nsew')
        side.canvas.configure(width=self.display.px(224),background=COLORS['surface'])
        side.inner.configure(style='Sidebar.TFrame')
        self.sidebar_canvas=side.canvas
        self.sidebar_scroll=side
        self.sidebar=Sidebar(side.inner,self.display,self.navigate)
        self.sidebar.pack(fill='both',expand=True)
        content=ttk.Frame(self.app_shell,style='Page.TFrame')
        content.grid(row=0,column=1,sticky='nsew')
        self.header=build_header(self,content)
        title=ttk.Frame(content,style='Page.TFrame',padding=(self.display.px(22),self.display.px(15)))
        title.pack(fill='x')
        self.screen_title=tk.StringVar(value='업무 요약')
        self.context_text=tk.StringVar(value='자료·대사·조서를 한 업무에 연결해요.')
        ttk.Label(title,textvariable=self.screen_title,style='Page.TLabel',font='AuditTitle').pack(anchor='w')
        self.info_label=ttk.Label(title,textvariable=self.context_text,style='PageMuted.TLabel')
        self.info_label.pack(anchor='w',pady=(5,0))
        self.status_label=ttk.Label(content,textvariable=self.status,style='PageMuted.TLabel',
                                   padding=(self.display.px(22),self.display.px(7)),wraplength=900)
        self.status_label.pack(side='bottom',fill='x')
        build_tabs(self,content)
        self.request_saved=self.request_signature()
        self.review_saved=('','')
        self.display.refresh_widgets()
        self.display.fit_window(initial=True)
        root.bind('<<AuditDisplayChanged>>',lambda _:self.reflow_display(),add='+')
        root.bind('<Control-plus>',lambda _:self.step_ui_zoom(1))
        root.bind('<Control-equal>',lambda _:self.step_ui_zoom(1))
        root.bind('<Control-minus>',lambda _:self.step_ui_zoom(-1))
        root.bind('<Control-Key-0>',lambda _:self.set_ui_zoom(100))
        root.bind('<Control-Tab>',lambda _:self.navigate_adjacent(1))
        root.bind('<Control-Shift-Tab>',lambda _:self.navigate_adjacent(-1))
        root.protocol('WM_DELETE_WINDOW',self.close)
        self._poll_timer=root.after(80,self.poll)
        root.bind('<Destroy>',self._cancel_poll,add='+')
        self._bind_wrapping(self.app_shell)
        self.sidebar.select('업무 요약')

    def _bind_wrapping(self,parent):
        for child in parent.winfo_children():
            if (isinstance(child,ttk.Label) and child.cget('wraplength')
                    and not getattr(child,'audit_managed_wrap',False)):
                parent.bind('<Configure>',lambda event,w=child:w.configure(
                    wraplength=max(80,event.width-self.display.px(20))),add='+')
            self._bind_wrapping(child)

    def _cancel_poll(self,event):
        if event.widget is self.root and getattr(self,'_poll_timer',None) is not None:
            try:self.root.after_cancel(self._poll_timer)
            except tk.TclError:pass
            self._poll_timer=None
