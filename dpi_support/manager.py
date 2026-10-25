"""Apply logical typography and metrics to one Tk interpreter."""
import sys,weakref
import tkinter as tk
from tkinter import ttk,font as tkfont
from .constants import *
from .metrics import display_metrics,normalize_scale,window_geometry
from .monitors import system_dpi,work_area
from .tracking import WindowDpiTracker

class DisplayManager:
    def __init__(self,root,scale=100,*,dpi=None,work_area_override=None):
        previous=getattr(root,'_audit_display_manager',None)
        if previous is not None:previous.close()
        self.root=root;self.dpi=system_dpi(root) if dpi is None else float(dpi)
        self.tracker=None
        self.work_area_override=work_area_override;self.percent=normalize_scale(scale);self.scale=self.percent
        self.font=NORMAL_FONT;self.text_font=TEXT_FONT;self.small_font=SMALL_FONT;self.heading_font=HEADING_FONT;self.bold_font=HEADING_FONT;self.mono_font=MONO_FONT
        self._trees=weakref.WeakKeyDictionary();self.fonts={};self.style=ttk.Style(root)
        available=set(tkfont.families(root))
        self.family=next((x for x in ('맑은 고딕','Malgun Gothic','Segoe UI','DejaVu Sans') if x in available),'TkDefaultFont')
        # Keep the creating Font wrappers alive for the interpreter's lifetime.
        # Replacing a DisplayManager must not let an old wrapper's __del__ delete
        # the named fonts the new manager has just adopted.
        owners=getattr(root,'_audit_named_font_owners',{})
        for name in (NORMAL_FONT,TEXT_FONT,SMALL_FONT,HEADING_FONT,MONO_FONT):
            if name not in owners or name not in tkfont.names(root):
                owners[name]=tkfont.nametofont(name,root=root) if name in tkfont.names(root) else tkfont.Font(root=root,name=name)
            self.fonts[name]=owners[name]
        root._audit_named_font_owners=owners
        root._audit_display_manager=self
        self.apply(self.percent);self.fit_window(initial=True)
        if dpi is None and sys.platform=='win32':
            self.tracker=WindowDpiTracker(root,self.update_dpi,self.dpi)

    def px(self,value):return max(1,round(float(value)*self.metrics['factor']))

    def apply(self,scale=100):
        percent=normalize_scale(scale);self.percent=self.scale=percent
        self.metrics=display_metrics(self.dpi,percent)
        self.root.tk.call('tk','scaling',self.metrics['tk_scaling'])
        # Tk 8.6 caches instantiated font metrics. Reconfigure point sizes
        # without altering family/weight so custom 13/18/26pt design fonts also
        # follow application zoom and monitor changes. Negative pixel fonts
        # deliberately retain their declared pixel size.
        for name in tkfont.names(self.root):
            font=tkfont.nametofont(name,root=self.root)
            font.configure(size=int(font.cget('size')))
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

    def update_dpi(self,dpi):
        """Receive this app's monitor DPI, preserving the user's text zoom."""
        display_metrics(dpi,self.percent)  # Validate before mutating state.
        self.dpi=float(dpi)
        self.apply(self.percent)
        self.fit_window(initial=False)
        return dict(self.metrics)

    def close(self):
        if self.tracker is not None:
            self.tracker.close();self.tracker=None

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
