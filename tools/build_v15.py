from pathlib import Path
import os,sys,subprocess,json,hashlib,re,shutil
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];QA=ROOT/'검증';DIST=ROOT/'배포'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,log,env,cwd=ROOT,timeout=600):
    with log.open('w',encoding='utf-8') as out:
        p=subprocess.Popen([str(x) for x in args],cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        code=p.wait(timeout)
    if code:raise RuntimeError(log.read_text(encoding='utf-8')[-3000:])
unit=(QA/'단위검사.txt').read_text(encoding='utf-8');assert unit.rstrip().endswith('OK');tests=int(re.search(r'Ran (\d+) tests',unit)[1])
source=json.loads((QA/'소스UI_3/report.json').read_text(encoding='utf-8'));assert source['ok']
headless=json.loads((QA/'headless_1/report.json').read_text(encoding='utf-8'));assert headless['ok']
files=list(ROOT.glob('*.py'))+list(ROOT.glob('*.json'))+[ROOT/'AuditSuite.spec']
for folder in ('engines','raw_sources','raw_accounts','financial_bridge','worker_library','gla','fia','cash_analytics','samples','templates','raw_analytics','문서','.runtime'):
    files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and 'verification' not in p.parts and p.suffix!='.pyc')
manifest=[{'file':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in sorted(set(files))]
tmp=ROOT/'build/temp';tmp.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',TEMP=str(tmp),TMP=str(tmp),PYINSTALLER_CONFIG_DIR=str(ROOT/'build/config'),TCL_LIBRARY=str(ROOT/'.runtime/tcl_library'),TK_LIBRARY=str(ROOT/'.runtime/tk_library'))
for key in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'):env.pop(key,None)
exe=ROOT/'dist/AuditSuite.exe';assert not exe.exists(),'Preserve earlier build first'
run([sys.executable,'-X','utf8','-B','-m','PyInstaller','--noconfirm','--clean','--distpath',ROOT/'dist','--workpath',ROOT/'build/work',ROOT/'AuditSuite.spec'],QA/'PyInstaller.txt',env,timeout=900)
independent=QA/'독립EXE_1';assert not independent.exists();independent.mkdir();target=independent/'통합 회계감사 v1.5.exe';shutil.copy2(exe,target)
temp=independent/'temp';temp.mkdir();win=os.environ.get('SystemRoot',r'C:\Windows')
minimal={'SystemRoot':win,'WINDIR':win,'PATH':str(Path(win)/'System32'),'TEMP':str(temp),'TMP':str(temp)}
run([target,'--self-test-v15','--report',independent/'report.json'],QA/'EXE_실행.txt',minimal,cwd=independent,timeout=600)
frozen=json.loads((independent/'report.json').read_text(encoding='utf-8'));assert frozen['ok'] and frozen['frozen']
assert source['observations']==frozen['observations'],'source/frozen accounting observations differ'
assert all(sha(ROOT/r['file'])==r['sha256'] for r in manifest),'build source changed during validation'
DIST.mkdir(exist_ok=True);shutil.copy2(target,DIST/target.name)
record={'version':'1.5.0','status':'passed','built_utc':datetime.now(timezone.utc).isoformat(),'unit_tests':tests,'total_cases':frozen['total_cases'],'new_cases':frozen['case_count'],
 'new_accounting_assertions':len(frozen['checks']),'native_assertions':len(frozen['native_checks']),'headless_assertions':headless['assertions'],'source_frozen_observations_identical':True,
 'exe_sha256':sha(target),'exe_bytes':target.stat().st_size,'python':sys.version,'environment':'Windows development PC, EXE-only folder, System32 PATH; no clean-OS or other-PC claim',
 'source_manifest':manifest,'source_report':'소스UI_3/report.json','frozen_report':'독립EXE_1/report.json','headless_report':'headless_1/report.json'}
(QA/'빌드결과.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k!='source_manifest'},ensure_ascii=False,indent=2))
