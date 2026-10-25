"""Existing engine regression plus current modular desktop lifecycle."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.release_v20.config import SOURCE,VERSION

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args();out=args.directory.resolve()
    if out==SOURCE or out in SOURCE.parents or out.is_relative_to(SOURCE):
        parser.error('Use a new validation folder outside source')
    if out.exists() and any(out.iterdir()):parser.error('Preserve prior evidence')
    out.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    with (out/'legacy.log').open('x',encoding='utf-8') as log:
        run=subprocess.run([sys.executable,'-B','-X','utf8',str(SOURCE/'tools/verify_headless_v19.py'),
                            '--directory',str(out/'legacy')],cwd=SOURCE,env=env,stdout=log,stderr=subprocess.STDOUT)
    if run.returncode:raise RuntimeError('Preserved regression failed: legacy.log')
    previous=json.loads((out/'legacy/report.json').read_text(encoding='utf-8'))
    from tools.verify_bento_v20 import self_test
    result=self_test(out/'desktop/report.json')
    current=json.loads((out/'desktop/report.json').read_text(encoding='utf-8'))
    summary={'ok':result==0 and previous['ok'] and current['ok'],'version':VERSION,
             'legacy':previous,'desktop':current,'current_actual_model_calls':0,
             'scope':'Synthetic engine regression and withdrawn-window UI checks; no actual IME key or model test.'}
    (out/'report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False));return 0 if summary['ok'] else 1

if __name__=='__main__':raise SystemExit(main())
