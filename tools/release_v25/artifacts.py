"""Validate the four packaged assets against pinned public source and EXE bytes."""
from io import BytesIO
import hashlib,stat,zipfile
from .config import *
from .policy import require,read,sha,manifest,json_bytes,safe_name
from .build import pinned


def blob(raw):return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def git_manifest(files):
    return {name:{'bytes':len(raw),'git_blob_sha':blob(raw)} for name,raw in sorted(files.items())}


def zip_match(raw,expected,empty=()):
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        items=archive.infolist();names=[r.filename for r in items]
        require(len(names)==len({n.casefold() for n in names}) and set(names)==set(expected)|set(empty),'패키지 파일 집합 불일치')
        for info in items:
            require(not stat.S_ISLNK(info.external_attr>>16) and not info.flag_bits&1,'패키지 특수·암호 파일 차단')
            if info.filename in empty:
                require(info.is_dir() and info.file_size==0,'빈 업무 폴더 형식 오류');continue
            require(not info.is_dir() and info.file_size==len(expected[info.filename])
                    and archive.read(info)==expected[info.filename],'패키지 바이트 불일치: '+info.filename)


def validate_set():
    folder,expected=pinned()
    files={name:(folder/name).read_bytes() for name in expected}
    out=PROJECT/'릴리스'/TAG
    require(out.is_dir() and {p.name for p in out.iterdir()}==set(ASSETS),'정확한 4개 배포 첨부 필요')
    raw={name:(out/name).read_bytes() for name in ASSETS}
    assets={name:{'bytes':len(value),'sha256':sha(value)} for name,value in raw.items()}
    require(assets==read(QA/'packaged-assets.json'),'고정 패키지 해시 변경')
    report=__import__('json').loads(raw['validation-report.json'])
    require(report['version']==VERSION and report['source_files']==expected,'검증 보고서 소스 버전/명세 불일치')
    from .package import validation
    fresh=validation(expected);given=dict(report);given.pop('exe',None)
    fresh.pop('checked_at_kst',None);given.pop('checked_at_kst',None)
    require(fresh==given,'현재 검증과 공개 검증 보고서 불일치')
    sums=''.join(assets[name]['sha256']+'  '+name+'\n' for name in ASSETS if name!='SHA256SUMS.txt').encode('utf-8')
    require(raw['SHA256SUMS.txt']==sums,'SHA256SUMS 불일치')
    zip_match(raw[SOURCE_NAME],{PREFIX+name:value for name,value in files.items()})
    prefix='JS-Audit-Suite-'+TAG+'/'
    exe=(PROJECT/'실행파일'/EXE).read_bytes()
    require(report['exe']=={'bytes':len(exe),'sha256':sha(exe)},'현재 EXE 검증 해시 불일치')
    windows={prefix+'실행파일/'+EXE:exe,prefix+'실행파일/portable-config.json':files['assets/portable-config.json'],
             prefix+'README.md':files['README.md'],prefix+'validation-report.json':raw['validation-report.json']}
    for name,value in files.items():
        safe_name(name)
        if name.startswith(('문서/','라이선스/')):windows[prefix+name]=value
        if name.startswith('sector_resources/'):
            windows[prefix+'데이터/업종별_합성원천자료/'+name[len('sector_resources/'):]]=value
    zip_match(raw[WINDOWS_NAME],windows,(prefix+'데이터/회사별업무/',))
    return assets,files
