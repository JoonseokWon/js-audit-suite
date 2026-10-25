"""One child fast-forward commit; no reset, delete, force, or inherited hooks."""
import hashlib
import os
import subprocess
from .config import *
from .policy import require,json_bytes,safe_file,baseline
from .artifacts import git_manifest

def git(args,cwd=None,input_bytes=None,timeout=180):
    WORK.mkdir(parents=True,exist_ok=True);hooks=WORK/'disabled-hooks';hooks.mkdir(exist_ok=True)
    command=['git','-c','safe.directory='+CHECKOUT.resolve().as_posix(),'-c','core.autocrlf=false',
             '-c','commit.gpgsign=false','-c','core.filemode=false','-c','core.hooksPath='+str(hooks),
             '-c','user.name=JoonseokWon','-c','user.email=300881227+JoonseokWon@users.noreply.github.com']+args
    proc=subprocess.run(command,cwd=cwd or CHECKOUT,input=input_bytes,capture_output=True,
                        env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never'),timeout=timeout)
    require(proc.returncode==0,'Git 작업 실패. 인증을 보호하기 위해 상세 출력은 생략합니다.')
    return proc.stdout

def check_checkout():
    safe_file(WORK,'checkout')
    require(CHECKOUT.is_dir() and CHECKOUT.resolve()==WORK.resolve()/'checkout'
            and (CHECKOUT/'.git').is_dir() and not (CHECKOUT/'.git').is_symlink(),'릴리스 전용 checkout 필요')
    require(git(['remote','get-url','origin']).decode().strip()==REMOTE,'checkout origin 불일치')

def blob(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()

def commit(files,state,save):
    if not CHECKOUT.exists():git(['clone','--branch',BRANCH,'--single-branch','--',REMOTE,str(CHECKOUT)],cwd=WORK,timeout=600)
    check_checkout()
    require(git(['rev-parse','HEAD']).decode().strip()==BASE and not git(['status','--porcelain=v1','-z']),
            'checkout 기준/사용자 변경 확인 실패. 덮어쓰지 않습니다.')
    old={}
    for row in git(['ls-tree','-rz','HEAD']).split(b'\0'):
        if row:
            meta,path=row.split(b'\t',1);mode,kind,ident=meta.split(b' ')
            require(kind==b'blob' and mode in (b'100644',b'100755'),'기존 git 특수 파일 차단')
            old[path.decode()]=ident.decode()
    require(set(old)==set(baseline())|set(OLD_WORKFLOWS),'기존 공개 파일 집합 누락/추가')
    require(WORKFLOW not in old,'새 workflow가 이미 존재함')
    workflow=files['ci/audit-suite-v21.yml']
    changes={**files,WORKFLOW:workflow};preserved={}
    for path in OLD_WORKFLOWS:
        raw=safe_file(CHECKOUT,path).read_bytes();require(blob(raw)==old[path],'기존 workflow 변경')
        preserved[path]=raw
    for path,raw in changes.items():
        target=safe_file(CHECKOUT,path)
        if target.exists():require(blob(target.read_bytes())==old.get(path),'추적 원문/사용자 변경 불일치')
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    wanted={p for p,raw in changes.items() if old.get(p)!=blob(raw)}
    paths=WORK/'publication-pathspec.nul';paths.write_bytes(b''.join((':(literal)'+p).encode()+b'\0' for p in sorted(changes)))
    git(['add','-f','--pathspec-from-file='+str(paths),'--pathspec-file-nul'])
    actual={p.decode() for p in git(['diff','--cached','--name-only','-z']).split(b'\0') if p}
    require(actual==wanted and wanted,'stage 허용집합 불일치')
    index={}
    for row in git(['ls-files','--stage','-z']).split(b'\0'):
        if row:
            meta,path=row.split(b'\t',1);mode,ident,stage=meta.split(b' ')
            require(mode in (b'100644',b'100755') and stage==b'0','index 특수파일/충돌 차단')
            index[path.decode()]=ident.decode()
    require(set(index)==set(old)|set(changes),'index에 예상 밖 삭제/파일')
    require(all(index[p]==blob(v) for p,v in {**changes,**preserved}.items()),'index 바이트 불일치')
    state.update(phase='STAGED_LOCAL',additional_files=git_manifest({**preserved,WORKFLOW:workflow}),staged_paths=sorted(wanted));save(state)
    git(['commit','-m','Add explicit ERP, audit procedures and linked cash flow in JS audit suite v2.1.0'])
    ident=git(['rev-parse','HEAD']).decode().strip()
    require(git(['rev-list','--parents','-n','1','HEAD']).decode().split()==[ident,BASE],'유일 부모 fast-forward 확인 실패')
    state.update(phase='COMMITTED',commit=ident);save(state)

def push(state):
    check_checkout()
    require(git(['rev-parse','HEAD']).decode().strip()==state['commit'] and not git(['status','--porcelain=v1','-z']),
            '공개 커밋 checkout 변경')
    git(['push','origin','HEAD:refs/heads/'+BRANCH],timeout=600)
