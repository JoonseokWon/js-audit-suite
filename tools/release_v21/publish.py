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
    return ('ERP 원본 자료와 원장, 계정별 실증절차와 조서를 연결하는 공개 시험 버전입니다.\n\n'
        '**이번에 추가한 기능**\n\n'
        '- ERP 열·계정·부호·단위를 연결하고 원본 파일·물리행을 보존합니다. '
        '별도 시산표·추출 통제와 대사해 차대가 맞는 전표 누락도 확인합니다.\n'
        '- 취소전표를 보존하며 계정·월·부문 분석과 전표 전체 탐색을 지원합니다. '
        '사람이 확인한 조정을 조정전·후 TB와 본문·선택 주석·제조원가에 연결합니다.\n'
        '- 자산 증감·표본선정·금융기관 조회·주석 구성·분류 검토를 명시된 자료와 방법 범위에서 지원합니다.\n'
        '- 원장 연결 현금흐름표에서 제조상각 배부, 실제 현금행, 비현금·대체, '
        '분류정책과 검증 그룹을 구분합니다. 기존 독립 현금흐름표 도구도 보존합니다.\n'
        '- 현재 원장 검사 버전과 원본·설정 해시를 결과와 조서에 연결하고, 변경 시 재검사를 요구합니다.\n\n'
        '**실행과 확인**\n\n'
        '`'+WINDOWS_NAME+'`을 풀고 `실행파일/'+EXE+'`를 실행하세요. '
        '회사·업무 선택 → 감사계획 → 자료 등록과 원장 통제 → 계정별 검사 → '
        '조서 작성·검토 순서로 확인합니다. 자세한 방법은 `문서/v2.1_사용안내.md`를 참고하세요.\n\n'
        '실제 수행·판단·표본 방법과 규모·분류정책·회신 진위·승인·검토는 사람이 확인합니다. '
        '대사 일치와 프로그램의 완료 상태는 실제 감사완료나 감사의견이 아닙니다. '
        '확정 KRW·명시 매핑의 기계적 지원이며 모든 회계·감사기준 준수나 모든 표본기법을 구현하지 않습니다.\n\n'
        '검증 범위와 현재 전체 단위검사·소스/EXE 비교 결과는 `validation-report.json`에 기록합니다. '
        '새 실제 AI 모델 호출·한글 조합 키 입력을 시험했다고 주장하지 않습니다. '
        '배포에는 교육 문제집·모범답안 원본, 실제 고객 자료·업무 DB·키·AI 모델·검증 로그를 넣지 않습니다. '
        '이전 태그·릴리스·실행파일과 CI는 보존합니다.\n\n')

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
