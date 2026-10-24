from pathlib import Path
import os
root=Path(SPECPATH)
os.environ['TCL_LIBRARY']=str(root/'.runtime/tcl_library')
os.environ['TK_LIBRARY']=str(root/'.runtime/tk_library')
a=Analysis([str(root/'app.py')],pathex=[str(root)],binaries=[],
    datas=[(str(root/'sector_resources'),'sector_resources'),(str(root/'raw_analytics'),'raw_analytics'),(str(root/'문서'),'문서'),(str(root/'samples'),'samples'),(str(root/'templates'),'templates'),(str(root/'procedure_catalog.json'),'.'),(str(root/'samples_specs.json'),'.'),(str(root/'new_specs.json'),'.'),(str(root/'v12_specs.json'),'.'),(str(root/'v13_specs.json'),'.'),(str(root/'worker_cases.json'),'.'),(str(root/'worker_library'),'worker_library'),(str(root/'financial_bridge'),'financial_bridge'),(str(root/'.runtime/tcl_library'),'_tcl_data'),(str(root/'.runtime/tk_library'),'_tk_data')],
    hiddenimports=['tkinter','tkinter.ttk','defusedxml.ElementTree','sqlite3','et_xmlfile','gla','fia','cash_analytics','sector_demo','procedures']+['worker_library.'+w+'.engine' for w in ('cash_finance','revenue_ar','inventory_ap','fixed_assets','leases','payroll','debt_tax','equity_disclosure','financial_reporting')],hookspath=[],hooksconfig={},runtime_hooks=[],
    excludes=['lxml','numpy','pandas','anthropic','pytest','requests'],noarchive=False,optimize=0)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='AuditSuite',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,runtime_tmpdir=None,console=False,disable_windowed_traceback=False,uac_admin=False,uac_uiaccess=False)
