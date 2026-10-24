"""Process-local settings; Tcl/Tk selection is explicit and GUI-only."""
import os,re,sys
from pathlib import Path
DPI_STATUS=None

def _resource_root():
    return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))

def configure():
    """Configure calculation paths without importing Tk or changing its env."""
    os.environ['OPENPYXL_LXML']='False'
    os.environ['OPENPYXL_DEFUSEDXML']='True'
    return _resource_root()

def _library_family(folder,component):
    """Read script metadata, never execute Tcl while choosing a library."""
    filename='init.tcl' if component=='tcl' else 'tk.tcl'
    try:
        with (Path(folder)/filename).open(encoding='utf-8-sig') as source:
            header=source.read(16384)
    except (OSError,UnicodeError):
        return None
    match=re.search(r'^\s*package\s+require\s+-exact\s+'+component+r'\s+(\d+)\.(\d+)(?:\.\d+)?\s*(?:;[^\n]*)?$',header,re.I|re.M)
    return tuple(map(int,match.groups())) if match else None

def configure_tk_libraries():
    """Select matching GUI scripts, leaving installed Python discovery intact.

    Source bundles can contain Tcl/Tk 9 while a CI Python uses 8.6. Only a
    matching major/minor family is selected; Tcl's own ``-exact`` startup
    check still validates the patch version. A frozen EXE must use its own
    matching packaged scripts. Explicit compatible user paths are preserved.
    No interpreter or window is created here.
    """
    import _tkinter
    root=_resource_root()
    frozen=bool(getattr(sys,'frozen',False))
    selection={}
    for name,component,folder,packaged,version in (
        ('TCL_LIBRARY','tcl','tcl_library','_tcl_data',_tkinter.TCL_VERSION),
        ('TK_LIBRARY','tk','tk_library','_tk_data',_tkinter.TK_VERSION),
    ):
        family=tuple(map(int,str(version).split('.')[:2]))
        candidate=root/packaged if frozen else root/'.runtime'/folder
        existing=os.environ.get(name)
        if frozen:
            if _library_family(candidate,component)!=family:
                raise RuntimeError(f'{name}: packaged {component} scripts do not match the {version} binary: {candidate}')
            selection[name]=str(candidate)
        elif existing:
            if _library_family(existing,component)==family:
                selection[name]=existing
            elif Path(existing).resolve() in ((root/'.runtime'/folder).resolve(),(root/packaged).resolve()):
                # Discard only this application's stale paths; Python then
                # discovers the scripts installed with its own Tcl/Tk binary.
                selection[name]=str(candidate) if _library_family(candidate,component)==family else None
            else:
                raise RuntimeError(f'{name}: configured {component} scripts do not match the {version} binary: {existing}')
        else:
            selection[name]=str(candidate) if _library_family(candidate,component)==family else None
    # Validate both libraries before making any environment changes.
    for name,path in selection.items():
        if path is None:os.environ.pop(name,None)
        else:os.environ[name]=path
    return dict(selection,tcl_version=str(_tkinter.TCL_VERSION),tk_version=str(_tkinter.TK_VERSION),mode='frozen' if frozen else 'source')
