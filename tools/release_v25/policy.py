"""A pinned public ZIP plus code-only additions. No traversal of user data."""
import hashlib,json,re,zipfile
from pathlib import Path
from .config import *
from tools.release_v22.policy import safe_file,safe_name,require


def sha(raw):return hashlib.sha256(raw).hexdigest()
def json_bytes(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def manifest(files):return {r:{'bytes':len(raw),'sha256':sha(raw)} for r,raw in sorted(files.items())}
def manifest_hash(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode())


def baseline():
    require(BASE_ZIP.is_file() and sha(BASE_ZIP.read_bytes())==BASE_SHA,'공개 v2.3.0 기준 ZIP 변경')
    files={}
    with zipfile.ZipFile(BASE_ZIP) as archive:
        for name in archive.namelist():
            if name.endswith('/'):continue
            require(name.startswith(PREFIX),'기준 ZIP 접두부 오류')
            relative=name[len(PREFIX):];safe_name(relative)
            require(relative not in files,'기준 ZIP 중복 경로')
            files[relative]=archive.read(name)
    require(len(files)==BASE_COUNT,'기준 ZIP 공개 파일 수 변경')
    return files


def new_path(relative):
    try:safe_name(relative)
    except RuntimeError:return False
    if relative in V24_ADDITIONS|FIXED:return True
    path=Path(relative)
    if path.suffix!='.py':return False
    if '/' not in relative:return bool(re.fullmatch(r'test_(?:v25|misstatements|audit_links|ai_.*v25|review_.*v25).*\.py',relative))
    return any(relative.startswith(package+'/') for package in PACKAGES)


def public_files(root=SOURCE):
    old=baseline();files={}
    for relative,raw in old.items():
        current=safe_file(root,relative).read_bytes()
        mutable=(relative in MUTABLE or relative.startswith('desktop/') or
                 '/' not in relative and relative.startswith('test_') and relative.endswith('.py'))
        require(current==raw or mutable,'예상 밖 기존 공개 자료 변경: '+relative)
        files[relative]=current
    additions=set(V24_ADDITIONS)|FIXED
    for package in PACKAGES:
        folder=safe_file(root,package)
        if folder.exists():additions.update(p.relative_to(root).as_posix() for p in folder.rglob('*.py'))
    additions.update(p.name for p in Path(root).glob('test_*.py') if p.name not in old and new_path(p.name))
    for relative in sorted(additions):
        require(new_path(relative),'새 공개 경로 차단: '+relative)
        files[relative]=safe_file(root,relative).read_bytes()
    require(len(files)==len({r.casefold() for r in files}),'대소문자 경로 중복')
    roots={p.name for p in Path(root).iterdir() if p.is_file() and p.suffix in ('.py','.spec','.manifest')}
    require(roots<=set(files),'공개 빌드에서 누락된 root 코드: '+str(roots-set(files)))
    require(all(not r.endswith(('.sqlite3','.gguf','.exe','.zip')) for r in files),'개인 DB/모델/배포 중첩 차단')
    return files


def run(command,log,cwd=SOURCE):
    import os,subprocess
    path=Path(log);path.parent.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',
             PYINSTALLER_CONFIG_DIR=str(QA/'pyinstaller-cache'))
    with path.open('x',encoding='utf-8') as out:
        result=subprocess.run([str(v) for v in command],cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    require(result.returncode==0,'검증/빌드 실패: '+str(path))
