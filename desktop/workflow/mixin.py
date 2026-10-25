"""Composition of the small workflow UI controllers."""
from .view import WorkflowView
from .profile import ProfileActions
from .risk import RiskActions
from .procedure import ProcedureActions
from .archive import ArchiveActions

class WorkflowDesktopMixin(WorkflowView,ProfileActions,RiskActions,ProcedureActions,ArchiveActions):
    pass
