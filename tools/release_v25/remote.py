"""Exact v2.5 repository/preflight checks; never call the legacy inspector."""
from .config import REPO, REPO_ID, QA, TAG
from .policy import read, require, sha, json_bytes
from tools.release_v22.github_api import fingerprint

BASE='80be94519588c0f9a5e48d550c34319ce6591fc4'
BRANCH='main'
OWNER=REPO.split('/')[0]
PREVIOUS={'v2.3.0':BASE,'v2.2.0':'da03273609f62ee1f95ea88d29b418b1f57819e1',
    'v2.1.0':'f6d32f5972a28f27efafef5f6ff90c740d5269bd','v2.0.0':'0a9cb33fcf0f551b5ce8937fb871fa2326626fbd',
    'v1.9.0':'945bdb4970271f0000998c8ccaadfcdeaad639f7','v1.8.1':'d9d3c18459eddce6a01d51b9bafbce441782cc16',
    'v1.8.0':'c47250b5c092010342462a6a63d23692fd062637','v1.7.1':'fbd5be7f074c1be978a3ba604acd564703e1c3c2',
    'v1.7.0':'2562258ac0e0c02db8f3b9f0d98036740ab67aab'}
OLD_WORKFLOWS=tuple('.github/workflows/audit-suite-'+v+'.yml' for v in
                    ('v17','v171','v18','v181','v19','v20','v21','v22','v23'))


def preflight():
    value=read(QA/'github-preflight.json')
    require(value['repo']==REPO and value['id']==REPO_ID and value['visibility']=='public'
            and value['head']==BASE and value['tags']==PREVIOUS and set(value['releases'])==set(PREVIOUS),
            'v2.5 이전 공개 이력 기준 불일치')
    require(all(not r['draft'] and r['prerelease'] for r in value['releases'].values()),'기존 공개 사전 릴리스 기준 오류')
    return value


def preflight_hash():return sha(json_bytes(preflight()))


def tag_commit(api,obj):
    for _ in range(4):
        if obj['type']=='commit':return obj['sha']
        require(obj['type']=='tag','태그 참조 형식 오류')
        obj=api.call('GET','/git/tags/'+obj['sha'])['object']
    raise RuntimeError('태그 참조 깊이 초과')


def inspect(api):
    expected=preflight()
    require(api.call('GET','https://api.github.com/user').get('login')==OWNER,'GitHub 소유자 불일치')
    repo=api.call('GET','')
    require(repo.get('id')==REPO_ID and repo.get('full_name')==REPO and repo.get('private') is False
            and repo.get('visibility')=='public' and repo.get('default_branch')==BRANCH
            and repo.get('permissions',{}).get('push') and not repo.get('archived'),'감사 전용 공개 저장소 확인 실패')
    require([r['name'] for r in api.call('GET','/branches?per_page=100')]==[BRANCH],'예상 밖 브랜치')
    tags=api.call('GET','/tags?per_page=100');releases=api.call('GET','/releases?per_page=100')
    by_tag={r['tag_name']:r for r in releases};names={r['name'] for r in tags}
    require(len(names)==len(tags) and names in (set(PREVIOUS),set(PREVIOUS)|{TAG}),'기존 태그 집합 변경')
    require(len(by_tag)==len(releases) and set(by_tag) in (set(PREVIOUS),set(PREVIOUS)|{TAG}),'기존 릴리스 집합 변경')
    for name,commit in PREVIOUS.items():
        obj=api.call('GET','/git/ref/tags/'+name)['object'];release=by_tag[name]
        require(tag_commit(api,obj)==commit,'기존 태그 커밋 변경: '+name)
        require(release['id']==expected['releases'][name]['id'] and
                fingerprint(release)==expected['releases'][name]['fingerprint'],'기존 릴리스·첨부 이력 변경: '+name)
    return {'repo_id':REPO_ID,'head':api.call('GET','/git/ref/heads/'+BRANCH)['object']['sha'],
            'tag':api.call('GET','/git/ref/tags/'+TAG,optional=True),'release':by_tag.get(TAG),
            'preflight_hash':preflight_hash()}
