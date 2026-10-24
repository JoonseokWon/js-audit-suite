"""Tie structured statements to this engagement's controlled, unadjusted GL/TB.

The preserved v1.1 graph engine does the arithmetic. This adapter recomputes the
current ledger controls and rejects unavailable, blocked or stale lead results.
Financial.json metadata never substitutes for the actual ledger input tables.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json

from common import AuditError, atomic, cancelled, day, digest, dumps, issue, num, plain, result, text
from .vendor import financial as engine

MODULE = '재무제표·주석'
CORE_CONTEXT = ('회사코드', '시작일', '기준일', '통화')
LIMITS = [
    '구조화 financial.json의 확정 금액·합계식·매핑만 검사. PDF/OCR/XBRL 추출 없음.',
    '현재 업무에서 검증한 실제 입력 원장/TB와 리드의 조정전 기말잔액을 사용. 승인조정은 반영하지 않음.',
    '원장양식에 연결구분 필드가 없으므로 별도 업무만 지원. 연결구분이 ERP에서 독립 확인되었다는 뜻이 아님.',
    '필수주석은 명시한 선택 범위. 모든 회계기준 공시의 완전성·적정성을 자동 결론내리지 않음.',
    '정상 더미의 원장과 재무제표는 같은 합성 시나리오에서 생성. 서로 독립된 외부 감사증거가 아님.',
    '표시부호는 매핑의 +1/-1을 보존하며 abs로 맞추지 않음. 허용오차 안의 비영 차이도 미해결 검토사항.',
]


class BridgeError(AuditError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _context(value):
    if not isinstance(value, dict):
        raise BridgeError('FS_CONTEXT', '업무 문맥이 필요합니다.')
    c = {k: value.get(k) for k in ('회사코드', '시작일', '기준일')}
    for k, v in c.items():
        text(v, k)
    c['통화'] = value.get('통화', 'KRW')
    c['연결구분'] = value.get('연결구분', '별도')
    if c['통화'] != 'KRW' or c['연결구분'] != '별도':
        raise BridgeError('FS_CONTEXT', '현재 통합 원장 양식은 KRW 별도 업무만 지원합니다.')
    if day(c['시작일']) > day(c['기준일']):
        raise BridgeError('FS_CONTEXT', '업무 기간 순서 오류')
    return c


def _ledger(ledger_result, context, event=None):
    import ledger
    cancelled(event)
    if not isinstance(ledger_result, dict) or ledger_result.get('module') != '원장·리드':
        raise BridgeError('FS_LEDGER_UNAVAILABLE', '현재 업무의 원장·리드 검사를 먼저 실행하세요.')
    if type(ledger_result.get('blocking')) is not int or ledger_result['blocking'] != 0:
        raise BridgeError('FS_LEDGER_BLOCKED', '원장 차단사항을 해결한 뒤 재무제표를 대사하세요.')
    issues = ledger_result.get('issues')
    if not isinstance(issues, list) or any(not isinstance(x, dict) or x.get('severity') == '차단' for x in issues):
        raise BridgeError('FS_LEDGER_BLOCKED', '원장 결과의 차단 상태를 확인할 수 없습니다.')
    tables = ledger_result.get('tables')
    if not isinstance(tables, dict):
        raise BridgeError('FS_LEDGER_INPUT', '원장 결과에 실제 원장 입력표가 없습니다.')
    inputs = {}
    for role in ledger.SCHEMA:
        rows = tables.get('입력_' + role)
        if not isinstance(rows, list) or len(rows) > 10000 or any(not isinstance(r, dict) for r in rows):
            raise BridgeError('FS_LEDGER_INPUT', '실제 원장 입력표 누락·형식 오류: ' + role)
        for r in rows:
            if not set(ledger.SCHEMA[role]) <= set(r) or type(r.get('_row')) is not int or r['_row'] < 2:
                raise BridgeError('FS_LEDGER_INPUT', '원장 필수 열/원본 행 위치 누락: ' + role)
        inputs[role] = deepcopy(rows)
    try:
        cfg = ledger.config(inputs)
        computed = ledger.analyze(inputs, event)
    except (AuditError, KeyError, TypeError, ValueError) as exc:
        cancelled(event)
        raise BridgeError('FS_LEDGER_INPUT', '실제 원장 통제 재계산 불가: ' + str(exc)) from exc
    if computed['blocking']:
        codes = ', '.join(sorted({x['code'] for x in computed['issues'] if x['severity'] == '차단'}))
        raise BridgeError('FS_LEDGER_BLOCKED', '실제 원장 통제 재계산이 차단되었습니다: ' + codes)
    if any(cfg[k] != context[k] for k in CORE_CONTEXT):
        raise BridgeError('FS_LEDGER_CONTEXT', '실제 원장 입력의 회사·기간·통화가 현재 업무와 다릅니다.')
    declared = ledger_result.get('context')
    if not isinstance(declared, dict) or any(declared.get(k) != context[k] for k in ('회사코드', '시작일', '기준일')):
        raise BridgeError('FS_LEDGER_CONTEXT', '원장 결과가 현재 업무의 회사·기간과 다릅니다.')
    for k in ('통화', '연결구분'):
        if k in declared and declared[k] != context[k]:
            raise BridgeError('FS_LEDGER_CONTEXT', '원장 결과의 통화·연결구분이 현재 업무와 다릅니다.')
    for table in ('리드스케줄', '리드집계', '원장통제'):
        if digest(tables.get(table)) != digest(computed['tables'][table]):
            raise BridgeError('FS_LEDGER_STALE', '보관된 원장 리드/통제가 실제 입력 재계산과 다릅니다: ' + table)
    if len(inputs['시산표']) > 5000:
        raise BridgeError('FS_LEDGER_INPUT', '재무제표 연결은 TB 5,000계정 이내입니다.')
    return inputs, computed


def _duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise AuditError('JSON 중복 키: ' + k)
        out[k] = v
    return out


def _read(path):
    p = Path(path)
    if p.suffix.lower() != '.json':
        raise AuditError('확정 금액을 담은 financial.json 파일을 선택하세요.')
    if p.stat().st_size > 2 * 1024 * 1024:
        raise AuditError('재무제표 JSON은 2MB 이하만 지원합니다.')
    data = p.read_bytes()
    try:
        source = json.loads(data.decode('utf-8-sig'), object_pairs_hook=_duplicates,
                            parse_constant=lambda _: (_ for _ in ()).throw(AuditError('NaN/Infinity 미지원')))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise AuditError('올바른 UTF-8 JSON이 필요합니다.') from exc
    def depth(value, n=0):
        if n > 80:
            raise AuditError('JSON 중첩 한도 초과')
        if isinstance(value, dict):
            for x in value.values(): depth(x, n + 1)
        elif isinstance(value, list):
            for x in value: depth(x, n + 1)
    depth(source)
    return source, {'filename': p.name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def analyze(path, context, ledger_result=None, event=None):
    """Return a review draft; malformed data blocks every financial comparison."""
    cancelled(event)
    tables = {'재무제표대사': [], 'TB본문매핑': [], '원장리드연결': [], '원천위치': []}
    issues = []
    detail = {'잔액기준': '조정전기말잔액', '범위': '재무상태표·손익계산서·선택한 필수 주석',
              '제한': LIMITS, '검토상태': '미검토 초안', '수행확정': False, '검토확정': False,
              '조정승인': False, 'posting_allowed': False, '조정전비교': True}
    metrics = {'대사항목수': 0, '차이항목수': 0, '매핑계정수': 0, '필수주석수': 0}
    source_meta = None
    try:
        c = _context(context)
        inputs, computed = _ledger(ledger_result, c, event)
        detail['원장입력SHA256'] = digest(inputs)
        detail['원장리드SHA256'] = digest(computed['tables']['리드스케줄'])
        detail['원장원천'] = deepcopy(ledger_result.get('source', {}))
        detail['승인조정계정수'] = sum(num(x['승인조정']) != 0 for x in computed['tables']['리드스케줄'])
        if detail['승인조정계정수']:
            issue(issues, 'FS_PRE_ADJUSTMENT', '승인조정이 있으나 이 비교는 조정전 TB 기준입니다. 조정후 재무제표 결론은 미수행.', 'ledger:리드스케줄', False)
        source, source_meta = _read(path)
        detail['재무제표원천'] = source_meta
        if not isinstance(source, dict) or not isinstance(source.get('설정'), dict):
            raise AuditError('재무제표 설정 누락')
        if source['설정'].get('연결구분') != c['연결구분']:
            raise AuditError('본문 연결구분과 현재 별도 업무 문맥 불일치')
        actual = engine.analyze(inputs, source)
        cancelled(event)
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != source_meta['sha256']:
            raise AuditError('검사 중 재무제표 입력 파일이 변경되었습니다.')
        for x in actual['checks']:
            tables['재무제표대사'].append({'검사': x['category'], '코드': x['code'], '항목ID': x['item'],
                '항목': x['item_label'], '기대금액': x['expected'], '보고금액': x['actual'], '차이': x['difference'],
                '허용오차': x['tolerance'], '상태': x['status'], '산식': x['formula'],
                '원본행': ' | '.join(x['source_origins']), '원천위치': x['source_origins'], '검토상태': '미검토'})
        leads = {r['계정코드']: (i, r) for i, r in enumerate(computed['tables']['리드스케줄'])}
        for x in actual['mapping']:
            i, lead = leads[x['account']]
            refs = x['source_origins'] + [f'ledger:리드스케줄:{i + 1}', lead['원본행']]
            tables['TB본문매핑'].append({'계정코드': x['account'], '계정명': lead['계정명'],
                '리드코드': lead['리드코드'], '리드명': lead['리드명'], '표시구분': lead['표시구분'],
                '본문항목ID': x['body_item'], '본문항목': x['body_name'], '표시부호': x['factor'],
                '조정전': x['tb_signed'], '반영금액': x['contribution'], '비교기준': '조정전기말잔액',
                '원본행': ' | '.join(refs), '원천위치': refs, '검토상태': '미검토'})
            tables['원장리드연결'].append({'계정코드': lead['계정코드'], '계정명': lead['계정명'],
                '리드코드': lead['리드코드'], '본문항목ID': x['body_item'], '원장조정전': lead['조정전'],
                '승인조정': lead['승인조정'], '원장조정후': lead['조정후'], '사용잔액': lead['조정전'],
                '본문반영금액': x['contribution'], '표시부호': x['factor'], '차이': lead['조정전'] - x['tb_signed'],
                '상태': '조정전 연결', '원본행': lead['원본행'], '검토상태': '미검토'})
        for section in engine.HEADERS:
            tables['입력_' + section] = deepcopy(source[section])
        for section in ('설정', 'TB문맥'):
            tables['입력_' + section] = [{'항목': k, '값': v} for k, v in source[section].items()]
        for section in engine.HEADERS:
            for i, row in enumerate(source[section]):
                tables['원천위치'].append({'원천파일': source_meta['filename'], 'SHA256': source_meta['sha256'],
                    '구분': section, 'JSON위치': engine.reference(section, i), '문서ID': row.get('문서ID', ''),
                    '페이지': row.get('페이지', ''), '표시위치': row.get('위치', ''), '검토상태': '미검토'})
        issues.extend(actual['issues'])
        metrics.update(대사항목수=len(actual['checks']), 차이항목수=sum(x['difference'] != 0 for x in actual['checks']),
                       매핑계정수=actual['coverage']['mapped_accounts'], 필수주석수=actual['coverage']['required_note_ties'])
        detail['engine_version'] = actual['version']
        detail['financial_context'] = actual['context']
        detail['coverage'] = actual['coverage']
    except (AuditError, OSError, KeyError, TypeError, RecursionError) as exc:
        cancelled(event)
        issue(issues, getattr(exc, 'code', 'FS_INPUT'), str(exc), 'financial:/')
        tables = {'재무제표대사': [], 'TB본문매핑': [], '원장리드연결': [], '원천위치': []}
        metrics = {'대사항목수': 0, '차이항목수': 0, '매핑계정수': 0, '필수주석수': 0}
    cancelled(event)
    detail['대사상태'] = '차단' if any(x['severity'] == '차단' for x in issues) else '차이검토' if issues else '일치·미검토'
    out = result(MODULE, context, tables, issues, metrics, detail)
    if source_meta is not None: out['source'] = source_meta
    return out


def _sample_source(ledger_result):
    """Explicit sample-only chart; no heuristic classification of user accounts."""
    raw_c = ledger_result.get('context', {}) if isinstance(ledger_result, dict) else {}
    c = _context(raw_c)
    inputs, computed = _ledger(ledger_result, c)
    leaves = computed['tables']['리드스케줄']
    roles = {
        'A_CURRENT': {'1000','1100','1200','1300','1390','1400','1450','1460','1490'},
        'A_NONCURRENT': {'1350','1359','1500','1590','1600','1700','1710','1720','1800','1890','1900','1950'},
        'LIABILITIES': {'2100','2200','2210','2300','2310','2320','2330','2400','2410','2420','2500','2600','2700','2800'},
        'CAPITAL': {'3000','3100'}, 'REVENUE': {'4000','4100','4200'},
        'EXPENSE': {'5000','5100','5200','5300','5400','5410','5500','5510','5520','5600','5700','5701','5710','5720','5730','5740','5750','5760','5770'},
    }
    sample_roles = {account: role for role, accounts in roles.items() for account in accounts}
    if any(r['계정코드'] not in sample_roles for r in leaves):
        raise AuditError('더미 자동 생성은 명시한 기존 v1.3 합성 계정코드만 지원합니다. 사용자 자료의 분류는 직접 매핑하세요.')
    if any(r['표시구분'] != ('PL' if sample_roles[r['계정코드']] in ('REVENUE','EXPENSE') else 'BS') for r in leaves):
        raise AuditError('기존 합성 계정의 BS/PL 분류와 다릅니다.')
    meta = c | {'버전': 'SYNTH-v1.4'}
    names = {'A_CURRENT': '유동자산', 'A_NONCURRENT': '비유동자산', 'ASSETS': '자산총계',
             'LIABILITIES': '부채총계', 'CAPITAL': '납입자본', 'EQUITY': '자본총계(당기손익 포함)',
             'REVENUE': '수익합계', 'EXPENSE': '비용합계', 'PROFIT': '당기순손익'}
    notes = ['B_' + r['계정코드'] for r in leaves if r['계정코드'] in ('1000','1300','1400','1500','1600','2300','2500')] + ['PROFIT']
    source = {'schema_version': '1.1', '설정': meta | {'허용오차원': 0, 'TB비교기준': '조정전기말잔액',
        '자산총계': 'ASSETS', '부채총계': 'LIABILITIES', '자본총계': 'EQUITY', '당기손익': 'PROFIT', '필수주석본문항목': notes},
        'TB문맥': meta | {'잔액기준': '조정전기말잔액'},
        '문서': [{'문서ID': 'FS', '구분': '본문', '문서명': '합성 재무제표(법적효력 없음)', **meta},
                 {'문서ID': 'NOTES', '구분': '주석', '문서명': '합성 선택 주석(법적효력 없음)', **meta}],
        '항목': [], '합계관계': [], '계정매핑': [], '주석연결': []}
    amounts = {}; grouped = {k: [] for k in roles}
    def item(doc, ident, name, table, kind, amount):
        source['항목'].append({'문서ID': doc, '항목ID': ident, '표ID': table, '명칭': name, '유형': kind,
            '금액': amount, '단위': '원', '페이지': 1 if doc == 'FS' else 2, '위치': name})
        amounts[(doc, ident)] = amount
    def total(ident, children):
        amount = sum(amounts[('FS', child)] * factor for child, factor in children)
        item('FS', ident, names[ident], 'PL' if ident in ('REVENUE','EXPENSE','PROFIT') else 'BS', '합계', amount)
        for child, factor in children:
            source['합계관계'].append({'관계ID': 'R_' + str(len(source['합계관계']) + 1), '문서ID': 'FS', '합계항목': ident, '구성항목': child, '계수': factor})
    for r in leaves:
        account = r['계정코드']; role = sample_roles[account]
        factor = -1 if role in ('LIABILITIES','CAPITAL','REVENUE') else 1
        ident = 'B_' + account
        item('FS', ident, r['계정명'], r['표시구분'], '명세', num(r['조정전']) * factor)
        grouped[role].append((ident, 1))
        source['계정매핑'].append({'계정코드': account, '본문항목': ident, '계수': factor})
    if any(not children for children in grouped.values()):
        raise AuditError('더미 생성에는 자산·부채·자본·수익·비용의 모든 합성 계정군이 필요합니다.')
    for group in ('A_CURRENT','A_NONCURRENT','LIABILITIES','CAPITAL','REVENUE','EXPENSE'):
        total(group, grouped[group])
    total('ASSETS', [('A_CURRENT',1),('A_NONCURRENT',1)])
    total('PROFIT', [('REVENUE',1),('EXPENSE',-1)])
    total('EQUITY', [('CAPITAL',1),('PROFIT',1)])
    for i, target in enumerate(notes, 1):
        label = next(r['명칭'] for r in source['항목'] if r['문서ID'] == 'FS' and r['항목ID'] == target)
        item('NOTES', 'N_' + target + '_DETAIL', label + ' 명세', 'N_' + target, '명세', amounts[('FS',target)])
        item('NOTES', 'N_' + target, label + ' 주석합계', 'N_' + target, '합계', amounts[('FS',target)])
        source['합계관계'].append({'관계ID': 'N_R_' + str(i), '문서ID': 'NOTES', '합계항목': 'N_' + target,
            '구성항목': 'N_' + target + '_DETAIL', '계수': 1})
        source['주석연결'].append({'연결ID': 'TIE_' + str(i), '본문항목': target, '주석문서': 'NOTES', '주석항목': 'N_' + target})
    # Generation must never hide an incomplete source ledger or fabricate equality.
    actual = engine.analyze(inputs, source)
    if actual['issues']:
        raise AuditError('기존 합성 원장에서 정상 재무제표를 만들 수 없습니다: ' + str(actual['issues']))
    return source


def build_sample(target, ledger_result):
    """Build one coherent normal fixture and explicit fault variants beside it."""
    source = _sample_source(ledger_result)
    target = Path(target)
    normal = target if target.suffix.lower() == '.json' else target / 'financial.json'
    normal.parent.mkdir(parents=True, exist_ok=True)
    atomic(normal, json.dumps(source, ensure_ascii=False, indent=2).encode('utf-8'))
    cases = []
    def save(name, modify, expected):
        v = deepcopy(source); modify(v)
        path = normal.parent / 'financial_cases' / (name + '.json')
        atomic(path, json.dumps(v, ensure_ascii=False, indent=2).encode('utf-8'))
        cases.append({'name': name, 'file': path.name, **expected})
    def change(v, doc, ident, delta):
        r = next(x for x in v['항목'] if x['문서ID'] == doc and x['항목ID'] == ident)
        r['금액'] += delta
    save('01_소계차이', lambda v: change(v, 'FS','A_CURRENT',1000), {'blocking':0,'required_code':'FS_SUM'})
    def note(v):
        change(v,'NOTES','N_B_1000',700); change(v,'NOTES','N_B_1000_DETAIL',700)
    save('02_주석차이', note, {'blocking':0,'required_code':'FS_NOTE'})
    save('03_매핑누락', lambda v: v['계정매핑'].pop(), {'blocking':1,'required_code':'FS_INPUT'})
    save('04_주석연결누락', lambda v: v['주석연결'].pop(), {'blocking':1,'required_code':'FS_INPUT'})
    save('05_미지원단위', lambda v: v['항목'][0].update(단위='만원'), {'blocking':1,'required_code':'FS_INPUT'})
    save('06_기간불일치', lambda v: v['문서'][1].update(기준일='2025-12-31'), {'blocking':1,'required_code':'FS_INPUT'})
    save('07_계정중복매핑', lambda v: v['계정매핑'].append(deepcopy(v['계정매핑'][0])), {'blocking':1,'required_code':'FS_INPUT'})
    def cycle(v):
        v['합계관계'].append({'관계ID':'CYCLE','문서ID':'FS','합계항목':'A_CURRENT','구성항목':'ASSETS','계수':1})
    save('08_순환합계', cycle, {'blocking':1,'required_code':'FS_INPUT'})
    def unit(v):
        for r in v['항목']:
            from decimal import Decimal
            r['금액'] = format(Decimal(r['금액'])/1000, 'f'); r['단위'] = '천원'
    save('09_천원단위정상', unit, {'blocking':0,'review':0})
    def tiny(v):
        v['설정']['허용오차원']=10; change(v,'FS','A_CURRENT',1)
    save('10_허용범위내차이', tiny, {'blocking':0,'required_code':'FS_SUM'})
    def after(v):
        v['설정']['TB비교기준']='조정후기말잔액';v['TB문맥']['잔액기준']='조정후기말잔액'
    save('11_조정후미지원', after, {'blocking':1,'required_code':'FS_INPUT'})
    def sign(v):
        r=next(x for x in v['계정매핑'] if x['계정코드']=='1390');r['계수']=-1
    save('12_표시부호오류', sign, {'blocking':0,'required_code':'FS_TB'})
    def coherent(v):
        for doc, ident in [('FS','B_1000'),('FS','A_CURRENT'),('FS','ASSETS'),('FS','B_3000'),('FS','CAPITAL'),('FS','EQUITY'),
                           ('NOTES','N_B_1000'),('NOTES','N_B_1000_DETAIL')]: change(v,doc,ident,1200)
    save('13_합계는맞지만TB불일치', coherent, {'blocking':0,'required_code':'FS_TB'})
    atomic(normal.parent/'financial_cases'/'cases.json', json.dumps({'normal':normal.name,'cases':cases},ensure_ascii=False,indent=2).encode('utf-8'))
    return normal
