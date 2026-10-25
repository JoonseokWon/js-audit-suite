"""Wrapping action rows with no hidden primary control."""
import tkinter as tk
from tkinter import ttk

class FlowFrame(ttk.Frame):
    """Keep primary actions reachable when the window or text scale changes."""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.items = []
        self.pending = None
        self.layout = None
        self._closed = False
        self._variables = {}
        self.bind('<Configure>', lambda _: self.schedule())
        self.bind('<Destroy>', self.cleanup, add='+')

    def add(self, widget):
        self.items.append(widget)
        if isinstance(widget, ttk.Label):
            widget.audit_managed_wrap = True
        widget.bind('<Configure>', lambda _: self.schedule(), add='+')
        if 'textvariable' in widget.keys():
            variable = str(widget.cget('textvariable'))
            if variable and variable not in self._variables:
                command = self.register(lambda *_: self.schedule())
                self.tk.call('trace', 'add', 'variable', variable, 'write', command)
                self._variables[variable] = command
        self.schedule()
        return widget

    def schedule(self):
        if not self._closed and self.pending is None:
            self.pending = self._root().after_idle(self.reflow)

    def cleanup(self, event):
        if event.widget is self:
            self._closed = True
            for variable, command in self._variables.items():
                try:
                    self.tk.call('trace', 'remove', 'variable', variable, 'write', command)
                except tk.TclError:
                    pass
            self._variables.clear()
            if self.pending is not None:
                try:
                    self._root().after_cancel(self.pending)
                except tk.TclError:
                    pass
                self.pending = None

    def reflow(self):
        self.pending = None
        if self._closed:
            return
        if self.winfo_width() <= 1:
            # Hidden notebook pages receive a real Configure event when shown.
            # Waiting here used to keep every hidden action row polling forever.
            return
        manager = getattr(self.winfo_toplevel(), 'audit_display', None)
        px = manager.px if manager else lambda n: n
        gap, edge, vertical = px(10), px(1), px(3)
        width = max(1, self.winfo_width() - 2 * edge)
        rows = [[]]
        used = 0
        positions = []
        ordinary = [w for w in self.items if not getattr(w, 'flow_compact_only', False)]
        compact = sum(w.winfo_reqwidth() for w in ordinary) + gap * max(0, len(ordinary)-1) > width
        visible = [w for w in self.items if (not getattr(w, 'flow_secondary', False) if compact else not getattr(w, 'flow_compact_only', False))]
        for widget in self.items:
            if widget not in visible:
                widget.place_forget()
        for widget in visible:
            if isinstance(widget, ttk.Label):
                widget.configure(wraplength=width)
            w = min(width, widget.winfo_reqwidth())
            h = widget.winfo_reqheight()
            if rows[-1] and used + gap + w > width:
                rows.append([])
                used = 0
            rows[-1].append((widget, w, h))
            used += w + (gap if len(rows[-1]) > 1 else 0)
        y = vertical
        controls = (ttk.Button, ttk.Menubutton, ttk.Combobox, ttk.Entry)
        for row in rows:
            row_height = max((h for _, _, h in row), default=0)
            x = edge
            for index, (widget, w, h) in enumerate(row):
                if isinstance(widget, controls):
                    h = row_height
                if getattr(widget, 'flow_align_end', False) and index == len(row)-1:
                    x = edge + width - w
                positions.append((widget, x, y + (row_height-h)//2, w, h))
                x += w + gap
            y += row_height + gap
        layout = tuple(((str(w), x, y, width, height) for w, x, y, width, height in positions))
        total_height = max(1, y-gap+vertical)
        if layout != self.layout:
            for child, left, top, child_width, child_height in positions:
                child.place(x=left, y=top, width=child_width, height=child_height)
            self.configure(height=total_height)
            self.layout = layout
