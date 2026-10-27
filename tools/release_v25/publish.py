"""Explicit staging and CI-gated publication of one new v2.5 prerelease."""
import urllib.parse
from .config import *
from .policy import require,json_bytes
from .remote import BASE,PREVIOUS,OLD_WORKFLOWS,inspect,tag_commit,preflight_hash
from .artifacts import validate_set,git_manifest
from .state import STATE,load,save,check_pins
from .ci import status,gate
from .notes import notes,TITLE
from .downloads import verify_public
from . import git_ops


def assets_match(release,value,partial=False):
    found={item['name']:item for item in release['assets']};expected=value['local_assets']
    require(len(found)==len(release['assets']) and (set(found)<=set(expected) if partial else set(found)==set(expected)),
            '릴리스 첨부 파일 집합 불일치')
    output={}
    for name,item in found.items():
        wanted=expected[name]
        require(item.get('digest')=='sha256:'+wanted['sha256'] and item.get('size')==wanted['bytes']
                and item.get('state')=='uploaded','서버 첨부 해시·크기·상태 불일치: '+name)
        output[name]={**wanted,'asset_id':item['id'],'url':item['browser_download_url']}
    return output


def check_commit(api,value):
    commit=api.call('GET','/git/commits/'+value['commit'])
    require([p['sha'] for p in commit['parents']]==[BASE],'단일 부모 fast-forward 커밋 필요')
    return commit


def check_tree(api,value):
    commit=check_commit(api,value)
    tree=api.call('GET','/git/trees/'+commit['tree']['sha']+'?recursive=1')
    require(not tree.get('truncated') and all(row['type'] in ('tree','blob') for row in tree['tree']),
            '원격 트리 잘림·특수파일 차단')
    entries=[row for row in tree['tree'] if row['type']=='blob'];blobs={row['path']:row for row in entries}
    expected={**value['source_files'],**value['additional_files']}
    require(len(entries)==len(blobs) and set(blobs)==set(expected),'원격 소스 파일 집합 불일치')
    for name,item in expected.items():
        row=blobs[name]
        require(row['sha']==item['git_blob_sha'] and row['size']==item['bytes'] and row['mode'] in ('100644','100755'),
                '원격 Git blob 바이트 불일치: '+name)
    return commit


def stage(api):
    remote=inspect(api)
    if STATE.exists():
        value=load();check_pins(value)
        require(value['phase'] not in ('PUBLISHED','VERIFIED'),'이미 게시했습니다. github-verify를 사용하세요.')
    else:
        require(remote['head']==BASE and not remote['tag'] and not remote['release'],'기준 main과 새 태그·릴리스 부재 필요')
        require(not CHECKOUT.exists(),'상태 없는 checkout을 덮어쓰지 않습니다.')
        assets,files=validate_set()
        value={'repository':REPO,'tag':TAG,'base':BASE,'private':False,'repo_id':REPO_ID,
            'preflight_hash':preflight_hash(),'phase':'PREPARED','local_assets':assets,
            'source_files':git_manifest(files),'body':notes()};save(value)
    require(remote['preflight_hash']==value['preflight_hash'],'이전 공개 이력 기준 변경')
    if value['phase']=='PREPARED':
        require(remote['head']==BASE and not remote['tag'] and not remote['release'],'준비 이후 원격 변경')
        git_ops.commit(check_pins(value),value,save)
    require(value['phase']!='STAGED_LOCAL','중단된 index를 자동 재작성하지 않습니다. 전용 checkout을 검토하세요.')
    if value['phase']=='COMMITTED':
        remote=inspect(api)
        require(not remote['tag'] and not remote['release'] and remote['head'] in (BASE,value['commit']),
                'push 이전 원격 main·태그·릴리스 충돌')
        if remote['head']==BASE:git_ops.push(value)
        require(inspect(api)['head']==value['commit'],'push 후 커밋 불일치')
        value['phase']='PUSHED';save(value)
    require(value['phase'] in ('PUSHED','DRAFT_CREATED','STAGED'),'이 단계에서는 stage를 재개할 수 없습니다.')
    check_pins(value);remote=inspect(api);check_commit(api,value)
    require(remote['head']==value['commit'],'첨부 업로드 전 main 변경')
    if remote['tag']:require(tag_commit(api,remote['tag']['object'])==value['commit'],'새 태그 커밋 충돌')
    release=remote['release']
    if release is None:
        release=api.call('POST','/releases',{'tag_name':TAG,'target_commitish':value['commit'],
            'name':TITLE,'body':value['body'],'draft':True,'prerelease':True,'make_latest':'false'})
    require(release['draft'] and release['prerelease'] and release['target_commitish']==value['commit']
            and release['tag_name']==TAG and release['name']==TITLE and release['body']==value['body']
            and value.get('release_id') in (None,release['id']),'새 draft 대상·본문·ID 불일치')
    value.update(phase='DRAFT_CREATED',release_id=release['id']);save(value)
    assets_match(release,value,partial=True);found={a['name'] for a in release['assets']}
    for name in ASSETS:
        if name not in found:
            base=release['upload_url'].split('{')[0]
            require(base=='https://uploads.github.com/repos/'+REPO+'/releases/'+str(value['release_id'])+'/assets',
                    '첨부 업로드 대상 저장소·릴리스 불일치')
            url=base+'?'+urllib.parse.urlencode({'name':name})
            api.call('POST',url,raw=(PROJECT/'릴리스'/TAG/name).read_bytes())
    release=api.call('GET','/releases/'+str(value['release_id']))
    value.update(phase='STAGED',assets=assets_match(release,value));save(value)
    return {'phase':'STAGED','commit':value['commit'],'release_id':value['release_id'],
            'source_files':len(value['source_files']),'assets':value['assets'],'private':False,'draft':True}


def publish(api):
    value=load();require(value['phase'] in ('STAGED','PUBLISHED','VERIFIED'),'검증한 STAGED 릴리스 필요')
    if value['phase'] in ('PUBLISHED','VERIFIED'):return verify(api)
    check_pins(value);ci=gate(status(api,value));check_tree(api,value);remote=inspect(api)
    require(remote['head']==value['commit'],'게시 전 main 변경')
    if remote['tag']:require(tag_commit(api,remote['tag']['object'])==value['commit'],'새 태그 커밋 충돌')
    release=api.call('GET','/releases/'+str(value['release_id']))
    require(release['tag_name']==TAG and release['target_commitish']==value['commit'] and release['prerelease']
            and release['name']==TITLE and release['body']==value['body'],'게시 대상 draft 불일치')
    assets_match(release,value)
    # An interrupted successful PATCH may already be public: verify it, do not create another release.
    if release['draft']:
        if not remote['tag']:api.call('POST','/git/refs',{'ref':'refs/tags/'+TAG,'sha':value['commit']})
        release=api.call('PATCH','/releases/'+str(value['release_id']),
                         {'draft':False,'prerelease':True,'make_latest':'false'})
    value.update(phase='PUBLISHED',url=release['html_url'],ci_url=ci['url']);save(value)
    return verify(api)


def verify(api):
    value=load();check_pins(value);remote=inspect(api)
    require(remote['head']==value['commit'] and remote['tag'] and
            tag_commit(api,remote['tag']['object'])==value['commit'],'최종 main·태그 불일치')
    release=remote['release']
    require(release and not release['draft'] and release['prerelease'] and release['id']==value['release_id']
            and release['target_commitish']==value['commit'] and release['name']==TITLE
            and release['body']==value['body'],'최종 공개 사전 릴리스 불일치')
    ci=gate(status(api,value));assets=assets_match(release,value);check_tree(api,value)
    downloads=verify_public(assets)
    output={'phase':'VERIFIED','repository':REPO,'private':False,'tag':TAG,'commit':value['commit'],
        'prerelease':True,'url':release['html_url'],'source_files':len(value['source_files']),
        'remote_git_blob_sha_exact':True,'preserved_tags':list(PREVIOUS),
        'previous_release_fingerprints_preserved':True,'preserved_workflows':list(OLD_WORKFLOWS),
        'assets':assets,'public_downloads':downloads,'ci_url':ci['url'],'ci_run_id':ci['id']}
    value.update(phase='VERIFIED',url=release['html_url']);save(value)
    WORK.mkdir(parents=True,exist_ok=True);(WORK/'release-verified.json').write_bytes(json_bytes(output));return output


def dispatch(mode):
    require(mode in ('github-stage','github-status','github-publish','github-verify'),'명시적 GitHub 동작 필요')
    from tools.release_v22.github_api import GitHub
    api=GitHub()  # Credential helper only here; token is never returned or printed.
    if mode=='github-status':return status(api,load())
    return {'github-stage':stage,'github-publish':publish,'github-verify':verify}[mode](api)
