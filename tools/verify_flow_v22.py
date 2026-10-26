"""Source/frozen deterministic walkthrough and GUI checks; zero model calls."""
from pathlib import Path
import json
import sys
import traceback


def self_test(report_path):
    from tools.verify_onboarding_v21 import self_test as previous
    path=Path(report_path).resolve()
    code=previous(path)
    if code:return code
    record=json.loads(path.read_text(encoding='utf-8'))
    try:
        from common import VERSION
        from demo_case.verification import verify
        from demo_case import create_demo
        from desktop.demo.verification import verify as verify_gui
        flow=verify(path.parent/'js-electronics-flow')
        if not flow['ok'] or flow['actual_model_calls']!=0:
            raise AssertionError('Deterministic case must not call a model')
        ws,_=create_demo(path.parent/'js-electronics-gui')
        gui=verify_gui(ws)
        if not gui['ok']:raise AssertionError('Read-only desktop verification failed')
        for checks in (flow['checks'],gui['checks']):
            if not checks or set(checks)&set(record['checks']):
                raise AssertionError('Missing or duplicate deterministic check names')
            record['checks'].extend(checks)
        record.update(ok=True,version=VERSION,frozen=bool(getattr(sys,'frozen',False)),
            demo_case_verified=True,gui_demo_verified=True,current_actual_model_calls=0,
            demo_flow=flow,demo_gui=gui,
            scope='Existing regression plus deterministic JS전자 case and read-only GUI. '
                  'Actual local inference is a separate required source/frozen release check.')
    except Exception as exc:
        record.update(ok=False,error=str(exc),traceback=traceback.format_exc())
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ok':record['ok'],'version':record.get('version'),
        'checks':len(record['checks']),'error':record.get('error')},ensure_ascii=False))
    return 0 if record['ok'] else 1
