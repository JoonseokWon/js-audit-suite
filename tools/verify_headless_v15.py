from pathlib import Path
import sys,json,argparse,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
import runtime
runtime.configure()
from verify_headless_v14 import run as legacy_run
from analytics_validation import exercise
def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',required=True);a=p.parse_args();out=Path(a.output_dir).resolve()
    if out==ROOT or out in ROOT.parents or any(out.is_relative_to(ROOT/n) for n in ('samples','gla','fia','cash_analytics','tools','engines','worker_library')):p.error('Use a new validation output directory')
    if out.exists() and any(out.iterdir()):p.error('Keep earlier evidence; use new/empty directory')
    out.mkdir(parents=True,exist_ok=True)
    try:
        assert legacy_run(out/'legacy')==0
        result=exercise(ROOT,out/'analytics');old=json.loads((out/'legacy/report.json').read_text(encoding='utf-8'))
        result.update(legacy_cases=270,total_cases=270+result['case_count'],legacy_assertions=old['assertions'],assertions=old['assertions']+len(result['checks']))
        assert 'tkinter' not in sys.modules and 'app' not in sys.modules
    except Exception as e:result={'ok':False,'error':str(e),'traceback':traceback.format_exc()}
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('checks','observations','traceback')},ensure_ascii=False))
    return 0 if result['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
