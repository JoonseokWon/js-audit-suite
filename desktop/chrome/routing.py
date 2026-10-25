"""Read-only screen/module navigation with the existing unsaved-input guard."""
from adapters import MODULES
from common import AuditError
from desktop.design import apply_theme
from desktop.widgets.flow import FlowFrame


class ShellRouting:
    def navigate_adjacent(self,step):
        keys=list(self.tabs)
        selected=str(self.nb.select())
        index=next((i for i,key in enumerate(keys) if str(self.tabs[key])==selected),0)
        self.navigate(keys[(index+step)%len(keys)])
        return 'break'

    def navigate(self,key):
        if key not in self.tabs:
            raise AuditError('열 수 없는 화면이에요.')
        if self.busy:
            self.status.set('진행 중인 작업을 마치거나 중단한 뒤 화면을 이동할 수 있어요.')
            return False
        if not self.check_navigation():
            return False
        self.nb.select(self.tabs[key])
        self.sidebar.select(key)
        self.on_screen_changed()
        return True

    def route_module(self,module):
        if module not in MODULES:
            raise AuditError('지원하는 분석 모듈을 선택하세요.')
        if not self.navigate('자료·검사'):
            return False
        if self.module.get()!=module:
            self.file.set('')
        self.module.set(module)
        if self.ws and module in self.ws.latest():
            self.result_module.set(module)
            self.choose_result_module()
        self.status.set(module+' 분석을 선택했어요. 해당 계정의 자료를 등록하고 검사하세요.')
        return True

    def on_screen_changed(self,event=None):
        selected=str(self.nb.select())
        key=next((name for name,frame in self.tabs.items() if str(frame)==selected),'업무 요약')
        self.sidebar.select(key)
        self.screen_title.set({'절차·조서':'조서 초안·작성',
                               '계획·절차·취합':'감사계획·완료 점검'}.get(key,key))
        self.refresh_dashboard()

    def refresh_dashboard(self):
        if hasattr(self,'dashboard'):
            self.dashboard.refresh()
        if hasattr(self,'context_text'):
            if self.ws:
                e=self.ws.engagement
                scope=' · 연결재무제표' if e['회사코드']=='JS' else ''
                self.context_text.set(e['회사명']+scope+' · '+e['시작일']+' ~ '+e['기준일']+
                                      (' · 예제 자료' if e.get('더미업무') else ''))
            else:
                self.context_text.set('자료·대사·조서를 한 업무에 연결해요.')

    def reflow_display(self):
        apply_theme(self.root,self.display)
        def walk(parent):
            for widget in parent.winfo_children():
                if isinstance(widget,FlowFrame):widget.schedule()
                elif hasattr(widget,'refresh_layout'):widget.refresh_layout()
                walk(widget)
        walk(self.root)
        for scroll in self.tab_scrolls.values():scroll.refresh()
        if hasattr(self,'proc_scroll'):self.proc_scroll.refresh()
        if hasattr(self,'sidebar'):
            self.sidebar.refresh_layout()
            self.sidebar_canvas.configure(width=self.display.px(224))
