"""Package the final IME-tested v1.8.1 candidate; never infer missing evidence.

No work, network, credential lookup or application startup occurs on import.
Only explicit public files are selected. User workspaces, store.json, SQLite,
models, runtime/profile caches and raw local QA reports are never traversed.
"""
from __future__ import annotations

from pathlib import Path,PurePosixPath
import hashlib,importlib.util,json,os,re,stat,struct,uuid,zipfile,shutil

SOURCE=Path(__file__).resolve().parents[1]
PROJECT=SOURCE.parents[1]
QA=PROJECT/'검증'
VERSION='1.8.1'
SOURCE_PREFIX='js-audit-suite/'
WINDOWS_PREFIX='JS-Audit-Suite-v1.8.1/'
EXE_NAME='통합 회계감사 v1.8.1.exe'
SOURCE_NAME='js-audit-suite-v1.8.1-source.zip'
WINDOWS_NAME='JS-Audit-Suite-v1.8.1-windows.zip'
VALIDATION_NAME='validation-report.json'
NAMES=(WINDOWS_NAME,SOURCE_NAME,VALIDATION_NAME,'SHA256SUMS.txt')
BASELINE_SOURCE_SHA256='4347fa683434f5f0871832c880b565e79f6cdfcad5e700e93313518ac293d90d'
BASELINE_VALIDATION_SHA256='e4ab1f1839f9efaf7edd3f1a04ed23f87c7d4ba4f2deea58b9a3f2b675c01388'
NEW_REQUIRED={
    'app_paths.py','test_app_paths.py','windows_text.py','test_windows_text.py',
    'verify_ime_patch.py','tools/build_v181.py','tools/package_v181.py',
    'tools/github_release_v181.py','ci/audit-suite-v181.yml',
    '문서/v1.8.1_한글입력_수정안내.md',
    'assets/js-audit.ico','assets/js-audit.png','assets/ICON_SOURCE.md',
    'assets/portable-config.json',
}
IMMUTABLE=('sector_resources/','samples/','templates/','testdata/','raw_input_seed/',
           'reference_evidence/','raw_analytics/','.runtime/')

def require(ok,message):
    if not ok:raise RuntimeError(message)

def sha(data):return hashlib.sha256(data).hexdigest()

def json_bytes(value):
    return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')

def read_json(path):
    require(path.is_file() and path.stat().st_size<=32*1024**2,'필수 검증 JSON 누락/크기 오류: '+path.name)
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'JSON 중복 키: '+path.name)
            result[key]=value
        return result
    return json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,
                      parse_constant=lambda _:(_ for _ in ()).throw(RuntimeError('비유한 JSON 값')))

def safe_file(root,relative):
    require(isinstance(relative,str) and relative and '\\' not in relative and ':' not in relative,'명시적인 상대 파일 경로가 필요합니다.')
    parts=relative.split('/')
    require(not relative.startswith('/') and all(p not in ('','.','..') for p in parts),'파일 경로 이탈')
    path=root.joinpath(*parts)
    require(path.resolve().is_relative_to(root.resolve()),'파일 경로가 허용 범위를 벗어났습니다.')
    for item in (path,*path.parents):
        if item.exists() or item.is_symlink():
            flags=getattr(item.lstat(),'st_file_attributes',0)
            require(not item.is_symlink() and not flags&stat.FILE_ATTRIBUTE_REPARSE_POINT,'공개 입력의 연결 폴더/파일은 허용하지 않습니다.')
        if item==root:break
    return path

def load_module(name,relative):
    path=safe_file(SOURCE,relative)
    spec=importlib.util.spec_from_file_location(name,path)
    require(spec is not None and spec.loader is not None,'검토된 공개 도구를 읽지 못했습니다.')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def load_policy():
    helper=load_module('_js_audit_release_v181','tools/github_release_v181.py')
    require(helper.TAG=='v1.8.1' and helper.SOURCE_NAME==SOURCE_NAME,'공개 도구의 버전/첨부 이름 불일치')
    # Retain the reviewed path/credential redaction functions without executing
    # the earlier package builder or relabelling its actual-AI evidence.
    redactor=load_module('_js_audit_redaction_baseline','tools/package_v18.py')
    return helper,redactor

def current_checks():
    unit=read_json(QA/'한글입력_단위통합검사.json')
    require(unit.get('ok') is True and type(unit.get('tests')) is int and unit['tests']>=752,
            '현재 전체 단위검사 752개 이상의 실제 통과 기록이 필요합니다.')
    require(all(type(unit.get(k)) is int and unit[k]==0 for k in ('errors','failures','skipped')),
            '단위검사 오류/실패/건너뛰기 기록이 남아 있습니다.')
    build=read_json(QA/'최종빌드.json')
    require(build.get('version')==VERSION and build.get('status')=='candidate_verified','현재 v1.8.1 후보 EXE 빌드 검증이 필요합니다.')
    require(build.get('icon_embedded_verified') is True and build.get('source_frozen_observations_identical') is True,
            '현재 EXE의 아이콘·소스/EXE 저장 검증 누락')
    require(type(build.get('attempt')) is int and build['attempt']>=1 and build.get('source_frozen_checks')==18,
            '현재 소스/EXE 검사 기록이 불완전합니다.')
    ime=read_json(QA/'실제한글입력.json')
    require(ime.get('status')=='passed' and ime.get('portable_layout_verified') is True,
            '실제 키 입력 IME와 포터블 데이터 위치 확인이 완료되어야 합니다.')
    require(isinstance(ime.get('checks'),list) and ime['checks'] and
            all(isinstance(value,str) and value.strip() for value in ime['checks']),
            '실제 수행한 키 입력 확인 항목이 필요합니다.')
    exe_record=build.get('exe')
    require(isinstance(exe_record,dict) and exe_record.get('name')==EXE_NAME and
            type(exe_record.get('bytes')) is int and exe_record['bytes']>0 and
            re.fullmatch('[0-9a-f]{64}',str(exe_record.get('sha256',''))),
            '현재 EXE 파일 명세 오류')
    require(ime.get('tested_exe_sha256')==exe_record['sha256'],'실제 IME 검사 대상 EXE가 최종 빌드와 다릅니다.')
    exe_path=safe_file(PROJECT,'실행파일/'+EXE_NAME)
    require(exe_path.is_file(),'현재 실행파일이 없습니다.')
    exe=exe_path.read_bytes()
    require(len(exe)==exe_record['bytes'] and sha(exe)==exe_record['sha256'],'현재 실행파일 바이트가 IME/빌드 검증 기록과 다릅니다.')
    attempt=build['attempt']
    inputs=read_json(QA/f'최종빌드입력_{attempt}.json')
    require(isinstance(inputs,dict) and inputs,'고정된 빌드 소스 manifest가 필요합니다.')
    for relative,digest in inputs.items():
        path=safe_file(SOURCE,relative)
        require(path.is_file() and sha(path.read_bytes())==digest,'고정한 빌드 입력이 변경되었습니다: '+relative)
    source=read_json(QA/f'소스_최종_{attempt}/report.json')
    frozen=read_json(QA/f'EXE_최종_{attempt}/report.json')
    require(source.get('ok') is True and source.get('frozen') is False and frozen.get('ok') is True and frozen.get('frozen') is True,
            '현재 소스/EXE 통합 검사가 필요합니다.')
    require(source.get('version')==frozen.get('version')==VERSION and
            source.get('checks')==frozen.get('checks') and len(source.get('checks',[]))==18,
            '소스/EXE의 현재 저장·Excel 검사 결과가 다릅니다.')
    config=safe_file(PROJECT,'실행파일/portable-config.json').read_bytes()
    source_config=safe_file(SOURCE,'assets/portable-config.json').read_bytes()
    require(config==source_config,'실행파일 옆 설정이 공개할 설정 원본과 다릅니다.')
    require(json.loads(config.decode('utf-8-sig'))=={'schema_version':1,'data_directory':'../데이터/회사별업무'},
            '공개 포터블 설정은 지정된 프로젝트 내 상대 업무 위치여야 합니다.')
    ico=safe_file(SOURCE,'assets/js-audit.ico').read_bytes()
    require(len(ico)>=6 and struct.unpack_from('<HHH',ico)==(0,1,9),'9개 해상도의 원본 ICO가 필요합니다.')
    require(isinstance(build.get('actual_inference_scope'),str) and build['actual_inference_scope'].strip(),
            '현재 재추론 또는 이전 버전 AI 증거 재사용 범위를 명시해야 합니다.')
    return unit,build,ime,source,frozen,inputs,exe,config

def source_payloads(helper,baseline):
    require(baseline.is_file(),'기준 v1.8.0 공개 source ZIP이 필요합니다.')
    require(sha(baseline.read_bytes())==BASELINE_SOURCE_SHA256,'기준 v1.8.0 공개 source ZIP 해시가 다릅니다.')
    old={}
    with zipfile.ZipFile(baseline) as archive:
        require(archive.testzip() is None,'기준 공개 소스 ZIP CRC 오류')
        for info in archive.infolist():
            require(not info.is_dir() and info.filename.startswith(SOURCE_PREFIX),'기준 소스 ZIP prefix/디렉터리 오류')
            relative=info.filename[len(SOURCE_PREFIX):]
            helper.allowed_public_path(relative)
            require(relative not in old,'기준 소스 ZIP 경로 중복')
            require(not info.flag_bits&1 and ((info.external_attr>>16)&0o170000) in (0,stat.S_IFREG),'기준 ZIP 특수파일/암호화 오류')
            old[relative]=archive.read(info)
    require(len(old)==1725,'기준 공개 소스 1725개 보존 기준 불일치')
    selected=set(old)|NEW_REQUIRED
    sources={}
    for relative in sorted(selected):
        helper.allowed_public_path(relative)
        path=safe_file(SOURCE,relative)
        if relative in NEW_REQUIRED:require(path.is_file(),'신규 공개 필수 파일 누락: '+relative)
        payload=path.read_bytes() if path.is_file() else old[relative]
        if relative.startswith(IMMUTABLE) and relative in old:
            require(payload==old[relative],'기존 합성 원천자료/런타임 스크립트 변경: '+relative)
        sources[relative]=payload
    require(sources['ci/audit-suite-v181.yml']==helper.DEFAULT_WORKFLOW.encode('utf-8'),'공개 CI 설정이 검토된 새 workflow와 다릅니다.')
    require(set(old)<=set(sources),'이전 공개 소스 경로 누락')
    return sources,old

def write_archive(path,payloads,prefix,empty_directories=()):
    require(not path.exists(),'기존 ZIP을 덮어쓰지 않습니다: '+path.name)
    seen=set()
    with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED,compresslevel=8) as archive:
        for directory in empty_directories:
            info=zipfile.ZipInfo(prefix+directory.rstrip('/')+'/',date_time=(2026,10,24,0,0,0))
            info.external_attr=(stat.S_IFDIR|0o755)<<16|0x10
            archive.writestr(info,b'')
        for relative,payload in sorted(payloads.items()):
            parts=PurePosixPath(relative).parts
            require(not PurePosixPath(relative).is_absolute() and '\\' not in relative and ':' not in relative and
                    all(p not in ('','.','..') for p in relative.split('/')),'ZIP 파일 경로 이탈')
            key=relative.casefold()
            require(key not in seen,'ZIP 경로 중복');seen.add(key)
            info=zipfile.ZipInfo(prefix+relative,date_time=(2026,10,24,0,0,0))
            info.external_attr=(stat.S_IFREG|0o644)<<16;info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,payload)
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None,'생성 ZIP CRC 오류')
        require(all(archive.read(prefix+name)==payload for name,payload in payloads.items()),'ZIP 원문 바이트 불일치')

def verify_inputs(inputs,source_payloads,exe,config):
    for relative,digest in inputs.items():
        require(sha(safe_file(SOURCE,relative).read_bytes())==digest,'패키징 중 빌드 입력 변경: '+relative)
    for relative,payload in source_payloads.items():
        path=safe_file(SOURCE,relative)
        if path.is_file():require(path.read_bytes()==payload,'패키징 중 공개 소스 변경: '+relative)
    require(safe_file(PROJECT,'실행파일/'+EXE_NAME).read_bytes()==exe,'패키징 중 실제 IME 검증 EXE 변경')
    require(safe_file(PROJECT,'실행파일/portable-config.json').read_bytes()==config,'패키징 중 포터블 설정 변경')

def main():
    helper,redactor=load_policy()
    unit,build,ime,source,frozen,inputs,exe,config=current_checks()
    baseline=safe_file(PROJECT,'릴리스/기준버전/js-audit-suite-v1.8.0-source.zip')
    sources,old=source_payloads(helper,baseline)
    baseline_report=safe_file(PROJECT,'릴리스/기준버전/validation-v1.8.0.json')
    baseline_validation=read_json(baseline_report)
    require(sha(baseline_report.read_bytes())==BASELINE_VALIDATION_SHA256,'기준 v1.8.0 공개 검증 보고서 해시가 다릅니다.')
    require(baseline_validation.get('version')=='1.8.0' and baseline_validation.get('status')=='passed'
            and baseline_validation.get('actual_local_inference') is True,
            '재사용하는 v1.8.0 실제 AI 기준 검증 기록이 필요합니다.')
    dist=SOURCE/'배포';dist.mkdir(exist_ok=True)
    project_dist=PROJECT/'릴리스';project_dist.mkdir(exist_ok=True)
    stage=safe_file(dist,'package-v181-'+uuid.uuid4().hex);stage.mkdir()
    source_zip=stage/SOURCE_NAME
    write_archive(source_zip,sources,SOURCE_PREFIX)
    require(helper.publication_files(source_zip)==sources,'공개 도구가 읽은 소스 ZIP 원문 불일치')
    validation={
        'version':VERSION,'status':'passed','unit_tests':unit['tests'],
        'unit_errors':0,'unit_failures':0,'unit_skipped':0,
        'exe':build['exe'],
        'source':{'name':SOURCE_NAME,'files':len(sources),'sha256':sha(source_zip.read_bytes()),
                  'previous_public_paths_preserved':len(old)},
        'actual_hardware_ime_test':True,
        'ime_verification':redactor.sanitize(ime),
        'portable_layout_verified':True,'portable_config_schema_version':1,
        'portable_layout':{'executable':'실행파일/'+EXE_NAME,'config':'실행파일/portable-config.json',
                           'company_store':'데이터/회사별업무'},
        'icon_embedded_verified':True,'icon_group_sizes':build.get('icon_group_sizes',[]),
        'icon_source':'Original built-in ImageGen asset; attached stock image not used.',
        'icon_sha256':sha(sources['assets/js-audit.ico']),
        'source_frozen_observations_identical':True,'source_frozen_checks':18,
        'current_actual_model_calls':build.get('current_actual_model_calls',0),
        'actual_inference_scope':build['actual_inference_scope'],
        'actual_ai_baseline_version':'1.8.0',
        'baseline_actual_inference_evidence':{'version':'1.8.0',
            'validation_sha256':sha(baseline_report.read_bytes()),
            'source_zip_sha256':sha(baseline.read_bytes()),
            'actual_local_inference':True,
            'evidence_scope':'Previous released v1.8.0 validation; not current-patch model inference.'},
        'previous_release':'https://github.com/JoonseokWon/js-audit-suite/releases/tag/v1.8.0',
        'human_approval_simulated':False,'workspaces_models_runtime_profiles_excluded':True,
        'public_reports_are_path_redacted_reading_copies':True,
        'limitations':['Synthetic inputs are not independent audit evidence.',
                      'Actual local AI inference was performed in v1.8.0 and reused as labelled baseline, not rerun for this editor patch.',
                      'Actual OpenAI API calls are not verified.',
                      'AI content approval is separate from independent workpaper review and overall audit completion.',
                      'Real key-driven IME testing applies only to the described development PC and final EXE hash.',
                      'Single-line Tk fields remain separate from the native narrative and approval-note editor change.'],
    }
    validation_data=redactor.public_json(validation)
    windows={'실행파일/'+EXE_NAME:exe,'실행파일/portable-config.json':config,
             'README.md':redactor.redact_text(sources['README.md'].decode('utf-8-sig')).encode('utf-8'),
             VALIDATION_NAME:validation_data,
             '문서/아이콘출처.md':redactor.redact_text(sources['assets/ICON_SOURCE.md'].decode('utf-8-sig')).encode('utf-8')}
    for relative,payload in sources.items():
        if relative.startswith('sector_resources/'):
            windows['데이터/업종별_합성원천자료/'+relative.removeprefix('sector_resources/')]=payload
        elif relative.startswith('문서/'):
            if relative.endswith('.json'):payload=redactor.public_json(json.loads(payload.decode('utf-8-sig')))
            else:payload=redactor.redact_text(payload.decode('utf-8-sig')).encode('utf-8')
            windows[relative]=payload
        elif relative.startswith('라이선스/'):windows[relative]=payload
    windows['문서/회사별업무_보관안내.txt']=(
        '데이터/회사별업무는 새 회사 연습을 저장할 빈 폴더입니다. 첫 회사 선택 시 앱이 보관 목록과 업무를 만듭니다.\n'
        '기존 로컬 업무·자료요청·검토 기록은 이 공개 ZIP에 포함하지 않았습니다.\n'
        'EXE와 portable-config.json은 실행파일 폴더에 함께 두고 전체 폴더 구조를 유지하세요.\n').encode('utf-8')
    windows['파일목록_SHA256.json']=json_bytes([{'file':name,'bytes':len(value),'sha256':sha(value)} for name,value in sorted(windows.items())])
    windows_zip=stage/WINDOWS_NAME
    write_archive(windows_zip,windows,WINDOWS_PREFIX,empty_directories=('데이터/회사별업무/',))
    (stage/VALIDATION_NAME).write_bytes(validation_data)
    assets={name:{'name':name,'bytes':(stage/name).stat().st_size,'sha256':sha((stage/name).read_bytes())}
            for name in (WINDOWS_NAME,SOURCE_NAME,VALIDATION_NAME)}
    (stage/'SHA256SUMS.txt').write_text(''.join(assets[name]['sha256']+'  '+name+'\n' for name in (WINDOWS_NAME,SOURCE_NAME,VALIDATION_NAME)),encoding='utf-8')
    assets['SHA256SUMS.txt']={'name':'SHA256SUMS.txt','bytes':(stage/'SHA256SUMS.txt').stat().st_size,'sha256':sha((stage/'SHA256SUMS.txt').read_bytes())}
    helper.validate_current_evidence(json.loads(validation_data),assets,windows_zip)
    verify_inputs(inputs,sources,exe,config)
    for folder in (dist,project_dist):
        for name in NAMES:
            path=folder/name
            require(not path.exists() or (path.is_file() and sha(path.read_bytes())==assets[name]['sha256']),
                    '다른 내용의 기존 배포 파일은 덮어쓰지 않습니다: '+name)
    for name in NAMES:
        target=dist/name
        if not target.exists():os.replace(stage/name,target)
        mirror=project_dist/name
        if not mirror.exists():shutil.copy2(target,mirror)
        require(sha(mirror.read_bytes())==assets[name]['sha256'],'프로젝트 릴리스 사본 해시 불일치')
    require(helper.local_artifacts(WINDOWS_NAME)[0]==assets,'최종 공개 도구 첨부 검증 불일치')
    record={'version':VERSION,'status':'passed','unit_tests':unit['tests'],'source_files':len(sources),
            'previous_public_paths_preserved':1725,'source_manifest_unchanged':True,
            'actual_hardware_ime_test':True,'tested_exe_sha256':build['exe']['sha256'],
            'portable_layout_verified':True,'icon_embedded_verified':True,
            'current_actual_model_calls':build.get('current_actual_model_calls',0),
            'actual_inference_scope':build['actual_inference_scope'],
            'runtime_models_profiles_workspaces_excluded':True,'zip_crc_and_file_hashes_verified':True,
            'assets':list(assets.values())}
    (QA/'최종배포검증_v181.json').write_bytes(json_bytes(record))
    print(json.dumps(record,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except RuntimeError as exc:raise SystemExit(str(exc))
    except Exception:raise SystemExit('패키징 입력/실행 오류. 원본 자료를 보존하고 로컬 검증 파일을 확인하세요.')
