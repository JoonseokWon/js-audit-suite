"""Compatibility façade for modular DPI metrics, typography and form widgets."""
import ctypes,math,sys,weakref
import tkinter as tk
from tkinter import ttk,font as tkfont
from tkinter.scrolledtext import ScrolledText
from dpi_support.constants import *
from dpi_support.metrics import normalize_scale,display_metrics,window_geometry
from dpi_support.monitors import system_dpi,work_area
from dpi_support.awareness import _awareness_mode,_enable_windows
from dpi_support.manager import DisplayManager
from dpi_support.widgets import create_scrolled_text,create_editable_text,ScrollableFrame

_awareness=None

def enable_dpi_awareness():
    """Idempotent source fallback before constructing Tk; never changes OS settings."""
    global _awareness
    if _awareness is not None:return dict(_awareness)
    if sys.platform!='win32':
        _awareness={'mode':'platform','status':'not_windows','enabled':False,'method':'none'}
    else:
        try:
            user32=ctypes.WinDLL('user32',use_last_error=True,winmode=0x800)
            try:shcore=ctypes.WinDLL('shcore',use_last_error=True,winmode=0x800)
            except OSError:shcore=None
            _awareness=_enable_windows(user32,shcore)
        except (AttributeError,OSError):
            _awareness={'mode':'unknown','status':'unavailable','enabled':False,'method':'none'}
    return dict(_awareness)
