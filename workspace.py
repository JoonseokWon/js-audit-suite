"""Local event-sourced engagement. Immutable source copies, pinned runs and review revisions."""
import sqlite3,shutil,uuid
from common import *
from human_input import text
import adapters
from export_support.text import validate_structure

def uid():return uuid.uuid4().hex
SCHEMA="""CREATE TABLE meta(version TEXT NOT NULL);
INSERT INTO meta VALUES ('audit-suite-1');
CREATE TABLE events(seq INTEGER PRIMARY KEY,payload TEXT NOT NULL,prev TEXT NOT NULL,hash TEXT NOT NULL);
CREATE TRIGGER no_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable');END;
CREATE TRIGGER no_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable');END;"""
def schema_digest(db):return digest(db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall())
def expected_schema():
    db=sqlite3.connect(':memory:')
    try:db.executescript(SCHEMA);return schema_digest(db)
    finally:db.close()
EXPECTED_SCHEMA=expected_schema()
HUMAN_EVENTS={'engagement','procedure','note','evidence_request','ai_apply','ai_content_approval',
    'workflow_profile','workflow_risk','workflow_procedure','workflow_finalize','workflow_reopen',
    'workflow_f01_classification','workflow_risk_retire','workflow_procedure_retire'}
HUMAN_EVENTS.update({'misstatement_record','misstatement_group','misstatement_verification','misstatement_reconfirm',
    'audit_link_assessment','audit_link_response','audit_link_performance','audit_link_workpaper','audit_link_retire'})

class Workspace:
    def __init__(self,folder,create=None):
        self.root=Path(folder).resolve();self.dbpath=self.root/'업무.sqlite3';self.anchor=self.root/'이력헤드.json'
        if not self.dbpath.exists():
            if not create:raise AuditError('업무.sqlite3가 있는 업무 폴더를 선택하세요.')
            if self.root.exists() and any(self.root.iterdir()):raise AuditError('새 업무는 비어 있는 폴더에 만드세요.')
            c={k:text(create[k],k) for k in ('회사코드','회사명','시작일','기준일','회계체계','감사기준','작성자')}
            validate_structure(c,'새 업무')
            if day(c['시작일'])>day(c['기준일']):raise AuditError('업무기간 오류')
            c['더미업무']=bool(create.get('더미업무',False))
            self.root.mkdir(parents=True,exist_ok=True)
            db=sqlite3.connect(self.dbpath)
            try:db.executescript(SCHEMA);db.commit()
            finally:db.close()
            atomic(self.anchor,dumps({'seq':0,'hash':''}).encode())
            self._append('engagement',{'id':uid(),**c})
        self.refresh()
    def _read(self,db):
        if schema_digest(db)!=EXPECTED_SCHEMA or db.execute('SELECT version FROM meta').fetchall()!=[('audit-suite-1',)]:raise AuditError('업무 DB 스키마/버전 검증 실패. 원본을 보존하세요.')
        rows=db.execute('SELECT seq,payload,prev,hash FROM events ORDER BY seq').fetchall();last='';decoded=[]
        for i,(seq,payload,prev,h) in enumerate(rows,1):
            if seq!=i or prev!=last or digest({'seq':seq,'payload':payload,'prev':prev})!=h:raise AuditError('업무 이력 무결성 검증 실패')
            decoded.append(json.loads(payload));last=h
        try:a=json.loads(self.anchor.read_text(encoding='utf-8'))
        except (OSError,ValueError) as e:raise AuditError('이력 헤드 파일 없음/오류') from e
        if a!={'seq':len(rows),'hash':last}:raise AuditError('이력 끝부분/헤드 불일치. DB와 헤드를 함께 보존·복구하세요.')
        return decoded,last
    def _connect(self):
        db=sqlite3.connect(self.dbpath,timeout=5);db.execute('PRAGMA trusted_schema=OFF');return db
    def _append(self,kind,data,expected_head=None):
        # New human records must be exportable. Immutable source/run/model
        # evidence is retained verbatim; legacy text is escaped only for display.
        if kind in HUMAN_EVENTS:validate_structure(data,kind)
        db=self._connect()
        try:
            db.execute('BEGIN IMMEDIATE');events,last=self._read(db);seq=len(events)+1
            locked=False
            for event in events:
                if event['kind']=='workflow_finalize':locked=True
                elif event['kind']=='workflow_reopen':locked=False
            if locked and kind!='workflow_reopen':raise AuditError('보관 잠금된 업무입니다. 명시적 재개 사유를 기록하세요.')
            if kind=='workflow_reopen' and not locked:raise AuditError('보관 잠금되지 않은 업무입니다.')
            if expected_head is not None and last!=expected_head:raise AuditError('완료 점검 중 이력이 변경되었습니다. 다시 확인하세요.')
            payload=dumps({'kind':kind,'at':now(),'data':data});h=digest({'seq':seq,'payload':payload,'prev':last})
            db.execute('INSERT INTO events VALUES (?,?,?,?)',(seq,payload,last,h));db.commit()
            atomic(self.anchor,dumps({'seq':seq,'hash':h}).encode())
        finally:db.close()
    def refresh(self):
        db=self._connect()
        try:self.events,self.head=self._read(db)
        finally:db.close()
        self.sources={};self.runs={};self.procedures={};self.notes={};self.requests={};self.engagement=None
        self.ai_drafts={};self.ai_approvals={};self.ai_applications=[]
        for e in self.events:
            d=e['data'];kind=e['kind']
            if kind=='engagement':self.engagement=d
            elif kind=='source':self.sources[d['id']]=d
            elif kind=='run':self.runs[d['id']]=d
            elif kind=='procedure':self.procedures[d['id']]=d
            elif kind=='note':self.notes[d['id']]=d
            elif kind=='evidence_request':self.requests[d['id']]=d
            elif kind=='ai_draft':self.ai_drafts[d['id']]=d
            elif kind=='ai_apply':self.ai_applications.append(d)
            elif kind=='ai_content_approval':self.ai_approvals[d['procedure_id']]=d
        if any(digest(r['result'])!=r['result_hash'] for r in self.runs.values()):raise AuditError('검사 결과 해시 불일치')
        if self.engagement is None:raise AuditError('업무 기본정보 없음')
        from audit_workflow import refresh_state
        refresh_state(self)
        from audit_links import refresh
        refresh(self)
        return self
    @property
    def context(self):return {k:self.engagement[k] for k in ('회사코드','시작일','기준일')}
    def data_basis(self):return digest({'sources':self.sources,'runs':self.runs,'engagement':self.engagement})
    def basis(self):
        from audit_workflow import workflow_basis
        plan=workflow_basis(self)
        base=digest({'data_basis':self.data_basis(),'workflow':plan}) if plan else self.data_basis()
        from audit_extensions import basis_parts
        parts=basis_parts(self)
        return digest({'legacy_basis':base,'extensions':parts}) if parts else base
    def assert_writeable(self,expected_head=None):
        self.refresh()
        if expected_head is not None and self.head!=expected_head:raise AuditError('화면을 연 뒤 업무 이력이 변경되었습니다. 새 상태를 확인하고 다시 입력하세요.')
        if self.workflow_locked:raise AuditError('보관 잠금된 업무입니다. 명시적 재개 사유를 기록하세요.')
        return self.head
    def workflow_status(self):
        from audit_workflow import status
        return status(self)
    def save_workflow_profile(self,payload,actor,*,expected_head=None):
        from audit_workflow import save_profile
        return save_profile(self,payload,actor,expected_head=expected_head)
    def save_workflow_risk(self,payload,actor,*,expected_head=None):
        from audit_workflow import save_risk
        return save_risk(self,payload,actor,expected_head=expected_head)
    def save_workflow_procedure(self,payload,actor,*,expected_head=None):
        from audit_workflow import save_procedure_link
        return save_procedure_link(self,payload,actor,expected_head=expected_head)
    def retire_workflow_risk(self,risk_id,actor,reason,*,expected_head=None):
        from audit_workflow import retire
        return retire(self,risk_id,actor,reason,risk=True,expected_head=expected_head)
    def retire_workflow_procedure(self,procedure_id,actor,reason,*,expected_head=None):
        from audit_workflow import retire
        return retire(self,procedure_id,actor,reason,expected_head=expected_head)
    def classify_legacy_f01(self,purpose_code,actor,reason,*,expected_head=None):
        from audit_workflow import classify_legacy_f01
        return classify_legacy_f01(self,purpose_code,actor,reason,expected_head=expected_head)
    def finalize_workflow(self,actor,note,*,expected_head=None):
        from audit_workflow import finalize
        return finalize(self,actor,note,expected_head=expected_head)
    def reopen_workflow(self,actor,reason,*,expected_head=None):
        from audit_workflow import reopen
        return reopen(self,actor,reason,expected_head=expected_head)
    def procedure_module(self,pid):
        from audit_workflow import module_for
        return module_for(self,pid)
    def add_source(self,path,label,role='증거'):
        self.assert_writeable();p=Path(path).resolve();label=text(label,'자료명');role=text(role,'자료유형')
        from input_limits import MAX_SOURCE_BYTES
        if not p.is_file() or p.stat().st_size>MAX_SOURCE_BYTES:raise AuditError('자료는 256MB 이하 파일이어야 합니다.')
        raw=p.read_bytes();sid=uid();relative=Path('원본')/(sid+p.suffix.lower());dest=self.root/relative
        atomic(dest,raw)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=hashlib.sha256(raw).hexdigest():dest.unlink();raise AuditError('자료 복사 중 원본 변경')
        data={'id':sid,'name':label,'role':role,'original':str(p),'file':relative.as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'registered_at':now()}
        self._append('source',data);self.refresh();return sid
    def verify_sources(self):
        problems=[]
        for sid,s in self.sources.items():
            p=(self.root/s['file']).resolve()
            if not p.is_relative_to(self.root) or not p.is_file() or sha(p)!=s['sha256']:problems.append(sid+': '+s['name'])
        return problems
    def latest(self):
        out={}
        for r in self.runs.values():out[r['module']]=r
        return out
    def execute(self,module,path,event=None):
        self.refresh()
        if self.verify_sources():raise AuditError('등록한 원본 사본의 변경/누락을 먼저 해결하세요.')
        sid=self.add_source(path,module+' 입력',module);source=self.sources[sid];rid=uid()
        ledger=self.latest().get('원장·리드')
        try:
            out=adapters.run(module,self.root/source['file'],self.context,event,ledger_result=ledger['result'] if ledger else None)
            if module in ONBOARDING_MODULES:
                from onboarding.integration import validate_sources
                validate_sources(self,out)
        except Exception as e:
            out=result(module,self.context,{},[{'code':'RUN_FAILED','severity':'차단','message':str(e),'reference':source['name']}],detail={'failed':True})
        if module in ('원천증빙','재무제표·주석','GLA','FIA','현금분석')+ONBOARDING_MODULES:
            out['detail']['ledger_run_id']=ledger['id'] if ledger else None
            out['detail']['ledger_result_hash']=ledger['result_hash'] if ledger else None
        cancelled_flag=bool(event and event.is_set())
        data={'id':rid,'module':module,'source_id':sid,'at':now(),'result':out,'result_hash':digest(out),'cancelled':cancelled_flag}
        self._append('run',data);self.refresh();return data
    def cross_checks(self):
        self.refresh();latest=self.latest();ledger=latest.get('원장·리드');rows=[]
        if not ledger:return [{'모듈':'전체','지표':'TB 연결','상태':'미확인','기대':None,'실제':None,'차이':None,'사유':'원장·리드 검사를 먼저 실행하세요.'}]
        binds=defaultdict(list)
        for r in ledger['result']['tables'].get('모듈연결',[]):binds[(r['모듈'],r['지표'])].append(r)
        for mod,r in latest.items():
            if mod not in ('금융상품','매출','감가상각','리스','대손충당금','재고평가','종업원급여','미기록부채·비용이연'):continue
            for metric,value in r['result']['metrics'].items():
                bs=binds.get((mod,metric),[]);expected=sum(x['기대금액'] for x in bs) if bs else None
                valid=bool(bs) and value is not None and not r['result']['blocking'] and not ledger['result']['blocking']
                scope_ok=True
                if mod=='미기록부채·비용이연':
                    declared=r['result'].get('detail',{}).get('대상계정',{}).get(metric,[])
                    basis='기말잔액' if metric in ('기말미지급비용','기말선급비용') else '당기순변동'
                    sign=-1 if metric=='기말미지급비용' else 1
                    scope_ok=bool(declared) and set(declared)=={x['계정코드'] for x in bs} and all(x['비교기준']==basis and x['부호']==sign for x in bs)
                    valid=valid and scope_ok
                delta=num(value)-expected if expected is not None and value is not None else None
                rows.append({'모듈':mod,'지표':metric,'상태':'일치' if valid and delta==0 else '차이' if valid else '미확인','기대':expected,'실제':value,'차이':delta,'사유':'모듈 범위와 TB 연결 계정·기준·부호 불일치' if not scope_ok else ' / '.join(x['계정코드'] for x in bs) if bs else '모듈연결 설정 없음'})
        for (mod,metric),bs in binds.items():
            if mod not in latest:rows.append({'모듈':mod,'지표':metric,'상태':'미실행','기대':sum(x['기대금액'] for x in bs),'실제':None,'차이':None,'사유':'해당 모듈 실행 필요'})
        for module in ('원천증빙','재무제표·주석'):
            run=latest.get(module)
            if not run:continue
            current=run['result'].get('detail',{}).get('ledger_run_id')==ledger['id'] and run['result'].get('detail',{}).get('ledger_result_hash')==ledger['result_hash']
            valid=current and not run['result']['blocking'] and not ledger['result']['blocking']
            rows.append({'모듈':module,'지표':'현재원장·원천 연결','상태':('차이' if run['result']['review'] else '일치') if valid else '미확인','기대':None,'실제':None,'차이':None,'사유':'현재 원장 실행과 연결된 원천·개별 대사표 확인. 차이는 합산하지 않음.' if valid else '원장 변경·차단 또는 원천/재무제표 검증 미완료. 다시 실행하세요.'})
        for module in ('GLA','FIA','현금분석'):
            run=latest.get(module)
            if not run:continue
            current=run['result']['detail'].get('ledger_run_id')==ledger['id'] and run['result']['detail'].get('ledger_result_hash')==ledger['result_hash']
            valid=current and not run['result']['blocking'] and not ledger['result']['blocking'] and run['result']['detail'].get('현재원장연결') is True
            rows.append({'모듈':module,'지표':'분석모집단·현재원장 연결','상태':'일치' if valid else '미확인','기대':None,'실제':None,'차이':None,'사유':'입력 7시트·GL·TB 연결 확인. 위험후보·미확인 규칙·은행 미대사는 별도 검토.' if valid else '현재 원장과 분석자료 불일치·차단·재실행 필요'})
        if '계정별증빙연습' in latest:rows.append({'모듈':'계정별증빙연습','지표':'독립 사례 범위','상태':'미확인','기대':None,'실제':None,'차이':None,'사유':'독립 거래 연습으로 현재 업무 TB와 합산·대사하지 않음. 검토중 조서만 출력 가능.'})
        from onboarding.integration import workspace_checks
        rows.extend(workspace_checks(latest,ledger))
        return rows
    def save_procedure(self,p,_ai_draft_id=None):
        self.assert_writeable();p=dict(p);pid=text(p['id'])
        if pid in ('F01','FS01'):
            from audit_workflow import purpose_code
            expected=purpose_code(self,pid)
            if p.get('purpose_code')!=expected:raise AuditError('F01/FS01 절차 목적을 명시하고 원래 목적과 일치시켜야 합니다.')
        p['title']=text(p['title']);p['preparer']=text(p['preparer']);p['state']='작성중';p['basis']=self.basis();p['reviewer']='';p['reviewed_at']='';p['review_note']=''
        previous=self.procedures.get(pid,{})
        # The normal form omits hidden metadata. Preserve AI lineage so edits
        # cannot accidentally turn an AI-applied draft into an untracked one.
        origin=_ai_draft_id or previous.get('ai_draft_id')
        p.pop('ai_draft_id',None)
        if origin:
            if origin not in self.ai_drafts:raise AuditError('AI 초안 연결 이력이 없습니다.')
            draft=self.ai_drafts[origin]
            if draft.get('procedure_id')!=pid:raise AuditError('다른 절차의 AI 초안 연결 금지')
            if pid in ('F01','FS01') and draft.get('packet',{}).get('procedure',{}).get('purpose_code')!=p.get('purpose_code'):raise AuditError('구형/다른 목적 AI 초안을 전용할 수 없습니다.')
            p['ai_draft_id']=origin
        p['edit_revision']=uid()
        for key in ('purpose','risk','scope','performed','conclusion','performed_date','evidence','excluded_reason'):p.setdefault(key,'')
        ids=p.get('evidence_ids',[])
        if not isinstance(ids,list) or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):raise AuditError('증거 ID 목록/중복 오류')
        for sid in ids:
            if sid not in self.sources:raise AuditError('등록되지 않은 증거 ID')
        p['updated_at']=now();self._append('procedure',p);self.refresh();return p
    def request_review(self,pid):
        self.assert_writeable()
        if pid=='F01':self.procedure_module(pid)
        p=dict(self.procedures[pid])
        required=('excluded_reason',) if p.get('excluded') else ('purpose','risk','scope','performed','conclusion','performed_date')
        if any(not str(p.get(k,'')).strip() for k in required):raise AuditError('필수 수행·판단 필드 또는 제외 사유를 채우세요.')
        if not p.get('excluded'):
            day(p['performed_date'])
            if not p.get('evidence_ids'):raise AuditError('등록한 원본 증거를 하나 이상 연결하세요.')
            mod=self.procedure_module(pid)
            latest=self.latest()
            if mod in ('GLA','FIA','현금분석')+ONBOARDING_MODULES and mod not in latest:raise AuditError('분석 조서에 연결할 검사를 먼저 실행하세요.')
            if mod in latest:
                if mod!='계정별증빙연습' and '원장·리드' not in latest:raise AuditError('계산 조서의 원장·리드 실행 필요')
                required_evidence={latest[mod]['source_id']}|({latest['원장·리드']['source_id']} if mod!='계정별증빙연습' else set())
                if not required_evidence<=set(p['evidence_ids']):raise AuditError('추정 계산자료와 독립 원장·리드 증거를 모두 연결하세요.')
                if mod in ONBOARDING_MODULES and not set(latest[mod]['result']['detail'].get('origin_source_ids',[]))<=set(p['evidence_ids']):
                    raise AuditError('실무절차 입력에 사용한 원본 자료도 조서 증거에 연결하세요.')
                if mod in ('원천증빙','재무제표·주석','GLA','FIA','현금분석')+ONBOARDING_MODULES:
                    r=latest[mod];active=latest['원장·리드']
                    if r['result']['blocking'] or r['result']['detail'].get('ledger_run_id')!=active['id'] or r['result']['detail'].get('ledger_result_hash')!=active['result_hash']:
                        raise AuditError('현재 원장과 연결된 차단 없는 검사를 다시 실행한 후 검토요청하세요.')
        if p['basis']!=self.basis():raise AuditError('자료/검사 변경 후 조서를 다시 저장하세요.')
        if self.verify_sources():raise AuditError('증거 사본 무결성 오류')
        p['state']='검토요청';p['updated_at']=now();self._append('procedure',p);self.refresh()
    def review(self,pid,reviewer,note,accepted=True):
        self.assert_writeable()
        if pid=='F01':self.procedure_module(pid)
        p=dict(self.procedures[pid]);reviewer=text(reviewer,'검토자');note=text(note,'검토내용·범위')
        if reviewer==p['preparer']:raise AuditError('이 제품의 검토 정책: 작성자와 다른 검토자 필요')
        if p['state']!='검토요청' or p['basis']!=self.basis():raise AuditError('현재 자료 버전의 검토요청 상태여야 합니다.')
        if self.verify_sources():raise AuditError('증거 사본 무결성 오류')
        p.update(state='검토기록완료' if accepted else '검토의견',reviewer=reviewer,review_note=note,reviewed_at=now())
        self._append('procedure',p);self.refresh()
    def add_note(self,title,body,actor,resolved=False,note_id=None):
        self.refresh();n={'id':note_id or uid(),'title':text(title),'body':text(body),'actor':text(actor),'resolved':bool(resolved),'at':now()}
        self._append('note',n);self.refresh();return n['id']
    def procedure_state(self,p):return '자료변경·재검토' if p['basis']!=self.basis() else p['state']
    def save_request(self,entry):
        self.refresh();d=dict(entry);d['id']=d.get('id') or uid()
        for key in ('title','requested_from','note'):d[key]=text(d.get(key),key)
        d['due_date']=day(d.get('due_date')).isoformat()
        if d.get('state') not in ('요청','부분수령','수령','검토완료','취소'):raise AuditError('자료요청 상태 오류')
        ids=d.get('source_ids',[])
        if not isinstance(ids,list) or len(set(ids))!=len(ids) or any(i not in self.sources for i in ids):raise AuditError('등록된 증거 사본을 연결하세요.')
        if d['state'] in ('부분수령','수령','검토완료') and not ids:raise AuditError('수령 자료의 등록된 원본 사본이 필요합니다.')
        if d['state'] in ('부분수령','수령','검토완료') and self.verify_sources():raise AuditError('수령 자료 사본 무결성 확인 필요')
        d['updated_at']=now();self._append('evidence_request',d);self.refresh();return d
    def calculation_refs(self,pid):
        try:module=self.procedure_module(pid)
        except AuditError:return None
        r=self.latest().get(module)
        if not r:return None
        return {'모듈':module,'실행ID':r['id'],'자료ID':r['source_id'],'원본자료ID':r['result']['detail'].get('origin_source_ids',[]),'결과해시':r['result_hash'],'계산지표':r['result']['metrics'],'계산정책':r['result']['detail'],'원장대사':[x for x in self.cross_checks() if x['모듈']==module],'계산표':list(r['result']['tables']),'차단':r['result']['blocking'],'검토':r['result']['review']}
    def required_procedures(self):
        required=set()
        mapping={'원장·리드':['C04','C05','P07'],'금융상품':['A02'],'매출':['A04'],'감가상각':['A12'],'확장검사':['A01','A06','A08','A10'],'리스':['A15'],'대손충당금':['A07'],'재고평가':['A11'],'종업원급여':['A16'],'미기록부채·비용이연':['A08','A09'],'원천증빙':['R01'],'재무제표·주석':['FS01'],'계정별증빙연습':['W01']}
        mapping.update({'GLA':['G01'],'FIA':['I01'],'현금분석':['H01']})
        mapping.update({module:[pid] for pid,module in ONBOARDING_PROCEDURES.items()})
        for r in self.latest().values():
            required.update(mapping[r['module']])
            for i,issue in enumerate(r['result']['issues']):
                if issue['severity']!='차단':required.add('X-'+r['id']+'-'+str(i))
        for r in self.cross_checks():
            if r['상태']=='차이':required.add('B-'+digest(r)[:16])
        from audit_extensions import required_procedures
        required.update(required_procedures(self))
        return required
    def snapshot(self,final=False):
        self.refresh()
        if self.verify_sources():raise AuditError('원본 사본이 변경/누락되었습니다. 내보내기 중단')
        workflow=self.workflow_status()
        form_references=[]
        if workflow['active']:
            from audit_workflow import form_reference_rows
            form_references=form_reference_rows(self)
        latest=self.latest();cross=self.cross_checks();procedures=[{**p,'current_state':self.procedure_state(p),'ai_status':self.ai_status(p['id'])} for p in self.procedures.values()]
        if final:
            if workflow['blockers']:raise AuditError('감사 흐름 완료 점검 차단: '+' / '.join(r['message'] for r in workflow['blockers'][:6]))
            if any(p['ai_status']['required'] and not p['ai_status']['approved'] for p in procedures):raise AuditError('AI 적용 조서의 최종내용 미승인/변경: 사람이 현재 내용과 근거를 확인·승인해야 합니다.')
            if any(r['state'] not in ('검토완료','취소') for r in self.requests.values()):raise AuditError('미완료 자료요청을 수령·검토하거나 취소 사유를 기록하세요.')
            if '원장·리드' not in latest or any(r['result']['blocking'] for r in latest.values()) or any(r['상태'] not in ('일치','차이') for r in cross):raise AuditError('자동검사 차단/모듈-TB 미확인: 검토완료본 저장 불가')
            if not procedures or any(p['current_state']!='검토기록완료' for p in procedures):raise AuditError('조서 검토·현재 자료 버전 확인 필요')
            required=self.required_procedures()
            if not required<=set(self.procedures) or any(self.procedures[p].get('excluded') for p in required):raise AuditError('필수 검사 관련 수동절차·예외 조서가 누락되었거나 제외되었습니다.')
            if any(not n['resolved'] for n in self.notes.values()):raise AuditError('미해결 검토의견이 있습니다.')
        from review_support import source_requirements
        from audit_extensions import snapshots
        extensions=snapshots(self)
        return {**extensions,'version':VERSION,'engagement':self.engagement,'export_state':'선택조서 검토기록완료' if final else '검토중 초안','scope':'등록한 조서와 검사 범위. 전체 감사완료나 감사의견을 뜻하지 않음.','basis':self.basis(),'head':self.head,'sources':list(self.sources.values()),'latest':list(latest.values()),'all_runs':list(self.runs.values()),'cross':cross,'procedures':procedures,'notes':list(self.notes.values()),'requests':list(self.requests.values()),'events':self.events,'risk_register':self.risk_register(),'analytics_source_requirements':source_requirements(),'ai_drafts':list(self.ai_drafts.values()),'ai_applications':self.ai_applications,'ai_approvals':list(self.ai_approvals.values()),'workflow':workflow,'form_references':form_references,'legacy_f01_documents':self.legacy_f01_documents,'legacy_f01_approvals':self.legacy_f01_approvals}

    def ai_packet(self,pid,catalog=None,limits=None,event=None):
        from ai_workpapers import build_packet
        return build_packet(self,pid,catalog,limits,event)

    def record_ai_draft(self,packet,response,actor):
        from ai_workpapers import record_draft
        return record_draft(self,packet,response,actor)

    def apply_ai_draft(self,draft_id,actor):
        from ai_workpapers import apply_draft
        return apply_draft(self,draft_id,actor)

    def approve_ai_content(self,pid,actor,note):
        from ai_workpapers import approve_content
        return approve_content(self,pid,actor,note)

    def ai_status(self,pid):
        from ai_workpapers import status
        return status(self,pid)

    def risk_register(self):
        from review_support import collect_candidates
        return collect_candidates(self)

    def candidate_request_draft(self,key):
        from review_support import request_draft
        return request_draft(self,key)

from collections import defaultdict
