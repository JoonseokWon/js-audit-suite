"""Freeze explicit inputs, test those bytes, then build a new executable."""
import shutil,sys,struct,xml.etree.ElementTree as ET
from .config import *
from .policy import *


def stage():
    require(sys.version_info[:2]==(3,14),'지정 Python 3.14 빌드 환경 필요')
    base=QA/'build';require(not base.exists(),'이전 빌드를 보존하고 별도 경로를 사용하세요.')
    files=public_files();folder=base/'stage';folder.mkdir(parents=True)
    for name,raw in files.items():
        path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    (folder/'검증').mkdir(exist_ok=True)
    (base/'manifest.json').write_bytes(json_bytes(manifest(files)))
    return {'source_files':len(files),'manifest':str(base/'manifest.json')}


def pinned():
    expected=read(QA/'build/manifest.json');current=manifest(public_files())
    require(current==expected,'고정 후 소스 변경. 기존 빌드 증거는 보존하고 새 빌드가 필요합니다.')
    folder=QA/'build/stage'
    # Existing regression tests create private temporary engagements here.
    # Neither folder is scanned by public_files() or included in AuditSuite.spec.
    scratch={'검증','sector_verification'}
    found={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()
           and (p.relative_to(folder).parts[0] not in scratch or p.relative_to(folder).as_posix() in expected)}
    require(found==set(expected),'고정 stage에 추가·누락 파일이 있습니다.')
    require(all(sha(safe_file(folder,name).read_bytes())==item['sha256'] for name,item in expected.items()),'고정 stage 변경')
    return folder,expected


def verify_source():
    folder,_=pinned()
    for name in ('boundary','publish'):
        file='tools/test_release_v25.py' if name=='boundary' else 'tools/test_release_v25_publish.py'
        run([sys.executable,'-B','-X','utf8',file],QA/('source-policy-'+name+'.log'),folder)
    run([sys.executable,'-B','-X','utf8','app.py','--self-test-v22','--report',QA/'source-legacy/report.json'],
        QA/'source-legacy.log',folder)
    run([sys.executable,'-B','-X','utf8','app.py','--self-test-v25','--report',QA/'source-flow/report.json'],
        QA/'source-flow.log',folder)
    run([sys.executable,'-B','-X','utf8','-m','unittest','discover','-v'],QA/'source-unit.log',folder)
    _,expected=pinned()
    (QA/'source-check-receipt.json').write_bytes(json_bytes({'source_manifest_hash':manifest_hash(expected),
        'reports':{n:sha((QA/n).read_bytes()) for n in
            ('source-unit.log','source-legacy/report.json','source-flow/report.json',
             'source-policy-boundary.log','source-policy-publish.log')}}))
    return {'ok':True,'stage':str(folder)}


def build():
    folder,_=pinned();base=QA/'build';target=PROJECT/'실행파일'/EXE
    require(not target.exists() and not (base/'dist').exists(),'기존 새 버전 실행파일을 덮어쓰지 않습니다.')
    run([sys.executable,'-B','-X','utf8','-m','PyInstaller','--noconfirm','--clean',
         '--distpath',base/'dist','--workpath',base/'work',folder/'AuditSuite.spec'],base/'build.log',folder)
    import pefile
    from PyInstaller.utils.win32.winmanifest import read_manifest_from_executable
    candidate=base/'dist/AuditSuite.exe';pe=pefile.PE(str(candidate));groups=[]
    try:
        for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if kind.id==14:
                for name in kind.directory.entries:
                    for lang in name.directory.entries:
                        data=lang.data.struct
                        groups.append(struct.unpack_from('<HHH',pe.get_data(data.OffsetToData,data.Size))[2])
    finally:pe.close()
    require(groups and min(groups)>=9,'다중 해상도 아이콘 누락')
    actual=ET.fromstring(read_manifest_from_executable(str(candidate)))
    values=lambda root:{e.tag.split('}')[-1]:(e.text or '').strip() for e in root.iter()}
    expected=values(ET.parse(folder/'windows.manifest').getroot());embedded=values(actual)
    require(all(embedded[k]==expected[k] for k in ('dpiAwareness','dpiAware')),'EXE DPI manifest 정책 불일치')
    require((target.parent/'portable-config.json').read_bytes()==(folder/'assets/portable-config.json').read_bytes(),
            '포터블 설정 불일치')
    (base/'embedded-resources.json').write_bytes(json_bytes({'icon_group_sizes':groups,
        'dpi_awareness':embedded['dpiAwareness'],'physical_ime_test':False,'mixed_dpi_test':False}))
    shutil.copy2(base/'dist/AuditSuite.exe',target)
    run([target,'--self-test-v22','--report',QA/'frozen-legacy/report.json'],QA/'frozen-legacy.log',target.parent)
    run([target,'--self-test-v25','--report',QA/'frozen-flow/report.json'],QA/'frozen-flow.log',target.parent)
    source=read(QA/'source-flow/report.json');frozen=read(QA/'frozen-flow/report.json')
    require(source['ok'] and frozen['ok'] and source['checks']==frozen['checks'],'소스·EXE 신규 통합 검사 불일치')
    require(read(QA/'source-legacy/report.json')['checks']==read(QA/'frozen-legacy/report.json')['checks'],
            '소스·EXE 기존 통합 검사 불일치')
    _,expected=pinned()
    (QA/'frozen-check-receipt.json').write_bytes(json_bytes({'source_manifest_hash':manifest_hash(expected),
        'exe_sha256':sha(target.read_bytes()),'reports':{n:sha((QA/n).read_bytes()) for n in
            ('frozen-legacy/report.json','frozen-flow/report.json')}}))
    return {'exe':str(target),'sha256':sha(target.read_bytes()),'new_checks':len(source['checks'])}
