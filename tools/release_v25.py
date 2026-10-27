"""Explicit operations only; importing this file never builds or publishes."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=(
        'stage','verify-source','build','large-source','large-frozen','actual-source','actual-frozen','package',
        'github-stage','github-status','github-publish','github-verify'))
    mode=parser.parse_args().mode
    if mode in ('stage','verify-source','build'):
        from tools.release_v25 import build
        result=getattr(build,mode.replace('-','_'))()
    elif mode.startswith('actual-'):
        from tools.release_v25.actual import verify
        result=verify(mode=='actual-frozen')
    elif mode.startswith('large-'):
        from tools.release_v25.large import verify
        result=verify(mode=='large-frozen')
    elif mode=='package':
        from tools.release_v25.package import package
        result=package()
    else:
        from tools.release_v25.publish import dispatch
        result=dispatch(mode)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
