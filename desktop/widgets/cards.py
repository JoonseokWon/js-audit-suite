"""Reusable rounded native card; no bitmap scaling or interactive canvas controls."""
import tkinter as tk
from tkinter import ttk
from desktop.design import COLORS


class BentoCard(ttk.Frame):
    def __init__(self, parent, title='', description=None, padding=18, **kwargs):
        super().__init__(parent, style='Page.TFrame', **kwargs)
        self.padding = padding
        self.canvas = tk.Canvas(self, background=COLORS['page'], highlightthickness=0,
                                borderwidth=0, height=110)
        self.canvas.pack(fill='both', expand=True)
        self.surface = ttk.Frame(self.canvas, style='Card.TFrame')
        self.window = self.canvas.create_window(9, 9, anchor='nw', window=self.surface)
        self.heading = ttk.Label(self.surface, text=title, style='Section.TLabel')
        self.heading.audit_managed_wrap = True
        if title:
            self.heading.pack(anchor='w', fill='x', pady=(0,8))
        self.description = None
        if description:
            self.description = ttk.Label(self.surface, text=description, style='Muted.TLabel',
                                         wraplength=450, justify='left')
            self.description.audit_managed_wrap = True
            self.description.pack(fill='x', pady=(0,12))
        self.body = ttk.Frame(self.surface, style='Card.TFrame')
        self.body.pack(fill='both', expand=True)
        self._pending = None
        self._closed = False
        self.canvas.bind('<Configure>', self._schedule)
        self.surface.bind('<Configure>', self._schedule)
        self.bind('<Destroy>', self._cleanup, add='+')
        self._schedule()

    def _schedule(self, event=None):
        if not self._closed and self._pending is None:
            self._pending = self._root().after_idle(self._layout)

    def _layout(self):
        self._pending = None
        if self._closed:
            return
        manager = getattr(self.winfo_toplevel(), 'audit_display', None)
        px = manager.px if manager else lambda x: int(x)
        margin, radius = px(9), px(17)
        w = max(40, self.canvas.winfo_width())
        self.surface.configure(padding=px(max(4, self.padding-9)))
        self.canvas.itemconfigure(self.window, width=max(20,w-2*margin))
        requested = self.surface.winfo_reqheight()+2*margin
        if abs(int(float(self.canvas.cget('height')))-requested)>1:
            self.canvas.configure(height=requested)
        actual_height = self.canvas.winfo_height()
        h = actual_height if actual_height > 1 else requested
        self.canvas.coords(self.window, margin, margin)
        self.canvas.itemconfigure(self.window, height=max(20,h-2*margin))
        self.canvas.delete('card-outline')
        x1,y1,x2,y2=1,1,w-1,h-1
        points=(x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,
                x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,
                x1,y2,x1,y2-radius,x1,y1+radius,x1,y1)
        self.canvas.create_polygon(points, smooth=True, splinesteps=24,
                                   fill=COLORS['surface'], outline=COLORS['border'],
                                   width=1, tags='card-outline')
        self.canvas.tag_lower('card-outline')
        for label in (self.heading, self.description):
            if label is not None:
                label.configure(wraplength=max(60,w-2*margin-2*px(self.padding)))

    def _cleanup(self, event):
        if event.widget is self:
            self._closed = True
            if self._pending is not None:
                try:
                    self._root().after_cancel(self._pending)
                except tk.TclError:
                    pass
                self._pending = None

    def refresh_layout(self):
        self._schedule()
