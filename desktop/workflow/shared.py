"""Dependencies for this UI package; independent of desktop.shared."""
from pathlib import Path
from decimal import Decimal
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from common import AuditError, dumps
from desktop_display import ScrollableFrame, create_editable_text, create_scrolled_text
from .tables import _table,_fill

__all__=[name for name in globals() if not name.startswith('__')]


def install_facade(name,prefix):
    """Keep historical module monkeypatches visible in the small submodules."""
    import sys
    from types import ModuleType
    class ForwardingFacade(ModuleType):
        def __setattr__(self,key,value):
            ModuleType.__setattr__(self,key,value)
            if not key.startswith('__'):
                for namespace in self.__dict__.get('_forwarded_namespaces',()):
                    if key in namespace:namespace[key]=value
    module=sys.modules[name]
    module.__class__=ForwardingFacade
    module._forwarded_namespaces=tuple(value.__dict__ for key,value in tuple(sys.modules.items())
                                      if key==prefix or key.startswith(prefix+'.'))
