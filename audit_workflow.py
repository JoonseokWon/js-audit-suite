"""Human-entered audit planning and mechanical completion controls.

No method in this module infers a risk, performs an audit procedure, or records
an approval. Every change is an append-only Workspace event.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import json
import re
import uuid
from common import AuditError, digest, dumps, day, now
from human_input import text
from export_support.text import validate_structure

AUDIT_FRAMEWORKS = ('KSA_200_720', 'KSA_1200')
FORM_FRAMEWORKS = ('KIFRS', '일반기업', '소규모기업')
PURPOSES = ('subsequent_events', 'financial_statement_reconciliation')


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out: raise AuditError('JSON 중복 키: ' + key)
        out[key] = value
    return out


def payload(value, allowed, required=()):
    if isinstance(value, str):
        if len(value) > 200000: raise AuditError('계획 입력 크기 한도 초과')
        try: value = json.loads(value, object_pairs_hook=_pairs,
                              parse_constant=lambda x: (_ for _ in ()).throw(AuditError('유한 숫자만 허용: ' + x)))
        except (ValueError, RecursionError) as exc: raise AuditError('계획 JSON 오류: ' + str(exc)) from exc
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise AuditError('계획 입력 필드 누락/미지원 필드')
    try:
        if len(dumps(value)) > 200000: raise AuditError('계획 입력 크기 한도 초과')
    except (ValueError, TypeError, RecursionError) as exc: raise AuditError('계획 입력 JSON/유한 숫자 오류') from exc
    validate_structure(value,'계획 원본 입력')
    return deepcopy(value)


def strings(value, label, *, allow_empty=False):
    if not isinstance(value, list) or len(value) > 500: raise AuditError(label + ': 목록/한도 오류')
    result = [text(v, label) for v in value]
    if len(set(result)) != len(result) or (not allow_empty and not result): raise AuditError(label + ': 비어 있거나 중복된 ID/값')
    return result


def decimal(value, label, rate=False, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise AuditError(label + ': 숫자 필수')
    raw = str(value).strip()
    if not re.fullmatch(r'\d+(?:\.\d+)?', raw): raise AuditError(label + ': 유한 양수 형식 필요')
    try: number = Decimal(raw)
    except InvalidOperation as exc: raise AuditError(label + ': 숫자 오류') from exc
    if not number.is_finite() or number < 0 or (number == 0 and not allow_zero) or number > (1 if rate else 10**16): raise AuditError(label + ': 범위 오류')
    if not rate and number != number.to_integral_value(): raise AuditError(label + ': 원 단위 정수 필요')
    return number


def known_ids(ws):
    catalog = json.loads(Path(__file__).with_name('procedure_catalog.json').read_text(encoding='utf-8'))
    generated = {'X-'+r['id']+'-'+str(i) for r in ws.latest().values() for i, _ in enumerate(r['result']['issues'])}
    return {m['id'] for m in catalog['modules']} | {'FS01', 'R01', 'W01', 'G01', 'I01', 'H01'} | set(ws.required_procedures()) | generated


def _source_ids(ws, value):
    ids = strings(value, '증거ID', allow_empty=True)
    if any(s not in ws.sources for s in ids): raise AuditError('현재 업무에 없는 증거ID')
    if ws.verify_sources(): raise AuditError('원본 사본 변경/누락')
    return ids


def _current_basis(ws, value):
    if value != ws.data_basis(): raise AuditError('현재 자료/실행 basis와 다릅니다. 자료와 실행을 확인하세요.')
    return value


def refresh_state(ws):
    ws.workflow_profile = None
    ws.workflow_risks = {}
    ws.workflow_procedure_links = {}
    ws.workflow_classification = None
    ws.workflow_lock = None
    ws.workflow_locked = False
    legacy = []
    for index, event in enumerate(ws.events, 1):
        kind, data = event['kind'], event['data']
        if kind == 'workflow_profile': ws.workflow_profile = data
        elif kind == 'workflow_risk': ws.workflow_risks[data['id']] = data
        elif kind == 'workflow_risk_retire': ws.workflow_risks.pop(data['risk_id'], None)
        elif kind == 'workflow_procedure': ws.workflow_procedure_links[data['procedure_id']] = data
        elif kind == 'workflow_procedure_retire': ws.workflow_procedure_links.pop(data['procedure_id'], None)
        elif kind == 'workflow_f01_classification': ws.workflow_classification = data
        elif kind == 'workflow_finalize': ws.workflow_lock = data; ws.workflow_locked = True
        elif kind == 'workflow_reopen': ws.workflow_locked = False
        if ((kind == 'procedure' and data.get('id') == 'F01' and not data.get('purpose_code')) or
            (kind == 'ai_draft' and data.get('procedure_id') == 'F01' and not data.get('packet', {}).get('procedure', {}).get('purpose_code'))):
            legacy.append({'seq': index, 'kind': kind, 'data_hash': digest(data)})
    ws.workflow_legacy_f01 = legacy
    ws.legacy_f01_documents = []
    ws.legacy_f01_approvals = []
    if ws.workflow_classification:
        ws.legacy_f01_documents = [deepcopy(e['data']) for e in ws.events if e['kind'] == 'procedure' and e['data'].get('id') == 'F01' and not e['data'].get('purpose_code')]
        ws.legacy_f01_approvals = [deepcopy(e['data']) for e in ws.events if e['kind'] == 'ai_content_approval' and e['data'].get('procedure_id') == 'F01' and not e['data'].get('purpose_code')]
        if ws.procedures.get('F01') and not ws.procedures['F01'].get('purpose_code'): ws.procedures.pop('F01')
        if ws.ai_approvals.get('F01') and not ws.ai_approvals['F01'].get('purpose_code'): ws.ai_approvals.pop('F01')


def legacy_f01(ws):
    records = ws.workflow_legacy_f01
    classification = ws.workflow_classification
    bound = bool(classification and classification.get('legacy_records_hash') == digest(records))
    return {'present': bool(records), 'resolved': not records or bound, 'records': records,
            'classification': deepcopy(classification), 'purpose_code': classification.get('purpose_code') if bound else None,
            'draft_ids': [d['id'] for d in ws.ai_drafts.values() if d.get('procedure_id')=='F01' and not d.get('packet',{}).get('procedure',{}).get('purpose_code')]}


def purpose_code(ws, pid):
    if pid == 'FS01': return 'financial_statement_reconciliation'
    if pid != 'F01': return pid
    legacy = legacy_f01(ws)
    if not legacy['resolved']: raise AuditError('구형 F01 목적이 모호합니다. 원본을 보존하고 사람이 목적을 명시 분류하세요.')
    return 'subsequent_events'


def module_for(ws, pid):
    from common import PROCEDURE_MODULES
    if pid == 'F01':
        purpose_code(ws, pid)
        return None
    return PROCEDURE_MODULES.get(pid)


def workflow_basis(ws):
    data = {'profile': ws.workflow_profile, 'risks': ws.workflow_risks,
            'procedure_links': ws.workflow_procedure_links, 'f01_classification': ws.workflow_classification}
    if not any(data.values()):return None
    planning_kinds={'workflow_profile','workflow_risk','workflow_procedure','workflow_f01_classification','workflow_risk_retire','workflow_procedure_retire'}
    data['planning_history_hash']=digest([e for e in ws.events if e['kind'] in planning_kinds])
    return data


def classify_legacy_f01(ws, purpose, actor, reason, *, expected_head=None):
    before=ws.assert_writeable(expected_head=expected_head)
    if purpose not in PURPOSES: raise AuditError('F01 목적은 후속사건 또는 재무제표대사 중 사람이 선택해야 합니다.')
    if not ws.workflow_legacy_f01: raise AuditError('분류할 구형 F01 이력이 없습니다.')
    if ws.workflow_classification: raise AuditError('기존 F01 목적 분류를 바꿔 조서/AI 근거를 전용할 수 없습니다.')
    data = {'id': uuid.uuid4().hex, 'purpose_code': purpose, 'actor': text(actor, '목적 분류자'),
            'reason': text(reason, '원본 확인·분류 사유'), 'legacy_records_hash': digest(ws.workflow_legacy_f01),
            'legacy_records': deepcopy(ws.workflow_legacy_f01), 'at': now()}
    ws._append('workflow_f01_classification', data, expected_head=before); ws.refresh()
    return data


def save_profile(ws, value, actor, *, expected_head=None):
    before=ws.assert_writeable(expected_head=expected_head)
    p = payload(value, ('audit_framework', 'audit_framework_reason', 'form_framework', 'materiality', 'scope'), ('audit_framework', 'audit_framework_reason', 'form_framework', 'materiality', 'scope'))
    if p['audit_framework'] not in AUDIT_FRAMEWORKS or p['form_framework'] not in FORM_FRAMEWORKS: raise AuditError('감사체계와 참고 서식계열을 각각 사람이 선택하세요.')
    p['audit_framework_reason'] = text(p['audit_framework_reason'], '감사체계 선택·적용가능성 판단 근거')
    m = payload(p['materiality'], ('benchmark_name', 'benchmark_amount', 'materiality_rate', 'performance_rate', 'trivial_rate'), ('benchmark_name', 'benchmark_amount', 'materiality_rate', 'performance_rate', 'trivial_rate'))
    m['benchmark_name'] = text(m['benchmark_name'], '중요성 기준지표')
    amount = decimal(m['benchmark_amount'], '기준지표 금액')
    rates = {k: decimal(m[k], k, rate=True, allow_zero=k=='trivial_rate') for k in ('materiality_rate', 'performance_rate', 'trivial_rate')}
    if rates['trivial_rate'] >= rates['performance_rate']: raise AuditError('명백히 사소한 비율은 수행중요성 비율보다 작아야 합니다.')
    m['benchmark_amount'] = int(amount)
    for key, rate in rates.items(): m[key] = format(rate, 'f')
    overall = (amount * rates['materiality_rate']).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    m['overall_materiality'] = int(overall)
    m['performance_materiality'] = int((overall * rates['performance_rate']).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    m['clearly_trivial_threshold'] = int((overall * rates['trivial_rate']).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    m['calculation_policy'] = '전체 중요성=기준지표×선택비율; 수행중요성=전체 중요성×사람 선택 수행비율; 사소한 금액=전체 중요성×사람 선택 사소비율. 각각 원 단위 ROUND_HALF_UP. 사소비율 0은 자동 무시 범위 없음.'
    if m['clearly_trivial_threshold'] >= m['performance_materiality'] or m['performance_materiality'] <= 0: raise AuditError('계산된 수행중요성은 양수이고 사소한 금액 < 수행중요성이어야 합니다. 사소한 비율 0은 자동 무시 범위 없음입니다.')
    if not isinstance(p['scope'], list) or not p['scope'] or len(p['scope']) > 500: raise AuditError('절차 범위를 선택하세요.')
    seen = set(); scope = []; known = known_ids(ws)
    for item in p['scope']:
        item = payload(item, ('procedure_id', 'applicable', 'reason'), ('procedure_id', 'applicable', 'reason'))
        pid = text(item['procedure_id'], '절차ID')
        if pid not in known or pid in seen or type(item['applicable']) is not bool: raise AuditError('절차ID 중복/타 업무/적용 여부 오류')
        seen.add(pid); item.update(procedure_id=pid, reason=text(item['reason'], '적용/제외 사유')); scope.append(item)
    p.update(materiality=m, scope=scope, actor=text(actor, '계획 작성자'), at=now(), revision=uuid.uuid4().hex)
    ws._append('workflow_profile', p, expected_head=before); ws.refresh(); return p


def save_risk(ws, value, actor, *, expected_head=None):
    before=ws.assert_writeable(expected_head=expected_head)
    if not ws.workflow_profile: raise AuditError('감사계획을 먼저 저장하세요.')
    required = ('title', 'accounts', 'assertions', 'procedure_ids', 'basis', 'evidence_ids', 'nature', 'timing', 'extent', 'assessment')
    r = payload(value, ('id', *required), required)
    r['id'] = text(r.get('id') or uuid.uuid4().hex, '위험ID')
    if not re.fullmatch(r'[A-Za-z0-9가-힣_.-]{1,100}', r['id']): raise AuditError('위험ID 형식 오류')
    for key in ('title', 'nature', 'timing', 'extent', 'assessment'): r[key] = text(r[key], key)
    for key in ('accounts', 'assertions', 'procedure_ids'): r[key] = strings(r[key], key)
    active = {s['procedure_id'] for s in ws.workflow_profile['scope'] if s['applicable']}
    if not set(r['procedure_ids']) <= active: raise AuditError('계획에 적용으로 선택한 절차만 위험과 연결하세요.')
    r['basis'] = _current_basis(ws, r['basis']); r['evidence_ids'] = _source_ids(ws, r['evidence_ids'])
    r.update(actor=text(actor, '위험 평가자'), at=now(), revision=uuid.uuid4().hex)
    ws._append('workflow_risk', r, expected_head=before); ws.refresh(); return r


def save_procedure_link(ws, value, actor, *, expected_head=None):
    before=ws.assert_writeable(expected_head=expected_head)
    if not ws.workflow_profile: raise AuditError('감사계획을 먼저 저장하세요.')
    required = ('procedure_id', 'risk_ids', 'evidence_ids', 'basis', 'nature', 'timing', 'extent', 'plan')
    p = payload(value, (*required, 'performed', 'performed_date', 'performer'), required)
    pid = text(p['procedure_id'], '절차ID')
    active = {s['procedure_id'] for s in ws.workflow_profile['scope'] if s['applicable']}
    if pid not in active: raise AuditError('적용 범위에 없는 절차ID')
    p['risk_ids'] = strings(p['risk_ids'], '위험ID')
    if any(r not in ws.workflow_risks or pid not in ws.workflow_risks[r]['procedure_ids'] for r in p['risk_ids']): raise AuditError('타 위험ID 또는 위험-절차 고아 연결')
    for key in ('nature', 'timing', 'extent', 'plan'): p[key] = text(p[key], key)
    p['basis'] = _current_basis(ws, p['basis']); p['evidence_ids'] = _source_ids(ws, p['evidence_ids'])
    for key in ('performed', 'performed_date', 'performer'):
        if p.get(key): p[key] = text(p[key], key)
        else: p[key] = ''
    if any(p[k] for k in ('performed', 'performed_date', 'performer')):
        if not all(p[k] for k in ('performed', 'performed_date', 'performer')) or not p['evidence_ids']: raise AuditError('실제 수행내용·일자·수행자·증거를 함께 기록하세요.')
        p['performed_date'] = day(p['performed_date']).isoformat()
    p.update(procedure_id=pid, actor=text(actor, '절차 계획/수행 기록자'), at=now(), revision=uuid.uuid4().hex)
    ws._append('workflow_procedure', p, expected_head=before); ws.refresh(); return p


def status(ws):
    ws.refresh()
    rows = []; blockers = []; human_pending = []
    def add(code, message, *, pid='', rid='', pending=False, ok=False):
        row = {'code': code, 'procedure_id': pid, 'risk_id': rid, 'status': '확인' if ok else '사람입력대기' if pending else '차단', 'message': message}
        rows.append(row)
        if not ok: blockers.append(row)
        if pending and not ok: human_pending.append(row)
    legacy = legacy_f01(ws)
    if not legacy['resolved']: add('LEGACY_F01_UNCLASSIFIED', '구형 F01 원본 목적을 사람이 확인·분류해야 합니다.', pid='F01', pending=True)
    active = ws.workflow_profile is not None
    if active:
        profile = ws.workflow_profile
        scopes = {s['procedure_id']: s for s in profile['scope']}
        selected = {pid for pid, s in scopes.items() if s['applicable']}
        if not selected: add('SCOPE_EMPTY', '적용 절차를 선택하세요.', pending=True)
        current_ids=known_ids(ws)
        for pid in sorted(set(scopes)-current_ids):add('SCOPE_ID_STALE','절차ID가 현재 정의/실행 예외에 없습니다. 이전 기록은 보존하고 범위를 다시 선택하세요.',pid=pid,pending=True)
        for pid in sorted(ws.required_procedures() - selected): add('REQUIRED_SCOPE_MISSING', '현재 실행에서 필요한 절차가 적용 계획에 없습니다.', pid=pid, pending=True)
        if ws.verify_sources(): add('SOURCE_INTEGRITY', '등록 원본 사본이 변경/누락되었습니다.')
        if not ws.runs: add('RUN_MISSING', '현재 업무 자동검사를 실행하지 않았습니다.')
        latest=ws.latest()
        if '원장·리드' not in latest:add('LEDGER_MISSING','독립 원장·리드 실행이 없습니다.')
        for module,run in latest.items():
            if run['result']['blocking'] or run.get('cancelled'):add('RUN_BLOCKED','자동검사 차단/취소: '+module)
        for cross in ws.cross_checks():
            if cross['상태'] not in ('일치','차이'):add('CROSS_CHECK_UNCONFIRMED',cross['모듈']+' '+cross['지표']+': '+cross['상태'])
        for pid,workpaper in ws.procedures.items():
            if pid not in selected and ws.procedure_state(workpaper)!='검토기록완료':add('UNSELECTED_WORKPAPER_REVIEW_PENDING','추가 조서도 현재 자료/계획 기준 검토가 필요합니다.',pid=pid,pending=True)
            if pid not in selected and ws.ai_status(pid).get('required') and not ws.ai_status(pid).get('approved'):add('AI_APPROVAL_PENDING','추가 AI 조서 최종내용 사람 승인 필요',pid=pid,pending=True)
        for rid, risk in ws.workflow_risks.items():
            if risk['basis'] != ws.data_basis(): add('RISK_STALE', '위험 평가 이후 자료/실행 변경. 근거 확인 후 다시 기록하세요.', rid=rid, pending=True)
            if not risk['evidence_ids']: add('RISK_EVIDENCE_MISSING', '위험 평가에 등록 증거를 연결하세요.', rid=rid, pending=True)
            for pid in risk['procedure_ids']:
                if pid not in selected: add('RISK_PROCEDURE_ORPHAN', '위험에 연결한 절차가 현재 적용 범위에 없습니다.', rid=rid, pid=pid)
                link = ws.workflow_procedure_links.get(pid)
                if not link or rid not in link['risk_ids']: add('RISK_LINK_MISSING', '위험과 절차의 대응 계획을 연결하세요.', rid=rid, pid=pid, pending=True)
        for pid in sorted(set(ws.workflow_procedure_links) - selected): add('PROCEDURE_LINK_ORPHAN', '현재 범위에서 제외된 절차 연결 기록이 있습니다. 계획을 조정하세요.', pid=pid)
        for pid in sorted(selected):
            link = ws.workflow_procedure_links.get(pid); p = ws.procedures.get(pid)
            try:module=module_for(ws,pid)
            except AuditError:module=None
            if module and module not in ws.latest():add('MODULE_NOT_EXECUTED','선택한 절차에 대응하는 자동검사를 아직 실행하지 않았습니다.',pid=pid)
            if not link: add('PROCEDURE_PLAN_MISSING', '위험·성격·시기·범위 및 실제 수행 계획을 기록하세요.', pid=pid, pending=True)
            else:
                if link['basis'] != ws.data_basis(): add('PROCEDURE_PLAN_STALE', '절차 계획/수행 근거 자료가 변경되었습니다.', pid=pid, pending=True)
                for rid in link['risk_ids']:
                    if rid not in ws.workflow_risks or pid not in ws.workflow_risks[rid]['procedure_ids']: add('PROCEDURE_RISK_ORPHAN', '절차에 연결한 위험이 현재 대응관계에 없습니다.', pid=pid, rid=rid)
                if not link['evidence_ids']: add('PROCEDURE_EVIDENCE_MISSING', '절차에 등록 증거를 연결하세요.', pid=pid, pending=True)
                if not all(link.get(k) for k in ('performed', 'performed_date', 'performer')): add('PROCEDURE_NOT_PERFORMED', '사람의 실제 수행내용·일자·수행자를 기록하세요.', pid=pid, pending=True)
            if not p: add('WORKPAPER_MISSING', '수행·판단 조서가 없습니다.', pid=pid, pending=True)
            elif p.get('excluded'): add('SELECTED_PROCEDURE_EXCLUDED', '적용 계획과 조서 제외 기록이 서로 다릅니다.', pid=pid)
            elif ws.procedure_state(p) != '검토기록완료': add('WORKPAPER_REVIEW_PENDING', '현재 계획·자료 기준의 사람 검토 기록이 필요합니다.', pid=pid, pending=True)
            elif link and not set(link['evidence_ids']) <= set(p.get('evidence_ids', [])): add('WORKPAPER_EVIDENCE_MISMATCH', '계획/수행 기록 증거가 조서와 연결되지 않았습니다.', pid=pid)
            elif not any(row['procedure_id']==pid for row in blockers) and (not ws.ai_status(pid).get('required') or ws.ai_status(pid).get('approved')): add('PROCEDURE_RECORDED', '선택 절차의 입력·수행·검토 기록을 확인했습니다. 실제 감사완료 인증이 아닙니다.', pid=pid, ok=True)
            if p and ws.ai_status(pid).get('required') and not ws.ai_status(pid).get('approved'): add('AI_APPROVAL_PENDING', 'AI 적용 최종내용을 사람이 확인·승인해야 합니다.', pid=pid, pending=True)
        for request in ws.requests.values():
            if request['state'] not in ('검토완료', '취소'): add('REQUEST_PENDING', '미완료 자료 요청: ' + request['title'], pending=True)
        if any(not n['resolved'] for n in ws.notes.values()): add('REVIEW_NOTE_PENDING', '미해결 검토의견이 있습니다.', pending=True)
    from audit_extensions import workflow_rows
    extension_rows=workflow_rows(ws)
    rows.extend(extension_rows);blockers.extend(extension_rows);human_pending.extend(extension_rows)
    return {'active': active, 'locked': ws.workflow_locked, 'lock': deepcopy(ws.workflow_lock),
            'profile': deepcopy(ws.workflow_profile), 'risks': deepcopy(list(ws.workflow_risks.values())),
            'procedure_links': deepcopy(list(ws.workflow_procedure_links.values())), 'legacy_f01': legacy,
            'rows': rows, 'blockers': blockers, 'human_pending': human_pending,
            'scope': '입력·근거버전·수행/검토 기록의 기계적 점검. 실제 감사완료·기준준수·감사의견 인증이 아님. 서식계열은 참고 ZIP의 분류이며 실제 회계체계 또는 감사기준의 적용 판단을 대신하지 않음.'}


def finalize(ws, actor, note, *, expected_head=None):
    before=ws.assert_writeable(expected_head=expected_head)
    actor, note = text(actor, '보관 잠금 기록자'), text(note, '보관 잠금 근거')
    if not ws.workflow_profile: raise AuditError('감사계획을 설정한 업무만 보관 잠금할 수 있습니다.')
    snap = ws.snapshot(final=True)
    data = {'id': uuid.uuid4().hex, 'actor': actor, 'note': note, 'basis': snap['basis'], 'head_before': before, 'at': now()}
    ws._append('workflow_finalize', data, expected_head=before); ws.refresh(); return data


def reopen(ws, actor, reason, *, expected_head=None):
    ws.refresh()
    before=ws.head
    if expected_head is not None and before!=expected_head:raise AuditError('화면을 연 뒤 업무 이력이 변경되었습니다. 새 상태를 확인하세요.')
    if not ws.workflow_locked: raise AuditError('보관 잠금된 업무만 재개할 수 있습니다.')
    data = {'id': uuid.uuid4().hex, 'actor': text(actor, '재개 기록자'), 'reason': text(reason, '재개 사유'),
            'previous_lock': deepcopy(ws.workflow_lock), 'at': now()}
    ws._append('workflow_reopen', data, expected_head=before); ws.refresh(); return data


def retire(ws, identifier, actor, reason, *, risk=False, expected_head=None):
    before=ws.assert_writeable(expected_head=expected_head)
    identifier = text(identifier, '위험ID' if risk else '절차ID')
    records = ws.workflow_risks if risk else ws.workflow_procedure_links
    if identifier not in records: raise AuditError('현재 사용 중인 계획/위험 연결 ID가 아닙니다.')
    data = {'id': uuid.uuid4().hex, 'risk_id' if risk else 'procedure_id': identifier,
            'actor': text(actor, '사용 해제 기록자'), 'reason': text(reason, '사용 해제 사유'),
            'previous_record': deepcopy(records[identifier]), 'at': now()}
    ws._append('workflow_risk_retire' if risk else 'workflow_procedure_retire', data, expected_head=before)
    ws.refresh()
    return data


def form_reference_rows(ws):
    if not ws.workflow_profile:return []
    from audit_forms import registry_rows
    profile=ws.workflow_profile
    static=[s['procedure_id'] for s in profile['scope'] if not s['procedure_id'].startswith(('X-','B-'))]
    rows=registry_rows(profile['form_framework'],static) if static else []
    current_ids=known_ids(ws)
    for entry in profile['scope']:
        pid=entry['procedure_id']
        if pid.startswith(('X-','B-')):
            rows.append({'절차ID':pid,'절차명':'자동검사 예외·대사차이 수동 조사','서식계열':profile['form_framework'],
                         '공식서식ID':'','파일':'','시트':[],'연결상태':'공식 참고 미지정' if pid in current_ids else '이전 실행 예외 · 현재 연결 미해결',
                         '대응범위':'현재 업무 자동검사에서 생성된 예외 조사. 공식서식 일대일 대응을 지정하지 않음.',
                         '주의':'실제 수행·증거·판단·검토는 사람이 기록해야 하며 감사완료 인증이 아님.'})
    return rows
