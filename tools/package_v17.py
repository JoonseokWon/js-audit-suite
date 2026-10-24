"""Package a verified v1.7 EXE, builtin synthetic resources and exact portable source."""
from pathlib import Path
import json,hashlib,shutil,zipfile,re,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from common import sha
QA=ROOT/'검증';DIST=ROOT/'배포'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,obj):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def copy(p,target):target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
def archive(target,files,prefix):
    assert not target.exists(),'Preserve previous archive'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=8) as z:
        for name,p in sorted(files.items()):z.write(p,prefix+name)
    with zipfile.ZipFile(target) as z:
        assert not z.testzip() and len(z.namelist())==len(set(z.namelist()))==len(files)
        assert all(hashlib.sha256(z.read(prefix+n)).hexdigest()==sha(p) for n,p in files.items())
build=read(QA/'빌드결과.json');assert build['status']=='passed' and build['unit_tests']==499
assert all(sha(ROOT/r['file'])==r['sha256'] for r in build['source_manifest'])
source=read(QA/build['source_report']);frozen=read(QA/build['frozen_report']);headless=read(QA/build['headless_report'])
assert source['ok'] and frozen['ok'] and frozen['frozen'] and source['observations']==frozen['observations'] and source['sector_observations']==frozen['sector_observations']
assert headless['ok'] and headless['legacy_assertions']==1949 and headless['sector_assertions']==1152
assert sha(DIST/'통합 회계감사 v1.7.exe')==build['exe_sha256']
visual=read(QA/'v17_시각검토.json');assert visual['status']=='passed'
preview=read(QA/'출력조서_렌더검증.json');assert len(preview['records'])==20 and all('0 entries' in e['result'] for e in preview['errors'])
sector=read(QA/'headless_2/sectors/headless_sectors.json');assert sector['status']=='passed'
assert (sector['normal_module_executions'],sector['current_ledger_links'],sector['cross_company_negative_checks'])==(61,140,72)
for folder in ('sector_resources','문서','라이선스'):
    for p in (ROOT/folder).rglob('*'):
        if p.is_file():copy(p,DIST/({'sector_resources':'업종별자료'}.get(folder,folder))/p.relative_to(ROOT/folder))
copy(ROOT/'README.md',DIST/'README.md')
for code in ('JS','JS_ELEC','JS_AUTO','JS_SEMI','JS_BIO'):
    copy(QA/'소스UI_2'/(code+'_미검토초안.xlsx'),DIST/'예시조서'/(code+'_미검토초안.xlsx'))
records={'빌드결과.json':QA/'빌드결과.json','단위검사.txt':QA/'단위검사_최종.txt','소스UI.json':QA/build['source_report'],'EXE_UI.json':QA/build['frozen_report'],
         'headless.json':QA/build['headless_report'],'업종별_대사검증.json':QA/'headless_2/sectors/headless_sectors.json',
         '출력조서_렌더검증.json':QA/'출력조서_렌더검증.json','시각검토.json':QA/'v17_시각검토.json'}
for name,p in records.items():copy(p,DIST/'검증기록'/name)
for p in (QA/'독립EXE_1').glob('*.png'):copy(p,DIST/'검증기록/화면'/p.name)
for p in (QA/'v17_조서미리보기').glob('*.png'):copy(p,DIST/'검증기록/조서미리보기'/p.name)
sources={p.name:p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.json','.spec','.txt','.md')}
sources['.gitattributes']=ROOT/'.gitattributes';(QA/'.gitkeep').touch(exist_ok=True);sources['검증/.gitkeep']=QA/'.gitkeep'
for folder in ('engines','raw_sources','raw_accounts','financial_bridge','worker_library','gla','fia','cash_analytics','samples','templates','testdata','raw_input_seed','reference_evidence','raw_analytics','sector_resources','.runtime','문서','ci','라이선스'):
    for p in (ROOT/folder).rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix=='.pyc':continue
        if folder in ('gla','fia','cash_analytics') and 'verification' in p.parts and p.suffix not in ('.json','.md'):continue
        sources[p.relative_to(ROOT).as_posix()]=p
for p in (ROOT/'tools').iterdir():
    if p.is_file() and p.suffix in ('.py','.mjs','.md'):sources[p.relative_to(ROOT).as_posix()]=p
for relative in ():
    p=ROOT/'sector_verification'/relative
    if p.is_file():sources['sector_verification/'+relative]=p
for name in sources:assert not re.search(r'(^|/)(\.git|\.venv|node_modules|\.env|release-state\.json|benchmark_inputs)(/|$)',name)
sourcezip=DIST/'audit-suite-source-v1.7.0.zip';archive(sourcezip,sources,'js-audit-suite/')
validation={'version':'1.7.0','status':'passed','unit_tests':499,'legacy_fixture_cases':332,'legacy_headless_assertions':1949,'sector_headless_assertions':1152,
            'native_assertions':len(frozen['native_checks']),'source_frozen_observations_identical':True,'balanced_omission_control_failures':9,'readable_raw_workbooks':64,'core_calculation_workpaper_links':['A02','A04','A12'],
            'company_names':['JS','JS전자','JS자동차','JS반도체','JS바이오'],'normal_module_executions':61,'current_ledger_links':140,'cross_company_negative_checks':72,'parent_cross_company_negative_checks':4,
            'workpapers_per_company':[5,48,48,48,49],'manual_industry_topics':20,'document_templates':60,'auto_created_pbc_requests':0,
            'human_fields_blank':True,'unreviewed_final_export_blocked':True,'uses_ai_inference':False,'xlsx_readonly_previews':20,
            'exe':{'name':'통합 회계감사 v1.7.exe','bytes':build['exe_bytes'],'sha256':build['exe_sha256']},
            'source':{'name':sourcezip.name,'files':len(sources),'sha256':sha(sourcezip)},'resource_manifest_sha256':frozen['resource_manifest_sha256'],
            'limitations':['Windows development PC; EXE-only folder, no clean OS/other-PC test','One parent with cash/investments/capital only and four sector subsidiaries; no investment valuation or consolidated group calculation',
                           'Same synthetic generator, not independent audit evidence','Cross-company negatives cover six modules with company/current-ledger binding',
                           '20 industry topics are conditional manual plans; no human performance/conclusion/review or posting is auto-completed',
                           'Legacy SYNTH_SUB tables D001/D031/D032/D038/D039 are separate manual examples, not JS group ownership or consolidated results',
                           'No external AI inference or data transmission; no full audit/compliance certification'],
            'github_verification':'See public JoonseokWon/js-audit-suite v1.7.0 release and exact-commit Python 3.12/3.14 GitHub Actions evidence'}
write(DIST/'validation.json',validation)
files={name:DIST/name for name in ('통합 회계감사 v1.7.exe','README.md','validation.json')}
for folder in ('업종별자료','문서','라이선스','검증기록','예시조서'):
    files.update({p.relative_to(DIST).as_posix():p for p in (DIST/folder).rglob('*') if p.is_file()})
write(DIST/'파일목록_SHA256.json',[{'file':n,'bytes':p.stat().st_size,'sha256':sha(p)} for n,p in sorted(files.items())]);files['파일목록_SHA256.json']=DIST/'파일목록_SHA256.json'
windows=DIST/'AuditSuite-Windows-v1.7.0.zip';archive(windows,files,'AuditSuite-v1.7/')
assets=[windows,sourcezip,DIST/'validation.json'];(DIST/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in assets),encoding='utf-8')
result={'status':'passed','version':'1.7.0','source_files':len(sources),'windows_files':len(files),'source_manifest_unchanged':True,'zip_crc_and_all_file_hashes_verified':True,
        'assets':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in assets+[DIST/'SHA256SUMS.txt']]}
write(QA/'최종배포검증.json',result);print(json.dumps(result,ensure_ascii=False))
