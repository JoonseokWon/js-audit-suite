"""Explicit v2 release CLI. Import never reads credentials or contacts GitHub."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.release_v22.github_api import GitHub
from tools.release_v22 import publish as operations
from tools.release_v22.ci import status
from tools.release_v22.state import load

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',required=True,choices=('inspect','stage','status','publish','verify'))
    args=parser.parse_args();api=GitHub()
    if args.mode=='inspect':result=api.inspect()
    elif args.mode=='status':result=status(api,load())
    else:result=getattr(operations,args.mode)(api)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
