"""Fixed synthetic risk cases; expected outcomes never enter the analyzer XLSX."""
from copy import deepcopy
from pathlib import Path
import json
from common import atomic
from tools.analytics_fixtures import load_base,write_input
from . import DEFAULT_SETTINGS,EXTRA_SCHEMA


def write_samples(target):
    target=Path(target);target.mkdir(parents=True,exist_ok=True);cases=[]
    base=load_base()
    def rows(config):return [{'항목':k,'값':v} for k,v in config.items()]
    def one(rule):
        cfg=deepcopy(DEFAULT_SETTINGS)
        for key in ('주말검토','월말검토','고액검토','반복검토'):cfg[key]='사용' if key==rule else '미사용'
        return cfg
    def save(case_id,config=None,source=None,block=False,review=False,codes=(),mutate_rows=None,companion=False):
        config=deepcopy(DEFAULT_SETTINGS if config is None else config);source=deepcopy(base if source is None else source)
        settings=rows(config)
        if mutate_rows:mutate_rows(settings)
        path=write_input(target/(case_id+'.xlsx'),EXTRA_SCHEMA,{'GLA설정':settings},base=source)
        case={'id':case_id,'file':path.name,'blocking':block,'review':review,'required_codes':list(codes)}
        if companion:
            current=write_input(target/(case_id+'_현재원장.xlsx'),{}, {},base=source)
            case['current_ledger']=current.name
        cases.append(case)
        return path
    normal=save('GLA_01_정상전체규칙',review=True,codes=('GLA_MONTH_END','GLA_HIGH_AMOUNT'))
    config=one('고액검토');config['고액기준원']=5000001
    save('GLA_02_고액정상대조',config)
    config=one('고액검토');config['고액기준원']=5000000
    save('GLA_03_고액경계',config,review=True,codes=('GLA_HIGH_AMOUNT',))
    changed=deepcopy(base)
    for r in changed['총계정원장']:
        if r['전표ID']=='J-I':r['전기일']='2026-12-05'
    save('GLA_04_주말전표',one('주말검토'),changed,review=True,codes=('GLA_WEEKEND',),companion=True)
    save('GLA_05_월말전표',one('월말검토'),review=True,codes=('GLA_MONTH_END',))
    repeated=deepcopy(base)
    copied=[deepcopy(r) for r in repeated['총계정원장'] if r['전표ID']=='J-I']
    for r in copied:
        r['전표ID']='J-I-REPEAT';r['_row']=len(repeated['총계정원장'])+2;repeated['총계정원장'].append(r)
        code=r['계정코드'];tb=next(v for v in repeated['시산표'] if v['계정코드']==code)
        control=next(v for v in repeated['독립통제'] if v['계정코드']==code)
        tb['당기차변']+=r['차변'];tb['당기대변']+=r['대변'];tb['기말잔액']+=r['차변']-r['대변']
        control['원장행수']+=1;control['차변합계']+=r['차변'];control['대변합계']+=r['대변'];control['기말잔액']+=r['차변']-r['대변']
    save('GLA_06_동일구성반복',one('반복검토'),repeated,review=True,codes=('GLA_REPEAT',),companion=True)
    save('GLA_07_동액다른계정정상',one('반복검토'))
    save('GLA_08_필수설정누락',one('고액검토'),block=True,codes=('GLA_INPUT',),mutate_rows=lambda r:r.pop())
    save('GLA_09_중복설정',one('고액검토'),block=True,codes=('GLA_INPUT',),mutate_rows=lambda r:r.append(deepcopy(r[0])))
    wrong=deepcopy(base)
    for r in wrong['설정']:
        if r['항목']=='회사코드':r['값']='OTHER'
    for rows_ in wrong.values():
        for r in rows_:
            if '회사코드' in r:r['회사코드']='OTHER'
    save('GLA_10_회사오류',source=wrong,block=True,codes=('AN_SCOPE','AN_LEDGER_DIFF'))
    wrong=deepcopy(base)
    for r in wrong['설정']:
        if r['항목']=='시작일':r['값']='2026-02-01'
    save('GLA_11_기간오류',source=wrong,block=True,codes=('AN_SCOPE',))
    stale=deepcopy(base)
    for r in stale['총계정원장']:
        if r['전표ID']=='J-I':r['전기일']='2026-12-30'
    save('GLA_12_현재원장불일치',source=stale,block=True,codes=('AN_LEDGER_DIFF',))
    manifest={'schema_version':'gla-cases-1','synthetic':True,'normal':normal.name,'cases':cases,
        'scope':'동일 생성기의 합성 원장·독립통제. 외부 독립 증거 아님. current_ledger가 있으면 그 7시트 원장을 먼저 실행.',
        'fixed_normal_oracle':{'원장행수':82,'전표수':34,'월수':5,'계정수':59,'작성자수':1,'복합대응미확인전표수':11,'고액후보수':3,'월말후보수':21,'전체후보수':24}}
    atomic(target/'cases.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8'))
    return {'normal':normal,'cases':cases}
