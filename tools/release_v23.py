"""Explicit public-file staging, build and package for the large-ledger update."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path,PurePosixPath
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT.parents[1];QA=PROJECT/'검증/v2.3.0'
EXE='통합 회계감사 v2.3.0.exe'
ADDITIONS={'input_limits.py','xlsx_reader.py','export_streaming.py','test_large_ledger.py','tools/verify_large_ledger.py','tools/release_v23.py','문서/v2.3_큰원장.md','ci/audit-suite-v23.yml'}
MUTABLE={'AGENTS.md','README.md','common.py','adapters.py','analytics_support.py','workspace.py','audit_archive.py','exporter.py','onboarding/erp/schema.py','onboarding/erp/input_io.py','desktop/entry_tests.py'}
def sha(value):return hashlib.sha256(value).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def public_files():
    baseline=PROJECT/'릴리스/v2.2.0/js-audit-suite-v2.2.0-source.zip'
    declared=next(line.split()[0] for line in (baseline.parent/'SHA256SUMS.txt').read_text(encoding='utf-8-sig').splitlines() if line.endswith(baseline.name))
    assert sha(baseline.read_bytes())==declared
    files={}
    with ZipFile(baseline) as archive:
        for name in archive.namelist():
            if name.endswith('/'):continue
            assert name.startswith('js-audit-suite/');relative=name[len('js-audit-suite/'):]
            parts=PurePosixPath(relative);assert not parts.is_absolute() and '..' not in parts.parts
            current=(ROOT/relative).read_bytes()
            if relative not in MUTABLE:assert current==archive.read(name),'Unexpected changed public file: '+relative
            files[relative]=current
    for name in ADDITIONS:files[name]=(ROOT/name).read_bytes()
    return files
def manifest(files):return {k:{'bytes':len(v),'sha256':sha(v)} for k,v in sorted(files.items())}
def run(args,log,cwd=ROOT):
    with Path(log).open('x',encoding='utf-8') as output:
        result=subprocess.run([str(v) for v in args],cwd=cwd,stdout=output,stderr=subprocess.STDOUT,
            env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('See '+str(log))
def build():
    assert sys.version_info[:2]==(3,14)
    base=QA/'build';assert not base.exists();base.mkdir();files=public_files();stage=base/'stage';stage.mkdir()
    for name,value in files.items():
        dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(value)
    (base/'manifest.json').write_text(json.dumps(manifest(files),ensure_ascii=False,indent=2),encoding='utf-8')
    run([sys.executable,'-B','-X','utf8','app.py','--self-test-v22','--report',QA/'source-self/report.json'],QA/'source-self.log')
    run([sys.executable,'-B','-X','utf8','-m','PyInstaller','--noconfirm','--clean','--distpath',base/'dist','--workpath',base/'work',stage/'AuditSuite.spec'],base/'build.log',stage)
    target=PROJECT/'실행파일'/EXE;assert not target.exists();shutil.copy2(base/'dist/AuditSuite.exe',target)
    config=target.parent/'portable-config.json'
    if not config.exists():config.write_bytes(files['assets/portable-config.json'])
    run([target,'--self-test-v22','--report',QA/'frozen-self/report.json'],QA/'frozen-self.log',target.parent)
    source=read(QA/'source-self/report.json');frozen=read(QA/'frozen-self/report.json')
    assert source['ok'] and frozen['ok'] and source['checks']==frozen['checks'] and frozen['version']=='2.3.0'
    assert manifest(public_files())==manifest(files)
    print(json.dumps({'exe':str(target),'bytes':target.stat().st_size,'sourceFrozenChecks':len(source['checks'])},ensure_ascii=False))
def package():
    files=public_files();assert manifest(files)==read(QA/'build/manifest.json')
    source=read(QA/'source-large/report.json');frozen=read(QA/'frozen-large/report.json')
    assert source['ok'] and frozen['ok'] and source['rows']==frozen['rows']==250000 and source['inputSha256']==frozen['inputSha256']
    summary={'version':'2.3.0','scope':'큰 원장 입력·계산·저장·복원·Excel 출력·페이지 조회',
             'sourceLarge':source,'frozenLarge':frozen,'sourceFrozenChecks':len(read(QA/'source-self/report.json')['checks']),
             'unitRegression':{'existingPassed':1096,'newLargeLedgerPassed':6},'aiModelRetested':False,
             'limits':{'ledgerRows':1048575,'sourceMB':256,'otherTablesRows':10000},'sourceFiles':manifest(files)}
    out=PROJECT/'릴리스/v2.3.0';out.mkdir(parents=True,exist_ok=False)
    source_zip=out/'js-audit-suite-v2.3.0-source.zip';windows_zip=out/'JS-Audit-Suite-v2.3.0-windows.zip'
    with ZipFile(source_zip,'x',ZIP_DEFLATED) as archive:
        for name,value in sorted(files.items()):archive.writestr('js-audit-suite/'+name,value)
    validation=json.dumps(summary,ensure_ascii=False,indent=2).encode();(out/'validation-report.json').write_bytes(validation)
    exe=PROJECT/'실행파일'/EXE
    with ZipFile(windows_zip,'x',ZIP_DEFLATED) as archive:
        prefix='JS-Audit-Suite-v2.3.0/'
        archive.write(exe,prefix+'실행파일/'+EXE);archive.writestr(prefix+'실행파일/portable-config.json',files['assets/portable-config.json'])
        archive.writestr(prefix+'README.md',files['README.md']);archive.writestr(prefix+'validation-report.json',validation)
        for name,value in sorted(files.items()):
            if name.startswith(('문서/','라이선스/')):archive.writestr(prefix+name,value)
            if name.startswith('sector_resources/'):archive.writestr(prefix+'데이터/업종별_합성원천자료/'+name[len('sector_resources/'):],value)
        archive.writestr(prefix+'데이터/회사별업무/','')
    names=[windows_zip.name,source_zip.name,'validation-report.json']
    (out/'SHA256SUMS.txt').write_text(''.join(sha((out/name).read_bytes())+'  '+name+'\n' for name in names),encoding='utf-8')
    checkout=QA/'github-release/checkout'
    for name,value in files.items():
        target=checkout/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(value)
    workflow=checkout/'.github/workflows/audit-suite-v23.yml';workflow.parent.mkdir(parents=True,exist_ok=True);workflow.write_bytes(files['ci/audit-suite-v23.yml'])
    print(json.dumps({'release':str(out),'sourceFiles':len(files),'assets':[p.name for p in out.iterdir()]},ensure_ascii=False))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['build','package']);args=parser.parse_args()
    build() if args.mode=='build' else package()
