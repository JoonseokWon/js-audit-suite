"""SYNTHETIC ONLY byte-integrity fixtures; never contacts any model/server."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from . import config,actual,policy
from .mock_fixtures import fixture


def captured_fixture(root):
    from common import digest
    proof=fixture();proof['attempt']=1;proof['actual_capture_files']={}
    for mode,r in proof['actual_inference'].items():
        folder=root/f'build-attempt-1/ai-{mode}';folder.mkdir(parents=True)
        packet={'scope':'SYNTHETIC ONLY request fixture'}
        content=json.dumps({'scope':'SYNTHETIC ONLY output'})
        accepted={'raw_response':content,'model':config.ACTUAL_MODEL}
        request={'model':config.ACTUAL_MODEL,'messages':[{'role':'system','content':'SYNTHETIC ONLY'},
            {'role':'user','content':json.dumps({'evidence_packet':packet})}]}
        response={'model':config.ACTUAL_MODEL,'done':True,'message':{'content':content},
            'prompt_eval_count':1,'eval_count':2,'total_duration':3,'eval_duration':4}
        counters={k:response[k] for k in ('prompt_eval_count','eval_count','total_duration','eval_duration')}
        r.update(packet_hash=digest(packet),response_hash=digest(accepted),
            transport=[{'index':1,'transport':'actual_loopback_http','request_hash':digest(request),
                'response_hash':digest(response),'inference_counts':counters}])
        files={'evidence-packet.json':packet,'accepted-response.json':accepted,
               'request-1.json':request,'http-response-1.json':response,'report.json':r}
        for name,value in files.items():(folder/name).write_bytes(policy.json_bytes(value))
        proof['actual_capture_files'][mode]={name:{'bytes':(folder/name).stat().st_size,
            'sha256':policy.sha((folder/name).read_bytes())} for name in files}
    return proof


class CaptureByteTests(unittest.TestCase):
    def test_canonical_and_byte_capture_fixture_match(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(config,'QA',Path(directory)):
            self.assertTrue(actual.current_pair(captured_fixture(Path(directory))))

    def test_whitespace_tamper_is_rejected_despite_same_json_value(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(config,'QA',Path(directory)):
            root=Path(directory);proof=captured_fixture(root)
            path=root/'build-attempt-1/ai-source/http-response-1.json'
            value=json.loads(path.read_bytes());path.write_text(json.dumps(value),encoding='utf-8')
            with self.assertRaises(RuntimeError):actual.current_pair(proof)

    def test_unlisted_capture_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(config,'QA',Path(directory)):
            root=Path(directory);proof=captured_fixture(root)
            (root/'build-attempt-1/ai-frozen/unknown.json').write_text('{}')
            with self.assertRaises(RuntimeError):actual.current_pair(proof)
