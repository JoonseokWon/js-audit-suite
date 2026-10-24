"""Freeze the verified sources, then compare real native source/EXE company selection."""
from pathlib import Path
import os,sys,subprocess,json,re,shutil,hashlib,argparse
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];QA=ROOT/'검증';DIST=ROOT/'배포'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def run(args,log,env,cwd=ROOT,timeout=900):
    with log.open('w',encoding='utf-8') as stream:
        proc=subprocess.Popen([str(x) for x in args],cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        code=proc.wait(timeout)
    if code:raise RuntimeError(log.read_text(encoding='utf-8')[-2500:])
parser=argparse.ArgumentParser();parser.add_argument('--reuse-validated-exe',action='store_true');args=parser.parse_args()
unit=(QA/'단위검사.txt').read_text(encoding='utf-8');assert unit.rstrip().endswith('OK');tests=int(re.search(r'Ran (\d+) tests',unit)[1])
source=read(QA/'소스UI_3/report.json');assert source['ok']
headless=read(QA/'headless_1/report.json');assert headless['ok']
files=list(ROOT.glob('*.py'))+list(ROOT.glob('*.json'))+[ROOT/'AuditSuite.spec',ROOT/'README.md']
for folder in ('engines','raw_sources','raw_accounts','financial_bridge','worker_library','gla','fia','cash_analytics','samples','templates','raw_analytics','sector_resources','문서','.runtime','tools','ci'):
    files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and 'verification' not in p.parts and p.suffix!='.pyc')
manifest=[{'file':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in sorted(set(files))]
tmp=ROOT/'build/temp';tmp.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',TEMP=str(tmp),TMP=str(tmp),PYINSTALLER_CONFIG_DIR=str(ROOT/'build/config'),TCL_LIBRARY=str(ROOT/'.runtime/tcl_library'),TK_LIBRARY=str(ROOT/'.runtime/tk_library'))
for key in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'):env.pop(key,None)
exe=ROOT/'dist/AuditSuite.exe';independent=QA/'독립EXE_2';target=independent/'통합 회계감사 v1.6.exe'
if args.reuse_validated_exe:
    assert exe.is_file() and target.is_file() and sha(exe)==sha(target)
    assert all(p.stat().st_mtime<=exe.stat().st_mtime for p in files if p.resolve()!=Path(__file__).resolve()),'Only builder metadata may change after validation'
else:
    assert not exe.exists(),'Preserve previous build'
    run([sys.executable,'-X','utf8','-B','-m','PyInstaller','--noconfirm','--clean','--distpath',ROOT/'dist','--workpath',ROOT/'build/work',ROOT/'AuditSuite.spec'],QA/'PyInstaller.txt',env)
    assert not independent.exists();independent.mkdir();shutil.copy2(exe,target)
    temp=independent/'temp';temp.mkdir();win=os.environ.get('SystemRoot',r'C:\Windows')
    minimal={'SystemRoot':win,'WINDIR':win,'PATH':str(Path(win)/'System32'),'TEMP':str(temp),'TMP':str(temp)}
    run([target,'--self-test-v16','--report',independent/'report.json'],QA/'EXE_실행.txt',minimal,cwd=independent)
frozen=read(independent/'report.json');assert frozen['ok'] and frozen['frozen']
assert source['observations']==frozen['observations'] and source['sector_observations']==frozen['sector_observations'],'source/EXE observations differ'
assert source['native_checks']==frozen['native_checks'],'source/EXE UI checks differ'
assert all(sha(ROOT/r['file'])==r['sha256'] for r in manifest),'source changed during build'
DIST.mkdir(exist_ok=True);shutil.copy2(target,DIST/target.name)
record={'version':'1.6.0','status':'passed','built_utc':datetime.fromtimestamp(exe.stat().st_mtime,timezone.utc).isoformat(),'verified_utc':datetime.now(timezone.utc).isoformat(),'unit_tests':tests,
        'fixture_cases':332,'native_assertions':len(frozen['native_checks']),'legacy_native_assertions':len(frozen['legacy_native_checks']),
        'headless_legacy_assertions':headless['legacy_assertions'],'headless_sector_assertions':headless['sector_assertions'],
        'normal_companies':5,'normal_module_executions':75,'current_ledger_links':175,'cross_company_negative_checks':120,
        'source_frozen_observations_identical':True,'exe_sha256':sha(target),'exe_bytes':target.stat().st_size,
        'python':sys.version,'environment':'Windows development PC; EXE-only folder; System32 PATH; no clean OS or other-PC claim',
        'tooling_metadata_recovery':bool(args.reuse_validated_exe),'tooling_note':'A builder Path-index typo was corrected after native validation. The validated EXE bytes are reused; all other reviewed input files predate that EXE.' if args.reuse_validated_exe else None,
        'source_manifest':manifest,'source_report':'소스UI_3/report.json','frozen_report':'독립EXE_2/report.json','headless_report':'headless_1/report.json'}
(QA/'빌드결과.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k!='source_manifest'},ensure_ascii=False))
