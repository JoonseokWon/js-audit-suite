"""Scrollable forms and the established native Unicode editor adapter."""
import sys
import tkinter as tk
from tkinter import ttk,font as tkfont
from tkinter.scrolledtext import ScrolledText
from .constants import TEXT_FONT,NORMAL_FONT,SMALL_FONT,HEADING_FONT,MONO_FONT

def create_scrolled_text(parent,**options):
    """A Text-compatible widget whose pack/grid methods manage its scroll frame."""
    options.setdefault('wrap','word')
    options.setdefault('font',TEXT_FONT if TEXT_FONT in tkfont.names(parent) else 'TkTextFont')
    text=ScrolledText(parent,**options);text._audit_scroll_frame=text.frame;text.audit_container=text.frame
    return text

def create_editable_text(parent,**options):
    """Use Windows' native inline IME for authored workpaper text only."""
    if sys.platform=='win32':
        from windows_text import WindowsText
        options.setdefault('font',TEXT_FONT if TEXT_FONT in tkfont.names(parent) else 'TkTextFont')
        return WindowsText(parent,**options)
    return create_scrolled_text(parent,**options)

class ScrollableFrame(ttk.Frame):
    """Scrollable form area; children are placed in .inner, with no global wheel hook."""
    def __init__(self,parent,*,horizontal=False,**options):
        super().__init__(parent,**options)
        self.horizontal=horizontal;self.canvas=tk.Canvas(self,highlightthickness=0,borderwidth=0)
        self.scrollbar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0,column=0,sticky='nsew');self.scrollbar.grid(row=0,column=1,sticky='ns')
        if horizontal:
            self.hscrollbar=ttk.Scrollbar(self,orient='horizontal',command=self.canvas.xview)
            self.canvas.configure(xscrollcommand=self.hscrollbar.set);self.hscrollbar.grid(row=1,column=0,sticky='ew')
        self.rowconfigure(0,weight=1);self.columnconfigure(0,weight=1)
        self.inner=ttk.Frame(self.canvas);self.window_id=self.canvas.create_window((0,0),window=self.inner,anchor='nw')
        self._wheel_tag='AuditFormWheel'+str(id(self));self._wheel_commands=[];self._pending=None;self._closed=False
        for sequence in ('<MouseWheel>','<Button-4>','<Button-5>'):
            self._wheel_commands.append(self.bind_class(self._wheel_tag,sequence,self._wheel))
        self.canvas.bind('<Configure>',self._resize);self.inner.bind('<Configure>',self._schedule)
        self.bind('<Destroy>',self._cleanup,add='+')
        self._schedule()

    def _resize(self,event=None):
        width=self.canvas.winfo_width()
        if self.horizontal:width=max(width,self.inner.winfo_reqwidth())
        self.canvas.itemconfigure(self.window_id,width=max(1,width));self._schedule()

    def _schedule(self,event=None):
        # A test/window owner may cancel every interpreter timer through root.
        # Register with the same root so its Tcl command is removed from the
        # correct Python owner's cleanup list as well.
        if not self._closed and self._pending is None:self._pending=self._root().after_idle(self.refresh)

    def refresh(self):
        # A manual refresh supersedes any scheduled one; do not lose that timer.
        pending=self._pending;self._pending=None
        if pending is not None:
            try:self._root().after_cancel(pending)
            except tk.TclError:pass
        if self._closed:return
        self.canvas.configure(scrollregion=self.canvas.bbox('all') or (0,0,1,1))
        def tag(widget):
            tags=list(widget.bindtags())
            if self._wheel_tag not in tags:widget.bindtags(tuple(tags[:2]+[self._wheel_tag]+tags[2:]))
            for child in widget.winfo_children():tag(child)
        tag(self.canvas)

    def _wheel(self,event):
        delta=getattr(event,'delta',0);number=getattr(event,'num',None)
        amount=-max(1,abs(round(delta/120)))*(1 if delta>0 else -1) if delta else (-1 if number==4 else 1)
        axis=self.canvas.xview if self.horizontal and getattr(event,'state',0)&1 else self.canvas.yview
        if axis()==(0.0,1.0):return None
        (self.canvas.xview_scroll if axis==self.canvas.xview else self.canvas.yview_scroll)(amount,'units')
        return 'break'

    def _cleanup(self,event):
        if event.widget is not self:return
        self._closed=True
        if self._pending is not None:
            try:self._root().after_cancel(self._pending)
            except tk.TclError:pass
            self._pending=None
        # tkinter.bind_class registers its callbacks on root, not this frame.
        for sequence in ('<MouseWheel>','<Button-4>','<Button-5>'):self.unbind_class(self._wheel_tag,sequence)
        for command in self._wheel_commands:
            if command:
                try:self._root().deletecommand(command)
                except (tk.TclError,AttributeError):pass
