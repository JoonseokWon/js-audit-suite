"""Freeze reviewed v1.7.1 inputs and compare the real source/standalone EXE UI."""
from pathlib import Path
import os, sys, subprocess, json, re, shutil, hashlib
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[1]
QA = ROOT/'검증'; DIST = ROOT/'배포'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def run(args, log, env, cwd=ROOT, timeout=1200):
    with log.open('w', encoding='utf-8') as out:
        proc = subprocess.Popen([str(a) for a in args], cwd=cwd, env=env,
                                stdout=out, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        code = proc.wait(timeout)
    if code: raise RuntimeError(log.read_text(encoding='utf-8')[-3000:])
unit = (QA/'단위검사_최종3.txt').read_text(encoding='utf-8')
assert unit.rstrip().endswith('OK')
tests = int(re.search(r'Ran (\d+) tests', unit)[1]); assert tests == 540
source = read(QA/'소스UI_3/report.json'); assert source['ok']
headless = read(QA/'headless_3/report.json'); assert headless['ok']
assert (headless['normal_module_executions'], headless['current_ledger_links']) == (61, 140)
files = [p for p in ROOT.iterdir() if p.is_file() and (p.suffix in ('.py','.json','.txt','.md','.spec','.manifest') or p.name=='.gitattributes')]
for folder in ('engines','raw_sources','raw_accounts','financial_bridge','worker_library','gla','fia','cash_analytics',
               'samples','templates','raw_analytics','sector_resources','testdata','raw_input_seed','reference_evidence',
               '문서','.runtime','tools','ci','라이선스'):
    files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts
                 and 'verification' not in p.parts and p.suffix!='.pyc')
manifest = [{'file':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in sorted(set(files))]
tmp = ROOT/'build/temp'; tmp.mkdir(parents=True,exist_ok=True)
env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', TEMP=str(tmp), TMP=str(tmp),
           PYINSTALLER_CONFIG_DIR=str(ROOT/'build/config'), TCL_LIBRARY=str(ROOT/'.runtime/tcl_library'), TK_LIBRARY=str(ROOT/'.runtime/tk_library'))
for key in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'): env.pop(key,None)
exe = ROOT/'dist/AuditSuite.exe'; independent = QA/'독립EXE_1'; target = independent/'통합 회계감사 v1.7.1.exe'
assert not exe.exists() and not independent.exists(), 'Preserve existing build evidence'
run([sys.executable,'-X','utf8','-B','-m','PyInstaller','--noconfirm','--clean','--distpath',ROOT/'dist',
     '--workpath',ROOT/'build/work',ROOT/'AuditSuite.spec'], QA/'PyInstaller_v171.txt', env)
from PyInstaller.utils.win32.winmanifest import read_manifest_from_executable
from xml.etree import ElementTree as ET
manifest_bytes=read_manifest_from_executable(str(exe));xml=ET.fromstring(manifest_bytes)
manifest_values={e.tag.rsplit('}',1)[-1]:e.text for e in xml.iter()}
assert manifest_values.get('dpiAware')=='true' and manifest_values.get('dpiAwareness')=='system'
independent.mkdir(); shutil.copy2(exe,target); temp = independent/'temp'; temp.mkdir()
win = os.environ.get('SystemRoot',r'C:\Windows')
minimal = {'SystemRoot':win,'WINDIR':win,'PATH':str(Path(win)/'System32'),'TEMP':str(temp),'TMP':str(temp)}
run([target,'--self-test-v171','--report',independent/'report.json'],QA/'EXE_v171_실행.txt',minimal,cwd=independent)
frozen = read(independent/'report.json'); assert frozen['ok'] and frozen['frozen']
assert source['observations']==frozen['observations'] and source['sector_observations']==frozen['sector_observations'], 'Source/EXE results differ'
assert source['display_observations']==frozen['display_observations'], 'Source/EXE actual font/zoom measurements differ'
assert frozen['display_environment']['awareness']['mode']=='system'
assert source['native_checks']==frozen['native_checks'], 'Source/EXE UI checks differ'
assert all(sha(ROOT/r['file'])==r['sha256'] for r in manifest), 'Reviewed build inputs changed'
DIST.mkdir(exist_ok=True); shutil.copy2(target,DIST/target.name)
record = {'version':'1.7.1','status':'passed','built_utc':datetime.fromtimestamp(exe.stat().st_mtime,timezone.utc).isoformat(),
          'verified_utc':datetime.now(timezone.utc).isoformat(),'unit_tests':tests,'fixture_cases':332,
          'native_assertions':len(frozen['native_checks']),'display_assertions':len(frozen['display_checks']),'baseline_native_assertions':len(frozen['baseline_native_checks']),
          'dpi_policy':'system','embedded_manifest_dpi_verified':True,'exe_manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),'display_environment':frozen['display_environment'],'legacy_native_assertions':len(frozen['legacy_native_checks']),
          'headless_legacy_assertions':headless['legacy_assertions'],'headless_sector_assertions':headless['sector_assertions'],
          'normal_companies':5,'normal_module_executions':61,'current_ledger_links':140,'cross_company_negative_checks':72,
          'parent_cross_company_negative_checks':4,'extracted_raw_workbooks':64,
          'source_frozen_observations_identical':True,'exe_sha256':sha(target),'exe_bytes':target.stat().st_size,
          'python':sys.version,'environment':'Windows development PC; EXE-only folder; System32 PATH; no clean OS or other-PC claim',
          'source_manifest':manifest,'source_report':'소스UI_3/report.json','frozen_report':'독립EXE_1/report.json','headless_report':'headless_3/report.json'}
(QA/'빌드결과.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k!='source_manifest'},ensure_ascii=False))
