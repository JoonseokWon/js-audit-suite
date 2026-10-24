"""Signed bank/GL reconciliation and explainable payment review candidates."""
from collections import defaultdict
from datetime import datetime
from common import AuditError, cancelled, day, digest, issue, num, result, text
from analytics_support import read_bound

RULE_VERSION = 'cash-1.0'
SCHEMA = {
    '분석설정': ['항목', '값'],
    '현금계좌': ['회사코드', '계좌ID', '계정코드', '통화', '기초잔액', '기말잔액'],
    '은행거래': ['회사코드', '은행거래ID', '계좌ID', '거래일', '입금', '출금', '거래처ID', '상대계좌', '지급근거ID', '거래구분'],
    '은행독립통제': ['회사코드', '계좌ID', '시작일', '기준일', '행수', '입금합계', '출금합계', '추출근거', '추출일시', '작성자'],
    '현금원장선택': ['회사코드', '전표ID', '행ID', '계좌ID', '거래처ID', '상대계좌', '지급근거ID', '거래구분'],
    '현금배부': ['배부ID', '회사코드', '은행거래ID', '전표ID', '행ID', '금액'],
    '거래처계좌': ['회사코드', '거래처ID', '상대계좌', '소유구분', '근거'],
    '계좌변경': ['변경ID', '회사코드', '거래처ID', '이전계좌', '신규계좌', '효력일', '승인일', '근거'],
    '지급근거': ['회사코드', '지급근거ID', '거래처ID', '승인총액', '통화', '지급유형', '근거'],
}
CONFIG = {'대상계정', '반복지급검색일수', '계좌변경검색일수', '집중최소지급건수', '집중비율퍼센트'}
KINDS = ('일회', '분할', '정기', '자금이체')
LIMITS = [
    '대상계정에 명시한 현재 업무 조정전 원장과 제출 은행자료만 검사합니다. 회사 전체 계좌가 제출되었다는 뜻이 아닙니다.',
    '완전히 미제출된 계좌는 이 입력만으로 식별할 수 없습니다. 독립 계좌목록·금융기관조회·ERP 추출 조건을 별도로 확인해야 합니다.',
    '원장·은행·통제·지급근거가 동일 생성기의 합성자료입니다. 해시·산술 일치는 진위나 증거 독립성을 보장하지 않습니다.',
    '은행·장부 잔여 및 기초·기말 차이는 추가 확인 항목입니다. 미기록·미제출·시차·부정 중 어느 것인지 자동 결론내리지 않습니다.',
    '반복·집중·계좌변경 후보는 설명 가능한 검토 우선순위이며 부정 확정·발생확률·감사 결론이 아닙니다.',
    '같은 금액이라는 이유로 매칭하지 않습니다. 모든 연결은 제출된 명시 배부이며 거래 실질·수취인 진위는 사람이 확인해야 합니다.',
    '검토 후보가 없다는 결과도 안전 또는 부정 부재를 입증하지 않습니다. 외화·은행수수료 자동분개·차기기간 미결제 변환은 지원하지 않습니다.',
]


def analyze(path, context, ledger_result=None, event=None):
    tables, source, binding = read_bound(path, SCHEMA, context, ledger_result, event)
    issues = list(binding['issues'])
    out_tables = dict(binding['tables'])
    controls, balances, allocations, residuals, candidates, unknowns, scope, populations = [], [], [], [], [], [], [], []
    cfg, accounts, bank, selected, proofs, masters, changes = {}, {}, {}, {}, {}, {}, []
    examined = {'반복지급': 0, '상대계좌집중': 0, '계좌변경직후': 0}

    def ref(row):
        return source['filename'] + ' / ' + row['_sheet'] + '!' + str(row['_row'])

    def bad(code, message, row=None, blocking=True):
        issue(issues, code, message, ref(row) if isinstance(row, dict) else str(row or ''), blocking)

    def finish():
        cancelled(event)
        out_tables.update({'현금검사통제': controls, '계좌잔액대사': balances, '현금배부표': allocations,
                           '은행장부잔여': residuals, '검토후보': candidates, '규칙미확인': unknowns,
                           '현금분석범위': scope, '현금모집단': populations})
        blocking = any(i['severity'] == '차단' for i in issues)
        metrics = {'은행거래수': len(bank), '선택원장행수': len(selected), '명시배부수': len(allocations),
                   '잔여행수': sum(r['잔여'] != 0 for r in residuals), '검토후보수': len(candidates),
                   '규칙미확인수': len(unknowns), '대상계좌수': len(accounts),
                   '입금합계': sum(b['입금'] for b in bank.values()), '출금합계': sum(b['출금'] for b in bank.values())}
        detail = dict(binding['detail'], **{'source': source, '규칙버전': RULE_VERSION, '설정': cfg,
                     '검사대상수': examined, '한계': LIMITS, '위험검사실행': not blocking,
                     '상태': 'INPUT_BLOCKED' if blocking else 'REVIEW_PENDING',
                     '수행자': None, '결론': None, '검토자': None, '조정승인': None,
                     '후속확인': '원문 은행명세·승인된 지급근거·거래처 계좌 확인자료·변경 승인로그와 미결제 대사 항목을 확보하고 감사인이 판단하세요.'})
        return result('현금분석', context, out_tables, issues, metrics, detail)

    if not binding['valid']:
        scope.append({'범위': '현재 원장 연결', '상태': '차단', '내용': '현재 업무와 입력 원장 일치 전 위험 검사 미실행'})
        return finish()

    def check(name, expected, actual, row, blocking=True):
        controls.append({'검사': name, '기대': expected, '실제': actual, '차이': actual - expected,
                         '상태': '일치' if actual == expected else '차이', '원문위치': ref(row)})
        if actual != expected:
            bad('CASH_CONTROL' if blocking else 'CASH_BALANCE_DIFF', name + ' 차이', row, blocking)

    def company(row):
        if row['회사코드'] != context['회사코드']:
            raise AuditError('현재 업무와 다른 회사코드')

    def unknown(rule, row, reason):
        unknowns.append({'규칙': rule, '상태': '미확인', '사유': reason, '원문위치': ref(row)})

    def candidate(code, rule, rows, condition, amount, priority, followup):
        ident = code + '-' + str(len(candidates) + 1).zfill(4)
        locations = '; '.join(ref(r) for r in rows)
        candidates.append({'후보ID': ident, '규칙ID': code, '규칙': rule, '규칙버전': RULE_VERSION, '우선순위': priority,
                           '조건': condition, '관련금액': amount, '관련은행거래': ';'.join(r.get('은행거래ID', '') for r in rows),
                           '원문위치': locations, '해석': '추가 확인할 검토 후보; 부정·오류 확정 아님', '후속확인': followup,
                           '사유': condition, '원본행': locations, '후속절차': followup,
                           '은행거래ID': ';'.join(r.get('은행거래ID', '') for r in rows if r.get('은행거래ID')),
                           '수행자': None, '판단': None, '검토자': None})
        issue(issues, code, rule + ' 검토 후보', locations, False)

    try:
        rows = tables['분석설정']
        cfg = {r['항목']: r['값'] for r in rows}
        if len(cfg) != len(rows) or set(cfg) != CONFIG:
            raise AuditError('분석설정 누락·중복·미지원 항목')
        codes = text(cfg['대상계정']).split(';')
        if not codes or len(set(codes)) != len(codes) or any(not c.strip() or c != c.strip() for c in codes):
            raise AuditError('대상계정은 중복 없는 세미콜론 목록')
        account_codes = set(codes)
        for key in CONFIG - {'대상계정'}:
            cfg[key] = num(cfg[key], False)
        if not 1 <= cfg['반복지급검색일수'] <= 366 or not 0 <= cfg['계좌변경검색일수'] <= 366 or not 2 <= cfg['집중최소지급건수'] <= 10000 or not 1 <= cfg['집중비율퍼센트'] <= 100:
            raise AuditError('분석설정 일수·건수·비율 범위 오류')
        current = binding['ledger']['tables']
        gl = {(r['회사코드'], r['전표ID'], r['행ID']): r for r in current['입력_총계정원장']}
        tb = {r['계정코드']: r for r in current['입력_시산표']}
        if not account_codes <= set(tb):
            raise AuditError('대상계정이 현재 원장 TB에 없습니다.')
        lead_classes = {r['계정코드']: r['표시구분'] for r in current['리드스케줄']}
        if any(lead_classes.get(code) != 'BS' for code in codes):
            raise AuditError('현금 대상계정은 현재 리드에서 BS 계정이어야 합니다.')
        for row in tables['현금계좌']:
            cancelled(event)
            try:
                company(row)
                aid, code = text(row['계좌ID']), text(row['계정코드'])
                if aid in accounts or code not in account_codes or row['통화'] != 'KRW':
                    raise AuditError('계좌ID 중복·대상계정 밖·KRW 아님')
                accounts[aid] = dict(row, 기초잔액=num(row['기초잔액']), 기말잔액=num(row['기말잔액']))
            except AuditError as exc:
                bad('CASH_ACCOUNT', str(exc), row)
        if not accounts or {r['계정코드'] for r in accounts.values()} != account_codes:
            bad('CASH_ACCOUNT_SCOPE', '선언 대상계정과 제출 계좌 매핑 범위가 다릅니다.', '현금계좌')
        expected_keys = {key for key, row in gl.items() if row['계정코드'] in account_codes}
        for row in tables['현금원장선택']:
            try:
                company(row)
                key = (row['회사코드'], text(row['전표ID']), text(row['행ID']))
                aid = text(row['계좌ID'])
                if key in selected or key not in expected_keys or aid not in accounts:
                    raise AuditError('현금 원장 선택 중복·고아·미등록 계좌')
                if gl[key]['계정코드'] != accounts[aid]['계정코드']:
                    raise AuditError('계좌 매핑 계정과 선택 원장 계정이 다릅니다.')
                selected[key] = dict(row, _gl=gl[key], _amount=num(gl[key]['차변']) - num(gl[key]['대변']))
            except AuditError as exc:
                bad('CASH_GL_SCOPE', str(exc), row)
        if set(selected) != expected_keys:
            bad('CASH_GL_SCOPE', '선언 현금계정의 현재 원장 행을 빠짐없이 한 번씩 선택해야 합니다.', '현금원장선택')
        for row in tables['은행거래']:
            try:
                company(row)
                bid, aid = text(row['은행거래ID']), text(row['계좌ID'])
                if bid in bank or aid not in accounts:
                    raise AuditError('은행거래ID 중복·미등록 계좌')
                dt = day(row['거래일'])
                if not day(context['시작일']) <= dt <= day(context['기준일']):
                    raise AuditError('은행 거래일이 업무기간 밖입니다.')
                incoming, outgoing = num(row['입금'], False), num(row['출금'], False)
                if (incoming > 0) == (outgoing > 0):
                    raise AuditError('은행 행은 입금·출금 중 하나만 양수여야 합니다.')
                bank[bid] = dict(row, 입금=incoming, 출금=outgoing, _amount=incoming-outgoing, _date=dt)
            except AuditError as exc:
                bad('CASH_BANK_INPUT', str(exc), row)
        ctl = {}
        for row in tables['은행독립통제']:
            try:
                company(row)
                aid = text(row['계좌ID'])
                if aid in ctl or aid not in accounts or row['시작일'] != context['시작일'] or row['기준일'] != context['기준일']:
                    raise AuditError('통제 계좌 중복·미등록·기간 불일치')
                text(row['추출근거']); text(row['작성자'])
                stamp = datetime.fromisoformat(str(row['추출일시']))
                if stamp.tzinfo is None or stamp.date() < day(context['기준일']):
                    raise AuditError('기준일 이후 시간대 포함 추출시각 필수')
                ctl[aid] = row
                subset = [r for r in bank.values() if r['계좌ID'] == aid]
                for key, actual in [('행수', len(subset)), ('입금합계', sum(r['입금'] for r in subset)), ('출금합계', sum(r['출금'] for r in subset))]:
                    check(aid + ' 은행 ' + key, num(row[key], False), actual, row)
            except (AuditError, ValueError) as exc:
                bad('CASH_BANK_CONTROL', str(exc), row)
        if set(ctl) != set(accounts):
            bad('CASH_BANK_CONTROL', '모든 제출 계좌에 독립 행수·입출금 통제가 필요합니다. 무거래도 0을 명시하세요.', '은행독립통제')
        for aid, row in accounts.items():
            subset = [r for r in bank.values() if r['계좌ID'] == aid]
            incoming, outgoing = sum(r['입금'] for r in subset), sum(r['출금'] for r in subset)
            calculated = row['기초잔액'] + incoming - outgoing
            check(aid + ' 은행 기초+입금-출금=기말', row['기말잔액'], calculated, row)
            balances.append({'구분': '은행계좌', '계좌ID': aid, '계정코드': row['계정코드'], '기초': row['기초잔액'],
                             '입금': incoming, '출금': outgoing, '계산기말': calculated, '제출기말': row['기말잔액'],
                             '차이': calculated-row['기말잔액'], '원문위치': ref(row)})
        for code in codes:
            mapped = [r for r in accounts.values() if r['계정코드'] == code]
            beginning, ending = sum(r['기초잔액'] for r in mapped), sum(r['기말잔액'] for r in mapped)
            check(code + ' 은행·TB 기초', num(tb[code]['기초잔액']), beginning, mapped[0], False) if mapped else None
            check(code + ' 은행·TB 기말', num(tb[code]['기말잔액']), ending, mapped[0], False) if mapped else None
            balances.append({'구분': '현재 원장 계정', '계좌ID': ';'.join(r['계좌ID'] for r in mapped), '계정코드': code,
                             '기초': num(tb[code]['기초잔액']), '입금': num(tb[code]['당기차변']), '출금': num(tb[code]['당기대변']),
                             '계산기말': ending, '제출기말': num(tb[code]['기말잔액']), '차이': ending-num(tb[code]['기말잔액']),
                             '원문위치': source['filename'] + ' / 시산표!' + str(tb[code]['_row'])})
        ids, pairs, bank_alloc, gl_alloc = set(), set(), defaultdict(int), defaultdict(int)
        for row in tables['현금배부']:
            try:
                company(row)
                ident, bid = text(row['배부ID']), text(row['은행거래ID'])
                key = (row['회사코드'], text(row['전표ID']), text(row['행ID']))
                pair = (bid, key)
                if ident in ids or pair in pairs:
                    raise AuditError('배부ID 또는 동일 은행·전표행 연결쌍 중복')
                ids.add(ident); pairs.add(pair)
                if bid not in bank or key not in selected:
                    raise AuditError('배부가 미등록 은행거래·현금 원장행을 가리킵니다.')
                a, b = bank[bid], selected[key]
                amount = num(row['금액'])
                if not amount or not a['_amount'] or not b['_amount'] or any((amount > 0) != (v > 0) for v in (a['_amount'], b['_amount'])):
                    bad('CASH_ALLOC_SIGN', '배부·은행·원장 부호가 같아야 하며 abs로 바꾸지 않습니다.', row)
                    continue
                if a['계좌ID'] != b['계좌ID']:
                    raise AuditError('다른 계좌 사이의 배부는 허용하지 않습니다.')
                meta_wrong, meta_missing = [], []
                for field in ('거래처ID', '상대계좌', '지급근거ID', '거래구분'):
                    left, right = a.get(field), b.get(field)
                    if any(value is not None and not isinstance(value, str) for value in (left, right)):
                        meta_wrong.append(field + ' 형식')
                    elif not left or not left.strip() or not right or not right.strip():
                        meta_missing.append(field)
                    elif left != right:
                        meta_wrong.append(field)
                    elif field == '거래구분' and left not in KINDS:
                        meta_wrong.append(field + ' 미지원')
                if meta_wrong:
                    bad('CASH_LINK_META', '명시 배부 양쪽 거래 메타 모순: ' + ', '.join(meta_wrong) + '. 은행=' + ref(a) + '; 선택=' + ref(b), row)
                    continue
                if meta_missing:
                    unknown('배부 거래근거 대조', row, '양쪽 원문 메타 미제출: ' + ', '.join(meta_missing) + '; 금액 일치와 거래 실질 확인을 구분합니다.')
                bank_alloc[bid] += amount; gl_alloc[key] += amount
                allocations.append({'배부ID': ident, '회사코드': row['회사코드'], '은행거래ID': bid, '전표ID': key[1], '행ID': key[2],
                                    '계좌ID': a['계좌ID'], '금액': amount, '은행원문': ref(a), '선택원문': ref(b),
                                    '원장원문': source['filename'] + ' / 총계정원장!' + str(b['_gl']['_row']), '배부원문': ref(row)})
            except AuditError as exc:
                bad('CASH_ALLOCATION', str(exc), row)
        for side, rows, allocated in [('은행', bank, bank_alloc), ('장부', selected, gl_alloc)]:
            for key, row in rows.items():
                amount, used = row['_amount'], allocated[key]
                remaining = amount-used
                over = abs(used) > abs(amount)
                if over:
                    bad('CASH_OVERALLOC', side + ' 원문 금액보다 과다 배부되었습니다.', row)
                elif remaining:
                    bad('CASH_RESIDUAL', side + ' 잔여가 있습니다. 시차·미기록·미제출 여부를 추가 확인하세요.', row, False)
                residuals.append({'구분': side, '식별자': key if isinstance(key, str) else ' / '.join(key), '계좌ID': row['계좌ID'],
                                  '원문금액': amount, '명시배부합계': used, '잔여': remaining,
                                  '상태': '과배부·차단' if over else '잔여·검토' if remaining else '금액일치·미검토', '원문위치': ref(row)})
        scope.append({'범위': '현재 조정전 현금 원장·제출 은행자료', '대상계정': codes, '계좌목록': list(accounts),
                      '은행거래수': len(bank), '원장행수': len(selected), '선택정책': '대상계정의 모든 현재 GL행; 전체 회사 계좌 완전성은 별도 확인'})
    except (AuditError, KeyError, TypeError, ValueError) as exc:
        bad('CASH_INPUT', str(exc), '현금분석 입력')
    if any(i['severity'] == '차단' for i in issues):
        return finish()

    # Metadata is not invented. Missing review metadata leaves its rule unknown.
    for row in tables['거래처계좌']:
        try:
            company(row)
            key = (text(row['거래처ID']), text(row['상대계좌']))
            if key in masters or row['소유구분'] not in ('외부', '자사', '미확인'):
                raise AuditError('거래처·계좌 중복 또는 소유구분 미지원')
            text(row['근거']); masters[key] = row
        except AuditError as exc:
            bad('CASH_PARTY_META', str(exc), row)
    for row in tables['지급근거']:
        try:
            company(row)
            ident = text(row['지급근거ID'])
            if ident in proofs or row['지급유형'] not in KINDS or row['통화'] != 'KRW':
                raise AuditError('지급근거 중복·유형/통화 오류')
            text(row['거래처ID']); text(row['근거'])
            approved = num(row['승인총액'], False)
            proofs[ident] = dict(row, 승인총액=approved)
        except AuditError as exc:
            bad('CASH_PROOF_META', str(exc), row)
    changes_seen = set()
    for row in tables['계좌변경']:
        try:
            company(row)
            ident, party = text(row['변경ID']), text(row['거래처ID'])
            if ident in changes_seen:
                raise AuditError('변경ID 중복')
            changes_seen.add(ident)
            old, new = text(row['이전계좌']), text(row['신규계좌'])
            if old == new or (party, new) not in masters:
                raise AuditError('계좌 변경 전후 동일 또는 신규계좌가 거래처계좌에 없습니다.')
            effective, approved = day(row['효력일']), day(row['승인일'])
            if effective > day(context['기준일']) or approved > day(context['기준일']):
                raise AuditError('업무 기준일 뒤 계좌변경·승인일')
            text(row['근거']); changes.append(dict(row, _effective=effective, _approved=approved))
        except AuditError as exc:
            bad('CASH_CHANGE_META', str(exc), row)
    if any(i['severity'] == '차단' for i in issues):
        return finish()
    payments = [r for r in bank.values() if r['출금'] > 0]
    eligible = []
    by_proof = defaultdict(list)
    for row in payments:
        key = (row.get('거래처ID'), row.get('상대계좌'))
        proof = proofs.get(row.get('지급근거ID'))
        master = masters.get(key)
        if not master or master['소유구분'] == '미확인':
            unknown('상대계좌집중·자금이체구분', row, '거래처·계좌 소유 메타가 없거나 미확인입니다.')
        if proof is None:
            unknown('반복지급', row, '지급근거 승인총액·유형이 없습니다.')
        elif not row.get('거래처ID'):
            unknown('반복지급', row, '은행 행 거래처가 미제출되어 지급근거의 거래처와 대조할 수 없습니다.')
        elif proof['거래처ID'] != row.get('거래처ID'):
            bad('CASH_PARTY_PROOF', '지급 거래처가 지급근거 거래처와 다릅니다.', row)
        else:
            by_proof[row['지급근거ID']].append(row)
        if proof and master:
            if row.get('거래구분') not in KINDS or row['거래구분'] != proof['지급유형']:
                unknown('반복지급·자금이체구분', row, '은행 거래구분과 지급근거 유형이 다르거나 없습니다.')
            elif proof['지급유형'] == '자금이체':
                if master['소유구분'] != '자사' or row['상대계좌'] not in accounts:
                    unknown('자금이체', row, '자금이체로 선언했으나 자사 계좌 및 제출 계좌목록 연결을 확인할 수 없습니다.')
                else:
                    # A transfer must have an explicit incoming bank leg too.
                    opposite = [b for b in bank.values() if b['계좌ID'] == row['상대계좌'] and b['입금'] == row['출금']
                                and b['지급근거ID'] == row['지급근거ID'] and b['상대계좌'] == row['계좌ID']]
                    if len(opposite) != 1:
                        unknown('자금이체', row, '동일 자금이체 근거의 반대 은행 입금 한 건을 확인할 수 없습니다.')
                    elif bank_alloc[row['은행거래ID']] != row['_amount'] or bank_alloc[opposite[0]['은행거래ID']] != opposite[0]['_amount']:
                        unknown('자금이체', row, '제출 양쪽 은행행의 GL 배부가 완전하지 않습니다. 자금이체 대조군으로 확정하지 않습니다.')
                    else:
                        populations.append({'구분': '자금이체 대조군', '은행거래ID': row['은행거래ID'], '금액': row['출금'],
                                            '상태': '제출 양쪽 은행·원장 배부 있음; 실질 미검토', '원문위치': ref(row)})
            elif master['소유구분'] == '외부':
                eligible.append(row)
    if any(i['severity'] == '차단' for i in issues):
        return finish()
    for proof_id, rows in by_proof.items():
        proof = proofs[proof_id]
        total = sum(r['출금'] for r in rows)
        examined['반복지급'] += len(rows)
        if total > proof['승인총액']:
            candidate('CASH_APPROVED_EXCESS', '제출 승인총액 초과 지급', rows,
                      f'근거 {proof_id}: 선택기간 지급합계 {total} > 승인총액 {proof["승인총액"]}', total-proof['승인총액'], '높음',
                      '승인총액 범위·다른 정산/환불·추가 승인·수취인과 송장을 확인하세요.')
        matched = {}
        if proof['지급유형'] not in ('분할', '정기', '자금이체'):
            same_amount = defaultdict(list)
            for row in rows:
                same_amount[(row['출금'], row['상대계좌'])].append(row)
            for group in same_amount.values():
                ordered = sorted(group, key=lambda r: (r['_date'], r['은행거래ID']))
                for a, b in zip(ordered, ordered[1:]):
                    if (b['_date']-a['_date']).days <= cfg['반복지급검색일수']:
                        matched[a['은행거래ID']] = a
                        matched[b['은행거래ID']] = b
            if matched:
                candidate('CASH_REPEAT_CANDIDATE', '동일 근거 반복 지급', list(matched.values()),
                          f'동일 근거·상대계좌·출금액, {cfg["반복지급검색일수"]}일 이내, 제출 유형 일회',
                          sum(r['출금'] for r in matched.values()), '높음', '별도 송장·취소·재지급·중복 승인 여부를 확인하세요.')
        elif len(rows) > 1 and total <= proof['승인총액']:
            populations.append({'구분': '합법 반복·분할 대조군', '은행거래ID': ';'.join(r['은행거래ID'] for r in rows),
                                '금액': total, '상태': f'{proof["지급유형"]} 선언 및 승인총액 이내; 근거 진위 미검토', '원문위치': ref(proof)})
    by_account = defaultdict(list)
    denominator = sum(r['출금'] for r in eligible)
    examined['상대계좌집중'] = len(eligible)
    for row in eligible:
        by_account[row['상대계좌']].append(row)
    if not denominator and payments:
        unknown('상대계좌집중', payments[0], '검증된 외부 지급 모집단이 없어 집중비율을 계산하지 않았습니다.')
    for account, rows in by_account.items():
        total = sum(r['출금'] for r in rows)
        if len(rows) >= cfg['집중최소지급건수'] and total*100 >= denominator*cfg['집중비율퍼센트']:
            candidate('CASH_CONCENTRATION', '상대계좌 지급 집중', rows,
                      f'검증된 외부 지급 모집단 {denominator}원 중 {account} {total}원; {len(rows)}건; 기준 {cfg["집중비율퍼센트"]}%·{cfg["집중최소지급건수"]}건',
                      total, '보통', '공동 수취계좌·대리수납·주요 공급처 등 정당한 사업 사유를 확인하세요.')
    if not changes:
        if payments:
            unknown('계좌변경직후', payments[0], '변경 이력이 제출되지 않았습니다. 변경 없음을 확정하지 않습니다.')
    else:
        for change in changes:
            rows = [r for r in payments if r['거래처ID'] == change['거래처ID'] and r['상대계좌'] == change['신규계좌']]
            examined['계좌변경직후'] += len(rows)
            matched = [r for r in rows if 0 <= (r['_date']-change['_effective']).days <= cfg['계좌변경검색일수']]
            if matched:
                candidate('CASH_ACCOUNT_CHANGE', '계좌변경 직후 지급', matched + [change],
                          f'효력일 {change["효력일"]}부터 {cfg["계좌변경검색일수"]}일 이내 신규계좌 지급; 승인일 {change["승인일"]}',
                          sum(r['출금'] for r in matched), '높음', '독립 경로의 거래처 계좌 확인과 변경 승인로그를 확인하세요.')
    for row in bank.values():
        populations.append({'구분': '제출 은행거래', '은행거래ID': row['은행거래ID'], '계좌ID': row['계좌ID'],
                            '거래처ID': row.get('거래처ID'), '상대계좌': row.get('상대계좌'), '지급근거ID': row.get('지급근거ID'),
                            '금액': row['_amount'], '원문위치': ref(row)})
    return finish()


def write_samples(target):
    from .samples import write_samples as create
    return create(target)
