"""Requests native desktop actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill

class RequestsActions:

    def request_signature(self):
        return dumps({'id': self.current_request, 'vars': {k: v.get() for k, v in self.request_vars.items()}, 'state': self.request_state.get(), 'sources': [self.request_sources[i]['id'] for i in self.request_evidence.curselection()]})

    def clear_request(self):
        self.current_request = None
        for v in self.request_vars.values():
            v.set('')
        self.request_state.set('요청')
        self.request_evidence.selection_clear(0, 'end')
        self.request_saved = self.request_signature()

    def select_request(self, _=None):
        if not self.ws or not self.request_tree.selection():
            return
        row = list(self.ws.requests.values())[int(self.request_tree.selection()[0])]
        self.current_request = row['id']
        for k, v in self.request_vars.items():
            v.set(row[k])
        self.request_state.set(row['state'])
        self.request_evidence.selection_clear(0, 'end')
        for i, s in enumerate(self.request_sources):
            if s['id'] in row['source_ids']:
                self.request_evidence.selection_set(i)
        self.request_saved = self.request_signature()

    def save_request(self):
        self.guard()
        d = {k: v.get() for k, v in self.request_vars.items()}
        d.update(id=self.current_request, state=self.request_state.get(), source_ids=[self.request_sources[i]['id'] for i in self.request_evidence.curselection()])
        row = self.ws.save_request(d)
        self.refresh()
        self.current_request = row['id']
        self.request_saved = self.request_signature()
        self.status.set('자료요청·수령 기록 저장 완료')
