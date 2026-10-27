"""Unauthenticated public downloads, streamed hashes and restricted redirects."""
import hashlib,urllib.parse,urllib.request
from .config import REPO,TAG
from .policy import require


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        target=urllib.parse.urlsplit(newurl)
        require(target.scheme=='https' and target.netloc in ('github.com','release-assets.githubusercontent.com',
                'objects.githubusercontent.com') and not target.username and not target.password,
                '공개 첨부 다운로드 리디렉션 대상 오류')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def verify_public(assets):
    opener=urllib.request.build_opener(PublicRedirect());records=[]
    for name,item in sorted(assets.items()):
        expected='https://github.com/'+REPO+'/releases/download/'+TAG+'/'+urllib.parse.quote(name)
        require(item['url']==expected,'공개 첨부 URL 불일치')
        request=urllib.request.Request(expected,headers={'User-Agent':'js-audit-suite-v25-public-verification'})
        total=0;digest=hashlib.sha256()
        with opener.open(request,timeout=180) as response:
            while True:
                raw=response.read(1024*1024)
                if not raw:break
                total+=len(raw);require(total<=item['bytes'],'공개 첨부 크기 초과');digest.update(raw)
        require(total==item['bytes'] and digest.hexdigest()==item['sha256'],'공개 다운로드 SHA256 불일치: '+name)
        records.append({'name':name,'bytes':total,'sha256':digest.hexdigest(),'public_download_verified':True})
    return records
