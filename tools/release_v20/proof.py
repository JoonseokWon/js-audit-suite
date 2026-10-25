"""Validation of completed evidence; no build or test is silently substituted."""
import json
import re
from .config import *
from .policy import require,sha,safe_file,public_files

def validate(proof):
    require(proof.get('schema')==PROOF_SCHEMA and proof.get('version')==VERSION
            and proof.get('status')=='passed','현재 v2.0.0 passed 검증 증거 필요')
    unit=proof.get('unit',{})
    require(type(unit.get('tests')) is int and unit['tests']>=853
            and all(type(unit.get(k)) is int and unit[k]==0 for k in ('errors','failures','skipped')),
            '로컬 전체 검사 853개 이상·실패/오류/skip0 필요')
    scope=proof.get('unit_scope',{})
    require(scope.get('full_suite_snapshot') in ('current_source','before_header_layout_patch')
            and type(scope.get('current_source_full_suite_rerun')) is bool
            and isinstance(scope.get('description'),str) and scope['description'].strip(),
            '전체 단위검사와 현재 소스의 관계를 명시해야 합니다.')
    require(scope['current_source_full_suite_rerun']==(scope['full_suite_snapshot']=='current_source'),
            '전체 단위검사 수행 범위가 일치하지 않습니다.')
    if not scope['current_source_full_suite_rerun']:
        require(scope.get('calculation_engines_unchanged') is True,'이전 전체 검사를 재사용하려면 계산 엔진 보존 확인이 필요합니다.')
        incremental=proof.get('incremental_validation',{});ui=incremental.get('ui_tests',{})
        geometry=incremental.get('geometry_matrix',{})
        require(incremental.get('ok') is True and type(ui.get('tests')) is int and ui['tests']>0
                and all(type(ui.get(k)) is int and ui[k]==0 for k in ('errors','failures','skipped')),
                '현재 UI 변경에 대한 추가 검사 통과 증거가 필요합니다.')
        require(geometry.get('ok') is True and type(geometry.get('cases')) is int and geometry['cases']>0
                and isinstance(geometry.get('scope'),str) and geometry['scope'].strip(),
                '현재 화면 크기·배율 검사 범위를 명시해야 합니다.')
    headless=proof.get('headless',{})
    a=headless.get('source',{});b=headless.get('frozen',{})
    require(a.get('ok') is True and b.get('ok') is True and isinstance(a.get('checks'),list)
            and len(a['checks'])>=36 and a['checks']==b.get('checks'),'소스/EXE 업무 단언 일치 증거 필요')
    for field in ('source_frozen_observations_identical','portable_layout_verified','icon_embedded_verified',
                  'unicode_roundtrip_verified','bento_navigation_verified','dpi_policy_verified'):
        require(proof.get(field) is True,'현재 검사 누락: '+field)
    require(proof.get('current_actual_model_calls')==0 and type(proof['current_actual_model_calls']) is int,
            '현재 실제 모델 호출 범위는 0회')
    ime=proof.get('ime',{})
    require(ime.get('current_actual_key_test') is False and isinstance(ime.get('scope'),str)
            and ime['scope'].strip(),'새 실제 IME 키 입력 미검증 범위 필요')
    exe=proof.get('exe',{})
    require(exe.get('name')==EXE and type(exe.get('bytes')) is int and 0<exe['bytes']<150*1024**2
            and re.fullmatch('[0-9a-f]{64}',str(exe.get('sha256',''))),'현재 EXE 해시/크기 오류')
    inputs=proof.get('build_inputs',{})
    require(isinstance(inputs,dict) and len(inputs)>=1758,'공개 빌드 입력 전체 manifest 필요')
    require(all(re.fullmatch('[0-9a-f]{64}',str(h)) for h in inputs.values()),'빌드 입력 해시 오류')
    return proof

def executable_path(proof, explicit=None):
    declared=proof.get('candidate_executable')
    canonical=PROJECT/'실행파일'/EXE
    if declared is None:
        require(explicit is None or Path(explicit).resolve()==canonical.resolve(),
                '증거에 선언하지 않은 별도 EXE 경로는 사용할 수 없습니다.')
        return safe_file(PROJECT,'실행파일/'+EXE)
    require(isinstance(declared,str) and declared,'별도 후보 EXE 경로 형식 오류')
    target=Path(declared).resolve()
    require(target.is_relative_to(QA.resolve()),'후보 EXE가 현재 버전 QA 폴더 밖에 있습니다.')
    relative=target.relative_to(QA.resolve()).as_posix()
    match=re.fullmatch(r'build-attempt-([1-9][0-9]*)/candidate/실행파일/'+re.escape(EXE),relative)
    require(match and type(proof.get('attempt')) is int and int(match.group(1))==proof['attempt'],
            '후보 EXE 경로가 검증 attempt와 다릅니다.')
    require(explicit is None or Path(explicit).resolve()==target,'명시한 EXE가 검증 후보와 다릅니다.')
    return safe_file(QA,relative)

def current(executable=None):
    proof=validate(json.loads((QA/'final-validation.json').read_text(encoding='utf-8-sig')))
    files,old=public_files()
    require({p:sha(v) for p,v in files.items()}==proof['build_inputs'],'고정 빌드 후 소스 파일/바이트 변경')
    target=executable_path(proof,executable);exe=target.read_bytes()
    require(len(exe)==proof['exe']['bytes'] and sha(exe)==proof['exe']['sha256'],'검증 EXE 바이트 변경')
    require(exe[:2]==b'MZ','Windows PE 실행파일 형식 오류')
    config=safe_file(PROJECT,'실행파일/portable-config.json').read_bytes()
    require(config==files['assets/portable-config.json'],'포터블 설정 원문 변경')
    require(json.loads(config.decode('utf-8-sig'))=={'schema_version':1,'data_directory':'../데이터/회사별업무'},
            '포터블 자료 저장 경로 변경')
    if proof.get('candidate_executable'):
        require(safe_file(target.parent,'portable-config.json').read_bytes()==config,'별도 후보의 포터블 설정 불일치')
    return proof,files,old,exe,config

def summary(proof,files,old,source_sha):
    keys=('schema','version','status','exe','source_frozen_observations_identical',
          'portable_layout_verified','icon_embedded_verified','unicode_roundtrip_verified',
          'bento_navigation_verified','dpi_policy_verified','current_actual_model_calls','build_inputs')
    out={k:proof[k] for k in keys}
    out['unit']={k:proof['unit'][k] for k in ('tests','errors','failures','skipped')}
    scope=proof['unit_scope']
    out['unit_scope']={k:scope[k] for k in ('full_suite_snapshot','current_source_full_suite_rerun','description')}
    if 'calculation_engines_unchanged' in scope:
        out['unit_scope']['calculation_engines_unchanged']=scope['calculation_engines_unchanged']
    if 'incremental_validation' in proof:
        extra=proof['incremental_validation'];geometry=extra['geometry_matrix']
        out['incremental_validation']={'ok':extra['ok'],
            'ui_tests':{k:extra['ui_tests'][k] for k in ('tests','errors','failures','skipped')},
            'geometry_matrix':{k:geometry[k] for k in ('ok','cases','scope')}}
    out['headless']={mode:{'ok':True,'checks':proof['headless'][mode]['checks']} for mode in ('source','frozen')}
    out['ime']={k:proof['ime'][k] for k in ('current_actual_key_test','scope')}
    out.update(supported_scope=SCOPE,source={'name':SOURCE_NAME,'files':len(files),'sha256':source_sha,
               'previous_public_paths_preserved':len(old),'baseline_source_sha256':BASE_ZIP_SHA},
               previous_tags_preserved=list(PREVIOUS),previous_root_workflows_preserved=list(OLD_WORKFLOWS),
               scope='합성 자료·기계적 연결·UI 상태 검증. 실제 감사 수행·판단·승인은 사람 입력.',
               source_frozen_comparison_scope='같은 기호화된 업무 단언. UUID·시각·raw DB/ZIP 바이트 동일성을 주장하지 않음.',
               excluded='실제 업무·DB·원본 첨부·키·AI 모델·런타임 캐시·공식 기준서/예시 원본')
    return out
