"""Process-local Windows DPI awareness and explicit, testable Tk display metrics.

System awareness is intentional. Tk's per-display scaling does not establish that
every dialog and widget in this application handles mixed-DPI monitor moves.
Restart the application on the target display after changing Windows DPI.
No operating-system display settings, registry values, or accounting data change.
"""
from __future__ import annotations
import ctypes,math,sys,weakref
import tkinter as tk
from tkinter import ttk,font as tkfont
from tkinter.scrolledtext import ScrolledText

SCALE_OPTIONS=(90,100,110,125,150,175)
DPI_POLICY='system'
NORMAL_FONT='AuditUIFont'
TEXT_FONT='AuditTextFont'
SMALL_FONT='AuditSmallFont'
HEADING_FONT='AuditHeadingFont'
MONO_FONT='AuditMono'
_awareness=None

def _awareness_mode(user32):
    try:
        get=user32.GetThreadDpiAwarenessContext;get.restype=ctypes.c_void_p;get.argtypes=[]
        mode=user32.GetAwarenessFromDpiAwarenessContext;mode.restype=ctypes.c_int;mode.argtypes=[ctypes.c_void_p]
        return {0:'unaware',1:'system',2:'per_monitor'}.get(int(mode(get())),'unknown')
    except (AttributeError,OSError,ValueError):return 'unknown'

def _enable_windows(user32,shcore=None):
    """Use source fallback only; a frozen executable normally gets its manifest."""
    try:
        api=user32.SetProcessDpiAwarenessContext;api.argtypes=[ctypes.c_void_p];api.restype=ctypes.c_bool
        if api(ctypes.c_void_p(-2)):return {'mode':'system','status':'set','enabled':True,'method':'SetProcessDpiAwarenessContext'}
        # Windows forbids resetting awareness established by a manifest or a host.
        if ctypes.get_last_error()==5:
            mode=_awareness_mode(user32)
            return {'mode':mode,'status':'already_configured','enabled':mode in ('system','per_monitor'),'method':'manifest_or_host'}
    except (AttributeError,OSError):pass
    if shcore is not None:
        try:
            api=shcore.SetProcessDpiAwareness;api.argtypes=[ctypes.c_int];api.restype=ctypes.c_long
            hr=int(api(1))
            if hr==0:return {'mode':'system','status':'set','enabled':True,'method':'SetProcessDpiAwareness'}
            if hr in (-2147024891,2147942405):
                mode=_awareness_mode(user32)
                return {'mode':mode,'status':'already_configured','enabled':mode in ('system','per_monitor'),'method':'manifest_or_host'}
        except (AttributeError,OSError):pass
    try:
        api=user32.SetProcessDPIAware;api.argtypes=[];api.restype=ctypes.c_bool
        if api():return {'mode':'system','status':'set','enabled':True,'method':'SetProcessDPIAware'}
    except (AttributeError,OSError):pass
    mode=_awareness_mode(user32)
    return {'mode':mode,'status':'not_changed','enabled':mode in ('system','per_monitor'),'method':'unavailable_or_host'}

def enable_dpi_awareness():
    """Call before constructing Tk. Idempotent and limited to this process."""
    global _awareness
    if _awareness is not None:return dict(_awareness)
    if sys.platform!='win32':_awareness={'mode':'platform','status':'not_windows','enabled':False,'method':'none'}
    else:
        try:
            user32=ctypes.WinDLL('user32',use_last_error=True)
            try:shcore=ctypes.WinDLL('shcore',use_last_error=True)
            except OSError:shcore=None
            _awareness=_enable_windows(user32,shcore)
        except (AttributeError,OSError):_awareness={'mode':'unknown','status':'unavailable','enabled':False,'method':'none'}
    return dict(_awareness)

def normalize_scale(value):
    try:
        text=str(value).strip().removesuffix('%').strip()
        number=float(text)
    except (TypeError,ValueError):raise ValueError('화면 배율은 90·100·110·125·150·175% 중에서 선택하세요.') from None
    if not math.isfinite(number) or number not in SCALE_OPTIONS:raise ValueError('지원하지 않는 화면 배율')
    return int(number)

def display_metrics(dpi=96,scale=100,linespace=None):
    dpi=float(dpi)
    if not math.isfinite(dpi) or not 48<=dpi<=768:raise ValueError('유효한 DPI 범위가 아닙니다.')
    percent=normalize_scale(scale);factor=dpi/96*percent/100
    px=lambda n:max(1,round(n*factor))
    line=math.ceil(11*dpi/72*percent/100*1.4) if linespace is None else int(linespace)
    return {'dpi':dpi,'percent':percent,'factor':factor,'tk_scaling':dpi/72*percent/100,
            'normal_points':11,'small_points':10,'row_height':max(px(30),line+px(8)),
            'column_width':px(170),'button_padding':(px(10),px(6)),'scrollbar_width':px(16)}

def window_geometry(work_area,dpi=96,scale=100):
    """Client geometry with enough margins for the Windows frame and taskbar."""
    if len(work_area)!=4:raise ValueError('작업영역은 left, top, right, bottom이어야 합니다.')
    left,top,right,bottom=map(int,work_area);w,h=right-left,bottom-top
    if w<160 or h<160:raise ValueError('작업영역이 너무 작습니다.')
    metric=display_metrics(dpi,scale);factor=metric['factor'];osfactor=float(dpi)/96
    margin_x=min(max(12,round(24*osfactor)),w//8)
    frame_margin=min(max(32,round(64*osfactor)),h//4)
    # App text zoom must not force the window or its minimum size to grow.
    width=min(round(1680*osfactor),w-2*margin_x)
    height=min(round(1080*osfactor),h-frame_margin)
    x=left+(w-width)//2;y=top+max(8,round(8*osfactor))
    return {'width':width,'height':height,'x':x,'y':y,
            'min_width':min(width,960),'min_height':min(height,640),
            'work_area':(left,top,right,bottom)}

def system_dpi(root=None):
    if sys.platform=='win32':
        try:
            user=ctypes.WinDLL('user32',use_last_error=True)
            if root is not None:
                get=user.GetDpiForWindow;get.argtypes=[ctypes.c_void_p];get.restype=ctypes.c_uint
                value=int(get(root.winfo_id()))
            else:
                get=user.GetDpiForSystem;get.argtypes=[];get.restype=ctypes.c_uint;value=int(get())
            if 48<=value<=768:return float(value)
        except (AttributeError,OSError,tk.TclError):pass
    if root is not None:
        try:return float(root.winfo_fpixels('1i'))
        except (tk.TclError,ValueError):pass
    return 96.0

def work_area(root=None):
    if sys.platform=='win32':
        from ctypes import wintypes
        class MONITORINFO(ctypes.Structure):
            _fields_=[('cbSize',wintypes.DWORD),('rcMonitor',wintypes.RECT),('rcWork',wintypes.RECT),('dwFlags',wintypes.DWORD)]
        try:
            user=ctypes.WinDLL('user32',use_last_error=True)
            if root is not None:
                monitor=user.MonitorFromWindow;monitor.argtypes=[wintypes.HWND,wintypes.DWORD];monitor.restype=wintypes.HMONITOR
                info=MONITORINFO();info.cbSize=ctypes.sizeof(info)
                get=user.GetMonitorInfoW;get.argtypes=[wintypes.HMONITOR,ctypes.POINTER(MONITORINFO)];get.restype=wintypes.BOOL
                if get(monitor(root.winfo_id(),2),ctypes.byref(info)):
                    r=info.rcWork;return (r.left,r.top,r.right,r.bottom)
            rect=wintypes.RECT()
            if user.SystemParametersInfoW(48,0,ctypes.byref(rect),0):return (rect.left,rect.top,rect.right,rect.bottom)
        except (AttributeError,OSError,tk.TclError):pass
    if root is not None:return (0,0,root.winfo_screenwidth(),root.winfo_screenheight())
    return (0,0,1280,800)

class DisplayManager:
    def __init__(self,root,scale=100,*,dpi=None,work_area_override=None):
        self.root=root;self.dpi=system_dpi(root) if dpi is None else float(dpi)
        self.work_area_override=work_area_override;self.percent=normalize_scale(scale);self.scale=self.percent
        self.font=NORMAL_FONT;self.text_font=TEXT_FONT;self.small_font=SMALL_FONT;self.heading_font=HEADING_FONT;self.bold_font=HEADING_FONT;self.mono_font=MONO_FONT
        self._trees=weakref.WeakKeyDictionary();self.fonts={};self.style=ttk.Style(root)
        available=set(tkfont.families(root))
        self.family=next((x for x in ('맑은 고딕','Malgun Gothic','Segoe UI','DejaVu Sans') if x in available),'TkDefaultFont')
        for name in (NORMAL_FONT,TEXT_FONT,SMALL_FONT,HEADING_FONT,MONO_FONT):
            self.fonts[name]=tkfont.nametofont(name,root=root) if name in tkfont.names(root) else tkfont.Font(root=root,name=name)
        root._audit_display_manager=self
        self.apply(self.percent);self.fit_window(initial=True)

    def px(self,value):return max(1,round(float(value)*self.metrics['factor']))

    def apply(self,scale=100):
        percent=normalize_scale(scale);self.percent=self.scale=percent
        self.metrics=display_metrics(self.dpi,percent)
        self.root.tk.call('tk','scaling',self.metrics['tk_scaling'])
        for name,points,weight in [(NORMAL_FONT,11,'normal'),(TEXT_FONT,11,'normal'),(SMALL_FONT,10,'normal'),(HEADING_FONT,11,'bold'),(MONO_FONT,10,'normal')]:
            self.fonts[name].configure(family='Consolas' if name==MONO_FONT and sys.platform=='win32' else self.family,size=points,weight=weight)
        for name in ('TkDefaultFont','TkTextFont','TkMenuFont','TkHeadingFont','TkCaptionFont','TkSmallCaptionFont','TkTooltipFont','TkIconFont'):
            if name in tkfont.names(self.root):tkfont.nametofont(name,root=self.root).configure(family=self.family,size=10 if name in ('TkSmallCaptionFont','TkTooltipFont') else 11)
        self.metrics=display_metrics(self.dpi,percent,self.fonts[NORMAL_FONT].metrics('linespace'))
        self.factor=self.metrics['factor']
        self.style.configure('.',font=NORMAL_FONT)
        self.style.configure('Treeview',font=NORMAL_FONT,rowheight=self.metrics['row_height'])
        self.style.configure('Treeview.Heading',font=HEADING_FONT,padding=(self.px(5),self.px(4)))
        self.style.configure('TButton',font=NORMAL_FONT,padding=self.metrics['button_padding'])
        self.style.configure('TEntry',font=NORMAL_FONT,padding=(self.px(4),self.px(4)))
        self.style.configure('TCombobox',font=NORMAL_FONT,padding=(self.px(4),self.px(4)))
        self.style.configure('TNotebook.Tab',font=SMALL_FONT,padding=(self.px(8),self.px(5)))
        self.style.configure('Vertical.TScrollbar',width=self.metrics['scrollbar_width'],arrowsize=self.px(14))
        self.style.configure('Horizontal.TScrollbar',width=self.metrics['scrollbar_width'],arrowsize=self.px(14))
        self.refresh_widgets()
        self.root.event_generate('<<AuditDisplayChanged>>',when='tail')
        return dict(self.metrics)

    def register_tree(self,tree,base_widths=None,*,reset=False,force=False):
        widths={} if reset or force else dict(self._trees.get(tree,{}))
        declared=dict(base_widths or {})
        for column in tree['columns']:
            if column in declared:widths[column]=float(declared[column])
            elif column not in widths:widths[column]=float(tree.column(column,'width'))
            tree.column(column,width=self.px(widths[column]),minwidth=self.px(40))
        self._trees[tree]=widths
        return widths

    def refresh_widgets(self):
        def walk(widget):
            for child in widget.winfo_children():
                if getattr(child,'audit_native_text',False):child.refresh_font()
                elif isinstance(child,ttk.Treeview):self.register_tree(child)
                elif isinstance(child,(tk.Text,tk.Listbox)):
                    current=str(child.cget('font'))
                    if current not in (NORMAL_FONT,TEXT_FONT,SMALL_FONT,HEADING_FONT,MONO_FONT):child.configure(font=TEXT_FONT if isinstance(child,tk.Text) else NORMAL_FONT)
                walk(child)
        walk(self.root)

    def fit_window(self,initial=False):
        area=self.work_area_override or work_area(self.root)
        bounds=window_geometry(area,self.dpi,self.percent)
        self.root.minsize(bounds['min_width'],bounds['min_height'])
        if initial:
            self.root.geometry(f"{bounds['width']}x{bounds['height']}+{bounds['x']}+{bounds['y']}")
        else:
            self.root.update_idletasks()
            width=min(self.root.winfo_width(),bounds['width']);height=min(self.root.winfo_height(),bounds['height'])
            x=max(area[0],min(self.root.winfo_x(),area[2]-width));y=max(area[1],min(self.root.winfo_y(),area[3]-height-32))
            self.root.geometry(f'{width}x{height}+{x}+{y}')
        return bounds

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
