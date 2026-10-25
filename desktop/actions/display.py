"""Display native desktop actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill

class DisplayActions:

    def reflow_display(self):

        def walk(parent):
            for widget in parent.winfo_children():
                if isinstance(widget, FlowFrame):
                    widget.schedule()
                walk(widget)
        walk(self.root)
        for scroll in self.tab_scrolls.values():
            scroll.refresh()
        if hasattr(self, 'proc_scroll'):
            self.proc_scroll.refresh()

    def set_ui_zoom(self, scale):
        self.display.apply(scale=int(scale))
        self.ui_zoom.set(str(int(scale)) + '%')
        self.reflow_display()
        self.status.set('화면 배율 ' + str(int(scale)) + '% · Ctrl + / - 로 조절, Ctrl + 0 기본 배율')
        return 'break'

    def step_ui_zoom(self, step):
        choices = [90, 100, 110, 125, 150, 175]
        current = int(self.ui_zoom.get().rstrip('%'))
        index = choices.index(current)
        return self.set_ui_zoom(choices[max(0, min(len(choices) - 1, index + step))])
