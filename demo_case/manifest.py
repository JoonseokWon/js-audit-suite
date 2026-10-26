"""Read only this walkthrough's fixed, local, hash-checked input manifest."""
from pathlib import Path, PurePosixPath
import json
from common import AuditError, digest, sha
from .definition import EXPECTED, INPUTS, SCHEMA, TARGET_PID, steps


def checked_root(folder):
    raw = Path(folder).absolute()
    for path in (raw, *raw.parents):
        if path.is_symlink() or (path.exists() and bool(getattr(path.lstat(),'st_file_attributes',0)&0x400)):
            raise AuditError('연결된 폴더 대신 별도의 시연 폴더를 선택하세요.')
    return raw.resolve()


def load_manifest(folder):
    from workspace import Workspace
    root = checked_root(folder);path = root/'시연_자료목록.json'
    if not path.is_file() or path.stat().st_size > 64*1024:
        raise AuditError('JS전자 감사 시연 자료목록을 확인하세요.')
    try:data = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:raise AuditError('시연 자료목록 형식 오류') from exc
    ws = Workspace(root)
    records = [e['data'] for e in ws.events if e['kind']=='demo_case_setup']
    expected_record = dict(schema=SCHEMA, workspace_id=ws.engagement['id'], manifest_hash=digest(data))
    if len(records)!=1 or records[0]!=expected_record:
        raise AuditError('시연 자료목록이 최초 생성 이력과 다릅니다. 기존 자료를 보존하세요.')
    if (not isinstance(data,dict) or data.get('schema')!=SCHEMA
            or data.get('company_code')!='JS_ELEC' or data.get('synthetic') is not True
            or data.get('workspace_id')!=ws.engagement['id']
            or ws.context['회사코드']!='JS_ELEC' or not ws.engagement.get('더미업무')
            or data.get('target_pid')!=TARGET_PID or data.get('expected')!=EXPECTED
            or data.get('steps')!=steps() or not isinstance(data.get('inputs'),dict)
            or set(data['inputs'])!=set(INPUTS)):
        raise AuditError('다른 업무 또는 변경된 시연 자료목록입니다.')
    for key, (module, name) in INPUTS.items():
        entry = data['inputs'][key]
        if (not isinstance(entry,dict) or set(entry)!={'path','module','bytes','sha256'}
                or entry.get('module')!=module or entry.get('path')!='시연입력/'+name
                or type(entry.get('bytes')) is not int or not 0<entry['bytes']<=25*1024**2):
            raise AuditError('시연 입력자료 경로·종류·크기 오류')
        relative = PurePosixPath(entry['path']);chosen = root.joinpath(*relative.parts)
        if not chosen.is_file() or not chosen.resolve().is_relative_to(root) or chosen.is_symlink():
            raise AuditError('시연 입력자료가 업무 폴더 밖을 가리킵니다.')
        for parent in (chosen, *chosen.parents):
            if parent == root.parent:break
            if parent.is_symlink() or bool(getattr(parent.lstat(),'st_file_attributes',0)&0x400):
                raise AuditError('연결된 시연 입력자료는 지원하지 않습니다.')
        if not chosen.is_file() or chosen.stat().st_size!=entry['bytes'] or sha(chosen)!=entry['sha256']:
            raise AuditError('시연 입력자료가 누락되거나 변경되었습니다. 기존 자료를 보존하세요.')
        entry['path'] = str(chosen)
    return data


def is_demo_workspace(folder):
    """Recognition only; this never authorizes approval or arbitrary file input."""
    try:load_manifest(folder)
    except (AuditError,OSError):return False
    return True
