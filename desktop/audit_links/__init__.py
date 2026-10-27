"""Head-pinned risk/response/performance/workpaper navigation."""
import json
from tkinter import ttk
from common import AuditError
from .dialog import LinkDialog as WorkflowDialog
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree
from desktop_display import create_scrolled_text
from export_support.text import display_text
import audit_links
from .forms import assessment_form, response_form, performance_form, binding_form, retire_form


def open_dialog(host):
    d = WorkflowDialog(host, '위험평가·감사절차·조서 연결')
    state = audit_links.status(d.ws)
    d.note('1 위험 분류·평가 → 2 대응계획·원본/실행 연결 → 3 실제 수행기록 → 4 현재 조서 저장 → 5 조서 연결·별도 검토\n' + state['scope'])
    listing = tree(d.body, ('위험ID', '절차ID', '대응ID', '상태', '내용'), height=9)
    for index, row in enumerate(state['rows']):
        listing.insert('', 'end', iid=str(index), values=[display_text(row[k]) for k in ('risk_id', 'procedure_id', 'response_id', 'status', 'message')])
    d.entry('risk_id', '평가·대응을 작성할 기존 위험ID · 직접 선택', '', tuple(d.ws.workflow_risks))
    d.entry('response_id', '수행기록·조서를 연결할 대응ID · 직접 선택', '', tuple(state['responses']))
    def selected(_=None):
        ids = listing.selection()
        if not ids: return
        row = state['rows'][int(ids[0])]
        d.fields['risk_id'].set(row['risk_id']); d.fields['response_id'].set(row['response_id'])
    listing.bind('<<TreeviewSelect>>', selected)
    bar = FlowFrame(d.body); bar.pack(fill='x', padx=10, pady=10)
    def navigate(fn, key):
        identifier = d.value(key)
        if not identifier: raise AuditError('작성할 위험 또는 대응ID를 직접 선택하세요.')
        d.close(force=True); return fn(host, identifier)
    for label, fn, key in (('위험평가 입력', assessment_form, 'risk_id'), ('대응계획·근거 연결', response_form, 'risk_id'),
                           ('실제 수행기록', performance_form, 'response_id'), ('조서·미해결사항 연결', binding_form, 'response_id')):
        bar.add(ttk.Button(bar, text=label, command=lambda f=fn, k=key: host.call(lambda: navigate(f, k))))
    def update_response():
        identifier = d.value('response_id'); response = state['responses'].get(identifier)
        if not response: raise AuditError('갱신할 대응ID를 선택하세요.')
        d.close(force=True); return response_form(host, response['risk_id'], identifier)
    bar.add(ttk.Button(bar, text='선택 대응 갱신', command=lambda: host.call(update_response)))
    bar.add(ttk.Button(bar, text='이전 연결 사용 해제', command=lambda: (d.close(force=True), retire_form(host))))
    text = create_scrolled_text(d.body, height=8, wrap='word'); text.audit_container.pack(fill='both', expand=True, padx=10)
    text.insert('1.0', display_text(json.dumps(state, ensure_ascii=False, indent=2))); text.configure(state='disabled')
    d.win.audit_links_tree = listing; d.win.audit_links_state = state
    d.finish(); return d
