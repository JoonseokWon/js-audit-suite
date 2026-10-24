"""Fixed, synthetic metadata cases, with literal expectations, never oracle input."""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import json

from common import atomic
from . import SCHEMA, VERSION


def normal_tables(base):
    cfg = {'규칙버전': VERSION, '정책명': '합성 결산 검토정책 2026', '마감시각': '2027-01-10T18:00:00+09:00',
           '메타추출시각': '2027-01-20T12:00:00+09:00', '업무시간대': '+09:00', '업무시작': '09:00', '업무종료': '18:00',
           '수동집중최소전표수': 3, '수동집중최소금액': 100000, '수동집중비율': 70, '반복재분류최소횟수': 2, '선승인허용': '아니오'}
    metas = []
    for row in base['총계정원장']:
        metas.append({**{k: row[k] for k in ('회사코드', '전표ID', '행ID')},
                      '입력시각': '2027-01-05T10:00:00+09:00', '입력자': '합성입력자', '전표유형': '자동',
                      '승인상태': '승인', '승인자': '합성승인자', '승인시각': '2027-01-05T10:05:00+09:00',
                      '부서': '합성회계팀', '원천시스템': 'SYNTHETIC_ERP', '재분류그룹': '해당없음'})
    return {'FIA설정': [{'항목': k, '값': v} for k, v in cfg.items()], '전표메타': metas}


def write_samples(target):
    from tools.analytics_fixtures import load_base, write_input
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    base = load_base()
    normal = normal_tables(base)
    first_jid = base['총계정원장'][0]['전표ID']
    def journal(data, **values):
        for row in data['전표메타']:
            if row['전표ID'] == first_jid:
                row.update(values)
    def setting(data, key, value):
        next(r for r in data['FIA설정'] if r['항목'] == key)['값'] = value
    cases = []
    def add(case_id, change=None, blocking=False, review=False, codes=(), base_change=None):
        data = deepcopy(normal)
        current = deepcopy(base)
        if change:
            change(data)
        if base_change:
            base_change(current)
        file = case_id + '.xlsx'
        write_input(target / file, SCHEMA, data, current)
        cases.append({'id': case_id, 'file': file, 'blocking': blocking, 'review': review, 'required_codes': list(codes)})
    add('FIA_01_정상마감전후속입력')
    add('FIA_02_마감후과거기간전기', lambda d: journal(d, 입력시각='2027-01-11T10:00:00+09:00', 승인시각='2027-01-11T10:05:00+09:00'), review=True, codes=['FIA_POST_CLOSE'])
    add('FIA_03_자기승인', lambda d: journal(d, 승인자='합성입력자'), review=True, codes=['FIA_SELF_APPROVAL'])
    add('FIA_04_추출후미래입력', lambda d: journal(d, 입력시각='2027-01-21T10:00:00+09:00', 승인시각='2027-01-21T10:05:00+09:00'), review=True, codes=['FIA_TIMESTAMP_ORDER', 'FIA_POST_CLOSE'])
    add('FIA_05_업무시간밖', lambda d: journal(d, 입력시각='2027-01-05T23:00:00+09:00', 승인시각='2027-01-05T23:05:00+09:00'), review=True, codes=['FIA_OUTSIDE_HOURS'])
    add('FIA_06_수동전표집중', lambda d: [r.update(전표유형='수동') for r in d['전표메타']], review=True, codes=['FIA_MANUAL_CONCENTRATION'])
    add('FIA_07_정상유사마감전입력', lambda d: journal(d, 입력시각='2027-01-09T10:00:00+09:00', 승인시각='2027-01-09T10:05:00+09:00'))
    add('FIA_08_메타누락', lambda d: d['전표메타'].pop(0), blocking=True, codes=['FIA_INPUT'])
    add('FIA_09_메타중복', lambda d: d['전표메타'].append(deepcopy(d['전표메타'][0])), blocking=True, codes=['FIA_INPUT'])
    add('FIA_10_타회사', lambda d: d['전표메타'][0].update(회사코드='OTHER'), blocking=True, codes=['FIA_INPUT'])
    add('FIA_11_기간불일치', blocking=True, codes=['AN_SCOPE'], base_change=lambda b: next(r for r in b['설정'] if r['항목'] == '시작일').update(값='2025-01-01'))
    add('FIA_12_현재원장불일치', blocking=True, codes=['AN_LEDGER_DIFF'], base_change=lambda b: b['총계정원장'][0].update(적요='현재 업무와 다른 합성적요'))
    add('FIA_13_유형미확인', lambda d: journal(d, 전표유형='미확인'), review=True, codes=['FIA_UNCONFIRMED'])
    add('FIA_14_선승인금지시각역전', lambda d: journal(d, 승인시각='2027-01-04T10:05:00+09:00'), review=True, codes=['FIA_TIMESTAMP_ORDER'])
    def preapproval(data):
        journal(data, 승인시각='2027-01-04T10:05:00+09:00')
        setting(data, '선승인허용', '예')
    add('FIA_15_정상허용선승인', preapproval)
    add('FIA_16_승인필수시각누락', lambda d: journal(d, 승인시각=None), blocking=True, codes=['FIA_INPUT'])
    patterns = defaultdict(list)
    grouped = defaultdict(list)
    for row in base['총계정원장']:
        grouped[row['전표ID']].append(row)
    for jid, rows in grouped.items():
        signature = (tuple(sorted({r['계정코드'] for r in rows if r['차변']})), tuple(sorted({r['계정코드'] for r in rows if r['대변']})))
        patterns[signature].append(jid)
    recurring = next((jids[:2] for jids in patterns.values() if len(jids) >= 2), None)
    if recurring is None:
        raise ValueError('반복 재분류 대조에 필요한 같은 계정 방향의 정상전표가 없습니다.')
    def repeat(data):
        for row in data['전표메타']:
            if row['전표ID'] in recurring:
                row['재분류그룹'] = 'SYNTH_RECLASS'
    add('FIA_17_명시반복재분류', repeat, review=True, codes=['FIA_RECLASS_REPEAT'])
    add('FIA_18_수동승인대기', lambda d: journal(d, 전표유형='수동', 승인상태='대기', 승인자=None, 승인시각=None), review=True, codes=['FIA_APPROVAL_STATUS'])
    add('FIA_19_부서시스템미확인', lambda d: journal(d, 부서=None, 원천시스템=None), review=True, codes=['FIA_UNCONFIRMED'])
    add('FIA_20_시간대누락', lambda d: journal(d, 입력시각='2027-01-05T10:00:00'), blocking=True, codes=['FIA_INPUT'])
    add('FIA_21_승인미확인', lambda d: journal(d, 승인상태='미확인', 승인자=None, 승인시각=None), review=True, codes=['FIA_UNCONFIRMED'])
    add('FIA_22_같은전표메타충돌', lambda d: d['전표메타'][0].update(입력자='다른합성입력자'), blocking=True, codes=['FIA_INPUT'])
    report = {'normal': target / cases[0]['file'], 'cases': cases}
    atomic(target / 'cases.json', json.dumps({'schema_version': 'fia-cases-1', 'normal': cases[0]['file'], 'cases': cases,
                                             'scope': '독립 합성 메타 변형. 기대 결과는 검사기 입력으로 사용하지 않음.'}, ensure_ascii=False, indent=2).encode('utf-8'))
    return report
