"""Workpapers native desktop actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill

class WorkpapersActions:

    def task_list(self):
        from procedures import task_definitions
        return task_definitions(self.ws, CATALOG)

    def on_procedure_select(self, _=None):
        selected = self.proc_tree.selection()
        if not selected:
            return
        pid = self.tasks[int(selected[0])]['id']
        if pid == self.current_pid:
            return
        if self.check_navigation():
            self.load_procedure(pid)
        else:
            # Keep the highlighted row consistent with the still-visible text.
            current = next((str(index) for index, task in enumerate(self.tasks)
                            if task['id'] == self.current_pid), None)
            if current is not None:
                self.proc_tree.selection_set(current)
            else:
                self.proc_tree.selection_remove(*self.proc_tree.selection())

    def load_procedure(self, pid):
        task = next((x for x in self.task_list() if x['id'] == pid))
        p = self.ws.procedures.get(pid, task) if self.ws else task
        self.current_pid = pid
        self.current_title = p['title']
        self.proc_heading.set(p['title'] + ' / ' + (self.ws.procedure_state(p) if self.ws and 'basis' in p else '미착수'))
        for key, var in self.proc_vars.items():
            var.set(p.get(key, self.ws.engagement['작성자'] if key == 'preparer' and self.ws else ''))
        self.excluded.set(p.get('excluded', False))
        for key, t in self.proc_text.items():
            t.delete('1.0', 'end')
            t.insert('1.0', p.get('excluded_reason', '') if key == 'risk' and p.get('excluded') else p.get(key, ''))
        self.evidence_list.selection_clear(0, 'end')
        for i, s in enumerate(self.evidence_sources):
            if s['id'] in p.get('evidence_ids', []):
                self.evidence_list.selection_set(i)
        self.reviewer.set(p.get('reviewer', ''))
        self.review_note.set(p.get('review_note', ''))
        self.review_saved = (self.reviewer.get(), self.review_note.get())
        self.saved_signature = self.form_signature()
        self.refresh_ai_status()

    def save_procedure(self):
        self.guard()
        if not self.current_pid:
            raise AuditError('절차를 선택하세요.')
        pending_review = self._pending_review_input()
        p = {'id': self.current_pid, 'title': self.current_title, **{k: v.get() for k, v in self.proc_vars.items()}, **{k: t.get('1.0', 'end').strip() for k, t in self.proc_text.items()}, 'excluded': self.excluded.get(), 'evidence_ids': [self.evidence_sources[i]['id'] for i in self.evidence_list.curselection()]}
        task = next((task for task in self.task_list() if task['id'] == self.current_pid), {})
        if task.get('purpose_code'):
            p['purpose_code'] = task['purpose_code']
        if p['excluded']:
            p['excluded_reason'] = p['risk']
        self.ws.save_procedure(p)
        self.refresh()
        self._restore_pending_review(pending_review)
        self.status.set('조서 개정 저장. 이전 검토는 다시 받아야 합니다.')

    def request_review(self):
        self.guard()
        pending_review = self._pending_review_input()
        if self.dirty():
            self.save_procedure()
        self.ws.request_review(self.current_pid)
        self.refresh()
        self._restore_pending_review(pending_review)

    def _pending_review_input(self):
        value = (self.reviewer.get(), self.review_note.get())
        return value if value != self.review_saved else None

    def _restore_pending_review(self, value):
        # Keep only unsaved UI text. This does not write review/approval records.
        if value is not None:
            self.reviewer.set(value[0])
            self.review_note.set(value[1])

    def review(self, accepted):
        self.guard()
        if self.dirty():
            raise AuditError('조서 수정 후 저장·검토요청을 다시 진행하세요.')
        self.ws.review(self.current_pid, self.reviewer.get(), self.review_note.get(), accepted)
        self.refresh()

    def select_issue(self, _=None):
        selected = self.issue_tree.selection()
        if selected and self.check_navigation():
            r, i = self.issue_items[int(selected[0])]
            self.nb.select(self.tabs['절차·조서'])
            self.load_procedure('X-' + r['id'] + '-' + str(i))
