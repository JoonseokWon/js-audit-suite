from pathlib import Path
import sys,json,shutil,importlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
all_cases=[]
for module,package in [('GLA','gla'),('FIA','fia'),('현금분석','cash_analytics')]:
    engine=importlib.import_module(package);target=ROOT/'samples/감사분석'/module
    generated=engine.write_samples(target)
    shutil.copy2(generated['normal'],ROOT/'samples/통합'/('통합_v1.5_'+module+'.xlsx'))
    for case in generated['cases']:all_cases.append({'module':module,'folder':module,**case})
out={'schema':'integrated-analytics-cases-1','cases':all_cases,'case_count':len(all_cases),'note':'모든 사례는 독립 합성 업무. current_ledger가 있으면 해당 7시트 파일을 먼저 실행. 기대값은 계산 입력에 주입하지 않음.'}
(ROOT/'samples/감사분석/cases.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'cases':len(all_cases),'groups':{m:sum(c['module']==m for c in all_cases) for m in ('GLA','FIA','현금분석')}},ensure_ascii=False))
