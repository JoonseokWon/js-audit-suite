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
from tools.release_v22 import config,policy,proof,ci,publish,artifacts

from tools.release_v22.mock_fixtures import fixture,green_ci,metadata_api
from tools.release_v22.capture_tests import CaptureByteTests

class ReleaseBoundaryTests(unittest.TestCase):
    def test_previous_coverage_without_new_demo_or_gui_is_rejected(self):
        for key in ('demo_case_verified','gui_demo_verified'):
            value=fixture();value['headless']['frozen'][key]=False
            with self.subTest(key=key),self.assertRaises(RuntimeError):proof.validate(value)
    def test_clean_staging_is_required_and_bound_to_public_manifest(self):
        for change in ({},{'files':1,'byte_exact':True,'manifest_sha256':'0'*64}):
            value=fixture();value['clean_build_staging']=change
            with self.assertRaises(RuntimeError):proof.validate(value)
    def test_clean_staging_copies_only_explicit_bytes(self):
        from tools.release_v22.staging import create,verify
        files={'app.py':b'public','assets/icon.ico':b'icon'}
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'clean';result=create(target,files)
            self.assertEqual(result['files'],2)
            self.assertTrue(result['byte_exact'])
            (target/'assets/private.json').write_bytes(b'private must block')
            with self.assertRaises(RuntimeError):verify(target,files)
    def test_clean_staging_never_overwrites_existing_folder(self):
        from tools.release_v22.staging import create
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(RuntimeError):create(Path(folder),{'app.py':b'code'})
    def test_missing_actual_pair_is_rejected(self):
        value=fixture();value.pop('actual_inference')
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_one_mock_only_inference_cannot_pass(self):
        value=fixture();value['actual_inference']['frozen']['actual_local_inference']=False
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_actual_request_count_must_equal_pair(self):
        for count in (0,1,3,True):
            value=fixture();value['current_actual_model_calls']=count
            with self.subTest(count=count),self.assertRaises(RuntimeError):proof.validate(value)
    def test_actual_model_identity_is_pinned(self):
        value=fixture();value['actual_inference']['source']['model_digest']='c'*64
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_inference_calls_are_positive_in_both_modes(self):
        value=fixture();value['actual_inference']['frozen']['current_actual_model_calls']=0
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_external_call_is_not_a_local_test(self):
        value=fixture();value['actual_inference']['source']['current_actual_openai_calls']=1
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_actual_grounding_and_human_gates_are_required(self):
        from tools.release_v22.actual import ACTUAL_GATES
        for gate in ACTUAL_GATES:
            value=fixture();value['actual_inference']['source']['gates'][gate]=False
            with self.subTest(gate=gate),self.assertRaises(RuntimeError):proof.validate(value)
    def test_actual_summary_excludes_private_paths_and_raw_model_text(self):
        value=fixture();r=value['actual_inference']['source']
        r.update(workspace='C:/private/company',raw_response='not public',runtime_root='C:/models')
        public=proof.summary(value,{'app.py':b'a'},{'app.py':b'a'},'c'*64)
        actual=public['actual_inference']['source']
        self.assertFalse({'workspace','raw_response','runtime_root'}&set(actual))
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
    def test_zero_model_inference_claim_is_rejected(self):
        value=fixture();value['current_actual_model_calls']=0
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
        for name in ('ai_quality/numbers.py','desktop/demo/panel.py','tools/release_v22/policy.py',
                     'test_ai_quality_numbers.py'):
            self.assertTrue(policy.new_path(name))
    def test_unapproved_new_paths_are_rejected(self):
        for name in ('desktop/data.xlsx','dpi_support/log.txt','private.py','tools/delete.py','문서/공식원본.pdf',
                     'onboarding/.codex/token.py','desktop/views/new.py','test_bento_new.py'):
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
        from tools.release_v22.git_ops import blob
        self.assertEqual(blob(b'hello\n'),'ce013625030ba8dba906f756967f9e9ca394464a')
    def test_publication_checks_ci_before_any_tag_or_release_change(self):
        api=MagicMock();pending=green_ci();pending['runs'][0]['conclusion']='failure'
        with patch.object(publish,'load',return_value={'phase':'STAGED'}),\
             patch.object(publish,'pinned'),patch.object(publish,'status',return_value=pending),\
             self.assertRaises(RuntimeError):publish.publish(api)
        api.call.assert_not_called();api.inspect.assert_not_called()
    def test_authenticated_transport_rejects_unknown_host_before_network(self):
        from tools.release_v22.github_api import GitHub
        api=GitHub.__new__(GitHub);api._token='mock-token';api._opener=MagicMock()
        with self.assertRaises(RuntimeError):api.call('GET','https://example.com/private')
        api._opener.open.assert_not_called()
    def test_authenticated_transport_rejects_userinfo_before_network(self):
        from tools.release_v22.github_api import GitHub
        api=GitHub.__new__(GitHub);api._token='mock-token';api._opener=MagicMock()
        with self.assertRaises(RuntimeError):api.call('GET','https://user@api.github.com/repos/example')
        api._opener.open.assert_not_called()
    def test_external_public_repository_does_not_gate_audit_release(self):
        from tools.release_v22 import github_api
        with tempfile.TemporaryDirectory() as folder,patch.object(github_api,'WORK',Path(folder)):
            api=metadata_api(folder);result=api.inspect()
            self.assertIs(result['previous_repository_private'],False)
            self.assertEqual(result['external_repository'],{'name':config.OWNER+'/for-ax-node-project',
                'id':1406782120,'private':False,'visibility':'public'})
            self.assertEqual(result['repo_id'],config.REPO_ID)
            self.assertTrue(all(c.args[0]=='GET' and '/contents' not in c.args[1] for c in api.call.call_args_list))
    def test_own_repository_private_state_still_blocks_release(self):
        from tools.release_v22 import github_api
        with tempfile.TemporaryDirectory() as folder,patch.object(github_api,'WORK',Path(folder)):
            with self.assertRaises(RuntimeError):metadata_api(folder,private=True,visibility='private').inspect()
    def test_own_repository_id_still_blocks_wrong_target(self):
        from tools.release_v22 import github_api
        with tempfile.TemporaryDirectory() as folder,patch.object(github_api,'WORK',Path(folder)):
            with self.assertRaises(RuntimeError):metadata_api(folder,id=1).inspect()
    def test_own_repository_push_permission_still_required(self):
        from tools.release_v22 import github_api
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
    def test_public_summary_preserves_current_full_source_and_16_coverage(self):
        value=fixture()
        proof.validate(value)
        public=proof.summary(value,{'app.py':b'a'},{'app.py':b'a'},'c'*64)
        self.assertTrue(public['unit_scope']['current_source_full_suite_rerun'])
        self.assertEqual(public['headless']['frozen']['coverage'],list(config.COVERAGE))
        self.assertEqual(public['source_manifest_sha256'],value['source_manifest_sha256'])
    def test_new_domain_requires_current_full_suite_even_with_incremental_ui(self):
        value=fixture();value['unit_scope']['current_source_full_suite_rerun']=False
        value['unit_scope']['full_suite_snapshot']='before_header_layout_patch'
        value['incremental_validation']={'ok':True}
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_missing_one_of_16_improvements_blocks_release(self):
        value=fixture();value['headless']['source']['coverage'].pop()
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_required_safety_gate_cannot_be_inferred(self):
        for gate in config.GATES:
            value=fixture();value['headless']['source']['gates'][gate]=False
            with self.subTest(gate=gate),self.assertRaises(RuntimeError):proof.validate(value)
    def test_full_suite_and_build_manifest_must_match(self):
        value=fixture();value['unit_scope']['source_manifest_sha256']='0'*64
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_manifest_hash_is_not_a_declared_true_flag(self):
        value=fixture();value['build_inputs']['baseline/0']='0'*64
        with self.assertRaises(RuntimeError):proof.validate(value)
    def test_common_guard_accepts_only_version_and_declared_procedure_extension(self):
        from tools.release_v22.common_guard import validate_common,ONBOARDING
        before=b"VERSION='2.0.0'\nPROCEDURE_MODULES={'A02':'finance'}\ndef num(v):return v\n"
        after=("VERSION='2.2.0'\nPROCEDURE_MODULES="+repr(dict({'A02':'finance'},**ONBOARDING))+"\ndef num(v):return v\n").encode()
        validate_common(before,after)
        for bad in (after.replace(b'return v',b'return 0'),after.replace(b"'finance'",b"'changed'")):
            with self.assertRaises(RuntimeError):validate_common(before,bad)
    def test_v20_base_tag_and_workflow_preserved(self):
        self.assertEqual(config.PREVIOUS['v2.1.0'],config.BASE)
        self.assertIn('.github/workflows/audit-suite-v20.yml',config.OLD_WORKFLOWS)
    def test_source_selection_preserves_baseline_and_adds_only_onboarding_code(self):
        base={'ledger.py':b'PRESERVED_ENGINE=True\n','tools/build_v20.py':b'PRESERVED_TOOL=True\n'}
        workflow=b'name: SYNTHETIC ONLY\n'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name,raw in dict(base,**{'ai_quality/a.py':b'NEW_DOMAIN=True\n',
                    'desktop/demo/form.py':b'NEW_FORM=True\n','test_demo_case_a.py':b'NEW_TEST=True\n',
                    'ci/audit-suite-v22.yml':workflow}).items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            with patch.object(policy,'baseline',return_value=base),\
                 patch.object(policy,'NEW_FIXED',{'ci/audit-suite-v22.yml'}),\
                 patch.object(policy,'WORKFLOW_SHA256',policy.sha(workflow)):
                files,old=policy.public_files(root)
                self.assertTrue(set(base)<=set(files));self.assertEqual(old,base)
                self.assertIn('ai_quality/a.py',files)
                (root/'ledger.py').write_bytes(b'UNAPPROVED_ENGINE_CHANGE=True\n')
                with self.assertRaises(RuntimeError):policy.public_files(root)

if __name__=='__main__':unittest.main(verbosity=2)
