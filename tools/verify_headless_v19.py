"""Preserved 332-fixture coverage plus the synthetic v1.9 lifecycle, without Tk."""
from pathlib import Path
import argparse,json,os,subprocess,sys,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args();out=args.directory.resolve()
    if out==ROOT or out in ROOT.parents or any(out.is_relative_to(ROOT/name) for name in ('samples','sector_resources','tools','engines','worker_library')):
        parser.error('Use a new validation directory')
    if out.exists() and any(out.iterdir()):parser.error('Preserve prior evidence; select a new directory')
    out.mkdir(parents=True,exist_ok=True)
    try:
        env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
        with (out/'legacy.log').open('w',encoding='utf-8') as stream:
            run=subprocess.run([sys.executable,'-B','-X','utf8',str(ROOT/'tools/verify_headless_v17.py'),
                                '--output-dir',str(out/'legacy')],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        assert run.returncode==0,'Existing headless regression failed; inspect legacy.log'
        previous=json.loads((out/'legacy/report.json').read_text(encoding='utf-8'))
        from verify_v19 import exercise_core
        workflow=exercise_core(out/'workflow',ROOT)
        assert 'tkinter' not in sys.modules and 'app' not in sys.modules
        result={'ok':True,'version':'1.9.0','legacy':previous,'workflow':workflow,'uses_tk':False,
                'current_actual_model_calls':0,'scope':'Synthetic mechanical controls and mocked human input only.'}
    except Exception as exc:result={'ok':False,'error':str(exc),'traceback':traceback.format_exc()}
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
