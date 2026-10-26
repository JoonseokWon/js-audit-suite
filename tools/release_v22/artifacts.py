"""Four-file release contract, checked again before every remote mutation."""
import json
import stat
import zipfile
from .config import *
from .policy import require,sha,read_zip,safe_file,safe_name
from .proof import validate,current

def record(files):
    return {name:{'name':name,'bytes':len(raw),'sha256':sha(raw)} for name,raw in files.items()}

def windows_files(path):
    found={}
    with zipfile.ZipFile(path) as z:
        require(z.testzip() is None and len(z.infolist())<5000,'Windows ZIP CRC/개수 오류')
        for info in z.infolist():
            require(info.filename.startswith(WINDOWS_PREFIX),'Windows ZIP 루트 오류')
            relative=info.filename[len(WINDOWS_PREFIX):]
            if info.is_dir():
                require(relative=='데이터/회사별업무/','Windows ZIP 예상 밖 폴더')
                continue
            safe_name(relative)
            require(relative.casefold() not in {p.casefold() for p in found},'Windows ZIP 중복')
            require(not info.flag_bits&1 and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG)
                    and info.file_size<150*1024**2,'Windows ZIP 특수파일/암호화/크기 오류')
            found[relative]=z.read(info)
    return found

def validate_set(folder):
    raw={name:safe_file(folder,name).read_bytes() for name in ASSETS}
    assets=record(raw)
    sums=''.join(assets[name]['sha256']+'  '+name+'\n' for name in ASSETS[:3]).encode('utf-8')
    require(raw['SHA256SUMS.txt']==sums,'SHA256SUMS 첨부 해시/순서 불일치')
    proof,files,old,exe,config=current()
    require(read_zip(Path(folder)/SOURCE_NAME,PREFIX)==files,'공개 소스 ZIP 바이트/파일 집합 불일치')
    validation=json.loads(raw[VALIDATION]);validate(validation)
    require(validation['supported_scope']==SCOPE and validation['source']['sha256']==assets[SOURCE_NAME]['sha256'],
            '검증보고서 버전/범위/소스 해시 불일치')
    require(validation['build_inputs']==proof['build_inputs'],'검증보고서 빌드 입력 불일치')
    windows=windows_files(Path(folder)/WINDOWS_NAME)
    require(windows.get('실행파일/'+EXE)==exe and windows.get('실행파일/portable-config.json')==config,
            'Windows ZIP EXE/설정 바이트 불일치')
    require(windows.get(VALIDATION)==raw[VALIDATION],'Windows ZIP 검증보고서 불일치')
    manifest=json.loads(windows.pop('파일목록_SHA256.json'))
    require(manifest==[{'file':p,'bytes':len(v),'sha256':sha(v)} for p,v in sorted(windows.items())],
            'Windows ZIP 내부 파일 manifest 불일치')
    allowed={'실행파일/'+EXE,'실행파일/portable-config.json','README.md',VALIDATION,'문서/회사별업무_보관안내.txt'}
    allowed|={p for p in files if p.startswith(('문서/','라이선스/'))}
    allowed|={'데이터/업종별_합성원천자료/'+p[len('sector_resources/'):] for p in files if p.startswith('sector_resources/')}
    require(set(windows)==allowed,'Windows ZIP 개인정보/예상 밖 파일 차단')
    for relative,payload in files.items():
        if relative.startswith('sector_resources/'):
            require(windows['데이터/업종별_합성원천자료/'+relative[len('sector_resources/'):]]==payload,'합성 원천자료 변경')
    return assets,files

def git_manifest(files):
    import hashlib
    return [{'path':path,'bytes':len(raw),'sha256':sha(raw),
             'git_blob_sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}
            for path,raw in sorted(files.items())]
