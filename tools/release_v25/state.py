"""Private resumable state with immutable package and preflight pins."""
import re,os,tempfile
from .config import WORK,REPO,TAG
from .policy import read,require,json_bytes
from .remote import BASE,preflight_hash
from .artifacts import validate_set,git_manifest

STATE=WORK/'release-state.json'
PHASES=('PREPARED','STAGED_LOCAL','COMMITTED','PUSHED','DRAFT_CREATED','STAGED','PUBLISHED','VERIFIED')


def save(value):
    WORK.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=WORK,prefix='.release-state-')
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(json_bytes(value));stream.flush();os.fsync(stream.fileno())
        os.replace(name,STATE)
    finally:
        from pathlib import Path
        if Path(name).exists():Path(name).unlink()


def load():
    require(STATE.is_file(),'먼저 github-stage를 실행하세요.')
    value=read(STATE)
    require(value.get('repository')==REPO and value.get('tag')==TAG and value.get('base')==BASE
            and value.get('private') is False and value.get('preflight_hash')==preflight_hash()
            and value.get('phase') in PHASES,'v2.5 고정 릴리스 상태 불일치')
    if 'commit' in value:require(re.fullmatch('[0-9a-f]{40}',value['commit']),'커밋 형식 오류')
    return value


def check_pins(value):
    assets,files=validate_set()
    require(assets==value['local_assets'] and git_manifest(files)==value['source_files']
            and value['preflight_hash']==preflight_hash(),'고정 패키지·공개 소스·이전 이력 변경')
    return files
