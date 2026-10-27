"""Opt-in QA instrumentation around the real transport, never a fake response."""
import json
import time
from common import atomic, digest


class ActualCapture:
    def __init__(self, folder):
        self.folder=folder;self.requests=[];self.original=None

    def __enter__(self):
        import ai_provider
        self.original=ai_provider._post_json
        ai_provider._post_json=self.call
        return self

    def call(self, target, payload, headers, timeout, event):
        if target[:3] != ('http','127.0.0.1',11437) or headers:
            raise ValueError('Actual QA permits the dedicated local endpoint only.')
        index=len(self.requests)+1
        record={'index':index,'request_hash':digest(payload),'provider':'ollama',
                'transport':'actual_loopback_http','timeout_seconds':timeout,
                'request_options':dict(payload.get('options',{}))}
        self.requests.append(record)
        atomic(self.folder/f'request-{index}.json',json.dumps(payload,ensure_ascii=False,indent=2).encode())
        started=time.monotonic()
        try:response=self.original(target,payload,headers,timeout,event)
        finally:record['transport_seconds']=round(time.monotonic()-started,3)
        record['response_hash']=digest(response)
        record['inference_counts']={key:response.get(key) for key in (
            'prompt_eval_count','prompt_eval_cached_count','eval_count','total_duration',
            'load_duration','prompt_eval_duration','eval_duration','done','done_reason')}
        atomic(self.folder/f'http-response-{index}.json',json.dumps(response,ensure_ascii=False,indent=2).encode())
        return response

    def __exit__(self, *args):
        import ai_provider
        ai_provider._post_json=self.original

