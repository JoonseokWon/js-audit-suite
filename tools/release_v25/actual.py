"""Bind each opt-in real attempt to the exact stage and executable tested."""
import sys
from .config import *
from .policy import read,run,require,sha,manifest_hash,json_bytes
from .build import pinned


def verify(frozen=False):
    folder,expected=pinned();name='frozen-ai' if frozen else 'source-ai';out=QA/name
    require(not out.exists(),'모든 실제 추론 시도를 보존하고 새 검증 경로를 사용하세요.')
    out.mkdir();exe=PROJECT/'실행파일'/EXE
    before={'source_manifest_hash':manifest_hash(expected),'frozen':frozen,
            'exe_sha256':sha(exe.read_bytes()) if frozen else None}
    receipt={**before,'completed':False};path=out/'input-receipt.json'
    path.write_bytes(json_bytes(receipt))
    args=['--self-test-ai-v25','--integrated','--report',out/'report.json',
          '--ai-runtime',PROJECT/'실행파일/로컬AI']
    command=[exe,*args] if frozen else [sys.executable,'-B','-X','utf8','app.py',*args]
    try:
        run(command,QA/(name+'.log'),exe.parent if frozen else folder)
        _,current=pinned();require(manifest_hash(current)==before['source_manifest_hash'],'추론 도중 소스 변경')
        if frozen:require(sha(exe.read_bytes())==before['exe_sha256'],'추론 도중 EXE 변경')
        report=read(out/'report.json')
        require(report.get('ok') and bool(report.get('frozen'))==frozen,'실제 추론 미통과')
        receipt.update(completed=True,report_sha256=sha((out/'report.json').read_bytes()))
    finally:
        if (out/'report.json').exists():receipt['report_sha256']=sha((out/'report.json').read_bytes())
        path.write_bytes(json_bytes(receipt))
    return {'ok':True,'mode':name,'checks':len(report['checks']),**receipt}
