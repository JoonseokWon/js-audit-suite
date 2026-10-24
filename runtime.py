"""Only process-local Tcl/Tk configuration, including frozen binaries."""
import os,sys
from pathlib import Path

def configure():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    resources=root/'.runtime'
    for name,folder in [('TCL_LIBRARY','tcl_library'),('TK_LIBRARY','tk_library')]:
        candidate=root/('_tcl_data' if name=='TCL_LIBRARY' else '_tk_data') if getattr(sys,'frozen',False) else resources/folder
        if candidate.is_dir():os.environ[name]=str(candidate)
    os.environ['OPENPYXL_LXML']='False'
    os.environ['OPENPYXL_DEFUSEDXML']='True'
    return root
