"""Resumable preparation and guarded publication of one new public prerelease."""
import urllib.parse
from .config import *
from .policy import require,json_bytes
from .artifacts import validate_set,git_manifest
from .github_api import tag_commit
from . import git_ops
from .state import load,save,pinned,preserved
from .ci import status,gate

def notes():
    from .proof import current
    value=current()[0]
    calls=value['current_actual_model_calls']
    return ('JS전자 가상 자료에서 입력·오류 확인·실제 로컬 AI 조서 생성과 사람의 수정·내용 승인·Excel 출력을 연결하는 공개 시험 버전입니다.\n\n'
        '**이번에 확인한 흐름**\n\n'
        '- 차대가 맞는 전표 전체 누락을 별도 시산표·추출 통제로 확인하고, 청구행 누락을 매출 자료 및 현재 원장과 대사합니다. 정상 입력도 별도로 제공합니다.\n'
        '- 지정 로컬 모델이 원본·대사·예외를 인용해 초안을 생성합니다. 소스와 새 EXE에서 실제 호출한 횟수는 이번 최종 검증 합계 '+str(calls)+'회입니다.\n'
        '- 근거 화면에서 실제 원본 행·계산·대사·예외와 생략 범위를 확인합니다. 근거 없는 수치·잘못된 인용·회사/절차/버전 불일치와 완료 주장을 검사합니다.\n'
        '- 초안 생성·적용은 승인과 별개입니다. 작성자가 수정·저장한 내용에 사람의 승인을 기록하고, 조서 검토는 별도로 남깁니다.\n'
        '- 원장·입력·본문 변경 시 재확인을 요구하며 이전 초안·승인 이력은 보존합니다. 수정 문구와 근거·승인 상태를 Excel로 출력합니다.\n\n'
        '**실행 방법**\n\n'
        '`'+WINDOWS_NAME+'`을 풀고 `실행파일/'+EXE+'`를 실행합니다. 더보기 → 새 JS전자 감사 시연 → 단계 안내를 따르세요. 상세 방법은 `문서/v2.2_사용안내.md`에 있습니다.\n\n'
        '사용자용 예제의 사람 입력·판단·승인·검토는 비어 있습니다. 검증의 승인 상태전이는 별도 SYNTHETIC ONLY 업무에서 가상값으로 시험했으며 실제 사람의 감사 승인으로 보고하지 않습니다. 내용 승인이 자료 예외 해결·별도 검토·전체 감사완료·감사의견을 뜻하지 않습니다.\n\n'
        '수치 출처 검사는 숫자 토큰과 인용 근거의 기계적 확인입니다. 문장 전체의 사실성·증거 충분성·회계적 판단을 인증하지 않습니다. 실제 OpenAI 호출이나 새 한글 조합키 입력을 검증한 것으로 보고하지 않습니다.\n\n'
        '로컬 모델·실행환경은 별도 준비하며, 원본 교육자료·모범답안·실제 고객 자료·업무 DB·키·모델 원응답·로컬 로그는 공개하지 않습니다. 기존 태그·릴리스·실행파일·workflow는 보존합니다. 전체 검사와 실제 추론 범위는 `validation-report.json`을 확인하세요.\n\n')

def assets_match(release,value,partial=False):
    found={a['name']:a for a in release['assets']};expected=value['local_assets']
    require(len(found)==len(release['assets']) and (set(found)<=set(expected) if partial else set(found)==set(expected)),
            '릴리스 첨부 파일 집합 불일치')
    records=[]
    for name,a in found.items():
        e=expected[name]
        require(a.get('digest')=='sha256:'+e['sha256'] and a.get('size')==e['bytes'] and a.get('state')=='uploaded',
                '첨부 해시·크기·상태 불일치: '+name)
        records.append(dict(e,asset_id=a['id'],url=a['browser_download_url']))
    return sorted(records,key=lambda a:a['name'])

def check_commit(api,value):
    item=api.call('GET','/git/commits/'+value['commit'])
    require([p['sha'] for p in item['parents']]==[BASE],'유일 부모 fast-forward 커밋만 허용')
    return item

def stage(api):
    report=api.inspect()
    if STATE.exists():
        value=load();pinned(value);preserved(report,value)
        require(value['phase'] not in ('PUBLISHED','VERIFIED'),'이미 게시했습니다. verify를 사용하세요.')
    else:
        require(report['head']==BASE and report['tag'] is None and report['release'] is None,'새 태그 부재/기준 main 필요')
        require(not CHECKOUT.exists(),'상태 파일 없는 checkout을 덮어쓰지 않습니다.')
        assets,files=validate_set(SOURCE/'배포')
        value={'repository':REPO,'tag':TAG,'base':BASE,'private':False,'repo_id':report['repo_id'],
               'previous':report['previous'],'phase':'PREPARED','local_assets':assets,'source_files':git_manifest(files)}
        save(value)
    if value['phase']=='PREPARED':
        require(report['head']==BASE and not report['tag'] and not report['release'],'준비 이후 원격 변경')
        git_ops.commit(pinned(value)[1],value,save)
    require(value['phase']!='STAGED_LOCAL','커밋 전 중단 상태의 index를 먼저 검토하세요.')
    if value['phase']=='COMMITTED':
        current=api.inspect();preserved(current,value)
        require(not current['tag'] and not current['release'],'push 이전 태그/릴리스 충돌')
        require(current['head'] in (BASE,value['commit']),'사용자 원격 변경은 강제 덮어쓰지 않습니다.')
        if current['head']==BASE:git_ops.push(value)
        require(api.inspect()['head']==value['commit'],'push 후 커밋 불일치')
        value['phase']='PUSHED';save(value)
    require(value['phase'] in ('PUSHED','DRAFT_CREATED','STAGED'),'이 단계에서는 stage를 재개할 수 없습니다.')
    pinned(value);current=api.inspect();preserved(current,value)
    require(current['head']==value['commit'],'업로드 전 main 변경')
    if current['tag']:require(tag_commit(api,current['tag']['object'])==value['commit'],'태그 충돌')
    release=current['release']
    if release is None:
        release=api.call('POST','/releases',{'tag_name':TAG,'target_commitish':value['commit'],
            'name':RELEASE_NAME,'body':notes(),
            'draft':True,'prerelease':True,'make_latest':'false'})
    require(release['draft'] and release['prerelease'] and release['target_commitish']==value['commit']
            and release['tag_name']==TAG and value.get('release_id') in (None,release['id']),'draft 대상/ID 불일치')
    value.update(phase='DRAFT_CREATED',release_id=release['id']);save(value)
    assets_match(release,value,partial=True)
    found={a['name'] for a in release['assets']}
    for name in ASSETS:
        if name not in found:
            url=release['upload_url'].split('{')[0]+'?'+urllib.parse.urlencode({'name':name})
            api.call('POST',url,raw=(SOURCE/'배포'/name).read_bytes())
    release=api.call('GET','/releases/'+str(value['release_id']))
    value.update(phase='STAGED',assets=assets_match(release,value));save(value)
    return {'phase':'STAGED','commit':value['commit'],'source_files':len(value['source_files']),
            'assets':4,'private':False,'draft':True}

def publish(api):
    value=load();require(value['phase'] in ('STAGED','PUBLISHED','VERIFIED'),'검증한 STAGED 릴리스 필요')
    if value['phase'] in ('PUBLISHED','VERIFIED'):return verify(api)
    pinned(value);ci=gate(status(api,value));check_commit(api,value)
    current=api.inspect();preserved(current,value)
    require(current['head']==value['commit'],'게시 전 main 변경')
    if not current['tag']:
        current['tag']=api.call('POST','/git/refs',{'ref':'refs/tags/'+TAG,'sha':value['commit']})
    require(tag_commit(api,current['tag']['object'])==value['commit'],'새 태그 커밋 충돌')
    release=api.call('GET','/releases/'+str(value['release_id']))
    require(release['tag_name']==TAG and release['target_commitish']==value['commit'] and release['prerelease'],
            '게시 대상 draft 불일치');assets_match(release,value)
    if release['draft']:
        release=api.call('PATCH','/releases/'+str(value['release_id']),{
            'draft':False,'prerelease':True,'make_latest':'false','body':notes()+'\nGitHub 자동검사: '+ci['url']+'\n'})
    value.update(phase='PUBLISHED',url=release['html_url']);save(value)
    return verify(api)

def verify(api):
    value=load();pinned(value);current=api.inspect();preserved(current,value)
    require(current['head']==value['commit'] and current['tag']
            and tag_commit(api,current['tag']['object'])==value['commit'],'최종 main/태그 불일치')
    release=current['release']
    require(release and not release['draft'] and release['prerelease'] and release['id']==value['release_id']
            and release['target_commitish']==value['commit'],'최종 공개 사전 릴리스 불일치')
    ci=gate(status(api,value));assets=assets_match(release,value);commit=check_commit(api,value)
    tree=api.call('GET','/git/trees/'+commit['tree']['sha']+'?recursive=1')
    require(not tree.get('truncated'),'원격 트리 목록 잘림')
    blobs={r['path']:r for r in tree['tree'] if r['type']=='blob'}
    expected=value['source_files']+value['additional_files']
    require(set(blobs)=={r['path'] for r in expected},'원격 소스 파일 집합 불일치')
    for row in expected:
        item=blobs[row['path']]
        require(item['sha']==row['git_blob_sha'] and item['size']==row['bytes']
                and item['mode'] in ('100644','100755'),'원격 Git blob 바이트 불일치: '+row['path'])
    output={'phase':'VERIFIED','repository':REPO,'private':False,'tag':TAG,'commit':value['commit'],
            'prerelease':True,'url':release['html_url'],'source_files':len(value['source_files']),
            'remote_git_blob_sha_exact':True,'previous_release_preserved':True,'preserved_tags':list(PREVIOUS),
            'preserved_workflows':list(OLD_WORKFLOWS),'assets':assets,'ci_url':ci['url']}
    value.update(phase='VERIFIED',url=release['html_url']);save(value)
    (WORK/'release-verified.json').write_bytes(json_bytes(output));return output
