"""Actual local inference is a separate release gate, never a CI mock substitute."""
import re
from .config import ACTUAL_MODEL, ACTUAL_MODEL_DIGEST
from .policy import require

ACTUAL_GATES=('actual_local_model','human_approval_preserved','evidence_grounding',
              'edited_content_exported','stale_approval_invalidated')
PUBLIC_FIELDS=('ok','status','version','frozen','checks','actual_local_inference',
    'current_actual_model_calls','current_actual_openai_calls','model','model_digest',
    'packet_hash','response_hash','gates','human_approval_scope',
    'actual_human_approvals','synthetic_approval_events')


def validate_pair(proof):
    pair=proof.get('actual_inference',{})
    require(isinstance(pair,dict) and set(pair)=={'source','frozen'},'현재 소스와 EXE의 실제 로컬 AI 검증 필요')
    counts=[]
    for mode in ('source','frozen'):
        r=pair[mode]
        require(isinstance(r,dict) and r.get('ok') is True and r.get('status')=='passed'
                and r.get('version')==proof['version'] and r.get('frozen') is (mode=='frozen')
                and r.get('actual_local_inference') is True,'실제 로컬 AI 실행 종류·버전·성공 여부 오류')
        n=r.get('current_actual_model_calls')
        require(type(n) is int and 1<=n<=20,'실제 로컬 AI HTTP 호출 횟수 필요')
        require(type(r.get('current_actual_openai_calls')) is int and r['current_actual_openai_calls']==0,
                '이번 검증은 외부 OpenAI 호출을 포함하지 않습니다.')
        require(r.get('model')==ACTUAL_MODEL and r.get('model_digest')==ACTUAL_MODEL_DIGEST,'실제 모델 고정값 불일치')
        require(all(re.fullmatch('[0-9a-f]{64}',str(r.get(k,''))) for k in ('packet_hash','response_hash')),
                '실제 요청·응답 해시 필요')
        checks=r.get('checks',[])
        require(isinstance(checks,list) and len(checks)>=10 and len(set(checks))==len(checks)
                and all(isinstance(x,str) and x.strip() for x in checks),'실제 AI 검증 단언 누락')
        require(all(r.get('gates',{}).get(g) is True for g in ACTUAL_GATES),'실제 AI의 근거·사람 상태·수정·출력 검증 누락')
        require(isinstance(r.get('human_approval_scope'),str) and r['human_approval_scope'].strip(),
                '합성 상태전이와 실제 사람 승인의 구분 필요')
        require(type(r.get('actual_human_approvals')) is int and r['actual_human_approvals']==0
                and type(r.get('synthetic_approval_events')) is int and r['synthetic_approval_events']>=1,
                '실제 사람 승인 0과 별도 합성 승인 상태전이 범위 필요')
        counts.append(n)
    require(pair['source']['checks']==pair['frozen']['checks'],'실제 소스/EXE의 검증 항목 불일치')
    total=proof.get('current_actual_model_calls')
    require(type(total) is int and total==sum(counts),'현재 실제 AI 호출 횟수 합계 불일치')
    return pair


def public_pair(proof):
    return {mode:{**{k:r[k] for k in PUBLIC_FIELDS},
        'hash_scope':'Canonical parsed-JSON digests. Private serialized capture files are also pinned by byte SHA256; not HTTP wire-byte capture.'}
        for mode,r in validate_pair(proof).items()}


def current_pair(proof):
    """Recheck private original reports and captured real response hashes."""
    import json
    from common import digest
    from .config import QA
    from .policy import safe_file,sha
    pair=validate_pair(proof)
    attempt=proof.get('attempt')
    require(type(attempt) is int and attempt>0,'실제 추론 build attempt 필요')
    for mode,r in pair.items():
        base=f'build-attempt-{attempt}/ai-{mode}'
        pinned=proof.get('actual_capture_files',{}).get(mode,{})
        require(isinstance(pinned,dict) and {'report.json','evidence-packet.json','accepted-response.json'}<=set(pinned),
                '실제 AI 직렬화 캡처파일의 바이트 고정 목록 필요')
        folder=safe_file(QA,base)
        require({p.name for p in folder.glob('*.json')}==set(pinned),'실제 AI 캡처파일 집합 변경')
        for name,item in pinned.items():
            require('/' not in name and name.endswith('.json'),'실제 AI 캡처파일 이름 오류')
            raw=safe_file(QA,base+'/'+name).read_bytes()
            require(len(raw)==item.get('bytes') and sha(raw)==item.get('sha256'),'실제 AI 직렬화 캡처 바이트 변경')
        original=json.loads(safe_file(QA,base+'/report.json').read_text(encoding='utf-8'))
        require(original==r,'빌드 후 실제 추론 원본 보고서 변경')
        evidence={}
        for name,field in (('evidence-packet.json','packet_hash'),('accepted-response.json','response_hash')):
            value=json.loads(safe_file(QA,base+'/'+name).read_text(encoding='utf-8'))
            require(digest(value)==r[field],'실제 요청·응답 원본 해시 변경: '+name)
            evidence[name]=value
        captures=r.get('transport',[])
        require(len(captures)==r['current_actual_model_calls'],'실제 HTTP 캡처 횟수 불일치')
        for index,item in enumerate(captures,1):
            require(item.get('index')==index and item.get('transport')=='actual_loopback_http','실제 전용 HTTP 증거 필요')
            for prefix,key in (('request','request_hash'),('http-response','response_hash')):
                value=json.loads(safe_file(QA,base+f'/{prefix}-{index}.json').read_text(encoding='utf-8'))
                require(digest(value)==item.get(key),'실제 HTTP 요청·응답 캡처 변경')
                if prefix=='request':
                    require(value.get('model')==ACTUAL_MODEL,'실제 요청 모델 불일치')
                    messages=value.get('messages',[])
                    require(len(messages)==2 and messages[1].get('role')=='user','실제 AI 근거 요청 형식 오류')
                    sent=json.loads(messages[1]['content'])
                    require(digest(sent.get('evidence_packet'))==r['packet_hash'],'실제 전송 근거와 저장 근거 불일치')
                else:
                    counters={k:value.get(k) for k in ('prompt_eval_count','eval_count','total_duration','eval_duration')}
                    require(counters==item.get('inference_counts') and all(type(n) is int and n>0 for n in counters.values()),
                            '실제 응답의 입력·출력·생성 카운터 검증 누락')
                    require(value.get('done') is True and value.get('model')==ACTUAL_MODEL,'실제 모델 응답 미완료/모델 불일치')
                    if index==len(captures):
                        require(value.get('message',{}).get('content')==evidence['accepted-response.json']['raw_response'],
                                '실제 모델 응답과 저장한 조서 본문 불일치')
    return pair
