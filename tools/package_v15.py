"""Package only the reviewed v1.5 build, synthetic data and portable sources."""
from pathlib import Path
import hashlib,json,shutil,zipfile,re,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from common import sha
from workspace import Workspace
QA=ROOT/'검증';DIST=ROOT/'배포';VERSION='1.5.0'

def copy_file(src,dest):
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)

def copy_folder(src,dest):
    assert src.is_dir(),str(src)
    for p in sorted(src.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':copy_file(p,dest/p.relative_to(src))

def write(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

def archive(target,files,prefix):
    assert not target.exists(),'Preserve existing package first: '+str(target)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=8) as z:
        for name,p in sorted(files.items()):z.write(p,prefix+name)
    with zipfile.ZipFile(target) as z:
        assert not z.testzip()
        assert len(z.namelist())==len(set(z.namelist()))==len(files)
        for name,p in files.items():assert hashlib.sha256(z.read(prefix+name)).hexdigest()==sha(p),name

def load(p):return json.loads(p.read_text(encoding='utf-8'))

build=load(QA/'빌드결과.json')
assert build['status']=='passed' and build['unit_tests']==464
assert all(sha(ROOT/x['file'])==x['sha256'] for x in build['source_manifest'])
assert sha(DIST/'통합 회계감사 v1.5.exe')==build['exe_sha256']
source_path=QA/build['source_report'];frozen_path=QA/build['frozen_report']
source=load(source_path);frozen=load(frozen_path);headless=load(QA/build['headless_report'])
assert source['ok'] and frozen['ok'] and frozen['frozen'] and source['observations']==frozen['observations']
assert headless['ok'] and headless['assertions']==1949 and headless['total_cases']==332
assert len(frozen['checks'])==284 and len(frozen['native_checks'])==17
preview=load(QA/'출력조서_렌더검증.json');assert '0 entries' in preview['errors'] and len(preview['records'])==55
visual=load(QA/'v15_시각검토.json');assert visual['status']=='passed'
raw=load(ROOT/'raw_analytics/verification.json')
assert raw['source_workbooks']==4 and raw['source_sheets']==19 and raw['data_rows']==464
assert raw['missing_rows']==raw['changed_cells']==0 and raw['original_analysis_inputs_unchanged']
for r in raw['checks']:
    if r.get('module'):
        name={'GLA':'GLA','FIA':'FIA','현금분석':'현금분석'}[r['module']]
        assert sha(ROOT/'samples/통합'/('통합_v1.5_'+name+'.xlsx'))==r['analysis_input_sha256']
benchmark=load(ROOT/'gla/verification/benchmark_10000.json')
assert benchmark['ok'] and len(benchmark['checks'])==32
assert all(sha(ROOT/p)==digest for p,digest in benchmark['source_before'].items())
ws=Workspace(DIST/'예시업무_미검토');assert not ws.verify_sources()
assert len(ws.latest())==15 and len(ws.cross_checks())==35 and all(r['상태']=='일치' for r in ws.cross_checks())
assert len(ws.risk_register())==24
assert all(not p['performed'] and not p['conclusion'] and not p['reviewer'] for p in ws.procedures.values())
example=load(ROOT/'outputs/01a16140-43b4-7e72-8585-04010bd5e6c9/예시검증.json')
assert sha(DIST/'예시조서/통합감사_미검토초안_v1.5.xlsx')==example['xlsx_sha256']

for folder,destination in [('samples','더미자료'),('templates','입력양식'),('raw_input_seed','원천자료'),('reference_evidence','참고증빙'),('raw_analytics','분석원천자료'),('문서','문서')]:
    copy_folder(ROOT/folder,DIST/destination)
copy_file(ROOT/'README.md',DIST/'README.md')
previous=ROOT.parent/'v1.4_원천증빙통합_2026-10-23/배포'
copy_folder(previous/'라이선스',DIST/'라이선스')
copy_folder(previous/'기존계산정책',DIST/'기존계산정책')
qdest=DIST/'검증기록';qdest.mkdir(exist_ok=True)
records=[(QA/'빌드결과.json','빌드결과.json'),(QA/'단위검사.txt','단위검사.txt'),
 (QA/'출력수정_회귀검사.txt','출력수정_회귀검사.txt'),(source_path,'소스UI.json'),(frozen_path,'EXE_UI.json'),
 (QA/build['headless_report'],'headless.json'),(QA/'출력조서_렌더검증.json','출력조서_렌더검증.json'),
 (QA/'v15_시각검토.json','v15_시각검토.json'),(ROOT/'gla/verification/benchmark_10000.json','GLA_10000행.json'),
 (ROOT/'raw_analytics/verification.json','원천분해_재구성검증.json')]
for src,name in records:copy_file(src,qdest/name)
for log in ('PyInstaller.txt','EXE_실행.txt','소스UI_3_실행.txt','headless_1_실행.txt'):copy_file(QA/log,qdest/log)
for p in frozen_path.parent.glob('*.png'):copy_file(p,qdest/p.name)
copy_folder(QA/'v15_조서미리보기',qdest/'조서미리보기')
for sub in ('legacy_v14','legacy_v14/legacy'):
    for p in (frozen_path.parent/sub).glob('*.png'):copy_file(p,qdest/'기존UI'/sub/p.name)

licenses={p.relative_to(DIST).as_posix():p for p in (DIST/'라이선스').rglob('*') if p.is_file()}
sources={p.name:p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.json','.spec','.txt','.md')}
sources['.gitattributes']=ROOT/'.gitattributes';(QA/'.gitkeep').touch(exist_ok=True);sources['검증/.gitkeep']=QA/'.gitkeep'
for folder in ('engines','raw_sources','raw_accounts','financial_bridge','worker_library','gla','fia','cash_analytics','samples','templates','testdata','raw_input_seed','reference_evidence','raw_analytics','.runtime','문서','ci'):
    for p in (ROOT/folder).rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix=='.pyc':continue
        if folder in ('gla','fia','cash_analytics') and 'verification' in p.parts and p.suffix not in ('.json','.md'):continue
        sources[p.relative_to(ROOT).as_posix()]=p
for p in (ROOT/'tools').iterdir():
    if p.is_file() and p.suffix in ('.py','.mjs','.md'):sources[p.relative_to(ROOT).as_posix()]=p
sources.update(licenses)
for name in sources:
    assert not re.search(r'(^|/)(\.git|\.venv|node_modules|\.env|release-state\.json|benchmark_inputs)(/|$)',name),name
sourcezip=DIST/'audit-suite-source-v1.5.0.zip';archive(sourcezip,sources,'audit-suite-v15/')
validation={'version':VERSION,'status':'passed','unit_tests':464,'fixture_cases':332,
 'case_groups':{'legacy_v14':270,'GLA':12,'FIA':22,'cash':28},'headless_assertions':1949,
 'new_accounting_assertions':284,'new_native_assertions':17,'legacy_native_checks':'Included by nested v1.4 verification report',
 'source_frozen_observations_identical':True,'normal_modules':15,'current_ledger_links':35,'normal_review_candidates':24,
 'raw_analytics':{'source_workbooks':4,'sheets':19,'data_rows':464,'pbc_requests':19,'reconstructed_inputs':3,'missing_rows':0,'changed_cells':0,'independently_collected_evidence':False},
 'GLA_benchmark':{'rows':10000,'journals':4993,'assertions':32,'source_analysis_seconds':benchmark['gla_read_validate_aggregate_candidates_seconds'],'input_limit':10000,'over_limit_rejected':True,'EXE_UI_export_timed':False},
 'workpaper_previews':55,'human_fields_blank':True,'unreviewed_final_export_blocked':True,'uses_ai_inference':False,
 'exe':{'name':'통합 회계감사 v1.5.exe','bytes':build['exe_bytes'],'sha256':build['exe_sha256']},
 'source':{'name':sourcezip.name,'files':len(sources),'sha256':sha(sourcezip)},'example_xlsx_sha256':example['xlsx_sha256'],
 'limitations':['Windows development PC only; EXE-only folder is not a clean OS or another PC test',
 'UI widgets invoked; operating-system file chooser not automated',
 'Synthetic selected transactions; full submitted population and source authenticity require independent evidence',
 'GLA performance is one source run; no EXE/UI/export timing or 100k/1m-row claim',
 'Local deterministic rules; human performance, judgment, conclusions and review are not auto-completed',
 'Unadjusted standalone KRW TB; no complete audit or compliance certification'],
 'github_verification':'Local checks only in this file. See audit-suite-v1.5.0 release and exact-commit Python 3.12/3.14 GitHub Actions records.'}
write(DIST/'validation.json',validation)
folders=('더미자료','입력양식','원천자료','참고증빙','분석원천자료','문서','라이선스','기존계산정책','검증기록','예시조서','예시업무_미검토')
files={name:DIST/name for name in ('통합 회계감사 v1.5.exe','README.md','validation.json')}
for folder in folders:
    files.update({p.relative_to(DIST).as_posix():p for p in (DIST/folder).rglob('*') if p.is_file()})
write(DIST/'파일목록_SHA256.json',[{'file':name,'bytes':p.stat().st_size,'sha256':sha(p)} for name,p in sorted(files.items())])
files['파일목록_SHA256.json']=DIST/'파일목록_SHA256.json'
package=DIST/'AuditSuite-Windows-v1.5.0.zip';archive(package,files,'AuditSuite-v1.5/')
assets=[package,sourcezip,DIST/'validation.json']
(DIST/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in assets),encoding='utf-8')
result={'status':'passed','version':VERSION,'windows_files':len(files),'source_files':len(sources),
 'assets':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in assets+[DIST/'SHA256SUMS.txt']],
 'source_manifest_unchanged':True,'zip_crc_and_all_file_hashes_verified':True,'prior_builds_excluded':True}
write(QA/'최종배포검증.json',result);print(json.dumps(result,ensure_ascii=False))
