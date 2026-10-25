"""Navigation native desktop actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill

class NavigationActions:

    def open_workpaper_draft(self):
        if not self.ws:
            raise AuditError('먼저 모회사·자회사를 선택하거나 업무를 여세요. 이후 계정별 조서 초안을 작성할 수 있습니다.')
        self.guard()
        if not self.check_navigation():
            return False
        self.nb.select(self.tabs['절차·조서'])
        if self.current_pid:
            self.status.set('작성 중인 조서를 유지합니다. 저장·개정 후 초안 Excel로 내보내세요.')
            return self.current_pid
        from common import PROCEDURE_MODULES
        preferred = next((pid for pid, module in PROCEDURE_MODULES.items() if module == self.result_module.get()), 'C04')
        if preferred not in {t['id'] for t in self.tasks}:
            preferred = 'C04'
        self.load_procedure(preferred)
        index = next((i for i, t in enumerate(self.tasks) if t['id'] == preferred))
        self.proc_tree.selection_set(str(index))
        self.proc_tree.see(str(index))
        self.status.set('계정별 초안: 목적·범위·계산 근거를 확인하고 실제 수행·판단을 입력한 뒤 조서 저장·개정을 누르세요.')
        return preferred

    def open_workflow_view(self):
        self.guard()
        if not self.check_navigation():
            return False
        self.refresh_workflow()
        self.nb.select(self.tabs['계획·절차·취합'])
        return True

    def set_busy(self, value):
        self.busy = value
        if value:
            self.disabled_widgets = []

            def disable(parent):
                for w in parent.winfo_children():
                    if isinstance(w, ttk.Widget):
                        previous = w.state()
                        w.state(['disabled'])
                        self.disabled_widgets.append((w, 'ttk', previous))
                    elif isinstance(w, (tk.Text, tk.Listbox)) or getattr(w, 'audit_native_text', False):
                        previous = w.cget('state')
                        w.configure(state='disabled')
                        self.disabled_widgets.append((w, 'tk', previous))
                    disable(w)
            disable(self.nb)
            self.root.focus_set()
            self.sector_box.configure(state='disabled')
            self.sector_new.configure(state='disabled')
            self.sector_cancel.configure(state='normal')
        else:
            for w, kind, previous in getattr(self, 'disabled_widgets', []):
                if kind == 'ttk':
                    w.state(['!disabled', *previous])
                else:
                    w.configure(state=previous)
            self.disabled_widgets = []
            self.sector_box.configure(state='readonly')
            self.sector_new.configure(state='normal')
            self.sector_cancel.configure(state='disabled')

    def reset_workspace_view(self):
        self.current_pid = None
        self.current_request = None
        self.file.set('')
        self.search.set('')
        self.result_module.set('')
        self.result_table.set('')
        self.page = 0
        self.table_rows = []
        self.visible_rows = []
        if hasattr(self, 'wf_detail'):
            self.wf_state = {}
            self.wf_last_archive = {}
            self.wf_detail.configure(state='normal')
            self.wf_detail.delete('1.0', 'end')
            self.wf_detail.configure(state='disabled')
        for var in self.proc_vars.values():
            var.set('')
        for text in list(self.proc_text.values()) + [self.row_text, self.risk_detail]:
            text.delete('1.0', 'end')
        self.set_history_text('')
        self.excluded.set(False)
        self.reviewer.set('')
        self.review_note.set('')
        self.review_saved = ('', '')
        self.evidence_list.selection_clear(0, 'end')
        self.proc_heading.set('절차를 선택하세요. 실제 수행·판단·검토는 별도로 기록합니다.')
        self.clear_request()
        self.saved_signature = self.form_signature()

    def check_navigation(self):
        pending_request = {k: v.get() for k, v in self.request_vars.items()}
        pending_state = self.request_state.get()
        pending_ids = [self.request_sources[i]['id'] for i in self.request_evidence.curselection()]
        pending_review = (self.reviewer.get(), self.review_note.get())
        if not self.check_draft():
            return False
        for k, v in self.request_vars.items():
            v.set(pending_request[k])
        self.request_state.set(pending_state)
        self.request_evidence.selection_clear(0, 'end')
        for i, s in enumerate(self.request_sources):
            if s['id'] in pending_ids:
                self.request_evidence.selection_set(i)
        self.reviewer.set(pending_review[0])
        self.review_note.set(pending_review[1])
        if self.request_signature() != getattr(self, 'request_saved', self.request_signature()):
            answer = messagebox.askyesnocancel('미저장 자료요청', '자료요청 수정 내용을 저장한 뒤 이동할까요? 아니오를 선택하면 수정 내용을 버립니다.', parent=self.root)
            if answer is None:
                return False
            if answer:
                try:
                    self.save_request()
                except Exception as e:
                    messagebox.showerror('저장 필요', str(e), parent=self.root)
                    return False
                self.reviewer.set(pending_review[0])
                self.review_note.set(pending_review[1])
        if (self.reviewer.get(), self.review_note.get()) != self.review_saved:
            if not messagebox.askokcancel('미저장 검토 입력', '검토자·검토내용 입력이 아직 검토기록으로 저장되지 않았습니다. 이 입력을 버리고 이동할까요?', parent=self.root):
                return False
        return True

    def guard(self):
        if self.busy:
            raise AuditError('검사가 실행 중입니다. 완료 또는 취소 후 변경하세요.')
        if not self.ws:
            raise AuditError('업무를 먼저 만들거나 여세요.')

    def call(self, fn):
        try:
            return fn()
        except Exception as e:
            self.status.set(str(e))
            messagebox.showerror('확인 필요', str(e), parent=self.root)
            return None

    def form_signature(self):
        return dumps({'id': self.current_pid, 'vars': {k: v.get() for k, v in self.proc_vars.items()}, 'text': {k: t.get('1.0', 'end').strip() for k, t in self.proc_text.items()}, 'excluded': self.excluded.get(), 'evidence': [self.evidence_sources[i]['id'] for i in self.evidence_list.curselection()]})

    def dirty(self):
        return bool(self.current_pid and hasattr(self, 'saved_signature') and (self.form_signature() != self.saved_signature))

    def check_draft(self):
        if not self.dirty():
            return True
        answer = messagebox.askyesnocancel('미저장 조서', '작성 중인 조서를 저장한 뒤 이동할까요? 아니오를 선택하면 수정 내용을 버립니다.', parent=self.root)
        if answer is None:
            return False
        if answer:
            try:
                self.save_procedure()
            except Exception as e:
                messagebox.showerror('저장 필요', str(e), parent=self.root)
                return False
        return True
