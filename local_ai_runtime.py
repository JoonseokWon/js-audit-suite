"""User-triggered portable Ollama setup; private folders, loopback, pinned bytes.

Constructing/status never downloads or starts a process. setup is the explicit
download operation. Existing loopback servers may be reused but never stopped by
this instance. No machine/user settings or global Ollama installation are edited.
"""
from __future__ import annotations
import hashlib,http.client,json,os,re,shutil,socket,stat,subprocess,sys,threading,time,unicodedata,uuid,zipfile
from pathlib import Path,PurePosixPath
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler,HTTPSHandler,ProxyHandler,Request,build_opener
import ssl

VERSION='0.40.7'
BASE_URL='http://127.0.0.1:11437'
MODEL='qwen3:4b-instruct-2507-q4_K_M'
MODEL_DIGEST='0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0'
MODEL_BLOB_BYTES=2497293803
ARCHIVES={
 'regular':{'name':'ollama-windows-amd64.zip','bytes':1582514985,'sha256':'e6527768c53e85ec4596495fb0f035ef07f437b4b591ebc3581684699a4668f4'},
 'rocm':{'name':'ollama-windows-amd64-rocm.zip','bytes':256506971,'sha256':'3910a28c107655c0b2c9d5d3f3ae95dc1f9e5f2e798b381d6b91d86f3ad99b41'}}
DOWNLOAD_HOSTS={'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com','github-releases.githubusercontent.com'}
MAX_EXPANDED=4*1024**3
MAX_API=512*1024

class LocalAIError(RuntimeError):pass
class LocalAICancelled(LocalAIError):pass

def default_root():
    return Path(sys.executable).resolve().parent/'로컬AI' if getattr(sys,'frozen',False) else Path(__file__).resolve().parent/'배포'/'로컬AI'

def _cancel(event):
    if event is not None and event.is_set():raise LocalAICancelled('로컬 AI 준비를 취소했습니다. 완료되지 않은 모델은 준비 완료로 표시하지 않습니다.')

def _sha(path,event=None):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk:=f.read(4*1024**2):_cancel(event);h.update(chunk)
    return h.hexdigest()

def _atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name('.'+path.name+'-'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()

def _reparse(path):
    if path.is_symlink():return True
    try:return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except AttributeError:return False

def _safe(root,name):
    p=PurePosixPath(name)
    if not name or '\\' in name or ':' in name or '\x00' in name or p.is_absolute() or '..' in p.parts or any(part in ('','.') for part in name.rstrip('/').split('/')):raise LocalAIError('설치 파일 경로가 안전하지 않습니다.')
    for part in p.parts:
        if part.endswith((' ','.')) or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',part):raise LocalAIError('설치 파일 이름이 안전하지 않습니다.')
    result=root.joinpath(*p.parts)
    if not result.resolve().is_relative_to(root.resolve()):raise LocalAIError('설치 파일이 선택 폴더 밖을 가리킵니다.')
    for parent in [result,*result.parents]:
        if parent.exists() or parent.is_symlink():
            if _reparse(parent):raise LocalAIError('설치 경로의 링크·재분석 지점은 지원하지 않습니다.')
        if parent==root:break
    return result

def _official(url):
    try:
        p=urlsplit(url);valid=p.scheme=='https' and p.hostname in DOWNLOAD_HOSTS and not p.username and not p.password and p.port in (None,443)
    except ValueError:valid=False
    if not valid:raise LocalAIError('공식 HTTPS 다운로드 주소만 허용합니다.')

class _Redirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        _official(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)

class LocalAIRuntime:
    base_url=BASE_URL
    model=MODEL
    def __init__(self,root=None):
        chosen=Path(root) if root is not None else default_root()
        absolute=chosen.absolute()
        for p in [absolute,*absolute.parents]:
            if (p.exists() or p.is_symlink()) and _reparse(p):raise LocalAIError('로컬 AI 폴더의 링크·재분석 지점은 지원하지 않습니다.')
        self.root=absolute.resolve()
        if self.root==Path(self.root.anchor):raise LocalAIError('드라이브 루트 대신 전용 로컬 AI 폴더를 선택하세요.')
        self.runtime=self.root/'runtime';self.exe=self.runtime/'ollama.exe';self.cache=self.root/'cache';self.models=self.root/'models';self.profile=self.root/'profile'
        self.manifest=self.root/'runtime-install.json';self._process=None;self._lock=threading.RLock();self._verified=None

    def _notify(self,progress,message):
        if progress:progress(message)

    def _json_api(self,path,payload=None,timeout=1):
        conn=http.client.HTTPConnection('127.0.0.1',11437,timeout=timeout)
        try:
            data=None if payload is None else json.dumps(payload).encode()
            conn.request('GET' if data is None else 'POST',path,body=data,headers={'Content-Type':'application/json','Connection':'close'})
            r=conn.getresponse()
            if r.status!=200:raise LocalAIError('로컬 AI 서버 응답을 확인할 수 없습니다.')
            raw=r.read(MAX_API+1)
            if len(raw)>MAX_API:raise LocalAIError('로컬 AI 응답 크기가 한도를 초과했습니다.')
            return json.loads(raw)
        finally:conn.close()

    def _runtime_ok(self,event=None):
        if not self.exe.is_file() or not self.manifest.is_file():return False
        try:
            if self.manifest.stat().st_size>2*1024**2:return False
            raw=self.manifest.read_bytes();m=json.loads(raw)
            if m.get('version')!=VERSION or m.get('schema')!='local-ai-install-1' or not 1<=len(m.get('files',[]))<=2000:return False
            fingerprint=[hashlib.sha256(raw).hexdigest()]
            seen=set()
            for r in m['files']:
                p=_safe(self.runtime,r['path'])
                if r['path'] in seen or not p.is_file() or p.stat().st_size!=r['bytes'] or not re.fullmatch('[0-9a-f]{64}',r['sha256']):return False
                seen.add(r['path']);s=p.stat();fingerprint.append((r['path'],s.st_size,s.st_mtime_ns,s.st_ctime_ns))
            if 'ollama.exe' not in seen:return False
            if self._verified==fingerprint:return True
            if any(_sha(_safe(self.runtime,r['path']),event)!=r['sha256'] for r in m['files']):return False
            self._verified=fingerprint;return True
        except (OSError,ValueError,KeyError,TypeError,AttributeError,LocalAIError):
            _cancel(event);return False

    def status(self):
        runtime=self.exe.is_file();verified=self._runtime_ok();server=False;model=False;reason=''
        try:
            server=self._json_api('/api/version').get('version')==VERSION
            if server:
                tags=self._json_api('/api/tags');items=tags.get('models',[])
                if isinstance(items,list):
                    for row in items:
                        if not isinstance(row,dict):continue
                        named=row.get('name',row.get('model'));digest=str(row.get('digest','')).removeprefix('sha256:')
                        size=row.get('size')
                        if named==MODEL and row.get('model',MODEL)==MODEL and digest==MODEL_DIGEST and type(size) is int and 0<size<=4*1024**3:model=True
        except (OSError,ValueError,TypeError,AttributeError,LocalAIError,http.client.HTTPException):pass
        if not runtime:reason='로컬 AI 런타임이 없습니다. 최초 준비를 실행하세요.'
        elif not verified:reason='런타임 설치 검증이 필요합니다. 최초 준비 또는 서버 준비를 실행하세요.'
        elif not server:reason='전용 로컬 AI 서버가 실행되지 않았거나 버전이 다릅니다.'
        elif not model:reason='지정 모델이 없거나 모델 digest가 다릅니다. 최초 준비를 실행하세요.'
        else:reason='지정 런타임·서버·모델 검증 완료'
        return {'ready':bool(verified and server and model),'runtime':runtime,'runtime_verified':verified,'model':model,'server':server,'reason':reason,'root':str(self.root),'base_url':BASE_URL,'model_name':MODEL,'model_digest':MODEL_DIGEST if model else None,'owned_server':bool(self._process and self._process.poll() is None)}

    def _download(self,info,event,progress):
        target=_safe(self.root,'cache/'+info['name']);target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if target.stat().st_size==info['bytes'] and _sha(target,event)==info['sha256']:return target
            raise LocalAIError('기존 런타임 캐시의 크기·해시가 다릅니다. 파일을 보존한 뒤 확인하세요.')
        url='https://github.com/ollama/ollama/releases/download/v'+VERSION+'/'+info['name'];_official(url)
        tmp=target.with_name('.'+target.name+'-'+uuid.uuid4().hex+'.part')
        opener=build_opener(ProxyHandler({}),HTTPSHandler(context=ssl.create_default_context()),_Redirect())
        try:
            self._notify(progress,'공식 런타임 다운로드: '+info['name']);h=hashlib.sha256();count=0;last=0
            with opener.open(Request(url,headers={'User-Agent':'JS-Audit-Suite-LocalAI/1.8'}),timeout=15) as response,tmp.open('xb') as out:
                _official(response.geturl())
                if response.status!=200:raise LocalAIError('공식 런타임 다운로드 응답 오류')
                length=response.headers.get('Content-Length')
                if length is not None and int(length)!=info['bytes']:raise LocalAIError('공식 런타임 다운로드 크기가 고정 명세와 다릅니다.')
                while True:
                    _cancel(event);chunk=response.read(1024**2)
                    if not chunk:break
                    count+=len(chunk)
                    if count>info['bytes']:raise LocalAIError('런타임 다운로드 한도 초과')
                    h.update(chunk);out.write(chunk)
                    if time.monotonic()-last>.25:self._notify(progress,f'런타임 다운로드 {count:,}/{info["bytes"]:,} 바이트');last=time.monotonic()
            _cancel(event)
            if count!=info['bytes'] or h.hexdigest()!=info['sha256']:raise LocalAIError('공식 런타임 다운로드 크기·SHA256 검증 실패')
            os.replace(tmp,target);return target
        except (OSError,ValueError,http.client.HTTPException) as e:
            _cancel(event);raise LocalAIError('런타임 다운로드를 완료하지 못했습니다. 네트워크·저장공간을 확인하세요.') from None
        finally:
            if tmp.exists():tmp.unlink()

    def _members(self,z):
        rows=z.infolist()
        if not rows or len(rows)>2000 or sum(r.file_size for r in rows)>MAX_EXPANDED:raise LocalAIError('런타임 ZIP 해제 한도 초과')
        seen=set();files=[]
        for r in rows:
            _safe(self.root/'runtime',r.filename.rstrip('/'));key=unicodedata.normalize('NFC',r.filename.rstrip('/')).casefold()
            kind=(r.external_attr>>16)&0o170000
            if key in seen or kind not in (0,stat.S_IFREG,stat.S_IFDIR) or r.flag_bits&1 or r.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):raise LocalAIError('런타임 ZIP 중복·링크·암호·압축 형식 오류')
            seen.add(key)
            if not r.is_dir():
                if r.file_size>2*1024**3 or r.file_size>max(1,r.compress_size)*250:raise LocalAIError('런타임 ZIP 파일 크기·압축률 한도 초과')
                files.append(r)
        return files

    def _archive_records(self,paths,event=None,stage=None):
        records={}
        for path in paths:
            with zipfile.ZipFile(path) as z:
                for r in self._members(z):
                    _cancel(event);h=hashlib.sha256();count=0;out=None
                    try:
                        if stage is not None:
                            p=_safe(stage,r.filename);p.parent.mkdir(parents=True,exist_ok=True);out=p.open('wb')
                        with z.open(r) as f:
                            while chunk:=f.read(4*1024**2):
                                _cancel(event);count+=len(chunk);h.update(chunk)
                                if out:out.write(chunk)
                        if count!=r.file_size:raise LocalAIError('런타임 ZIP 멤버 크기 불일치')
                    finally:
                        if out:out.close()
                    records[r.filename]={'path':r.filename,'bytes':count,'sha256':h.hexdigest()}
        if 'ollama.exe' not in records:raise LocalAIError('런타임 ZIP에 실행파일이 없습니다.')
        if sum(r['bytes'] for r in records.values())>MAX_EXPANDED:raise LocalAIError('합산 런타임 해제 한도 초과')
        return list(records.values())

    def _write_install(self,records,paths,event=None):
        data={'schema':'local-ai-install-1','version':VERSION,'files':records,'archives':[{'name':p.name,'sha256':_sha(p,event)} for p in paths]}
        _atomic(self.manifest,json.dumps(data,ensure_ascii=False,indent=2).encode());self._verified=None

    def _adopt(self,event=None):
        if not self.exe.is_file():return False
        paths=[]
        for key in ('regular','rocm'):
            info=ARCHIVES[key];p=self.cache/info['name']
            if key=='rocm' and not p.exists():continue
            if not p.is_file() or p.stat().st_size!=info['bytes'] or _sha(p,event)!=info['sha256']:return False
            paths.append(p)
        try:
            records=self._archive_records(paths,event)
            if any(not _safe(self.runtime,r['path']).is_file() or _safe(self.runtime,r['path']).stat().st_size!=r['bytes'] or _sha(_safe(self.runtime,r['path']),event)!=r['sha256'] for r in records):return False
            self._write_install(records,paths,event);return self._runtime_ok(event)
        except (OSError,ValueError,zipfile.BadZipFile,LocalAIError):_cancel(event);return False

    def _environment(self):
        env={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','PATH','TEMP','TMP','COMSPEC','PROGRAMFILES','PROGRAMFILES(X86)')}
        env.update({'USERPROFILE':str(self.profile),'HOME':str(self.profile),'APPDATA':str(self.profile/'AppData/Roaming'),'LOCALAPPDATA':str(self.profile/'AppData/Local'),'TEMP':str(self.root/'temp'),'TMP':str(self.root/'temp'),'OLLAMA_HOST':'127.0.0.1:11437','OLLAMA_MODELS':str(self.models),'OLLAMA_NO_CLOUD':'1','OLLAMA_NUM_PARALLEL':'1','OLLAMA_MAX_LOADED_MODELS':'1','OLLAMA_CONTEXT_LENGTH':'8192','OLLAMA_KEEP_ALIVE':'2m','NO_PROXY':'127.0.0.1,localhost'})
        return env

    def ensure_server(self,event=None,progress=None):
        with self._lock:
            _cancel(event)
            if not self._runtime_ok(event):
                self._notify(progress,'기존 로컬 런타임을 검증 중…')
                if not self._adopt(event):raise LocalAIError('검증된 로컬 런타임이 없습니다. 최초 준비를 실행하세요.')
            try:
                version=self._json_api('/api/version').get('version')
                if version==VERSION:return self.status()
                raise LocalAIError('전용 포트 11437에 다른 버전의 서버가 있습니다. 기존 프로세스를 임의 종료하지 않습니다.')
            except (OSError,http.client.HTTPException,ValueError):pass
            for name in ('profile','models','temp','profile/AppData/Roaming','profile/AppData/Local'):_safe(self.root,name).mkdir(parents=True,exist_ok=True)
            _atomic(_safe(self.root,'profile/.ollama/server.json'),b'{"disable_ollama_cloud":true}')
            if self._process is None or self._process.poll() is not None:
                self._notify(progress,'전용 로컬 AI 서버 준비 중…')
                try:self._process=subprocess.Popen([str(self.exe),'serve'],cwd=str(self.runtime),env=self._environment(),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),shell=False)
                except OSError:raise LocalAIError('로컬 AI 서버를 시작할 수 없습니다.') from None
            end=time.monotonic()+40
            try:
                while time.monotonic()<end:
                    _cancel(event)
                    if self._process.poll() is not None:raise LocalAIError('로컬 AI 서버가 종료됐습니다. 전용 포트·런타임을 확인하세요.')
                    try:
                        if self._json_api('/api/version').get('version')==VERSION:return self.status()
                    except (OSError,ValueError,LocalAIError,http.client.HTTPException):pass
                    if event is not None:event.wait(.1)
                    else:time.sleep(.1)
                raise LocalAIError('로컬 AI 서버 준비 시간이 초과했습니다.')
            except Exception:self.stop();raise

    def _pull_model(self,event=None,progress=None):
        conn=http.client.HTTPConnection('127.0.0.1',11437,timeout=15);finished=threading.Event();response=None
        def watch():
            while not finished.wait(.1):
                if event is not None and event.is_set():
                    try:
                        if conn.sock:conn.sock.shutdown(socket.SHUT_RDWR)
                    except OSError:pass
                    conn.close();return
        watcher=threading.Thread(target=watch,daemon=True);watcher.start()
        try:
            _cancel(event);conn.request('POST','/api/pull',json.dumps({'model':MODEL,'stream':True}),{'Content-Type':'application/json','Connection':'close'})
            response=conn.getresponse()
            if response.status!=200:raise LocalAIError('모델 다운로드 서버 응답 오류')
            success=False;total_bytes=0;records=0;last=0
            while True:
                _cancel(event);line=response.readline(65537)
                if not line:break
                total_bytes+=len(line);records+=1
                if len(line)>65536 or total_bytes>16*1024**2 or records>100000:raise LocalAIError('모델 다운로드 진행 응답 한도 초과')
                try:item=json.loads(line)
                except (ValueError,UnicodeError):raise LocalAIError('모델 다운로드 진행 응답 형식 오류') from None
                if not isinstance(item,dict) or 'error' in item:raise LocalAIError('모델 다운로드를 완료하지 못했습니다.')
                state=item.get('status')
                if not isinstance(state,str) or not state or len(state)>300:raise LocalAIError('모델 다운로드 진행 상태 누락')
                if success:raise LocalAIError('모델 다운로드 완료 뒤 예상하지 않은 응답')
                success=state=='success'
                if 'completed' in item or 'total' in item:
                    done,full=item.get('completed',0),item.get('total',0)
                    if type(done) is not int or type(full) is not int or not 0<=done<=full<=8*1024**3:raise LocalAIError('모델 다운로드 크기 응답 오류')
                if time.monotonic()-last>.25 or success:
                    clean=re.sub(r'[\x00-\x1f]',' ',state)[:100];suffix=f' {item.get("completed",0):,}/{item["total"]:,} 바이트' if item.get('total') else ''
                    self._notify(progress,'모델 준비: '+clean+suffix);last=time.monotonic()
            _cancel(event)
            if not success:raise LocalAIError('모델 다운로드의 유효한 완료 응답이 없습니다.')
            if not self.status()['model']:raise LocalAIError('다운로드 후 모델 이름·digest 검증에 실패했습니다.')
        except (OSError,ValueError,http.client.HTTPException):
            _cancel(event);raise LocalAIError('모델 다운로드 연결이 중단됐습니다. 최초 준비를 다시 실행하세요.') from None
        finally:
            finished.set()
            if response:response.close()
            conn.close();watcher.join(.3)

    def setup(self,event=None,progress=None,with_rocm=False):
        with self._lock:
            _cancel(event);self.root.mkdir(parents=True,exist_ok=True)
            valid=self._runtime_ok(event) or self._adopt(event)
            has_rocm=False
            if valid:
                try:has_rocm=any(r['name']==ARCHIVES['rocm']['name'] for r in json.loads(self.manifest.read_bytes())['archives'])
                except (OSError,ValueError,KeyError,TypeError):pass
            if not valid or (with_rocm and not has_rocm):
                try:
                    self._json_api('/api/version')
                except (OSError,ValueError,http.client.HTTPException):pass
                else:
                    if self._process is None:raise LocalAIError('기존 로컬 AI 서버 실행 중에는 런타임을 교체하지 않습니다. 직접 종료한 뒤 다시 준비하세요.')
                    self.stop()
                required=(14 if with_rocm else 10)*1024**3
                if shutil.disk_usage(self.root).free<required:raise LocalAIError('로컬 AI 최초 준비에 여유 디스크 10GiB(ROCm 14GiB)가 필요합니다.')
                infos=[ARCHIVES['regular']]+([ARCHIVES['rocm']] if with_rocm else [])
                paths=[self._download(info,event,progress) for info in infos]
                stage=_safe(self.root,'install-'+uuid.uuid4().hex);stage.mkdir()
                try:
                    self._notify(progress,'런타임 ZIP 경로·크기·해시 검증 및 해제 중…');records=self._archive_records(paths,event,stage);_cancel(event)
                    # Keep the old directory recoverable; never recursively remove user files.
                    if self.runtime.exists():
                        backup=_safe(self.root,'runtime-previous-'+uuid.uuid4().hex);self.runtime.rename(backup)
                    stage.rename(self.runtime);self._write_install(records,paths,event)
                except (OSError,ValueError,zipfile.BadZipFile):raise LocalAIError('런타임 설치를 완료하지 못했습니다. 보존된 폴더와 공간을 확인하세요.') from None
            state=self.ensure_server(event,progress)
            if not state['model']:
                if self._process is None or self._process.poll() is not None:raise LocalAIError('기존 서버에 지정 모델이 없습니다. 저장 폴더를 확인할 수 없는 기존 서버에는 다운로드하지 않습니다. 서버 소유자가 종료한 뒤 다시 준비하세요.')
                self._pull_model(event,progress)
            result=self.status()
            if not result['ready']:raise LocalAIError('로컬 AI 준비가 완료되지 않았습니다.')
            self._notify(progress,'로컬 AI 런타임·모델 준비 완료');return result

    def stop(self):
        with self._lock:
            process=self._process
            if process is None:return False
            try:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            finally:self._process=None
            return True
