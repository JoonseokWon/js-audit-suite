"""Private one-call real verification. Run explicitly under PM coordination."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ai_quality.actual_v25 import self_test


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True,type=Path)
    p.add_argument('--ai-runtime',required=True,type=Path)
    p.add_argument('--cpu-diagnostic',action='store_true')
    p.add_argument('--integrated',action='store_true');args=p.parse_args()
    raise SystemExit(self_test(args.report,args.ai_runtime,args.cpu_diagnostic,args.integrated))
