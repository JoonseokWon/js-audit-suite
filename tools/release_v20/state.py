"""Release-local state only. Existing source, workspaces and credentials are excluded."""
import json
import re
from .config import *
from .policy import require,json_bytes
from .artifacts import validate_set,git_manifest

def save(value):
    WORK.mkdir(parents=True,exist_ok=True)
    STATE.write_bytes(json_bytes(value))

def load():
    require(STATE.is_file(),'stage로 릴리스 상태를 먼저 준비하세요.')
    value=json.loads(STATE.read_text(encoding='utf-8-sig'))
    require(value.get('repository')==REPO and value.get('tag')==TAG and value.get('base')==BASE
            and value.get('private') is False,'고정 릴리스 상태 불일치')
    require(value.get('phase') in ('PREPARED','STAGED_LOCAL','COMMITTED','PUSHED','DRAFT_CREATED','STAGED','PUBLISHED','VERIFIED'),
            '알 수 없는 릴리스 단계')
    if 'commit' in value:require(re.fullmatch('[0-9a-f]{40}',str(value['commit'])),'릴리스 커밋 형식 오류')
    return value

def pinned(value):
    assets,files=validate_set(SOURCE/'배포')
    require(assets==value['local_assets'] and git_manifest(files)==value['source_files'],'고정 첨부/공개 소스 변경')
    return assets,files

def preserved(report,value):
    require(report['repo_id']==value['repo_id'] and report['previous']==value['previous'],
            '이전 태그·릴리스·저장소 보존 확인 실패')
