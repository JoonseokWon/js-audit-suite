"""Freeze reviewed v1.8.0 inputs and verify source, EXE UI and actual local AI."""
from pathlib import Path
import os,sys,subprocess,json,re,shutil,hashlib
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];QA=ROOT/'검증';DIST=ROOT/'배포'
attempt=2 if '--retry' in sys.argv else 1
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def run(args,log,env,cwd=ROOT,timeout=1800):
    with log.open('w',encoding='utf-8') as out:
        proc=subprocess.Popen([str(a) for a in args],cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        code=proc.wait(timeout)
    if code:raise RuntimeError('검증 프로세스 실패: '+log.name+' / '+log.read_text(encoding='utf-8')[-1000:])
unit=(QA/'단위검사_최종.txt').read_text(encoding='utf-8');assert unit.rstrip().endswith('OK') and 'skipped=' not in unit
tests=int(re.search(r'Ran (\d+) tests',unit)[1]);assert tests>=690
source=read(QA/'소스UI_6/report.json');headless=read(QA/'headless_1/report.json');actual_source=read(QA/'실제AI_소스_4/report.json')
assert source['ok'] and headless['ok'] and actual_source['status']=='passed' and actual_source['actual_local_inference']
assert (headless['normal_module_executions'],headless['current_ledger_links'])==(61,140)
files=[p for p in ROOT.iterdir() if p.is_file() and (p.suffix in ('.py','.json','.txt','.md','.spec','.manifest') or p.name=='.gitattributes')]
for folder in ('engines','raw_sources','raw_accounts','financial_bridge','worker_library','gla','fia','cash_analytics','samples','templates','raw_analytics','sector_resources','testdata','raw_input_seed','reference_evidence','문서','.runtime','tools','ci','라이선스'):
    files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and 'verification' not in p.parts and p.suffix!='.pyc')
manifest=[{'file':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in sorted(set(files))]
(QA/f'빌드입력_동결_{attempt}.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
tmp=ROOT/'build/temp';tmp.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',TEMP=str(tmp),TMP=str(tmp),PYINSTALLER_CONFIG_DIR=str(ROOT/'build/config'),TCL_LIBRARY=str(ROOT/'.runtime/tcl_library'),TK_LIBRARY=str(ROOT/'.runtime/tk_library'))
for key in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'):env.pop(key,None)
build_dist=ROOT/('dist2' if attempt==2 else 'dist');exe=build_dist/'AuditSuite.exe';independent=QA/f'독립EXE_{attempt}';target=independent/'통합 회계감사 v1.8.0.exe'
assert not exe.exists() and not independent.exists(),'Preserve previous build evidence'
run([sys.executable,'-X','utf8','-B','-m','PyInstaller','--noconfirm','--clean','--distpath',build_dist,'--workpath',ROOT/f'build/work{attempt}',ROOT/'AuditSuite.spec'],QA/f'PyInstaller_v18_{attempt}.txt',env)
from PyInstaller.utils.win32.winmanifest import read_manifest_from_executable
from xml.etree import ElementTree as ET
manifest_bytes=read_manifest_from_executable(str(exe));xml=ET.fromstring(manifest_bytes);values={e.tag.rsplit('}',1)[-1]:e.text for e in xml.iter()}
assert values.get('dpiAware')=='true' and values.get('dpiAwareness')=='system'
independent.mkdir();shutil.copy2(exe,target);temp=independent/'temp';temp.mkdir();win=os.environ.get('SystemRoot',r'C:\Windows')
minimal={'SystemRoot':win,'WINDIR':win,'PATH':str(Path(win)/'System32'),'TEMP':str(temp),'TMP':str(temp)}
run([target,'--self-test-v18','--report',independent/'report.json'],QA/f'EXE_v18_실행_{attempt}.txt',minimal,cwd=independent)
frozen=read(independent/'report.json');assert frozen['ok'] and frozen['frozen']
for key in ('observations','sector_observations','display_observations','native_checks'):assert source[key]==frozen[key],key+' differs source/frozen'
assert frozen['display_environment']['awareness']['mode']=='system'
actual_relative=f'실제AI_EXE_{attempt}/report.json'
run([target,'--self-test-ai-real','--ai-runtime',DIST/'로컬AI','--report',QA/actual_relative],QA/f'실제AI_EXE_실행_{attempt}.txt',minimal,cwd=independent)
actual_frozen=read(QA/actual_relative);assert actual_frozen['status']=='passed' and actual_frozen['frozen'] and actual_frozen['actual_local_inference']
assert all(sha(ROOT/r['file'])==r['sha256'] for r in manifest),'Reviewed build inputs changed'
DIST.mkdir(exist_ok=True);shutil.copy2(target,DIST/target.name)
record={'version':'1.8.0','status':'passed','built_utc':datetime.fromtimestamp(exe.stat().st_mtime,timezone.utc).isoformat(),'verified_utc':datetime.now(timezone.utc).isoformat(),'unit_tests':tests,'fixture_cases':332,
 'native_assertions':len(frozen['native_checks']),'ai_native_assertions':len(frozen['ai_native_checks']),'display_assertions':len(frozen['display_checks']),'baseline_native_assertions':len(frozen['baseline_native_checks']),
 'dpi_policy':'system','embedded_manifest_dpi_verified':True,'exe_manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),'display_environment':frozen['display_environment'],'legacy_native_assertions':len(frozen['legacy_native_checks']),
 'headless_legacy_assertions':headless['legacy_assertions'],'headless_sector_assertions':headless['sector_assertions'],'normal_companies':5,'normal_module_executions':61,'current_ledger_links':140,'cross_company_negative_checks':72,'parent_cross_company_negative_checks':4,'extracted_raw_workbooks':64,
 'source_frozen_observations_identical':True,'exe_sha256':sha(target),'exe_bytes':target.stat().st_size,'actual_local_inference':True,'actual_openai_calls':0,'actual_ai_source_report':'실제AI_소스_4/report.json','actual_ai_frozen_report':actual_relative,'python':sys.version,
 'environment':'Windows development PC; EXE-only folder; System32 PATH; no clean OS or other-PC claim','source_manifest':manifest,'source_report':'소스UI_6/report.json','source_baseline_report':'소스UI_1/baseline_v171/report.json','frozen_report':f'독립EXE_{attempt}/report.json','headless_report':'headless_1/report.json','attempt':attempt}
(QA/'빌드결과.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in record.items() if k!='source_manifest'},ensure_ascii=False))
