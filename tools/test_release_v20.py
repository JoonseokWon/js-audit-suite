"""Release boundary tests. No credentials, network, real workspaces or EXE execution."""
from pathlib import Path
import copy
import json
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch,MagicMock
from zipfile import ZipFile,ZipInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.release_v20 import config,policy,proof,ci,publish,artifacts

def fixture():
    return {'schema':config.PROOF_SCHEMA,'version':'2.0.0','status':'passed',
        'unit':{'tests':865,'errors':0,'failures':0,'skipped':0},
        'unit_scope':{'full_suite_snapshot':'current_source','current_source_full_suite_rerun':True,
                      'description':'This fixture declares a current-source full-suite run.'},
        'headless':{m:{'ok':True,'checks':['check'+str(i) for i in range(36)]} for m in ('source','frozen')},
        'source_frozen_observations_identical':True,'portable_layout_verified':True,
        'icon_embedded_verified':True,'unicode_roundtrip_verified':True,'bento_navigation_verified':True,
        'dpi_policy_verified':True,'current_actual_model_calls':0,
        'ime':{'current_actual_key_test':False,'scope':'No new physical IME key test.'},
        'exe':{'name':config.EXE,'bytes':200,'sha256':'a'*64},
        'build_inputs':{'baseline/'+str(i):'b'*64 for i in range(1758)}}

def green_ci():
    return {'runs':[{'status':'completed','conclusion':'success','url':'https://github.com/example',
        'jobs':[{'name':'Audit Suite Python '+version,'status':'completed','conclusion':'success',
                 'steps':[{'name':name,'conclusion':'success'} for name in
                          ('Unit tests','Release policy mock tests','Headless integration')]}
                for version in ('3.12','3.14')]}]}

def metadata_api(folder, **own_changes):
    from tools.release_v20.github_api import GitHub
    api=GitHub.__new__(GitHub)
    own={'full_name':config.REPO,'id':config.REPO_ID,'private':False,'visibility':'public',
         'default_branch':'main','permissions':{'push':True},'archived':False}
    own.update(own_changes)
    releases=[{'tag_name':tag,'target_commitish':commit,'draft':False,'id':i,'assets':[]}
              for i,(tag,commit) in enumerate(config.PREVIOUS.items(),1)]
    def call(method,path,**kwargs):
        if method!='GET':raise AssertionError('Read-only metadata inspection attempted a write')
        if path=='https://api.github.com/user':return {'login':config.OWNER}
        if path=='https://api.github.com/repos/'+config.OWNER+'/for-ax-node-project':
            return {'full_name':config.OWNER+'/for-ax-node-project','id':1406782120,'private':False,'visibility':'public'}
        if path=='':return own
        if path=='/branches?per_page=100':return [{'name':'main'}]
        if path=='/tags?per_page=100':return [{'name':tag} for tag in config.PREVIOUS]
        if path=='/releases?per_page=100':return releases
        if path=='/git/ref/heads/main':return {'object':{'sha':config.BASE}}
        if path=='/git/ref/tags/'+config.TAG:return None
        if path.startswith('/git/ref/tags/'):
            tag=path[len('/git/ref/tags/'):]
            return {'object':{'type':'commit','sha':config.PREVIOUS[tag]}}
        raise AssertionError('Unexpected metadata endpoint: '+path)
    api.call=MagicMock(side_effect=call)
    return api

class ReleaseBoundaryTests(unittest.TestCase):
    def test_proof_accepts_completed_current_scope(self):proof.validate(fixture())
    def test_stale_version_is_rejected(self):
        value=fixture();value['version']='1.9.0'
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_failed_unit_is_rejected(self):
        value=fixture();value['unit']['failures']=1
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_skipped_local_unit_is_rejected(self):
        value=fixture();value['unit']['skipped']=1
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_source_exe_check_mismatch_is_rejected(self):
        value=fixture();value['headless']['frozen']['checks'].pop()
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_new_model_inference_claim_is_rejected(self):
        value=fixture();value['current_actual_model_calls']=1
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_new_IME_claim_is_rejected(self):
        value=fixture();value['ime']['current_actual_key_test']=True
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_missing_bento_or_DPI_proof_is_rejected(self):
        for key in ('bento_navigation_verified','dpi_policy_verified'):
            value=fixture();value[key]=False
            with self.subTest(key=key),self.assertRaises(RuntimeError):proof.validate(value)
    def test_wrong_exe_name_is_rejected(self):
        value=fixture();value['exe']['name']='old.exe'
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_parent_and_absolute_paths_are_rejected(self):
        for name in ('../private.py','/absolute.py','C:/key.py','x\\y.py','a//b.py'):
            with self.subTest(name=name),self.assertRaises(RuntimeError):policy.safe_name(name)
    def test_private_path_names_are_rejected(self):
        for name in ('.env','desktop/.git/key.py','models/key.py','메일 자동화/rows.py'):
            with self.subTest(name=name),self.assertRaises(RuntimeError):policy.safe_name(name)
    def test_bounded_new_code_paths_are_accepted(self):
        for name in ('desktop/views/inputs.py','dpi_support/manager.py','tools/release_v20/policy.py'):
            self.assertTrue(policy.new_path(name))
    def test_unapproved_new_paths_are_rejected(self):
        for name in ('desktop/data.xlsx','dpi_support/log.txt','private.py','tools/delete.py','문서/공식원본.pdf'):
            self.assertFalse(policy.new_path(name))
    def test_safe_file_stays_inside_root(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(policy.safe_file(folder,'desktop/x.py'),Path(folder)/'desktop/x.py')
    def test_zip_duplicate_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.zip'
            with ZipFile(path,'w') as z:
                z.writestr(config.PREFIX+'a.py',b'a');z.writestr(config.PREFIX+'A.py',b'b')
            with self.assertRaises(RuntimeError):policy.read_zip(path,config.PREFIX)
    def test_zip_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.zip'
            with ZipFile(path,'w') as z:
                info=ZipInfo(config.PREFIX+'key.py');info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,b'target')
            with self.assertRaises(RuntimeError):policy.read_zip(path,config.PREFIX)
    def test_zip_wrong_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.zip'
            with ZipFile(path,'w') as z:z.writestr('other/a.py',b'a')
            with self.assertRaises(RuntimeError):policy.read_zip(path,config.PREFIX)
    def test_deterministic_zip_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'good.zip';files={'a.py':b'a','desktop/x.py':b'b'}
            policy.write_zip(path,files,config.PREFIX);self.assertEqual(policy.read_zip(path,config.PREFIX),files)
    def test_ci_requires_latest_success(self):
        value=green_ci();value['runs'][0]['status']='in_progress'
        with self.assertRaises(RuntimeError):ci.gate(value)
    def test_ci_requires_two_python_versions(self):
        value=green_ci();value['runs'][0]['jobs'][0]['name']='Audit Suite Python 3.14'
        with self.assertRaises(RuntimeError):ci.gate(value)
    def test_ci_requires_each_named_step(self):
        value=green_ci();value['runs'][0]['jobs'][0]['steps'][1]['conclusion']='skipped'
        with self.assertRaises(RuntimeError):ci.gate(value)
    def test_ci_accepts_complete_matrix(self):self.assertTrue(ci.gate(green_ci()))
    def test_remote_asset_digest_is_required(self):
        expected={'local_assets':{'a.zip':{'name':'a.zip','bytes':2,'sha256':'a'*64}}}
        release={'assets':[{'name':'a.zip','size':2,'state':'uploaded','digest':'sha256:'+'b'*64}]}
        with self.assertRaises(RuntimeError):publish.assets_match(release,expected)
    def test_unexpected_remote_asset_is_rejected(self):
        with self.assertRaises(RuntimeError):publish.assets_match({'assets':[{'name':'key.pem'}]},{'local_assets':{}})
    def test_remote_asset_matches_size_digest_and_state(self):
        expected={'local_assets':{'a.zip':{'name':'a.zip','bytes':2,'sha256':'a'*64}}}
        release={'assets':[{'name':'a.zip','size':2,'state':'uploaded','digest':'sha256:'+'a'*64,
                            'id':1,'browser_download_url':'https://github.com/example/a.zip'}]}
        self.assertEqual(publish.assets_match(release,expected)[0]['asset_id'],1)
    def test_git_blob_hash_is_literal_content_based(self):
        from tools.release_v20.git_ops import blob
        self.assertEqual(blob(b'hello\n'),'ce013625030ba8dba906f756967f9e9ca394464a')
    def test_publication_checks_ci_before_any_tag_or_release_change(self):
        api=MagicMock();pending=green_ci();pending['runs'][0]['conclusion']='failure'
        with patch.object(publish,'load',return_value={'phase':'STAGED'}),\
             patch.object(publish,'pinned'),patch.object(publish,'status',return_value=pending),\
             self.assertRaises(RuntimeError):publish.publish(api)
        api.call.assert_not_called();api.inspect.assert_not_called()
    def test_authenticated_transport_rejects_unknown_host_before_network(self):
        from tools.release_v20.github_api import GitHub
        api=GitHub.__new__(GitHub);api._token='mock-token';api._opener=MagicMock()
        with self.assertRaises(RuntimeError):api.call('GET','https://example.com/private')
        api._opener.open.assert_not_called()
    def test_authenticated_transport_rejects_userinfo_before_network(self):
        from tools.release_v20.github_api import GitHub
        api=GitHub.__new__(GitHub);api._token='mock-token';api._opener=MagicMock()
        with self.assertRaises(RuntimeError):api.call('GET','https://user@api.github.com/repos/example')
        api._opener.open.assert_not_called()
    def test_external_public_repository_does_not_gate_audit_release(self):
        from tools.release_v20 import github_api
        with tempfile.TemporaryDirectory() as folder,patch.object(github_api,'WORK',Path(folder)):
            api=metadata_api(folder);result=api.inspect()
            self.assertIs(result['previous_repository_private'],False)
            self.assertEqual(result['external_repository'],{'name':config.OWNER+'/for-ax-node-project',
                'id':1406782120,'private':False,'visibility':'public'})
            self.assertEqual(result['repo_id'],config.REPO_ID)
            self.assertTrue(all(c.args[0]=='GET' and '/contents' not in c.args[1] for c in api.call.call_args_list))
    def test_own_repository_private_state_still_blocks_release(self):
        from tools.release_v20 import github_api
        with tempfile.TemporaryDirectory() as folder,patch.object(github_api,'WORK',Path(folder)):
            with self.assertRaises(RuntimeError):metadata_api(folder,private=True,visibility='private').inspect()
    def test_own_repository_id_still_blocks_wrong_target(self):
        from tools.release_v20 import github_api
        with tempfile.TemporaryDirectory() as folder,patch.object(github_api,'WORK',Path(folder)):
            with self.assertRaises(RuntimeError):metadata_api(folder,id=1).inspect()
    def test_own_repository_push_permission_still_required(self):
        from tools.release_v20 import github_api
        with tempfile.TemporaryDirectory() as folder,patch.object(github_api,'WORK',Path(folder)):
            with self.assertRaises(RuntimeError):metadata_api(folder,permissions={'push':False}).inspect()
    def test_staged_candidate_path_is_bound_to_declared_attempt(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(proof,'QA',Path(folder)):
            target=Path(folder)/'build-attempt-2/candidate/실행파일'/config.EXE
            value={'attempt':2,'candidate_executable':str(target)}
            self.assertEqual(proof.executable_path(value,target),target)
    def test_staged_candidate_outside_qa_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(proof,'QA',Path(folder)/'qa'):
            value={'attempt':2,'candidate_executable':str(Path(folder)/config.EXE)}
            with self.assertRaises(RuntimeError):proof.executable_path(value)
    def test_staged_candidate_different_attempt_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(proof,'QA',Path(folder)):
            value={'attempt':2,'candidate_executable':str(Path(folder)/'build-attempt-3/candidate/실행파일'/config.EXE)}
            with self.assertRaises(RuntimeError):proof.executable_path(value)
    def test_explicit_exe_cannot_silently_replace_the_declared_candidate(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(proof,'QA',Path(folder)):
            target=Path(folder)/'build-attempt-2/candidate/실행파일'/config.EXE
            value={'attempt':2,'candidate_executable':str(target)}
            with self.assertRaises(RuntimeError):proof.executable_path(value,Path(folder)/'different.exe')
    def test_missing_full_suite_scope_is_rejected(self):
        value=fixture();value.pop('unit_scope')
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_previous_full_suite_requires_current_ui_and_geometry_evidence(self):
        value=fixture()
        value['unit_scope']={'full_suite_snapshot':'before_header_layout_patch',
                            'current_source_full_suite_rerun':False,'calculation_engines_unchanged':True,
                            'description':'Full regression predates the header patch.'}
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_public_summary_preserves_previous_full_and_current_ui_scope(self):
        value=fixture();value['unit']['tests']=895
        value['unit_scope']={'full_suite_snapshot':'before_header_layout_patch',
                            'current_source_full_suite_rerun':False,'calculation_engines_unchanged':True,
                            'description':'895 tests before header patch; current incremental UI and geometry below.'}
        value['incremental_validation']={'ok':True,'private_path':'not-for-publication',
            'ui_tests':{'tests':96,'errors':0,'failures':0,'skipped':0},
            'geometry_matrix':{'ok':True,'cases':10,'scope':'Controlled geometry checks; no OS settings changed.'}}
        proof.validate(value)
        public=proof.summary(value,{'app.py':b'a'},{'app.py':b'a'},'c'*64)
        self.assertFalse(public['unit_scope']['current_source_full_suite_rerun'])
        self.assertEqual(public['incremental_validation']['ui_tests']['tests'],96)
        self.assertEqual(public['incremental_validation']['geometry_matrix']['cases'],10)
        self.assertNotIn('private_path',public['incremental_validation'])

if __name__=='__main__':unittest.main(verbosity=2)
