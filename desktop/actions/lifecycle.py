"""Lifecycle native desktop actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill

class LifecycleActions:

    def export_dialog(self, final):

        def op():
            self.guard()
            if not self.check_draft():
                return
            path = filedialog.asksaveasfilename(parent=self.root, defaultextension='.xlsx', initialfile='통합감사_검토완료.xlsx' if final else '통합감사_초안.xlsx', filetypes=[('Excel 조서', '*.xlsx')])
            if path:
                exporter.export(self.ws, path, CATALOG, final)
                self.status.set('조서 저장: ' + path)
        self.call(op)

    def close(self):
        modal = getattr(self, 'wf_modal', None)
        if modal is not None and modal.win.winfo_exists() and (not modal.close()):
            return
        if self.busy:
            self.closing = True
            self.cancel.set()
            self.status.set('취소·이력 저장 후 종료 중…')
        elif self.check_navigation():
            self.shutdown_ai()
            self.root.destroy()
