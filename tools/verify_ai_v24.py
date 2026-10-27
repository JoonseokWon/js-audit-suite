"""Explicit private v2.4 one-call verification; PM controls actual execution."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ai_quality.actual_v24 import self_test


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path)
    p.add_argument('--ai-runtime',required=True,type=Path);args=p.parse_args()
    raise SystemExit(self_test(args.report,args.ai_runtime))
