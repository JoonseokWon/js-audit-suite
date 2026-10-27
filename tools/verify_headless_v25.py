"""CI checks use synthetic responses only; actual inference is a separate gate."""
import argparse,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import VERSION


def legacy_diagnostics(out):
    """Expose private job artifacts in the CI log; never masks a failed stage."""
    for path in sorted(out.rglob('*')):
        if not path.is_file() or path.name not in ('legacy.log', 'report.json'):
            continue
        if path.name == 'legacy.log':
            tail=path.read_text(encoding='utf-8',errors='replace')[-4000:]
            print(json.dumps({'legacy_artifact':str(path.relative_to(out)), 'tail':tail},ensure_ascii=False))
        else:
            try:
                report=json.loads(path.read_text(encoding='utf-8'))
                if report.get('ok') is False:
                    print(json.dumps({'legacy_artifact':str(path.relative_to(out)),
                        'error':report.get('error'), 'traceback':str(report.get('traceback',''))[-4000:]},ensure_ascii=False))
            except (ValueError,OSError) as exc:
                print(json.dumps({'legacy_artifact':str(path.relative_to(out)), 'read_error':str(exc)},ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True,type=Path)
    out=parser.parse_args().directory.resolve();root=Path(__file__).resolve().parents[1]
    if out.is_relative_to(root) or out==root or out.exists() and any(out.iterdir()):
        parser.error('새 소스 외부 검증 폴더를 사용하세요.')
    out.mkdir(parents=True,exist_ok=True)
    with (out/'legacy.log').open('x',encoding='utf-8') as log:
        prior=subprocess.run([sys.executable,'-B','-X','utf8',root/'tools/verify_headless_v22.py',
            '--directory',str(out/'legacy')],cwd=root,stdout=log,stderr=subprocess.STDOUT,
            env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if prior.returncode:
        legacy_diagnostics(out)
        raise RuntimeError('기존 통합 검사 실패: legacy.log')
    from tools.verify_flow_v25 import self_test
    code=self_test(out/'v25/report.json')
    report={'ok':code==0,'version':VERSION,'actual_model_calls':0,
        'legacy':json.loads((out/'legacy/report.json').read_text(encoding='utf-8')),
        'v25':json.loads((out/'v25/report.json').read_text(encoding='utf-8'))}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return code

if __name__=='__main__':raise SystemExit(main())
