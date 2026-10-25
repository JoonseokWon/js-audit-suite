"""Separate native entry point. No engagement workspace is opened or mutated."""
import sys
import runtime
RESOURCE=runtime.configure()
runtime.configure_tk_libraries()
from desktop_display import enable_dpi_awareness,DisplayManager
enable_dpi_awareness()
from desktop.design import apply_theme
from .shared import tk,queue,sample_cases
from .inputs import InputActions
from .runner import RunnerActions
from .results import ResultActions
from .view import View


class CashFlowApp(InputActions,RunnerActions,ResultActions,View):
    def __init__(self,root):
        self.root=root
        self.display=DisplayManager(root,scale=100);root.audit_display=self.display
        if sys.platform=='win32':root.iconbitmap(default=str(RESOURCE/'assets/js-audit.ico'))
        self.result,self.source_path,self.example=None,None,None
        self.generation,self.cancel_event,self.running=0,None,False
        self.messages,self.cases=queue.Queue(),sample_cases()
        self._closed,self._poll_timer=False,None
        self.build_view()
        root.bind('<<AuditDisplayChanged>>',self.refresh_display,add='+')
        root.protocol('WM_DELETE_WINDOW',self.close)
        self._poll_timer=root.after(50,self.poll)

    def refresh_display(self,event=None):
        apply_theme(self.root,self.display)
        self.metrics_grid.refresh_layout()
        self.scroll.refresh()

    def set_zoom(self,value):
        self.display.apply(int(str(value).removesuffix('%')))
        self.zoom.set(str(self.display.percent)+'%')
        self.refresh_display()


def main():
    root=tk.Tk()
    CashFlowApp(root)
    root.mainloop()
    return 0
