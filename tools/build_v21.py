"""Build a new candidate without overwriting any previous executable or evidence."""
from pathlib import Path
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.release_v21.config import *
from tools.release_v21.policy import require,sha,json_bytes,public_files,safe_file,manifest_sha256

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=1)
    parser.add_argument('--candidate-dir',type=Path,help='Use this attempt\'s QA/candidate folder while the installed EXE remains open')
    args=parser.parse_args()
    require(sys.platform=='win32' and sys.version_info[:2]==(3,14),'최종 Windows EXE는 지정된 Python 3.14 빌드 환경을 사용하세요.')
    require(args.attempt>0,'양수 build attempt 필요')
    QA.mkdir(parents=True,exist_ok=True);base=QA/f'build-attempt-{args.attempt}'
    require(not base.exists(),'기존 빌드 증거를 보존하고 새 attempt를 사용하세요.');base.mkdir()
    if args.candidate_dir is not None:
        candidate_dir=args.candidate_dir.resolve()
        require(candidate_dir==(base/'candidate').resolve(),'후보 폴더는 이번 build-attempt의 candidate 경로만 허용합니다.')
        safe_file(base,'candidate');require(not candidate_dir.exists(),'기존 후보 폴더를 덮어쓰지 않습니다.')
        (candidate_dir/'실행파일').mkdir(parents=True)
        target=candidate_dir/'실행파일'/EXE
        shutil.copy2(SOURCE/'assets/portable-config.json',target.parent/'portable-config.json')
    else:
        target=PROJECT/'실행파일'/EXE
    require(not target.exists(),'기존 EXE는 별도 보존한 뒤 새 후보를 만드세요.')
    files,_=public_files();inputs={p:sha(v) for p,v in files.items()}
    (base/'build-inputs.json').write_bytes(json_bytes(inputs))
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYINSTALLER_CONFIG_DIR=str(base/'config'))
    def run(argv,log,cwd=SOURCE):
        with (base/log).open('x',encoding='utf-8') as stream:
            result=subprocess.run([str(x) for x in argv],cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,
                                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        require(result.returncode==0,log+' 실패. 보존된 증거를 확인하세요.')
    source_report=base/'source/report.json'
    run([sys.executable,'-B','-X','utf8','app.py','--self-test-v21','--report',source_report],'source.log')
    source=json.loads(source_report.read_text(encoding='utf-8'))
    require(source['ok'] and source.get('version')==VERSION and source['frozen'] is False
            and len(source['checks'])>=len(COVERAGE) and set(source.get('coverage',[]))==set(COVERAGE)
            and all(source.get('gates',{}).get(gate) is True for gate in GATES)
            and source.get('bento_navigation_verified') and source.get('dpi_policy_verified'),'현재 소스 self-test 미완료')
    run([sys.executable,'-B','-X','utf8','-m','PyInstaller','--noconfirm','--clean',
         '--distpath',base/'dist','--workpath',base/'work',SOURCE/'AuditSuite.spec'],'pyinstaller.log')
    candidate=base/'dist/AuditSuite.exe'
    import pefile
    pe=pefile.PE(str(candidate));groups=[]
    try:
        for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if kind.id==14:
                for name in kind.directory.entries:
                    for lang in name.directory.entries:
                        data=lang.data.struct;groups.append(struct.unpack_from('<HHH',pe.get_data(data.OffsetToData,data.Size))[2])
    finally:pe.close()
    require(groups and min(groups)>=9,'기존 독자제작 다중 해상도 아이콘 누락')
    from PyInstaller.utils.win32.winmanifest import read_manifest_from_executable
    actual=ET.fromstring(read_manifest_from_executable(str(candidate)))
    expected=ET.parse(SOURCE/'windows.manifest').getroot()
    get=lambda root:{el.tag.split('}')[-1]:(el.text or '').strip() for el in root.iter()}
    require(get(expected).get('dpiAwareness') and get(actual).get('dpiAwareness')==get(expected).get('dpiAwareness')
            and get(actual).get('dpiAware')==get(expected).get('dpiAware'),'EXE DPI manifest 원문 정책 불일치')
    shutil.copy2(candidate,target)
    frozen_report=base/'frozen/report.json'
    run([target,'--self-test-v21','--report',frozen_report],'frozen.log',target.parent)
    frozen=json.loads(frozen_report.read_text(encoding='utf-8'))
    require(frozen['ok'] and frozen.get('version')==VERSION and frozen['frozen'] is True and source['checks']==frozen['checks']
            and source['coverage']==frozen.get('coverage') and source['gates']==frozen.get('gates')
            and frozen.get('bento_navigation_verified') and frozen.get('dpi_policy_verified'),'현재 소스/EXE 단언 불일치')
    require(all(type(r.get('current_actual_model_calls')) is int and r['current_actual_model_calls']==0
                for r in (source,frozen)),'실제 모델 호출은 이번 배포 검사 범위가 아닙니다.')
    require({p:sha(v) for p,v in public_files()[0].items()}==inputs,'빌드 도중 소스 변경')
    require((PROJECT/'실행파일/portable-config.json').read_bytes()==files['assets/portable-config.json'],'포터블 설정 변경')
    from app_paths import portable_storage_root
    expected_storage=(target.parent.parent/'데이터/회사별업무').resolve()
    require(portable_storage_root(executable=target,frozen=True)==expected_storage,'포터블 업무 상대 위치 변경')
    record={'schema':'audit-suite-v21-build-1','version':VERSION,'status':'candidate_verified','attempt':args.attempt,
        'exe':{'name':EXE,'bytes':target.stat().st_size,'sha256':sha(target.read_bytes())},'build_inputs':inputs,
        'source_manifest_sha256':manifest_sha256(inputs),
        'headless':{'source':source,'frozen':frozen},'source_frozen_observations_identical':True,
        'source_frozen_checks':len(source['checks']),'unicode_roundtrip_verified':True,'portable_layout_verified':True,
        'icon_embedded_verified':True,'icon_group_sizes':groups,'bento_navigation_verified':True,
        'dpi_policy_verified':True,'dpi_manifest':get(actual).get('dpiAwareness'),'current_actual_model_calls':0,
        'ime':{'current_actual_key_test':False,
               'scope':'v2.1 adds explicit data/procedure support and retains the native editor. No new physical IME keystroke test; Unicode/save/Excel roundtrip is tested again.'}}
    if args.candidate_dir is not None:record['candidate_executable']=str(target.resolve())
    (QA/'candidate-build.json').write_bytes(json_bytes(record))
    print(json.dumps({k:v for k,v in record.items() if k not in ('build_inputs','headless')},ensure_ascii=False));return 0

if __name__=='__main__':raise SystemExit(main())
