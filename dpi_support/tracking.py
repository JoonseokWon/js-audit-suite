"""Deliver native DPI changes to Tk without reentering Tcl from WndProc."""
import sys
import tkinter as tk
from .monitors import system_dpi
from .windows_hook import WindowsDpiHook


class WindowDpiTracker:
    def __init__(self, root, callback, initial_dpi):
        self.root, self.callback, self.dpi = root, callback, float(initial_dpi)
        self.hook, self.timer, self.closed = None, None, False
        self.status = {'tracking':'window_dpi_poll', 'native_hook':False}
        self.binding = root.bind('<Destroy>', self._destroyed, add='+')
        if sys.platform == 'win32':
            try:
                self.hook = WindowsDpiHook(root.winfo_id())
                self.status = {'tracking':'WM_DPICHANGED', 'native_hook':True}
            except (AttributeError, OSError) as error:
                self.status['hook_error'] = str(error)
        self.timer = root.after(120, self.poll)

    def poll(self):
        self.timer = None
        if self.closed:
            return
        try:
            pending = self.hook.pop() if self.hook else None
            # A working hook is authoritative. Re-querying a legacy system-DPI
            # fallback after a monitor notification could undo the new DPI.
            dpi = float(pending[0]) if pending else (self.dpi if self.hook else system_dpi(self.root))
            if abs(dpi-self.dpi) > .5:
                self.callback(dpi)
                self.dpi = dpi
            if not self.closed:
                self.timer = self.root.after(120, self.poll)
        except tk.TclError:
            self.close()

    def _destroyed(self, event):
        if event.widget is self.root:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.timer is not None:
            try:self.root.after_cancel(self.timer)
            except tk.TclError:pass
            self.timer = None
        if self.hook:
            self.hook.close()
        if self.binding:
            try:self.root.unbind('<Destroy>', self.binding)
            except tk.TclError:pass
            self.binding = None
