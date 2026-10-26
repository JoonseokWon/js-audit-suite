"""Current engines, desktop and all sixteen onboarding improvement topics."""
from pathlib import Path
import argparse,json,os,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import VERSION


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,required=True)
    out=parser.parse_args().directory.resolve();source=Path(__file__).resolve().parents[1]
    if out==source or out in source.parents or out.is_relative_to(source) or out.exists() and any(out.iterdir()):
        parser.error('Use a new validation folder outside source')
    out.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    with (out/'legacy.log').open('x',encoding='utf-8') as log:
        previous=subprocess.run([sys.executable,'-B','-X','utf8',str(source/'tools/verify_headless_v19.py'),
            '--directory',str(out/'legacy')],cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT)
    if previous.returncode:raise RuntimeError('Existing regression failed: legacy.log')
    from tools.verify_flow_v22 import self_test
    code=self_test(out/'desktop/report.json')
    report={'ok':code==0,'version':VERSION,'desktop':json.loads((out/'desktop/report.json').read_text(encoding='utf-8')),
            'legacy':json.loads((out/'legacy/report.json').read_text(encoding='utf-8')),'current_actual_model_calls':0}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ok':report['ok'],'version':VERSION}));return code


if __name__=='__main__':raise SystemExit(main())
