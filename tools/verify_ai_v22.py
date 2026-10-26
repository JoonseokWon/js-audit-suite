"""Explicit actual-model CLI, never imported by automated test discovery."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ai_quality.actual import self_test


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--ai-runtime',type=Path,required=True)
    args=parser.parse_args()
    return self_test(args.report,args.ai_runtime)


if __name__=='__main__':raise SystemExit(main())
