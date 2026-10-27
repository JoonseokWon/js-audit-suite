"""Mechanical gaps, relevance and freshness; never an automated audit conclusion."""
from copy import deepcopy
from common import digest
from .state import refresh, pin, latest_performance, latest_binding, workpaper_hash, SCOPE


def assessment_issues(ws, assessment, current=None):
    current = current or pin(ws); rid = assessment['risk_id']; risk = ws.workflow_risks.get(rid)
    issues = []
    if not risk:
        return [('RISK_ORPHAN', '현재 등록 위험ID가 없습니다.')]
    if assessment['pin'] != current or assessment['risk_hash'] != digest(risk) or risk['basis'] != current['data_basis']:
        issues.append(('ASSESSMENT_STALE', '자료·실행 또는 기존 위험평가가 변경되었습니다.'))
    for kind in ('inherent', 'control'):
        if not assessment[kind + '_rating'] or not assessment[kind + '_reason']:
            label = '고유위험' if kind == 'inherent' else '통제위험'
            issues.append((kind.upper() + '_UNASSESSED', label + ' 등급과 평가 근거를 사람이 기록하세요.'))
    if assessment['significant_risk'] is None or not assessment['significant_reason']:
        issues.append(('SIGNIFICANT_UNASSESSED', '유의적위험 여부와 근거를 사람이 기록하세요.'))
    mapped = {item['risk_assertion'] for item in assessment['assertions']}
    for assertion in set(risk['assertions']) - mapped:
        issues.append(('ASSERTION_UNCLASSIFIED', '기존 위험의 경영진주장 미분류: ' + assertion))
    return issues


def response_issues(ws, response, state, current=None):
    current = current or pin(ws); issues = []
    rid, pid = response['risk_id'], response['procedure_id']
    risk = ws.workflow_risks.get(rid); link = ws.workflow_procedure_links.get(pid)
    assessment = state['assessments'].get(rid)
    scopes = (ws.workflow_profile or {}).get('scope', [])
    active = {item['procedure_id'] for item in scopes if item['applicable']}
    if not risk or not link or pid not in active or pid not in risk['procedure_ids'] or rid not in link['risk_ids']:
        return [('RESPONSE_ORPHAN', '현재 위험·적용 절차의 대응관계가 없습니다.')]
    if (response['pin'] != current or response['risk_hash'] != digest(risk) or
            response['workflow_link_hash'] != digest(link) or not assessment or
            response['assessment_revision'] != assessment['revision']):
        issues.append(('RESPONSE_STALE', '자료·실행·평가·기존 대응계획 변경 후 연결을 갱신하세요.'))
    if assessment:
        issues.extend(assessment_issues(ws, assessment, current))
    for source in response['sources']:
        actual = ws.sources.get(source['source_id'])
        if not actual or actual['sha256'] != source['sha256']:
            issues.append(('SOURCE_STALE', '선택 원본ID·해시가 현재 등록 원본과 다릅니다.'))
        if not all(source.get(key) for key in ('company_code', 'start_date', 'end_date', 'locator', 'relevance')):
            issues.append(('SOURCE_SCOPE_UNCONFIRMED', '선택 원본의 회사·기간·위치·관련성을 사람이 확인하세요.'))
    for saved in response['runs']:
        run = ws.runs.get(saved['run_id'])
        if (not run or run['result_hash'] != saved['result_hash'] or
                ws.latest().get(saved['module'], {}).get('id') != saved['run_id']):
            issues.append(('RUN_STALE', '선택 실행ID·결과해시가 최신 실행과 다릅니다.'))
    module = ws.procedure_module(pid)
    if module and not any(run['module'] == module for run in response['runs']):
        issues.append(('PROCEDURE_RUN_UNSELECTED', '대응절차의 모듈 실행·결과해시가 선택되지 않았습니다.'))
    return issues


def binding_issues(ws, response, performance, binding):
    if not binding:
        return [('WORKPAPER_LINK_MISSING', '현재 수행기록을 반영한 조서를 저장하고 연결하세요.')]
    issues = []; pid = response['procedure_id']; paper = ws.procedures.get(pid)
    if binding['response_revision'] != response['revision'] or binding['performance_revision'] != performance['revision']:
        issues.append(('WORKPAPER_LINK_STALE', '대응·수행기록 변경 후 조서 연결이 갱신되지 않았습니다.'))
    if (not paper or paper.get('basis') != ws.basis() or
            workpaper_hash(paper) != binding['paper_hash'] or paper.get('edit_revision') != binding['edit_revision']):
        issues.append(('WORKPAPER_CHANGED', '연결 이후 조서 본문·근거가 변경되었거나 조서가 없습니다.'))
    elif ws.procedure_state(paper) != '검토기록완료':
        issues.append(('WORKPAPER_REVIEW_PENDING', '조서의 현재 내용은 별도 사람 검토가 필요합니다.'))
    if binding['f03_id']:
        f03 = ws.procedures.get('F03')
        if not f03 or f03.get('excluded') or f03.get('basis') != ws.basis() or workpaper_hash(f03) != binding['f03_hash']:
            issues.append(('F03_STALE', '왜곡표시 F03 조서의 본문·근거가 변경되었습니다.'))
        elif ws.procedure_state(f03) != '검토기록완료':
            issues.append(('F03_REVIEW_PENDING', '연결한 F03 조서의 현재 내용도 별도 사람 검토가 필요합니다.'))
    for identifier in binding['note_ids']:
        note = ws.notes.get(identifier)
        if not note or digest(note) != binding['note_hashes'][identifier]:
            issues.append(('NOTE_CHANGED', '연결 검토의견이 변경되어 후속 연결 확인이 필요합니다.'))
        if note and not note['resolved']:
            issues.append(('NOTE_UNRESOLVED', '연결된 미해결 검토의견: ' + note['title']))
    if binding['misstatement_ids']:
        from misstatements import get_record, record_status
        for identifier in binding['misstatement_ids']:
            try:
                record = get_record(ws, identifier)
                item_status = record_status(ws, identifier)
                valid = record['revision'] == binding['misstatement_revisions'][identifier] and item_status['current']
                if not item_status['complete']:
                    issues.append(('MISSTATEMENT_PENDING', '연결 왜곡표시의 사람 분류·회사확인·판단 또는 조정 검증에 미확인이 남아 있습니다.'))
            except Exception:
                valid = False
            if not valid:
                issues.append(('MISSTATEMENT_STALE', '왜곡표시 연결ID·현재 자료 또는 판단기록이 변경되었습니다.'))
    return issues


def status(ws):
    state = refresh(ws); active = any(event['kind'].startswith('audit_link_') for event in ws.events)
    rows = []; current = pin(ws) if active else None
    def add(code, message, rid='', pid='', response_id='', ok=False):
        rows.append({'code': code, 'risk_id': rid, 'procedure_id': pid, 'response_id': response_id,
                     'status': '기록연결확인' if ok else '미확인·조치필요', 'message': message, 'ok': ok})
    if active:
        if ws.verify_sources():
            add('SOURCE_INTEGRITY', '등록 원본 사본이 변경·누락되었습니다.')
        for rid, risk in ws.workflow_risks.items():
            assessment = state['assessments'].get(rid)
            if not assessment:
                add('ASSESSMENT_MISSING', '분류된 경영진주장·고유위험·통제위험 평가가 없습니다.', rid)
                continue
            for code, message in assessment_issues(ws, assessment, current):
                add(code, message, rid)
            candidates = [r for r in state['responses'].values() if r['risk_id'] == rid]
            for assertion in assessment['assertions']:
                if not any(assertion in r['assertions'] for r in candidates):
                    add('ASSERTION_RESPONSE_MISSING', '주장에 대응절차 연결 없음: ' + assertion['category'] + ' / ' + assertion['assertion'], rid)
            for pid in risk['procedure_ids']:
                if not any(r['procedure_id'] == pid for r in candidates):
                    add('RISK_RESPONSE_MISSING', '기존 위험에 연결된 대응절차의 구조화 연결이 없습니다.', rid, pid)
        for rid in set(state['assessments']) - set(ws.workflow_risks):
            add('RISK_ORPHAN', '등록 위험이 사용 해제되어 평가가 고아 연결로 남았습니다.', rid)
        for identifier, response in state['responses'].items():
            issues = response_issues(ws, response, state, current)
            performance = latest_performance(state, identifier)
            if not performance:
                issues.append(('NOT_PERFORMED', '자동검사·해시 확인과 별개로 사람이 실제 수행내용·일자·수행자를 기록해야 합니다.'))
            else:
                if performance['pin'] != current or performance['response_revision'] != response['revision']:
                    issues.append(('PERFORMANCE_STALE', '실제 수행기록의 자료·대응 버전이 변경되었습니다.'))
                if not all(performance.get(k) for k in ('performed', 'performed_date', 'performer')):
                    issues.append(('NOT_PERFORMED', '사람 실제 수행기록 미입력'))
                if performance['sufficiency'] != '충분' or not performance['sufficiency_reason']:
                    issues.append(('SUFFICIENCY_PENDING', '증거 충분성·적합성은 사람이 판단하고 근거를 기록해야 합니다.'))
                issues.extend(binding_issues(ws, response, performance, latest_binding(state, identifier)))
            for code, message in issues:
                add(code, message, response['risk_id'], response['procedure_id'], identifier)
            if not issues:
                add('LINK_RECORDS_CURRENT', '현재 버전의 사람 입력·수행·조서 연결을 확인했습니다. 감사완료 인증이 아닙니다.',
                    response['risk_id'], response['procedure_id'], identifier, True)
        if not ws.workflow_risks:
            add('RISK_REGISTER_EMPTY', '현재 등록 위험이 없습니다. 사람이 식별한 위험을 기존 감사계획에 등록하세요.')
        for record in state['performances'].values():
            if record['response_id'] not in state['responses']:
                add('PERFORMANCE_ORPHAN', '사용 해제된 대응에 수행기록이 남아 있습니다.', response_id=record['response_id'])
        for record in state['workpapers'].values():
            if record['response_id'] not in state['responses']:
                add('WORKPAPER_ORPHAN', '사용 해제된 대응에 조서 연결기록이 남아 있습니다.', response_id=record['response_id'])
    return {'schema': 'audit-links-1', 'active': active, 'rows': rows,
            'blockers': [r for r in rows if not r['ok']], 'scope': SCOPE, **deepcopy(state)}
