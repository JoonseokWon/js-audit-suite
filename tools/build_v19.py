"""Build one immutable candidate and compare its hidden desktop lifecycle."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,struct,subprocess,sys,zipfile
SOURCE=Path(__file__).resolve().parents[1];PROJECT=SOURCE.parents[1];QA=PROJECT/'검증/v1.9.0'
sys.path.insert(0,str(SOURCE))
from tools import github_release_v19 as policy


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=1);args=parser.parse_args()
    if args.attempt<1:parser.error('Positive attempt required')
    QA.mkdir(parents=True,exist_ok=True);base=QA/f'build-attempt-{args.attempt}'
    if base.exists():raise RuntimeError('Preserve prior build evidence; use a new attempt')
    base.mkdir();target=PROJECT/'실행파일/통합 회계감사 v1.9.0.exe'
    if target.exists():raise RuntimeError('Preserve the previous candidate executable')
    public=set(policy.BASELINE_PATHS)|policy.NEW_REQUIRED
    inputs={relative:sha(SOURCE/relative) for relative in sorted(public)}
    (base/'build-inputs.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYINSTALLER_CONFIG_DIR=str(base/'config'))
    def run(argv,log,cwd=SOURCE):
        with (base/log).open('x',encoding='utf-8') as stream:
            result=subprocess.run([str(x) for x in argv],cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,
                                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise RuntimeError(log+' failed; inspect preserved evidence')
    source_report=base/'source/report.json'
    run([sys.executable,'-B','-X','utf8','app.py','--self-test-v19','--report',source_report],'source.log')
    source=json.loads(source_report.read_text(encoding='utf-8'))
    if not source['ok'] or source['frozen'] or len(source['checks'])<36:raise RuntimeError('Source lifecycle incomplete')
    run([sys.executable,'-B','-X','utf8','-m','PyInstaller','--noconfirm','--clean',
         '--distpath',base/'dist','--workpath',base/'work',SOURCE/'AuditSuite.spec'],'pyinstaller.log')
    candidate=base/'dist/AuditSuite.exe'
    import pefile
    pe=pefile.PE(str(candidate));groups=[]
    try:
        for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if kind.id==14:
                for name in kind.directory.entries:
                    for lang in name.directory.entries:
                        entry=lang.data.struct;raw=pe.get_data(entry.OffsetToData,entry.Size)
                        groups.append(struct.unpack_from('<HHH',raw)[2])
    finally:pe.close()
    if not groups or min(groups)<9:raise RuntimeError('Original multi-resolution icon missing')
    from PyInstaller.utils.win32.winmanifest import read_manifest_from_executable
    from xml.etree import ElementTree as ET
    manifest=ET.fromstring(read_manifest_from_executable(str(candidate)))
    if not any(el.tag.endswith('dpiAwareness') and el.text=='system' for el in manifest.iter()):raise RuntimeError('DPI manifest differs')
    # The native adapter and matching interpreter family are unchanged from the
    # version whose actual Windows Korean IME key input was observed.
    with zipfile.ZipFile(PROJECT/'릴리스/js-audit-suite-v1.8.1-source.zip') as old:
        for relative in ('windows_text.py','desktop_display.py'):
            if old.read('js-audit-suite/'+relative)!=(SOURCE/relative).read_bytes():raise RuntimeError('IME baseline component changed')
    shutil.copy2(candidate,target)
    frozen_report=base/'frozen/report.json'
    run([target,'--self-test-v19','--report',frozen_report],'frozen.log',PROJECT/'실행파일')
    frozen=json.loads(frozen_report.read_text(encoding='utf-8'))
    if not frozen['ok'] or not frozen['frozen'] or frozen['checks']!=source['checks']:raise RuntimeError('Source/frozen lifecycle mismatch')
    if any(sha(SOURCE/relative)!=value for relative,value in inputs.items()):raise RuntimeError('Source changed during build')
    if (PROJECT/'실행파일/portable-config.json').read_bytes()!=(SOURCE/'assets/portable-config.json').read_bytes():raise RuntimeError('Portable configuration differs')
    from app_paths import portable_storage_root
    if portable_storage_root(executable=target,frozen=True)!=(PROJECT/'데이터/회사별업무').resolve():raise RuntimeError('Portable storage mismatch')
    record={'schema':'audit-suite-v19-build-1','version':'1.9.0','status':'candidate_verified','attempt':args.attempt,
        'exe':{'name':target.name,'bytes':target.stat().st_size,'sha256':sha(target)},'build_inputs':inputs,
        'headless':{'source':source,'frozen':frozen},'source_frozen_observations_identical':True,
        'source_frozen_checks':len(source['checks']),'unicode_roundtrip_verified':True,'portable_layout_verified':True,
        'icon_embedded_verified':True,'icon_group_sizes':groups,'current_actual_model_calls':0,
        'ime':{'current_actual_key_test':False,'baseline_version':'1.8.1',
               'baseline_evidence_sha256':sha(PROJECT/'검증/실제한글입력.json'),
               'scope':'v1.8.1 actual IME evidence reused with identical native adapter/display code and Python 3.14 family; v1.9 Unicode/save/Excel roundtrip tested again.'}}
    (QA/'candidate-build.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in record.items() if k not in ('build_inputs','headless')},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
