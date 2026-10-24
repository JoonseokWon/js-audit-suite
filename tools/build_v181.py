"""Build a candidate locally, then verify its owned hidden-window workflow.

Publication separately requires the full tests and real IME evidence for this
exact EXE hash. No remote operations or foreground activation are performed.
"""
from pathlib import Path
import os,sys,subprocess,json,shutil,hashlib,struct,argparse
SOURCE=Path(__file__).resolve().parents[1];PROJECT=SOURCE.parents[1];QA=PROJECT/'검증'
QA.mkdir(exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=1);attempt=parser.parse_args().attempt
assert attempt>=1
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYINSTALLER_CONFIG_DIR=str(QA/'build/config'))
def run(args,log,cwd=SOURCE):
    with (QA/log).open('w',encoding='utf-8') as out:
        r=subprocess.run([str(a) for a in args],cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    if r.returncode:raise RuntimeError(log+' failed; preserve and inspect log')
data=PROJECT/'데이터/AI조서_시연/JS전자_AI조서_한글검증'
assert data.is_dir()
source_report=QA/f'소스_최종_{attempt}/report.json'
run([sys.executable,'-B','-X','utf8',SOURCE/'app.py','--self-test-ime','--workspace',data,'--report',source_report],f'소스_최종_{attempt}.txt')
source=json.loads(source_report.read_text(encoding='utf-8'))
assert source['ok'] and len(source['checks'])==18
frozen_inputs={p.name:sha(p) for p in SOURCE.iterdir() if p.is_file() and p.suffix in ('.py','.spec','.manifest')}
frozen_inputs.update({'assets/'+p.name:sha(p) for p in (SOURCE/'assets').iterdir() if p.is_file()})
(QA/f'최종빌드입력_{attempt}.json').write_text(json.dumps(frozen_inputs,ensure_ascii=False,indent=2),encoding='utf-8')
dist=QA/f'build_{attempt}/dist';work=QA/f'build_{attempt}/work'
assert not dist.exists(),'Preserve prior candidate'
run([sys.executable,'-B','-X','utf8','-m','PyInstaller','--noconfirm','--clean','--distpath',dist,'--workpath',work,SOURCE/'AuditSuite.spec'],f'PyInstaller_v181_최종_{attempt}.txt')
exe=dist/'AuditSuite.exe'
import pefile
pe=pefile.PE(str(exe));groups=[]
for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
    if kind.id==14:
        for name in kind.directory.entries:
            for lang in name.directory.entries:
                r=lang.data.struct;raw=pe.get_data(r.OffsetToData,r.Size)
                reserved,itype,count=struct.unpack_from('<HHH',raw)
                groups.append(count)
assert groups and min(groups)>=9,'Expected multi-resolution embedded EXE icon'
pe.close()
from PyInstaller.utils.win32.winmanifest import read_manifest_from_executable
from xml.etree import ElementTree as ET
manifest=ET.fromstring(read_manifest_from_executable(str(exe)))
assert any(e.tag.endswith('dpiAwareness') and e.text=='system' for e in manifest.iter())
target=PROJECT/'실행파일/통합 회계감사 v1.8.1.exe'
assert not target.exists(),'Preserve previous executable'
shutil.copy2(exe,target)
frozen_report=QA/f'EXE_최종_{attempt}/report.json'
run([target,'--self-test-ime','--workspace',data,'--report',frozen_report],f'EXE_최종_{attempt}.txt',PROJECT/'실행파일')
frozen=json.loads(frozen_report.read_text(encoding='utf-8'))
assert frozen['ok'] and frozen['frozen'] and source['checks']==frozen['checks']
assert all(sha(SOURCE/p)==digest for p,digest in frozen_inputs.items()),'Build inputs changed'
record={'version':'1.8.1','status':'candidate_verified','exe':{'name':target.name,'bytes':target.stat().st_size,'sha256':sha(target)},
        'icon_embedded_verified':True,'icon_group_sizes':groups,'source_frozen_observations_identical':True,
        'attempt':attempt,'source_frozen_checks':18,'actual_hardware_ime_test':False,'current_actual_model_calls':0,
        'actual_inference_scope':'Actual local AI from v1.8.0 desktop demonstration reused; no inference rerun in this UI patch.'}
(QA/'최종빌드.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False))
