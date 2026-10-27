"""Publication boundaries only: no credentials, network, or release mutation."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.release_v25.policy import new_path
from tools.release_v22.policy import safe_name


class PublicationBoundaryTests(unittest.TestCase):
    def test_unregistered_asset_in_stage_is_rejected(self):
        import tempfile,json
        from unittest.mock import patch
        from tools.release_v25 import build
        from tools.release_v25.policy import manifest
        with tempfile.TemporaryDirectory() as temp:
            qa=Path(temp);folder=qa/'build/stage';folder.mkdir(parents=True)
            (folder/'app.py').write_bytes(b'# public\n')
            (qa/'build/manifest.json').write_text(json.dumps(manifest({'app.py':b'# public\n'})))
            with patch.object(build,'QA',qa),patch.object(build,'public_files',return_value={'app.py':b'# public\n'}):
                build.pinned()
                (folder/'assets').mkdir();(folder/'assets/private.bin').write_bytes(b'PRIVATE')
                with self.assertRaises(RuntimeError):build.pinned()

    def test_actual_gate_rejects_mock_wrong_scope_and_unfinished_transport(self):
        from copy import deepcopy
        from tools.release_v25.package import check_actual
        valid={'ok':True,'version':'2.5.0','actual_model_calls':1,'actual_human_approvals':0,
            'status':'passed','case_mode':'integrated_risk_misstatement','frozen':False,
            'transport':[{'inference_counts':{'prompt_eval_count':100,'prompt_eval_cached_count':0,
                'eval_count':50,'total_duration':1000,'done':True,'done_reason':'stop'}}]}
        check_actual(valid,False)
        for key,value in (('actual_model_calls',0),('actual_human_approvals',1),('case_mode','sales_only_initial'),
                          ('frozen',True),('ok',False)):
            bad=deepcopy(valid);bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):check_actual(bad,False)
        for key,value in (('eval_count',0),('done',False),('done_reason','length')):
            bad=deepcopy(valid);bad['transport'][0]['inference_counts'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):check_actual(bad,False)

    def test_public_summary_excludes_raw_response_paths_and_transport(self):
        from tools.release_v25.package import clean
        self.assertEqual(clean({'ok':True,'workspace':'C:/private','raw_response':'SECRET',
            'transport':[{'token':'SECRET'}]}),{'ok':True})
        with self.assertRaises(RuntimeError):clean({'model':'C:/private/model'})

    def test_new_code_packages_and_documents_are_allowed(self):
        for path in ('audit_links/status.py','misstatements/records.py','v25_demo/case.py',
                     'desktop/misstatements/dialog.py','ai_contract/generation.py',
                     'tools/release_v25/build.py','test_ai_links_v25.py','문서/v2.5_사용안내.md'):
            with self.subTest(path=path):self.assertTrue(new_path(path))

    def test_user_data_models_logs_and_reference_sources_are_not_new_public_files(self):
        for path in ('검증/report.json','검증/model-response.json','업무/업무.sqlite3',
                     'models/model.gguf','원본교육자료.xlsx','참고자료/모범답안.pdf',
                     'misstatements/actual-response.json','private/token.txt','sector_verification/data.json'):
            with self.subTest(path=path):self.assertFalse(new_path(path))

    def test_traversal_and_credentials_paths_are_rejected(self):
        for path in ('../secret.py','/root.py','C:/private.py','audit_links/../private.py',
                     'audit_links/.env','models/private.py','audit_links/file:secret.py'):
            with self.subTest(path=path),self.assertRaises(RuntimeError):safe_name(path)

if __name__=='__main__':unittest.main()
