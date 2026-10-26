"""Build only from exact public bytes, never from data-directory discovery."""
from pathlib import Path
from .policy import require,safe_file,sha,manifest_sha256


def verify(folder, files):
    folder=Path(folder);found={}
    for path in folder.rglob('*'):
        require(not path.is_symlink() and not getattr(path.lstat(),'st_file_attributes',0)&0x400,
                '빌드 사본에 연결 경로가 있습니다.')
        if path.is_file():
            relative=path.relative_to(folder).as_posix()
            found[relative]=sha(safe_file(folder,relative).read_bytes())
    expected={p:sha(v) for p,v in files.items()}
    require(found==expected,'빌드 사본의 파일 집합·바이트가 공개 manifest와 다릅니다.')
    return {'files':len(found),'byte_exact':True,'manifest_sha256':manifest_sha256(found)}


def create(folder, files):
    folder=Path(folder)
    require(not folder.exists(),'기존 빌드 사본을 덮어쓰지 않습니다.')
    folder.mkdir(parents=True)
    for relative,raw in files.items():
        target=safe_file(folder,relative);target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(raw)
    return verify(folder,files)
