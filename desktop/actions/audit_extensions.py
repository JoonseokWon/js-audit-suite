"""Small entry points; feature dialogs own their current-head save lifecycle."""


class AuditExtensionActions:
    def open_misstatements(self):
        self.guard()
        from desktop.misstatements import open_dialog
        return open_dialog(self)

    def open_audit_links(self):
        self.guard()
        from desktop.audit_links import open_dialog
        return open_dialog(self)
