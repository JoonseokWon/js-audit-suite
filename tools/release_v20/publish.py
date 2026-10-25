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
    return ('화면을 선명하게 바꾸고, 감사업무에서 다음에 할 일을 확인하기 쉽게 정리했습니다. '
        'Windows에서 실행하는 회계감사 지원 프로그램의 공개 시험 버전입니다.\n\n'
        '**화면에서 할 수 있는 일**\n\n'
        '- 업무 요약에서 등록 자료, 검사 결과, 보완할 사항과 작성·검토 상태를 확인합니다.\n'
        '- 감사계획과 중요성을 기록하고, 평가한 위험에 대응할 감사절차와 근거 자료를 연결합니다.\n'
        '- 계정별 계산 결과를 원장과 대사하고, 감사조서를 작성·검토합니다. '
        '자료나 내용이 바뀌면 다시 확인할 항목을 표시합니다.\n'
        '- 검토를 마친 조서는 실수로 바뀌지 않도록 수정을 제한합니다. '
        '수정이 필요하면 사유를 남기고 다시 작성할 수 있습니다.\n'
        '- 원본자료·감사조서·작성 및 검토 이력을 ZIP 파일로 저장하고, '
        '저장한 파일에 내용 변경이나 누락이 있는지 확인합니다.\n\n'
        '**이번 버전의 화면 개선**\n\n'
        '화면을 카드 형태로 정리하고 왼쪽 메뉴에서 기능별로 이동하도록 바꿨습니다. '
        'Windows 배율에 맞춰 글자와 표를 표시하며, 작은 창에서는 카드와 버튼을 다시 배치합니다. '
        '현금흐름표는 별도 입력 양식을 쓰는 독립 도구로 열 수 있습니다. '
        '이 도구의 결과가 현재 업무의 원장·조서에 자동으로 연결되지는 않습니다.\n\n'
        '**사용 방법**\n\n'
        '`JS-Audit-Suite-v2.0.0-windows.zip`을 풀고 '
        '`실행파일/통합 회계감사 v2.0.0.exe`를 실행하세요. '
        '회사 또는 저장된 업무를 선택한 뒤 자료 등록 → 원장 대사 → 조서 작성·검토로 진행합니다.\n\n'
        '**확인사항**\n\n'
        '실제 수행·판단·승인·검토는 사람이 기록합니다. 프로그램의 작성 상태는 실제 감사완료나 감사의견을 뜻하지 않습니다. '
        '공식 예시서식은 참고용으로 연결하며, 원본 서식의 모든 칸을 자동으로 채우지 않습니다. '
        '배포 파일에는 실제 회사 자료나 개인 업무, API 키, AI 모델을 넣지 않았습니다.\n\n'
        '<details>\n<summary>개발·검증 정보</summary>\n\n'
        '화면과 기능별 코드를 작은 모듈로 나눴으며 기존 계산 정책과 저장 이력을 유지합니다. '
        '검사 범위와 결과는 첨부한 `validation-report.json` 및 아래 자동검사 링크에서 확인할 수 있습니다. '
        '이번 변경에서는 실제 AI 응답 생성과 한글 키보드 조합 입력을 새로 시험하지 않았습니다. '
        '문자 저장·다시 열기·Excel 내보내기, 화면 배율 계산과 실제 화면 확인의 범위는 검증 기록에서 구분합니다. '
        '이전 실행파일·공개 버전·검사 이력은 보존합니다.\n\n</details>\n')

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
