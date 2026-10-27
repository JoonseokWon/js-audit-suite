"""Additional v2.5 deterministic integration check; never substitutes actual inference."""
from pathlib import Path
import json
import sys
import traceback


def self_test(report_path):
    from common import VERSION, atomic
    from v25_demo.verification import run_demo_verification
    path = Path(report_path).resolve()
    if path.exists(): raise ValueError('이전 검증 보고서를 보존하고 새 경로를 사용하세요.')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = run_demo_verification(path.parent/'v25-모의통합검증')
        result.update(version=VERSION, frozen=bool(getattr(sys, 'frozen', False)))
    except Exception as exc:
        result = {'ok': False, 'version': VERSION, 'frozen': bool(getattr(sys, 'frozen', False)),
                  'error': str(exc), 'traceback': traceback.format_exc(), 'actual_model_calls': 0,
                  'actual_local_inference': False, 'actual_human_approvals': 0,
                  'scope': 'Deterministic-only attempt; no actual model inference or actual human audit approval.'}
    atomic(path, json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'))
    print(json.dumps({'ok': result['ok'], 'checks': len(result.get('checks', [])), 'actual_model_calls': 0,
                      'error': result.get('error')}, ensure_ascii=False))
    return 0 if result['ok'] else 1

