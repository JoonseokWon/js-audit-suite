"""Compatibility façade; implementation lives in desktop.workflow."""
from desktop.workflow.shared import *
from desktop.workflow.mixin import WorkflowDesktopMixin
from desktop.workflow.dialog import WorkflowDialog
from desktop.workflow import shared as _shared
_shared.install_facade(__name__,"desktop.workflow")
