"""A dedicated checkout and one byte-checked child commit; never force or reset."""
import os,subprocess
from .config import WORK,CHECKOUT,REMOTE,WORKFLOW
from .policy import require,safe_file,baseline
from .remote import BASE,BRANCH,OLD_WORKFLOWS
from .artifacts import blob,git_manifest


def git(args,cwd=None,timeout=180):
    WORK.mkdir(parents=True,exist_ok=True)
    hooks=safe_file(WORK,'disabled-hooks');hooks.mkdir(exist_ok=True)
    command=['git','-c','safe.directory='+CHECKOUT.resolve().as_posix(),
             '-c','core.autocrlf=false','-c','commit.gpgsign=false','-c','core.filemode=false',
             '-c','core.hooksPath='+str(hooks),'-c','user.name=JoonseokWon',
             '-c','user.email=300881227+JoonseokWon@users.noreply.github.com']+args
    result=subprocess.run(command,cwd=cwd or CHECKOUT,capture_output=True,timeout=timeout,
        env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never'),
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    require(result.returncode==0,'Git 작업 실패. 인증 보호를 위해 상세 출력은 생략합니다.')
    return result.stdout


def check_checkout():
    safe_file(WORK,'checkout')
    require(CHECKOUT.is_dir() and CHECKOUT.resolve()==WORK.resolve()/'checkout'
            and (CHECKOUT/'.git').is_dir() and not (CHECKOUT/'.git').is_symlink()
            and not getattr((CHECKOUT/'.git').lstat(),'st_file_attributes',0)&0x400,'릴리스 전용 checkout 필요')
    require(git(['remote','get-url','origin']).decode().strip()==REMOTE,'checkout origin 불일치')


def commit(files,value,save):
    if not CHECKOUT.exists():
        git(['clone','--branch',BRANCH,'--single-branch','--',REMOTE,str(CHECKOUT)],cwd=WORK,timeout=600)
    check_checkout()
    require(git(['rev-parse','HEAD']).decode().strip()==BASE and not git(['status','--porcelain=v1','-z']),
            '전용 checkout 기준/사용자 변경 확인 실패. 덮어쓰지 않습니다.')
    old={}
    for row in git(['ls-tree','-rz','HEAD']).split(b'\0'):
        if not row:continue
        meta,path=row.split(b'\t',1);mode,kind,ident=meta.split(b' ')
        require(kind==b'blob' and mode in (b'100644',b'100755'),'기존 Git 특수 파일 차단')
        old[path.decode('utf-8')]=ident.decode()
    prior=baseline()
    require(set(old)==set(prior)|set(OLD_WORKFLOWS) and WORKFLOW not in old,'기존 공개 트리 집합 불일치')
    require(all(old[name]==blob(raw) for name,raw in prior.items()),'기준 공개 소스 바이트 불일치')
    preserved={name:safe_file(CHECKOUT,name).read_bytes() for name in OLD_WORKFLOWS}
    require(all(blob(raw)==old[name] for name,raw in preserved.items()),'기존 workflow 변경')
    workflow=files['ci/audit-suite-v25.yml'];changes={**files,WORKFLOW:workflow}
    for name,raw in changes.items():
        path=safe_file(CHECKOUT,name)
        if path.exists():require(blob(path.read_bytes())==old.get(name),'checkout 추적 원문/사용자 변경')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    wanted={name for name,raw in changes.items() if old.get(name)!=blob(raw)}
    paths=WORK/'publication-pathspec.nul'
    paths.write_bytes(b''.join((':(literal)'+name).encode('utf-8')+b'\0' for name in sorted(changes)))
    git(['add','-f','--pathspec-from-file='+str(paths),'--pathspec-file-nul'])
    actual={p.decode('utf-8') for p in git(['diff','--cached','--name-only','-z']).split(b'\0') if p}
    require(actual==wanted and wanted,'허용 stage 집합 불일치')
    index={}
    for row in git(['ls-files','--stage','-z']).split(b'\0'):
        if not row:continue
        meta,path=row.split(b'\t',1);mode,ident,stage=meta.split(b' ')
        require(mode in (b'100644',b'100755') and stage==b'0','index 특수파일/충돌 차단')
        index[path.decode('utf-8')]=ident.decode()
    require(set(index)==set(changes)|set(preserved) and all(index[name]==blob(raw)
        for name,raw in {**changes,**preserved}.items()),'index 공개 파일·바이트 불일치')
    value.update(phase='STAGED_LOCAL',additional_files=git_manifest({**preserved,WORKFLOW:workflow}),
                 staged_paths=sorted(wanted));save(value)
    git(['commit','-m','Connect grounded AI citations, misstatement evaluation and audit risk responses in v2.5.0'])
    ident=git(['rev-parse','HEAD']).decode().strip()
    require(git(['rev-list','--parents','-n','1','HEAD']).decode().split()==[ident,BASE],'단일 부모 fast-forward 커밋 필요')
    require(not git(['status','--porcelain=v1','-z']),'커밋 후 checkout 변경')
    value.update(phase='COMMITTED',commit=ident);save(value)


def push(value):
    check_checkout()
    require(git(['rev-parse','HEAD']).decode().strip()==value['commit'] and
            not git(['status','--porcelain=v1','-z']),'공개 커밋 checkout 변경')
    require(git(['rev-list','--parents','-n','1','HEAD']).decode().split()==[value['commit'],BASE],
            'push 전 단일 부모 커밋 확인 실패')
    git(['push','origin','HEAD:refs/heads/'+BRANCH],timeout=600)
