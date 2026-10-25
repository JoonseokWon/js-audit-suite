"""Read-only queries for this application window and monitor work area."""
import ctypes,sys
import tkinter as tk

def system_dpi(root=None):
    if sys.platform=='win32':
        try:
            user=ctypes.WinDLL('user32.dll',use_last_error=True,winmode=0x800)
            if root is not None:
                try:
                    get=user.GetDpiForWindow;get.argtypes=[ctypes.c_void_p];get.restype=ctypes.c_uint
                    value=int(get(root.winfo_id()))
                    if 48<=value<=768:return float(value)
                except (AttributeError,OSError):pass
                try:
                    shcore=ctypes.WinDLL('shcore.dll',use_last_error=True,winmode=0x800)
                    monitor=user.MonitorFromWindow;monitor.argtypes=[ctypes.c_void_p,ctypes.c_uint];monitor.restype=ctypes.c_void_p
                    get=shcore.GetDpiForMonitor
                    get.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_uint)];get.restype=ctypes.c_long
                    x,y=ctypes.c_uint(),ctypes.c_uint()
                    if get(monitor(root.winfo_id(),2),0,ctypes.byref(x),ctypes.byref(y))==0 and 48<=x.value<=768:return float(x.value)
                except (AttributeError,OSError):pass
            try:
                get=user.GetDpiForSystem;get.argtypes=[];get.restype=ctypes.c_uint;value=int(get())
                if 48<=value<=768:return float(value)
            except (AttributeError,OSError):pass
            # Last Windows fallback reads device DPI, not Tk's current scaling.
            # winfo_fpixels includes app text zoom and would feed that zoom back
            # into the OS DPI on the next tracking tick.
            gdi=ctypes.WinDLL('gdi32.dll',use_last_error=True,winmode=0x800)
            user.GetDC.argtypes=[ctypes.c_void_p];user.GetDC.restype=ctypes.c_void_p
            user.ReleaseDC.argtypes=[ctypes.c_void_p,ctypes.c_void_p];user.ReleaseDC.restype=ctypes.c_int
            gdi.GetDeviceCaps.argtypes=[ctypes.c_void_p,ctypes.c_int];gdi.GetDeviceCaps.restype=ctypes.c_int
            context=user.GetDC(None)
            if context:
                try:value=int(gdi.GetDeviceCaps(context,90))
                finally:user.ReleaseDC(None,context)
                if 48<=value<=768:return float(value)
        except (AttributeError,OSError,tk.TclError):pass
        return 96.0
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
            user=ctypes.WinDLL('user32.dll',use_last_error=True,winmode=0x800)
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
