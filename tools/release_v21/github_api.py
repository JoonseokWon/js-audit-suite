"""Authenticated GitHub transport; credentials stay in memory and are never logged."""
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from .config import *
from .policy import require,sha,json_bytes

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise RuntimeError('GitHub 인증 헤더 리디렉션을 차단했습니다.')

class GitHub:
    def __init__(self):
        env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never')
        result=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',
                              text=True,capture_output=True,env=env,timeout=60)
        fields=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
        require(result.returncode==0 and fields.get('password'),'기존 GitHub 인증을 읽지 못했습니다.')
        self._token=fields['password'];self._opener=urllib.request.build_opener(NoRedirect())

    def call(self,method,path,data=None,raw=None,optional=False):
        url=path if path.startswith('https://') else 'https://api.github.com/repos/'+REPO+path
        target=urllib.parse.urlsplit(url)
        require(target.scheme=='https' and target.netloc in ('api.github.com','uploads.github.com')
                and not target.username and not target.password,'GitHub 공식 API 주소만 허용합니다.')
        body=raw if raw is not None else json_bytes(data) if data is not None else None
        request=urllib.request.Request(url,data=body,method=method,headers={
            'Authorization':'Bearer '+self._token,'Accept':'application/vnd.github+json',
            'X-GitHub-Api-Version':'2022-11-28','User-Agent':'js-audit-suite-v21-release',
            'Content-Type':'application/octet-stream' if raw is not None else 'application/json'})
        try:
            with self._opener.open(request,timeout=180) as response:
                value=response.read();return json.loads(value) if value else None
        except urllib.error.HTTPError as exc:
            if optional and exc.code==404:return None
            raise RuntimeError('GitHub API HTTP '+str(exc.code)+' '+target.path) from None
        except urllib.error.URLError:
            raise RuntimeError('GitHub API 네트워크 오류. 인증·응답 본문은 출력하지 않습니다.') from None

    def inspect(self):
        require(self.call('GET','https://api.github.com/user').get('login')==OWNER,'GitHub 소유자 불일치')
        # This unrelated repository's visibility is the owner's choice. Observe
        # metadata only; it cannot authorize files or gate this audit release.
        try:
            old=self.call('GET','https://api.github.com/repos/'+OWNER+'/for-ax-node-project',optional=True)
        except RuntimeError:
            old=None
        external=({'name':old.get('full_name'),'id':old.get('id'),'private':old.get('private'),
                   'visibility':old.get('visibility')} if isinstance(old,dict) else None)
        repo=self.call('GET','')
        require(repo.get('full_name')==REPO and repo.get('id')==REPO_ID
                and repo.get('private') is False and repo.get('visibility')=='public'
                and repo.get('default_branch')==BRANCH and repo.get('permissions',{}).get('push')
                and not repo.get('archived'),'감사 전용 공개 저장소 확인 실패')
        branches=self.call('GET','/branches?per_page=100')
        require([b['name'] for b in branches]==[BRANCH],'예상 밖 공개 브랜치')
        tags=self.call('GET','/tags?per_page=100');releases=self.call('GET','/releases?per_page=100')
        names={t['name'] for t in tags};by_tag={r['tag_name']:r for r in releases}
        require(len(tags)==len(names) and names in (set(PREVIOUS),set(PREVIOUS)|{TAG}),'기존 태그 집합 변경')
        require(len(releases)==len(by_tag) and set(by_tag) in (set(PREVIOUS),set(PREVIOUS)|{TAG}),'기존 릴리스 집합 변경')
        preserved={}
        for tag,commit in PREVIOUS.items():
            require(tag_commit(self,self.call('GET','/git/ref/tags/'+tag)['object'])==commit,'기존 태그 커밋 변경: '+tag)
            item=by_tag[tag]
            require(not item['draft'] and item['target_commitish']==commit,'기존 릴리스 대상 변경: '+tag)
            preserved[tag]={'commit':commit,'id':item['id'],'sha256':fingerprint(item)}
        head=self.call('GET','/git/ref/heads/'+BRANCH)['object']['sha']
        tag=self.call('GET','/git/ref/tags/'+TAG,optional=True)
        output={'repository':REPO,'private':False,'previous_repository_private':external.get('private') if external else None,
                'external_repository':external,
                'repo_id':repo['id'],'head':head,'previous':preserved,'tag':tag,'release':by_tag.get(TAG)}
        WORK.mkdir(parents=True,exist_ok=True);(WORK/'preflight.json').write_bytes(json_bytes(output))
        return output

def fingerprint(item):
    fields=('id','tag_name','target_commitish','name','body','draft','prerelease','published_at','created_at','updated_at')
    value={k:item.get(k) for k in fields}
    value['assets']=sorted([{k:a.get(k) for k in ('id','name','size','digest','state','created_at','updated_at')}
                            for a in item.get('assets',[])],key=lambda a:a['name'])
    return sha(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())

def tag_commit(api,obj):
    for _ in range(4):
        if obj['type']=='commit':return obj['sha']
        require(obj['type']=='tag','Git 태그 형식 오류')
        obj=api.call('GET','/git/tags/'+obj['sha'])['object']
    raise RuntimeError('Git 태그 참조 깊이 초과')
