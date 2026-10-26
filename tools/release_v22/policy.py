"""Explicit baseline plus bounded code-only additions. Never traverse user data."""
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from .config import *

def require(value, message):
    if not value:
        raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def json_bytes(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')


def manifest_sha256(inputs):
    return sha(json.dumps(inputs,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))

def safe_name(relative):
    require(isinstance(relative,str) and relative and len(relative)<240
            and not any(c in relative for c in '\\:\x00') and not relative.startswith('/'), '공개 경로 형식 오류')
    parts=relative.split('/')
    require(all(p not in ('','.','..') and not p.endswith((' ','.')) for p in parts), '공개 경로 이탈')
    banned={'.git','.env','__pycache__','node_modules','메일 자동화','models','model','로컬ai','private','github공개릴리스'}
    require(not any(p.casefold() in banned or p.casefold().startswith('.env.') for p in parts), '개인 경로 공개 차단')
    require(not re.search(r'[\x01-\x1f<>"|?*]',relative), '지원하지 않는 공개 파일명')
    return relative

def safe_file(root, relative):
    safe_name(relative)
    root=Path(root)
    cursor=root
    require(not root.is_symlink() and (not root.exists() or not getattr(root.lstat(),'st_file_attributes',0)&0x400),
            '연결된 공개 소스 루트 차단')
    for part in PurePosixPath(relative).parts:
        cursor=cursor/part
        if cursor.exists():
            info=cursor.lstat()
            require(not cursor.is_symlink() and not getattr(info,'st_file_attributes',0)&0x400,
                    '공개 소스의 연결/재분석 경로 차단')
    require(cursor.resolve().is_relative_to(root.resolve()), '공개 소스 범위 이탈')
    return cursor

def baseline():
    require(BASE_ZIP.is_file() and sha(BASE_ZIP.read_bytes())==BASE_ZIP_SHA,'v2.1 공개 기준 ZIP 변경')
    return read_zip(BASE_ZIP,PREFIX,expected_count=BASELINE_COUNT)

def new_path(relative):
    safe_name(relative)
    p=PurePosixPath(relative)
    if any(part.startswith('.') for part in p.parts):
        return False
    code=(p.parts[0] in ('ai_quality','demo_case') or relative.startswith(('desktop/ai/','desktop/demo/','tools/release_v22/')))
    if code:
        return p.suffix=='.py' and len(p.parts)<=5
    return (relative in NEW_FIXED or
            ('/' not in relative and re.fullmatch(r'test_(?:ai_quality|demo_case|demo_desktop|v22)(?:_[a-z0-9_]+)?\.py',relative) is not None))

def public_files(source=SOURCE):
    old=baseline(); selected=dict(old)
    for relative,raw in old.items():
        path=safe_file(source,relative)
        require(path.is_file(),'기존 공개 파일 누락: '+relative)
        current=path.read_bytes()
        mutable=relative in MUTABLE or relative.startswith('desktop/') or ('/' not in relative and relative.startswith('test_') and relative.endswith('.py'))
        require(current==raw or mutable,'계산·자료·옛 도구/CI 변경 차단: '+relative)
        if relative=='common.py' and current!=raw:
            from .common_guard import validate_common
            validate_common(raw,current)
        selected[relative]=current
    additions=[]
    for directory in ('ai_quality','demo_case','desktop/ai','desktop/demo','tools/release_v22'):
        base=Path(source)/directory
        if base.exists():
            additions.extend(p.relative_to(source).as_posix() for p in base.rglob('*.py'))
    additions.extend(NEW_FIXED)
    additions.extend(p.name for p in Path(source).glob('test_*.py') if p.name not in old and new_path(p.name))
    for relative in sorted(set(additions)):
        require(new_path(relative),'새 공개 파일 허용 범위 오류: '+relative)
        path=safe_file(source,relative)
        require(path.is_file(),'새 공개 필수 파일 누락: '+relative)
        selected[relative]=path.read_bytes()
    require(len(selected)==len(set(p.casefold() for p in selected)),'공개 경로 대소문자 중복')
    require(all(p in selected for p in NEW_FIXED),'새 공개 필수 파일 누락')
    require(sha(selected['ci/audit-suite-v22.yml'])==WORKFLOW_SHA256,'검토한 v2 Windows CI 바이트가 변경되었습니다.')
    roots={p.name for p in Path(source).iterdir() if p.is_file() and p.suffix in ('.py','.spec','.manifest')}
    require(roots<=set(selected),'현재 root 코드가 공개 빌드 입력에서 누락되었습니다: '+str(sorted(roots-set(selected))))
    return selected,old

def write_zip(path, files, prefix, empty=()):
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        for relative,raw in sorted(files.items()):
            safe_name(relative)
            info=zipfile.ZipInfo(prefix+relative,date_time=(2026,10,26,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(stat.S_IFREG|0o644)<<16
            z.writestr(info,raw)
        for relative in empty:
            info=zipfile.ZipInfo(prefix+relative,date_time=(2026,10,26,0,0,0))
            info.external_attr=(stat.S_IFDIR|0o755)<<16;z.writestr(info,b'')

def read_zip(path,prefix,expected_count=None):
    result={}
    with zipfile.ZipFile(path) as z:
        require(len(z.infolist())<=5000 and z.testzip() is None,'공개 ZIP CRC/개수 오류')
        for item in z.infolist():
            require(item.filename.startswith(prefix) and item.orig_filename==item.filename,'ZIP 루트 오류')
            rel=safe_name(item.filename[len(prefix):])
            require(not item.is_dir() and rel.casefold() not in {p.casefold() for p in result},'ZIP 중복/폴더 오류')
            require(not item.flag_bits&1 and stat.S_IFMT(item.external_attr>>16) in (0,stat.S_IFREG),'ZIP 특수 파일 오류')
            require(item.file_size<150*1024**2,'공개 파일 크기 한도 초과')
            result[rel]=z.read(item)
    if expected_count is not None:require(len(result)==expected_count,'기준 공개 파일 수 오류')
    return result
