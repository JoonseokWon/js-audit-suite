"""Verified bundled inputs -> persistent, isolated synthetic company engagements."""
from pathlib import Path,PurePosixPath
from contextlib import contextmanager
from collections import defaultdict
import os,json,re,stat,uuid,hashlib,io,zipfile
from common import AuditError,atomic,sha,dumps,now
from workspace import Workspace
from procedures import task_definitions

STORE_FILE='store.json'
COMPANIES={'JS':'JS','JS_ELEC':'JS전자','JS_AUTO':'JS자동차','JS_SEMI':'JS반도체','JS_BIO':'JS바이오'}
MODULES=('원장·리드','금융상품','매출','감가상각','확장검사','리스','대손충당금','재고평가','종업원급여','미기록부채·비용이연','원천증빙','재무제표·주석','GLA','FIA','현금분석')
CONTRACT='1.7'
PARENT_PROCEDURES={'C02','C04','C05','P01','P07'}

def _modules(code):return ('원장·리드',) if code=='JS' else MODULES
def _kind(code):return 'parent' if code=='JS' else 'subsidiary'

def _read(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError) as e:raise AuditError('업종 자료 또는 보관 목록을 읽을 수 없습니다. 원본을 보존하세요.') from e

def _reparse(path):
    try:return path.is_symlink() or bool(path.stat(follow_symlinks=False).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except AttributeError:return path.is_symlink()

def _safe(root,relative):
    if not isinstance(relative,str) or '\\' in relative or ':' in relative or not relative or relative.startswith('/'):
        raise AuditError('자료 경로 형식 오류')
    parts=PurePosixPath(relative).parts
    if any(p in ('.','..') or p.endswith((' ','.')) for p in relative.split('/')):raise AuditError('자료 경로 범위 오류')
    path=root.joinpath(*parts)
    if not path.resolve().is_relative_to(root.resolve()):raise AuditError('자료 경로가 보관 범위를 벗어납니다.')
    for p in (path,*path.parents):
        if p==root.parent:break
        if p.is_symlink() or (p.exists() and _reparse(p)):raise AuditError('연결된 폴더·파일 대신 독립된 보관 폴더를 사용하세요.')
    return path

def _catalog(resource_root,verify=True):
    root=Path(resource_root).resolve();m=_read(root/'manifest.json')
    if not isinstance(m,dict) or m.get('schema_version')!='sector-resources-1' or str(m.get('engine_contract'))!=CONTRACT:raise AuditError('지원하지 않는 업종자료 버전')
    companies=m.get('companies',[])
    if not isinstance(companies,list) or len(companies)!=5 or any(not isinstance(c,dict) for c in companies) or {c.get('code'):c.get('name') for c in companies}!=COMPANIES:raise AuditError('회사 목록 누락·중복·불일치')
    entries=m.get('files',[])
    if not isinstance(entries,list) or any(not isinstance(r,dict) or not isinstance(r.get('path'),str) for r in entries):raise AuditError('내장자료 파일 목록 형식 오류')
    index={r.get('path'):r for r in entries}
    if len(index)!=len(entries) or not 1<=len(index)<=150:raise AuditError('내장자료 파일 목록 오류')
    for name,r in index.items():
        path=_safe(root,name)
        if not isinstance(r.get('bytes'),int) or not 0<r['bytes']<=25*1024**2 or not re.fullmatch('[0-9a-f]{64}',str(r.get('sha256',''))):raise AuditError('내장자료 해시·크기 명세 오류')
        if verify and (not path.is_file() or path.stat().st_size!=r['bytes'] or sha(path)!=r['sha256']):raise AuditError('내장 업종자료가 누락되거나 변경되었습니다: '+name)
    for c in companies:
        context=c.get('context',{})
        if context.get('회사코드')!=c['code'] or context.get('회사명')!=c['name'] or context.get('더미업무') is not True:raise AuditError('회사 자료 범위 불일치')
        if c.get('kind')!=_kind(c['code']):raise AuditError('모회사·자회사 구분 오류')
        if tuple(r.get('module') for r in c.get('inputs',[]))!=_modules(c['code']):raise AuditError('회사별 입력 순서·종류 오류')
        if c.get('ledger_links_expected')!=(0 if c['code']=='JS' else 35):raise AuditError('회사별 연결 범위 오류')
        if c['code']=='JS' and (c.get('industry_topic_count')!=0 or set(c.get('procedure_ids',[]))!=PARENT_PROCEDURES or c.get('ledger_links_expected')!=0):raise AuditError('모회사 업종·조서 범위 오류')
        metadata=c.get('metadata',{})
        if set(metadata)!={'master','profile','plan'}:raise AuditError('회사별 업종 메타자료 누락')
        for r in c['inputs']+list(metadata.values()):
            if not isinstance(r,dict) or not all(k in r for k in ('path','bytes','sha256')) or index.get(r.get('path'))!={k:r[k] for k in ('path','bytes','sha256')}:raise AuditError('회사 자료와 전체 파일 명세 불일치')
            if not r['path'].startswith('companies/'+c['code']+'/'):raise AuditError('다른 회사의 내장자료 참조')
    if 'procedure_catalog.json' not in index:raise AuditError('조서 절차 목록 누락')
    return root,m

def list_companies(resource_root):return _catalog(resource_root,verify=False)[1]['companies']

def default_storage_root():
    base=os.environ.get('LOCALAPPDATA')
    if not base and os.name=='nt':
        import ctypes
        buffer=ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None,28,None,0,buffer)==0:base=buffer.value
    if not base:
        try:base=Path.home()/'AppData/Local'
        except RuntimeError as exc:raise AuditError('사용자별 연습 저장 위치를 확인할 수 없습니다. Windows 사용자 프로필을 확인하세요.') from exc
    return Path(base)/'JSAudit/sector-demos/v1.7'

def _storage(storage_root,resource_root):
    raw=Path(storage_root).absolute();root=raw.resolve();source=Path(resource_root).resolve()
    if root==root.anchor or root==Path(root.anchor) or root.is_relative_to(source) or source.is_relative_to(root):raise AuditError('내장자료·상위 폴더를 연습 보관 위치로 쓸 수 없습니다.')
    for p in (raw,*raw.parents):
        if p.is_symlink() or (p.exists() and _reparse(p)):raise AuditError('연결된 폴더를 연습 보관 위치로 쓸 수 없습니다.')
    if root.exists() and (not root.is_dir() or (not (root/STORE_FILE).is_file() and any(p.name!='.lock' for p in root.iterdir()))):raise AuditError('전용 빈 폴더 또는 기존 업종 연습 보관 폴더를 사용하세요.')
    root.mkdir(parents=True,exist_ok=True)
    return root

@contextmanager
def _lock(root):
    path=_safe(root,'.lock');handle=path.open('a+b');locked=False
    try:
        if path.stat().st_size==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            locked=True
        except OSError as e:raise AuditError('다른 창에서 업종 연습을 준비하고 있습니다. 잠시 후 다시 선택하세요.') from e
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        handle.close()

def _store(root):
    path=_safe(root,STORE_FILE)
    if not path.exists():
        if any(p.name!='.lock' for p in root.iterdir()):raise AuditError('업종 연습 보관 목록이 없습니다. 기존 자료를 보존하세요.')
        store={'schema_version':'sector-demo-store-1','engine_contract':CONTRACT,'store_id':uuid.uuid4().hex,'companies':{}}
        atomic(path,dumps(store).encode());return store
    store=_read(path)
    if store.get('schema_version')!='sector-demo-store-1' or store.get('engine_contract')!=CONTRACT or not re.fullmatch('[0-9a-f]{32}',str(store.get('store_id',''))) or not isinstance(store.get('companies'),dict) or not set(store['companies'])<=set(COMPANIES):raise AuditError('업종 연습 보관 목록 버전·회사 오류')
    return store

def _existing(root,store,code):
    ref=store['companies'][code]
    if not isinstance(ref,dict) or not isinstance(ref.get('folder'),str):raise AuditError('업종 연습 회사 참조 형식 오류')
    relative=ref['folder'];parts=PurePosixPath(relative).parts
    if len(parts)!=4 or parts[:2]!=('companies',code) or parts[-1]!='업무' or not re.fullmatch('[0-9a-f]{32}',parts[2]):raise AuditError('업종 연습 경로 오류')
    folder=_safe(root,relative)
    if not (folder/'업무.sqlite3').is_file() or not (folder/'이력헤드.json').is_file():raise AuditError('기존 회사 연습이 없거나 손상되었습니다. 원본을 보존하고 새 연습을 선택하세요.')
    marker=_read(folder.parent/'session.json')
    if marker.get('state')!='ready' or marker.get('company_code')!=code or marker.get('store_id')!=store['store_id']:raise AuditError('회사 연습 소유·완료 상태 불일치')
    ws=Workspace(folder)
    if ws.engagement['회사코드']!=code or ws.engagement['회사명']!=COMPANIES[code] or not ws.engagement.get('더미업무') or ws.engagement['id']!=ref.get('workspace_id'):raise AuditError('저장된 업무가 선택한 합성회사와 다릅니다.')
    if ws.verify_sources():raise AuditError('기존 업무의 원본 사본이 변경되었습니다. 자료를 보존하고 확인하세요.')
    data_folder(ws)
    return _result(ws,code,True)

def _result(ws,code,reused):
    return {'folder':str(ws.root),'company_code':code,'workspace_id':ws.engagement['id'],'reused':reused,
            'company_kind':_kind(code),'modules':list(ws.latest()),'ledger_links':len(ws.cross_checks())}

def _raw_payload(pack_path,context,event=None):
    """Validate the complete archive before returning only its declared Excel bytes."""
    from raw_sources import load_pack
    pack=load_pack(pack_path,{'통화':'KRW','연결구분':'별도',**context},event)
    binary=Path(pack_path).read_bytes()
    if hashlib.sha256(binary).hexdigest()!=pack['source']['sha256']:raise AuditError('검증 중 원천 패키지 변경')
    entries=[r for r in pack['manifest']['files'] if r['path'].startswith('sources/') and r['path'].endswith('.xlsx')]
    if len(entries)!=16:raise AuditError('업종 원천 엑셀 16권 범위 불일치')
    out={}
    with zipfile.ZipFile(io.BytesIO(binary)) as z:
        for entry in entries:
            name=entry['path'][len('sources/'):];data=z.read(entry['path'])
            if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise AuditError('원천 엑셀 해시 불일치')
            out[name]=data
    return out

def _extract_raw(ws,local,event=None):
    path=next((p for module,p in local if module=='원천증빙'),None)
    if path is None:return []
    payload=_raw_payload(path,ws.context,event);root=ws.root.parent/'원천엑셀';root.mkdir(exist_ok=False)
    for name,data in payload.items():
        if event is not None and event.is_set():raise AuditError('원천 열람사본 준비 취소. 이전 연습은 보존됩니다.')
        atomic(_safe(root,name),data)
    return [{'path':'원천엑셀/'+name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in sorted(payload.items())]

def data_folder(ws):
    """Return this demo's session folder after checking originals and derived reading copies.

    Reading copies are never registered again as newly received evidence. Missing or
    edited copies are blocked instead of silently reconstructed over user files.
    """
    if not isinstance(ws,Workspace):raise AuditError('현재 회사 연습을 먼저 여세요.')
    ws.refresh();code=ws.engagement['회사코드'];session=ws.root.parent
    marker=_read(session/'session.json')
    if code not in COMPANIES or marker.get('state')!='ready' or marker.get('company_code')!=code or marker.get('company_kind')!=_kind(code) or marker.get('workspace_id')!=ws.engagement['id'] or not ws.engagement.get('더미업무'):
        raise AuditError('v1.7 회사별 연습의 원천자료 폴더가 아닙니다. 등록 원본 위치를 확인하세요.')
    if ws.root.name!='업무' or session.parent.name!=code or not re.fullmatch('[0-9a-f]{32}',session.name):raise AuditError('회사 연습 경로 불일치')
    if ws.verify_sources():raise AuditError('업무 원본 사본이 누락·변경되었습니다.')
    inputs=marker.get('inputs',[])
    if not isinstance(inputs,list) or tuple(r.get('module') for r in inputs)!=_modules(code):raise AuditError('회사별 열람 입력 목록 오류')
    by_module={}
    for entry in inputs:
        if not isinstance(entry,dict) or not all(k in entry for k in ('path','bytes','sha256','source_id')):raise AuditError('열람 입력 명세 오류')
        path=_safe(session,entry['path']);source=ws.sources.get(entry['source_id'],{})
        if not entry['path'].startswith('inputs/') or source.get('role')!=entry['module'] or source.get('sha256')!=entry['sha256'] or source.get('bytes')!=entry['bytes'] or Path(source.get('original','')).resolve()!=path.resolve():raise AuditError('열람 입력과 등록 원본 연결 오류')
        if not path.is_file() or path.stat().st_size!=entry['bytes'] or sha(path)!=entry['sha256']:raise AuditError('회사 입력 열람사본이 누락·변경되었습니다: '+path.name)
        by_module[entry['module']]=path
    actual_inputs={p.relative_to(session).as_posix() for p in (session/'inputs').rglob('*') if p.is_file()}
    if actual_inputs!={e['path'] for e in inputs}:raise AuditError('회사 입력 열람 폴더의 미등록·누락 파일')
    metadata=marker.get('metadata',[])
    if not isinstance(metadata,list) or {r.get('key') for r in metadata}!={'master','profile','plan'} or len(metadata)!=3:raise AuditError('회사 설정 열람 목록 오류')
    for entry in metadata:
        if not all(k in entry for k in ('path','bytes','sha256','source_id')):raise AuditError('회사 설정 열람 명세 오류')
        path=_safe(session,entry['path']);source=ws.sources.get(entry['source_id'],{})
        if entry['path']!='metadata/'+entry['key']+'.json' or source.get('sha256')!=entry['sha256'] or source.get('bytes')!=entry['bytes'] or Path(source.get('original','')).resolve()!=path.resolve():raise AuditError('회사 설정과 등록 원본 연결 오류')
        if not path.is_file() or path.stat().st_size!=entry['bytes'] or sha(path)!=entry['sha256']:raise AuditError('회사 설정 열람사본 누락·변경')
    rawroot=_safe(session,'원천엑셀')
    if code=='JS':
        if rawroot.exists() or marker.get('raw_excel_files'):raise AuditError('모회사에 자회사 원천자료가 섞였습니다.')
    else:
        expected=_raw_payload(by_module['원천증빙'],ws.context)
        names=set()
        for name,data in expected.items():
            path=_safe(rawroot,name);names.add(name)
            if not path.is_file() or path.stat().st_size!=len(data) or sha(path)!=hashlib.sha256(data).hexdigest():raise AuditError('원천 엑셀 열람사본이 누락·변경되었습니다: '+name)
        actual={p.relative_to(rawroot).as_posix() for p in rawroot.rglob('*') if p.is_file()}
        if actual!=names:raise AuditError('원천 엑셀 열람 폴더의 미등록·누락 파일')
        listing=[{'path':'원천엑셀/'+name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in sorted(expected.items())]
        if marker.get('raw_excel_files')!=listing:raise AuditError('원천 엑셀 열람 목록 변경')
    return session

def _seed(ws,c,catalog,ids,plan):
    by_pid=defaultdict(list)
    for t in plan.get('audit_topics',[]):
        for pid in [t['workpaper_id']]+t.get('additional_workpaper_ids',[]):by_pid[pid].append(t)
    required=ws.required_procedures()|{'C02','P01'}|set(by_pid)
    for task in task_definitions(ws,catalog):
        if task['id'] not in required:continue
        p={**task,'title':c['name']+' '+task['title'],'preparer':c['context']['작성자']}
        p['evidence_ids']=list(dict.fromkeys(p.get('evidence_ids',[])+ids))
        if c['kind']=='parent':p['evidence_ids']=list(dict.fromkeys(p['evidence_ids']+[ws.latest()['원장·리드']['source_id']]))
        p['scope']=p.get('scope','')+'\n업종: '+c['sector']+' / 회사별 별도 합성업무. 검사용 가상 선택 시나리오이며 실제 시장가격·업종 원가구조가 아님.'
        if c['kind']=='parent':p['scope']+='\n모회사 현금·투자주식·자본의 산술 통제만 실행. 지분율·취득근거·평가·은행확인·연결계산은 미검사. 매출·재고·제조·유형자산 자료 미제공을 0으로 대체하지 않음.'
        if p['id']=='A10':p['scope']+='\n판매 EA와 벌크 KG는 별도 SKU. 업종설정의 원문 선언 관계를 확인하며 자동환산 검증 아님.'
        for t in by_pid.get(p['id'],[]):
            support=t.get('app_support',{})
            docs=' / '.join(r['document'] if isinstance(r,dict) else str(r) for r in t.get('required_inputs',[]))
            p['scope']+='\n계획·미수행: '+t['title']+'\n적용조건: '+t['activity_condition']+'\n자동수치 범위: '+support.get('automatic_scope','없음')+'\n추가 요청: '+docs
            p['risk']+='\n업종별 조건부 수동 검토계획. 판단·실제 수행·결론·검토는 별도 기록.'
        ws.save_procedure(p)
    if not set(by_pid)<=set(ws.procedures):raise AuditError('업종별 검토계획 조서 연결 누락')

def open_company(company_code,storage_root,resource_root,*,fresh=False,event=None,progress=None):
    source,manifest=_catalog(resource_root);pin=sha(source/'manifest.json')
    c=next((c for c in manifest['companies'] if c['code']==company_code),None)
    if c is None:raise AuditError('지원하지 않는 업종 회사')
    root=_storage(storage_root,source)
    def step(message):
        if event is not None and event.is_set():raise AuditError('업종 연습 준비를 취소했습니다. 기존 연습은 보존됩니다.')
        if progress:progress(message)
        if event is not None and event.is_set():raise AuditError('업종 연습 준비를 취소했습니다. 기존 연습은 보존됩니다.')
    with _lock(root):
        store=_store(root)
        if not fresh and company_code in store['companies']:
            step(c['name']+' 저장된 연습 확인 중');return _existing(root,store,company_code)
        step(c['name']+' 새 업종 연습 준비 중')
        relative='companies/'+company_code+'/'+uuid.uuid4().hex
        session=_safe(root,relative);session.mkdir(parents=True,exist_ok=False)
        marker={'store_id':store['store_id'],'company_code':company_code,'company_kind':c['kind'],'state':'preparing','resource_manifest_sha256':pin,'created_at':now()}
        atomic(session/'session.json',dumps(marker).encode())
        try:
            local=[]
            for entry in c['inputs']:
                path=session/'inputs'/Path(entry['path']).name;data=_safe(source,entry['path']).read_bytes()
                if len(data)!=entry['bytes'] or __import__('hashlib').sha256(data).hexdigest()!=entry['sha256']:raise AuditError('준비 중 내장 입력이 변경되었습니다.')
                atomic(path,data);local.append((entry['module'],path))
            metadata={}
            for key,entry in c['metadata'].items():
                path=session/'metadata'/(key+'.json');atomic(path,_safe(source,entry['path']).read_bytes());metadata[key]=path
                if sha(path)!=entry['sha256']:raise AuditError('준비 중 업종 메타자료가 변경되었습니다.')
            ws=Workspace(session/'업무',create=c['context'])
            for i,(module,path) in enumerate(local,1):
                step(c['name']+' '+str(i)+'/'+str(len(local))+' '+module+' 검사 중')
                if ws.execute(module,path,event)['result']['blocking']:raise AuditError(c['name']+' '+module+' 입력 검사 차단. 부분 준비는 보존됩니다.')
            if len(ws.latest())!=len(local) or len(ws.cross_checks())!=c['ledger_links_expected'] or any(r['상태']!='일치' for r in ws.cross_checks()):raise AuditError('회사별 원장·모듈 대사 미완료')
            marker['inputs']=[{'module':module,'path':'inputs/'+path.name,'bytes':path.stat().st_size,'sha256':sha(path),'source_id':ws.latest()[module]['source_id']} for module,path in local]
            step(c['name']+' 원천 엑셀 열람사본 준비 중')
            marker['raw_excel_files']=_extract_raw(ws,local,event)
            atomic(session/'자료안내.txt',('이 폴더는 '+c['name']+' 별도 합성 연습입니다.\ninputs/: 최초 내장모본 실행 입력 '+str(len(local))+'개.\n원천엑셀/: 최초 자회사 auditpack에서 검증 후 푼 16권 열람사본. 모회사에는 없습니다.\n업무/원본/: 이후 별도로 추가 등록한 파일도 포함하는 불변 입력 사본. 최신 실행과 연결된 자료는 앱의 결과·증거 목록에서 확인하세요.\n최초 내장 입력과 원천 열람사본은 이후 외부 입력으로 자동 교체되지 않습니다.\n실제 외부 수령 증거·독립 증거가 아니며 열람사본은 다시 증거로 등록하지 않습니다.\nJS 모회사는 업종 없음. 현금·투자주식·자본만 있는 가상 선택 시나리오이며 투자평가·연결계산은 미검사입니다.\n').encode('utf-8'))
            labels=[('master','회사별 자료 마스터','합성 회사설정'),('profile','모회사 가상 선택 시나리오' if c['kind']=='parent' else '업종·단위 관계 설정','합성 회사설정'),('plan','회사별 감사 검토계획','미수행 검토계획')]
            ids=[ws.add_source(metadata[k],c['name']+' '+label,role) for k,label,role in labels]
            marker['metadata']=[{'key':k,'path':'metadata/'+k+'.json','bytes':metadata[k].stat().st_size,'sha256':sha(metadata[k]),'source_id':sid} for (k,_,_),sid in zip(labels,ids)]
            _seed(ws,c,_read(source/'procedure_catalog.json'),ids,_read(metadata['plan']))
            step(c['name']+' 원장·조서 연결 확인 중')
            if ws.verify_sources() or any(p['performed'] or p['conclusion'] or p['reviewer'] for p in ws.procedures.values()):raise AuditError('업종 원본·미검토 조서 상태 오류')
            if sha(source/'manifest.json')!=pin:raise AuditError('준비 중 내장 자료 명세가 변경되었습니다.')
            _catalog(source)
            step(c['name']+' 회사별 연습 저장 중')
            marker.update(state='ready',workspace_id=ws.engagement['id']);atomic(session/'session.json',dumps(marker).encode())
            data_folder(ws)
            step(c['name']+' 검증된 회사별 연습 선택 저장 중')
            store['companies'][company_code]={'folder':relative+'/업무','workspace_id':ws.engagement['id'],'created_at':now(),'resource_manifest_sha256':pin}
            atomic(root/STORE_FILE,dumps(store).encode())
            return _result(ws,company_code,False)
        except Exception as exc:
            marker.update(state='failed',error=str(exc));atomic(session/'session.json',dumps(marker).encode())
            raise
