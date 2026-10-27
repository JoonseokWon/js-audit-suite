"""Mock-only synthetic flow. Never evidence of actual inference or approval."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from ai_contract import build_catalog
from ai_contract.generation import generation_plan
from ai_contract.headers import response_context
from ai_quality.case_v25 import create_case
from ai_quality.flow_v25 import complete_flow
import ai_provider


class V25SyntheticFlowTests(unittest.TestCase):
    def test_mock_response_through_separate_program_records_edit_export_and_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);checks=[]
            def check(ok,name):
                self.assertTrue(ok,name);checks.append(name)
            ws,_=create_case(folder,check)
            packet=ws.ai_packet('A04',limits={'max_chars':12000,'max_references':40,
                'rows_per_table':3,'max_tables':8,'cell_chars':300})
            plan=generation_plan(packet)
            fields={f:'현재 등록된 자료에서 발췌한 근거 범위에 대해 사람이 추가 검토해야 하는 미검증 제안이다.' for f in ai_provider.FIELDS}
            for f,prefix in plan['prefixes'].items():fields[f]=prefix+fields[f]
            parsed={'context':response_context(packet),'claims':build_catalog(packet)['program_copy_claims'],
                'proposals':fields,'citations':plan['citations']}
            raw=json.dumps(parsed,ensure_ascii=False)
            envelope={'model':ai_provider.DEFAULT_MODEL,'done':True,'done_reason':'stop',
                'message':{'role':'assistant','content':raw}}
            with patch.object(ai_provider,'_post_json',return_value=envelope) as transport:
                response=ai_provider.generate_draft(packet,{})
                self.assertEqual(transport.call_count,1)
            result=complete_flow(ws,packet,response,folder,check)
            self.assertEqual(result['actual_human_approvals'],0)
            self.assertEqual(result['synthetic_approval_events'],2)
            self.assertGreaterEqual(len(checks),25)


if __name__=='__main__':unittest.main()
