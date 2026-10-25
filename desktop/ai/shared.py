"""Dependencies for this UI package; independent of desktop.shared."""
from pathlib import Path
import json, threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from common import AuditError,digest
from desktop_display import ScrollableFrame, create_scrolled_text, create_editable_text
from ai_provider import generate_draft, DEFAULT_MODEL
from local_ai_runtime import LocalAIRuntime
FIELD_LABELS={'purpose':'목적·주장','risk':'위험·기준','scope':'모집단·검사 범위','performed':'수행내용·근거·예외','conclusion':'판단·결론·추가절차'}

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
