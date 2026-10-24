"""GUI library selection across source Python/Tcl versions and frozen EXEs."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import runtime

class RuntimeGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for context in (
            patch.object(runtime,'_resource_root',return_value=self.root),
            patch.object(runtime.sys,'frozen',False,create=True),
            patch.dict(os.environ,{},clear=True),
            patch.dict(sys.modules,{'_tkinter':SimpleNamespace(TCL_VERSION='9.0',TK_VERSION='9.0')}),
        ):
            context.__enter__();self.addCleanup(context.__exit__,None,None,None)

    def scripts(self,version='9.0.4',frozen=False,base=None):
        base=base or self.root
        result={}
        for name,folder,filename,component in (
            ('TCL_LIBRARY','_tcl_data' if frozen else '.runtime/tcl_library','init.tcl','Tcl'),
            ('TK_LIBRARY','_tk_data' if frozen else '.runtime/tk_library','tk.tcl','Tk'),
        ):
            path=base/folder;path.mkdir(parents=True,exist_ok=True)
            (path/filename).write_text(f'# Script metadata\npackage require -exact {component} {version}\n',encoding='utf-8')
            result[name]=str(path)
        return result

    def use_86(self):
        sys.modules['_tkinter']=SimpleNamespace(TCL_VERSION='8.6',TK_VERSION='8.6')

    def test_calculation_configure_preserves_tk_env(self):
        os.environ.update(TCL_LIBRARY='custom-tcl',TK_LIBRARY='custom-tk')
        self.assertEqual(runtime.configure(),self.root)
        self.assertEqual(os.environ['TCL_LIBRARY'],'custom-tcl')
        self.assertEqual(os.environ['TK_LIBRARY'],'custom-tk')
        self.assertEqual(os.environ['OPENPYXL_LXML'],'False')
        self.assertEqual(os.environ['OPENPYXL_DEFUSEDXML'],'True')

    def test_calculation_configure_does_not_import_any_gui_module(self):
        code='import runtime,sys,json;runtime.configure();print(json.dumps([n for n in ("tkinter","_tkinter","desktop_display","app") if n in sys.modules]))'
        env=dict(os.environ)
        # This test uses a fresh process; it cannot inherit this suite's imports.
        result=subprocess.run([sys.executable,'-B','-X','utf8','-c',code],cwd=Path(__file__).resolve().parent,env=env,capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout),[])

    def test_matching_source_bundle_selected(self):
        expected=self.scripts()
        selected=runtime.configure_tk_libraries()
        self.assertEqual({key:selected[key] for key in expected},expected)
        self.assertEqual({key:os.environ[key] for key in expected},expected)
        self.assertEqual(selected['mode'],'source')

    def test_python_86_does_not_select_project_90_scripts(self):
        self.scripts();self.use_86()
        result=runtime.configure_tk_libraries()
        for key in ('TCL_LIBRARY','TK_LIBRARY'):
            self.assertIsNone(result[key]);self.assertNotIn(key,os.environ)

    def test_matching_explicit_paths_preserved(self):
        self.scripts()
        expected=self.scripts('8.6.14',base=self.root/'python-install')
        self.use_86();os.environ.update(expected)
        selected=runtime.configure_tk_libraries()
        self.assertEqual({key:selected[key] for key in expected},expected)

    def test_incompatible_explicit_paths_fail_without_mutation(self):
        expected=self.scripts('9.0.4',base=self.root/'custom-install')
        self.use_86();os.environ.update(expected)
        before=dict(os.environ)
        with self.assertRaisesRegex(RuntimeError,'TCL_LIBRARY.*8.6'):runtime.configure_tk_libraries()
        self.assertEqual(dict(os.environ),before)

    def test_stale_application_90_env_removed_for_86_native_discovery(self):
        os.environ.update(self.scripts());self.use_86()
        runtime.configure_tk_libraries()
        self.assertNotIn('TCL_LIBRARY',os.environ);self.assertNotIn('TK_LIBRARY',os.environ)

    def test_no_source_bundle_uses_python_native_discovery(self):
        result=runtime.configure_tk_libraries()
        self.assertIsNone(result['TCL_LIBRARY']);self.assertIsNone(result['TK_LIBRARY'])

    def test_unreadable_or_malformed_source_is_not_selected(self):
        paths=self.scripts()
        (Path(paths['TCL_LIBRARY'])/'init.tcl').write_text('not a version declaration',encoding='utf-8')
        selected=runtime.configure_tk_libraries()
        self.assertIsNone(selected['TCL_LIBRARY'])
        self.assertEqual(selected['TK_LIBRARY'],paths['TK_LIBRARY'])

    def test_frozen_selects_its_matching_bundle_over_external_env(self):
        expected=self.scripts(frozen=True)
        os.environ.update(TCL_LIBRARY='external',TK_LIBRARY='external')
        with patch.object(runtime.sys,'frozen',True):selected=runtime.configure_tk_libraries()
        self.assertEqual(selected['mode'],'frozen')
        self.assertEqual({key:os.environ[key] for key in expected},expected)

    def test_frozen_mismatch_fails_without_environment_changes(self):
        self.scripts('8.6.14',frozen=True)
        before=dict(os.environ)
        with patch.object(runtime.sys,'frozen',True),self.assertRaisesRegex(RuntimeError,'packaged tcl scripts'):runtime.configure_tk_libraries()
        self.assertEqual(dict(os.environ),before)

    def test_frozen_missing_tk_fails_without_partial_tcl_change(self):
        paths=self.scripts(frozen=True)
        (Path(paths['TK_LIBRARY'])/'tk.tcl').unlink()
        before=dict(os.environ)
        with patch.object(runtime.sys,'frozen',True),self.assertRaisesRegex(RuntimeError,'TK_LIBRARY'):runtime.configure_tk_libraries()
        self.assertEqual(dict(os.environ),before)

    def test_repeated_configuration_keeps_same_paths(self):
        self.scripts()
        first=runtime.configure_tk_libraries();before=dict(os.environ)
        self.assertEqual(runtime.configure_tk_libraries(),first)
        self.assertEqual(dict(os.environ),before)

if __name__=='__main__':unittest.main()
