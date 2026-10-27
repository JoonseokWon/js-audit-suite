"""Reuse lifecycle/IME controls while preserving original human input for validation."""
import tkinter as tk
from desktop.workflow.dialog import WorkflowDialog
from export_support.text import validate_structure


class LinkDialog(WorkflowDialog):
    def value(self, key):
        field = self.fields[key]
        if isinstance(field, tuple):
            box, records = field
            return [records[i][0] for i in box.curselection()]
        value = field.get() if isinstance(field, tk.Variable) else field.get('1.0', 'end-1c')
        validate_structure(value, key)
        return value
