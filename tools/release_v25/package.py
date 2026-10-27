"""Package verified bytes only; public reports contain no local paths or raw AI text."""
import re,zipfile
from datetime import datetime,timezone,timedelta
from .config import *
from .policy import *
from .build import pinned


def clean(report):
    keys=('version','frozen','ok','status','checks','actual_model_calls','actual_local_inference',
          'actual_human_approvals','actual_openai_calls','synthetic_approval_events','human_approval_scope',
          'execution_mode','case_mode','integrated','model','model_digest','packet_hash','response_hash',
          'seconds','independent_expected','integration_checks','gates','ui_request_policy','error')
    result={k:report[k] for k in keys if k in report}
    require(not re.search(r'(?i)[A-Z]:[\\/]|/Users/|/home/',str(result)),'공개 검증 요약에 로컬 경로 포함')
    return result


def check_actual(r,frozen):
    from desktop.ai.request_policy import POLICY_VERSION,packet_options
    require(r.get('ok') and r.get('version')==VERSION and r['actual_model_calls']==1
            and r['actual_human_approvals']==0 and r['status']=='passed'
            and r.get('case_mode')=='integrated_risk_misstatement','실제 통합 AI 검증 필요')
    require(bool(r['frozen'])==frozen,'소스/EXE 실제 추론 구분 실패')
    policy=r.get('ui_request_policy',{})
    require(policy.get('origin')=='desktop.ai.request_policy' and policy.get('version')==POLICY_VERSION
            and policy.get('packet_limits')==packet_options() and policy.get('num_ctx')==32768
            and policy.get('hardware_selection')=='automatic_default'
            and policy.get('matches_gui_default') is True and policy.get('matches_requested_policy') is True
            and policy.get('captured_options_match') is True,
            '실제 화면과 동일한 패킷·문맥·기본 실행정책 검증 필요')
    require(len(r['transport'])==1 and all(
        all(type(call['inference_counts'].get(k)) is int and call['inference_counts'][k]>0
            for k in ('prompt_eval_count','eval_count','total_duration'))
        and call['inference_counts'].get('done') is True
        and call['inference_counts'].get('done_reason')=='stop'
        for call in r['transport']),'실제 추론 counter 및 정상 종료 필요')


def validation(expected):
    source_hash=manifest_hash(expected);exe_hash=sha((PROJECT/'실행파일'/EXE).read_bytes())
    oracle=read(QA/'headless-fixed-v25-owner-freeze.json')
    headless=read(QA/'headless-fixed-v25/report.json')
    require(headless.get('ok') is True and headless['version']==VERSION
            and headless['actual_model_calls']==0 and oracle['status']=='passed'
            and oracle['original_assert_count_preserved'] is True,'전체 CI headless 경로 로컬 재검증 필요')
    require(all(expected[item['path']]['sha256']==item['sha256'] for item in oracle['files']),
            '논리 행 검증기 재검증 후 소스 변경')
    scope_chain=read(QA/'completion-scope-headless/report.json')
    scope_owner=read(QA/'completion-scope-headless-owner.json')
    require(scope_chain.get('ok') is True and scope_chain['version']==VERSION
            and scope_chain['actual_model_calls']==0 and scope_owner['status']=='passed'
            and all(expected[item['path']]['sha256']==item['sha256'] for item in scope_owner['files']),
            '완료 표현 검사 수정 후 전체 CI 경로 재검증 필요')
    for name in ('source','frozen'):
        receipt=read(QA/(name+'-check-receipt.json'))
        require(receipt['source_manifest_hash']==source_hash,'전체 검증 소스 명세 불일치')
        require(all(sha((QA/n).read_bytes())==value for n,value in receipt['reports'].items()),'전체 검증 증거 변경')
        if name=='frozen':require(receipt['exe_sha256']==exe_hash,'전체 검증 후 EXE 변경')
    reports={name:read(QA/name/'report.json') for name in
        ('source-legacy','frozen-legacy','source-flow','frozen-flow','source-ai','frozen-ai','source-large','frozen-large')}
    require(all(r.get('ok') and r.get('version')==VERSION for r in reports.values()),'현재 버전 필수 검증 미통과')
    for name in ('legacy','flow'):
        require(reports['source-'+name]['checks']==reports['frozen-'+name]['checks'],'소스·EXE 검사 항목 불일치')
    for name in ('source-ai','frozen-ai'):
        check_actual(reports[name],name=='frozen-ai')
        receipt=read(QA/name/'input-receipt.json')
        require(receipt['completed'] is True and receipt['source_manifest_hash']==source_hash
                and receipt['frozen']==(name=='frozen-ai')
                and receipt['report_sha256']==sha((QA/name/'report.json').read_bytes()),'실제 추론 입력·결과 명세 불일치')
        require(receipt['exe_sha256']==(exe_hash if name=='frozen-ai' else None),'실제 추론 후 EXE 변경')
    require(reports['source-ai']['checks']==reports['frozen-ai']['checks'],'소스·EXE 실제 통합 확인항목 불일치')
    require(all(reports[name]['rows']==10002 for name in ('source-large','frozen-large')),'큰 원장 경계 검증 필요')
    unit=(QA/'source-unit.log').read_text(encoding='utf-8-sig');match=re.search(r'Ran (\d+) tests in ([\d.]+)s',unit)
    require(match and int(match[1])>=1176 and re.search(r'\bOK(?: \(skipped=\d+\))?\s*$',unit),'고정 소스 전체 단위검사 필요')
    skipped=re.search(r'OK \(skipped=(\d+)\)\s*$',unit);skip_count=int(skipped[1]) if skipped else 0
    require(skip_count in (0,1) and (not skip_count or "skipped '공식 원본 ZIP은 공개 소스에 포함하지 않음" in unit),
            '공식 원본 비공개 외의 미실행 검사를 별도 확인하세요.')
    policy_counts=[]
    for name in ('boundary','publish'):
        log=(QA/('source-policy-'+name+'.log')).read_text(encoding='utf-8-sig')
        count=re.search(r'Ran (\d+) tests in',log)
        require(count and re.search(r'\bOK\s*$',log),'출판 경계 모의검사 미통과')
        policy_counts.append(int(count[1]))
    initial=read(QA/'ai-initial-feedback/report.json')
    previous={name:read(QA/'attempt3-before-GUI'/name/'report.json') for name in ('source-ai','frozen-ai')}
    previous_ci={name:read(QA/'attempt4-before-CI'/name/'report.json') for name in ('source-ai','frozen-ai')}
    previous_scope={name:read(QA/'attempt5-before-completion-scope'/name/'report.json') for name in ('source-ai','frozen-ai')}
    return {'schema':'js-audit-suite-v25-validation-1','version':VERSION,
        'checked_at_kst':datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'scope':'AI 예외 인용·왜곡표시 집계·위험/주장/절차/수행/조서 연결 및 가상 상태전이',
        'source_manifest_hash':manifest_hash(expected),'source_files':expected,
        'unit_tests':{'count':int(match[1]),'passed_count':int(match[1])-skip_count,'skipped_count':skip_count,
            'skip_reason':'공식 원본 ZIP은 공개 소스에 포함하지 않아 해당 원본 직접 열기 검사만 미실행' if skip_count else '',
            'seconds':float(match[2]),'passed':True},
        'publication_mock_tests':{'count':sum(policy_counts),'passed':True,'actual_remote_mutations':0},
        'local_ci_headless_regression':{k:v for k,v in oracle.items()
            if k not in ('headless_run_log','headless_report')},
        'post_completion_scope_headless_regression':{k:v for k,v in scope_owner.items()
            if k in ('files','status','version','actual_model_calls','physical_UI_control',
                     'legacy_fixture_cases','legacy_assertions','desktop_checks','v25_integration_checks','unchanged')},
        'source_legacy':clean(reports['source-legacy']),'frozen_legacy':clean(reports['frozen-legacy']),
        'source_integration':clean(reports['source-flow']),'frozen_integration':clean(reports['frozen-flow']),
        'source_actual_ai':clean(reports['source-ai']),'frozen_actual_ai':clean(reports['frozen-ai']),
        'initial_preintegration_feedback':clean(initial),
        'prior_integrated_before_ui_alignment':{name:clean(r) for name,r in previous.items()},
        'prior_integrated_before_ci_oracle_update':{name:clean(r) for name,r in previous_ci.items()},
        'prior_integrated_before_completion_scope_fix':{name:clean(r) for name,r in previous_scope.items()},
        'historical_rejection_note':'완료 전 단계·완료 여부 미확인이라는 명사구를 완료 단정으로 오인해 EXE 응답 1회를 저장 전에 거절했습니다. 최초 실패·원응답·승인 0 기록을 보존하고 국소 표현 구분을 별도로 개선했습니다. 과거 거절을 완료된 생성·승인·Excel 검증으로 바꾸지 않았습니다.',
        'actual_call_history_note':'초기 생성 1회, 화면 설정 정렬 전 각 1회, 논리 행 검증기 수정 전 각 1회, 완료 표현 오탐 수정 전 각 1회(거절 1회 포함), 최종 소스·EXE 각 1회. 모든 원응답·검증을 보존했습니다.',
        'current_actual_model_calls':initial['actual_model_calls']+sum(r['actual_model_calls'] for r in previous.values())
            +sum(r['actual_model_calls'] for r in previous_ci.values())
            +sum(r['actual_model_calls'] for r in previous_scope.values())
            +sum(reports[n]['actual_model_calls'] for n in ('source-ai','frozen-ai')),
        'actual_openai_calls':0,'actual_human_approvals':0,
        'large_ledger_current_version':{name:reports[name] for name in ('source-large','frozen-large')},
        'large_ledger_note':'현재 버전은 10,002행 경계를 검증했습니다. 이전 버전의 25만 행 검증을 이번 검증으로 재사용하지 않았습니다.',
        'physical_ime_test':False,'mixed_dpi_test':False,'actual_office_render':False,
        'human_scope':'SYNTHETIC ONLY 가상 기록·내용 승인·별도 검토. 실제 감사 수행·판단·승인 인증 아님.',
        'limits_note':'총계정원장 1,048,575행/256MB와 모듈별 기존 1,000/10,000행 한도를 유지합니다. 상한 전체를 성능 검증한 것은 아닙니다.'}


def package():
    _,expected=pinned();files=public_files();proof=validation(expected)
    exe=PROJECT/'실행파일'/EXE;proof['exe']={'bytes':exe.stat().st_size,'sha256':sha(exe.read_bytes())}
    out=PROJECT/'릴리스'/TAG;require(not out.exists(),'이전 패키지를 보존하세요.');out.mkdir()
    raw=json_bytes(proof);(out/'validation-report.json').write_bytes(raw)
    with zipfile.ZipFile(out/SOURCE_NAME,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,value in sorted(files.items()):archive.writestr(PREFIX+name,value)
    with zipfile.ZipFile(out/WINDOWS_NAME,'x',zipfile.ZIP_DEFLATED) as archive:
        prefix='JS-Audit-Suite-'+TAG+'/'
        archive.write(exe,prefix+'실행파일/'+EXE)
        archive.writestr(prefix+'실행파일/portable-config.json',files['assets/portable-config.json'])
        archive.writestr(prefix+'README.md',files['README.md']);archive.writestr(prefix+'validation-report.json',raw)
        for name,value in sorted(files.items()):
            if name.startswith(('문서/','라이선스/')):archive.writestr(prefix+name,value)
            if name.startswith('sector_resources/'):
                archive.writestr(prefix+'데이터/업종별_합성원천자료/'+name[len('sector_resources/'):],value)
        archive.writestr(prefix+'데이터/회사별업무/','')
    (out/'SHA256SUMS.txt').write_bytes(''.join(sha((out/name).read_bytes())+'  '+name+'\n'
        for name in ASSETS if name!='SHA256SUMS.txt').encode('utf-8'))
    assets={name:{'bytes':(out/name).stat().st_size,'sha256':sha((out/name).read_bytes())} for name in ASSETS}
    (QA/'packaged-assets.json').write_bytes(json_bytes(assets))
    pinned();return {'folder':str(out),'source_files':len(files),'assets':assets}
