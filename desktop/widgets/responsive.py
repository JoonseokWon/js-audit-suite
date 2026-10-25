"""A small deterministic Bento layout in logical units, shared by all summaries."""
from tkinter import ttk


def column_count(logical_width):
    return 4 if logical_width >= 1080 else (2 if logical_width >= 660 else 1)


def placements(spans, columns):
    row = column = 0
    result = []
    for desired in spans:
        span = min(columns, max(1, int(desired)))
        if column + span > columns:
            row += 1
            column = 0
        result.append((row, column, span))
        column += span
        if column == columns:
            row += 1
            column = 0
    return result


class BentoGrid(ttk.Frame):
    def __init__(self, parent, gap=14, **kwargs):
        super().__init__(parent, style='Page.TFrame', **kwargs)
        self.gap = gap
        self.items = []
        self._pending = None
        self._layout_key = None
        self.bind('<Configure>', self._schedule)
        self.bind('<Destroy>', self._cleanup, add='+')

    def add(self, widget, span=1):
        self.items.append((widget, span))
        self._schedule()
        return widget

    def _schedule(self, event=None):
        if self._pending is None:
            self._pending = self._root().after_idle(self.reflow)

    def reflow(self):
        self._pending = None
        manager = getattr(self.winfo_toplevel(), 'audit_display', None)
        factor = manager.metrics['factor'] if manager else 1
        count = column_count(self.winfo_width()/factor)
        gap = manager.px(self.gap) if manager else self.gap
        key = (count, gap, len(self.items))
        if key == self._layout_key:
            return
        for c in range(4):
            self.columnconfigure(c, weight=1 if c<count else 0, uniform='bento')
        positions = placements([span for _,span in self.items],count)
        for (widget,_),(row,column,span) in zip(self.items,positions):
            widget.grid(row=row,column=column,columnspan=span,sticky='nsew',
                        padx=(0,gap if column+span<count else 0),pady=(0,gap))
        self._layout_key = key

    def refresh_layout(self):
        self._layout_key = None
        self._schedule()

    def _cleanup(self,event):
        if event.widget is self and self._pending is not None:
            try:
                self._root().after_cancel(self._pending)
            except Exception:
                pass
            self._pending = None
