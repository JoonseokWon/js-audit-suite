"""Existing 332 fixtures plus isolated five-company provider validation, without Tk."""
from pathlib import Path
import sys,json,argparse,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
import runtime
runtime.configure()
from verify_headless_v14 import run as legacy_run
from analytics_validation import exercise as analytics
from verify_sectors_headless import exercise as sectors

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args();out=args.output_dir.resolve()
    if out==ROOT or out in ROOT.parents or any(out.is_relative_to(ROOT/n) for n in ('samples','sector_resources','tools','engines','worker_library')):parser.error('Use a new validation output directory')
    if out.exists() and any(out.iterdir()):parser.error('Preserve earlier evidence; use a new directory')
    out.mkdir(parents=True,exist_ok=True)
    try:
        assert legacy_run(out/'legacy')==0
        old=json.loads((out/'legacy/report.json').read_text(encoding='utf-8'));a=analytics(ROOT,out/'analytics')
        s=sectors(ROOT/'sector_resources',out/'sectors',check_originals=False)
        assert 'tkinter' not in sys.modules and 'app' not in sys.modules
        result={'ok':True,'fixture_cases':270+a['case_count'],'legacy_assertions':old['assertions']+len(a['checks']),
                'sector_assertions':len(s['checks']),'normal_company_count':s['normal_company_count'],
                'normal_module_executions':s['normal_module_executions'],'current_ledger_links':s['current_ledger_links'],
                'cross_company_negative_checks':s['cross_company_negative_checks'],'uses_tk':False,
                'sector_report':'sectors/headless_sectors.json'}
        assert result['fixture_cases']==332 and result['legacy_assertions']==1949
    except Exception as exc:result={'ok':False,'error':str(exc),'traceback':traceback.format_exc()}
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return 0 if result['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
