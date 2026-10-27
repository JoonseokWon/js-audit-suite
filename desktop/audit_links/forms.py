"""Small explicit forms. Every human choice starts blank in a new record."""
from tkinter import ttk
from .dialog import LinkDialog as WorkflowDialog
from common import AuditError
import audit_links


def _items(text):
    return [value.strip() for value in text.split(',') if value.strip()]


def _actor(dialog):
    dialog.entry('actor', '기록자 · 직접 입력')


def assessment_form(host, risk_id):
    d = WorkflowDialog(host, '경영진주장·고유위험·통제위험 평가')
    risk = d.ws.workflow_risks.get(risk_id)
    if not risk:
        d.close(force=True); raise AuditError('현재 위험을 먼저 선택하세요.')
    existing = audit_links.refresh(d.ws)['assessments'].get(risk_id, {})
    d.note(risk_id + ' · ' + risk['title'] + '\n등급과 유의적위험 여부는 사람이 판단합니다. 미확인은 그대로 남습니다.')
    for index, raw in enumerate(risk['assertions']):
        previous = next((a for a in existing.get('assertions', []) if a['risk_assertion'] == raw), {})
        choices = [''] + [category + ' / ' + label for category, labels in audit_links.ASSERTIONS.items() for label in labels]
        chosen = previous.get('category', '') + ' / ' + previous.get('assertion', '') if previous else ''
        d.entry('assertion_' + str(index), '기존 주장 분류: ' + raw, chosen, choices)
    for key, label in (('inherent', '고유위험'), ('control', '통제위험')):
        d.entry(key + '_rating', label + ' 등급', existing.get(key + '_rating', ''), audit_links.RATINGS)
        d.text(key + '_reason', label + ' 평가 근거', existing.get(key + '_reason', ''))
    significant = existing.get('significant_risk')
    d.entry('significant', '유의적위험 여부', '' if significant is None else '예' if significant else '아니오', ('', '예', '아니오'))
    d.text('significant_reason', '유의적위험 판단 근거', existing.get('significant_reason', '')); _actor(d)
    def value():
        choices = []
        for index, raw in enumerate(risk['assertions']):
            selected = d.value('assertion_' + str(index))
            if selected:
                category, label = selected.split(' / ', 1)
                choices.append({'risk_assertion': raw, 'category': category, 'assertion': label})
        return {'risk_id': risk_id, 'assertions': choices,
                **{key: d.value(key) for key in ('inherent_rating', 'inherent_reason', 'control_rating', 'control_reason', 'significant_reason')},
                'significant_risk': {'': None, '예': True, '아니오': False}[d.value('significant')]}
    d.button('평가 입력 저장', lambda: d.save(lambda: audit_links.save_assessment(d.ws, value(), d.value('actor'), expected_head=d.head), '사람 위험평가를 저장했어요. 대응절차를 연결하세요.'))
    d.finish(); return d


def response_form(host, risk_id, response_id=None):
    d = WorkflowDialog(host, '위험에 대응하는 감사절차 연결')
    risk = d.ws.workflow_risks.get(risk_id)
    assessment = audit_links.refresh(d.ws)['assessments'].get(risk_id)
    if not risk or not assessment:
        d.close(force=True); raise AuditError('위험과 구조화 평가를 먼저 등록하세요.')
    existing = d.ws.audit_links_state['responses'].get(response_id, {})
    d.note('원본은 직접 선택합니다. 회사·기간·원본 위치·관련성은 사람이 확인한 내용을 기록하세요. 파일해시가 내용의 진위를 인증하지 않습니다.')
    d.entry('pid', '대응절차', existing.get('procedure_id', ''), risk['procedure_ids'])
    assertion_rows = [(str(index), a['category'] + ' / ' + a['assertion'] + ' (기존: ' + a['risk_assertion'] + ')') for index, a in enumerate(assessment['assertions'])]
    d.selection('assertions', '이 절차가 대응하는 주장 · 직접 선택', assertion_rows,
                [str(i) for i, item in enumerate(assessment['assertions']) if item in existing.get('assertions', [])])
    for key, label in (('nature', '성격 · 어떤 방법으로 수행할지'), ('timing', '시기'), ('extent', '범위 · 모집단·표본·기간')):
        d.text(key, label, existing.get(key, ''))
    d.selection('sources', '관련 원본 · 직접 선택', [(s['id'], s['name'] + ' / ' + s['id']) for s in d.ws.sources.values()],
                [s['source_id'] for s in existing.get('sources', [])])
    d.entry('company_code', '선택 원본의 회사코드 · 원본 확인 후 입력')
    d.entry('start_date', '선택 원본의 기간 시작일 · YYYY-MM-DD')
    d.entry('end_date', '선택 원본의 기간 종료일 · YYYY-MM-DD')
    d.text('locator', '원본 위치 · 예: 매출 시트 2~15행 (자료별로 다르면 각각 별도 대응 연결)')
    d.text('relevance', '이 위험·주장·절차에 관련되는 이유')
    d.selection('runs', '실행·결과해시 연결 · 해당 절차 모듈과 원장만 선택', [(r['id'], r['module'] + ' / ' + r['id']) for r in d.ws.latest().values()],
                [r['run_id'] for r in existing.get('runs', [])])
    _actor(d)
    def value():
        return {**({'id': response_id} if response_id else {}), 'risk_id': risk_id, 'procedure_id': d.value('pid'),
                'assertions': [assessment['assertions'][int(i)] for i in d.value('assertions')],
                **{key: d.value(key) for key in ('nature', 'timing', 'extent')},
                'sources': [{'source_id': sid, **{key: d.value(key) for key in ('company_code', 'start_date', 'end_date', 'locator', 'relevance')}} for sid in d.value('sources')],
                'run_ids': d.value('runs')}
    d.button('대응계획·근거 연결 저장', lambda: d.save(lambda: audit_links.save_response(d.ws, value(), d.value('actor'), expected_head=d.head), '대응계획을 연결했어요. 실제 수행기록은 별도로 작성하세요.'))
    d.finish(); return d


def retire_form(host):
    d = WorkflowDialog(host, '이전 위험·대응 연결 사용 해제')
    d.note('기록을 삭제하지 않습니다. 범위 변경·오래된 중복 연결을 사용하는 것을 해제하고 사유를 남깁니다. 기존 승인·검토가 다시 유효해지지 않습니다.')
    d.entry('collection', '기록 종류', '', ('assessments', 'responses', 'performances', 'workpapers'))
    d.entry('record_id', '해제할 정확한 기록ID'); d.text('reason', '사용 해제 사유'); _actor(d)
    d.button('사용 해제 기록', lambda: d.save(lambda: audit_links.retire(d.ws, d.value('collection'), d.value('record_id'),
        d.value('actor'), d.value('reason'), expected_head=d.head), '사용 해제 사유를 기록했어요. 현재 연결 누락을 확인하세요.'))
    d.finish(); return d


def performance_form(host, response_id):
    d = WorkflowDialog(host, '실제 감사절차 수행기록')
    d.note('자동검사 실행과 실제 감사 수행은 다릅니다. 직접 수행한 내용만 기록하세요. 저장하면 기존 조서·승인은 변경된 수행 근거에 맞춰 다시 확인해야 합니다.')
    for key, label in (('performed', '실제 수행내용'), ('performed_date', '실제 수행일자 · YYYY-MM-DD'), ('performer', '실제 수행자')):
        d.text(key, label)
    d.entry('sufficiency', '증거 충분성·적합성에 관한 사람 판단', '', ('', '충분', '추가절차필요', '판단보류'))
    d.text('sufficiency_reason', '판단 근거 · 추가절차와 한계'); _actor(d)
    def value():
        return {'response_id': response_id, **{key: d.value(key) for key in ('performed', 'performed_date', 'performer', 'sufficiency', 'sufficiency_reason')}}
    d.button('사람 수행기록 저장', lambda: d.save(lambda: audit_links.save_performance(d.ws, value(), d.value('actor'), expected_head=d.head), '수행기록을 저장했어요. 현재 근거로 조서를 저장한 뒤 연결하세요.'))
    d.finish(); return d


def binding_form(host, response_id):
    d = WorkflowDialog(host, '현재 수행기록과 조서·미해결사항 연결')
    response = audit_links.refresh(d.ws)['responses'].get(response_id)
    if not response:
        d.close(force=True); raise AuditError('대응 연결을 선택하세요.')
    d.note('먼저 현재 수행기록을 반영해 해당 조서를 저장하세요. 연결은 승인이나 별도 검토를 대신하지 않습니다.')
    d.entry('workpaper_id', '대응절차와 동일한 조서ID', response['procedure_id'], (response['procedure_id'],))
    d.selection('note_ids', '연결할 검토의견 · 미해결은 계속 미해결로 표시', [(n['id'], n['title']) for n in d.ws.notes.values()])
    d.entry('f03_id', '왜곡표시 조서 연결 · 해당하는 경우 직접 선택', '', ('', 'F03'))
    d.entry('misstatement_ids', '왜곡표시ID · 해당하는 경우 쉼표 구분'); _actor(d)
    def value():
        return {'workpaper_id': d.value('workpaper_id'), 'note_ids': d.value('note_ids'),
                'f03_id': d.value('f03_id'), 'misstatement_ids': _items(d.value('misstatement_ids'))}
    d.button('현재 조서 연결 저장', lambda: d.save(lambda: audit_links.bind_workpaper(d.ws, response_id, value(), d.value('actor'), expected_head=d.head), '현재 조서 연결을 저장했어요. 별도 검토와 미해결사항을 확인하세요.'))
    d.finish(); return d
