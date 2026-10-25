"""Compose small screen and action mixins without owning app state or engines."""
from ai_desktop import AIDesktopMixin
from workflow_desktop import WorkflowDesktopMixin
from desktop.actions.display import DisplayActions
from desktop.actions.navigation import NavigationActions
from desktop.actions.company import CompanyActions
from desktop.actions.workspaces import WorkspacesActions
from desktop.actions.execution import ExecutionActions
from desktop.actions.history import HistoryActions
from desktop.actions.risks import RisksActions
from desktop.actions.requests import RequestsActions
from desktop.actions.results import ResultsActions
from desktop.actions.workpapers import WorkpapersActions
from desktop.actions.evidence import EvidenceActions
from desktop.actions.refresh import RefreshActions
from desktop.actions.lifecycle import LifecycleActions
from desktop.views.inputs import InputsView
from desktop.views.lead import LeadView
from desktop.views.results import ResultsView
from desktop.views.workpapers import WorkpapersView
from desktop.views.evidence import EvidenceView
from desktop.views.requests import RequestsView
from desktop.views.history import HistoryView
from desktop.views.risks import RisksView


class BaseAuditApp(
    DisplayActions,
    NavigationActions,
    CompanyActions,
    WorkspacesActions,
    ExecutionActions,
    HistoryActions,
    RisksActions,
    RequestsActions,
    ResultsActions,
    WorkpapersActions,
    EvidenceActions,
    RefreshActions,
    LifecycleActions,
    InputsView,
    LeadView,
    ResultsView,
    WorkpapersView,
    EvidenceView,
    RequestsView,
    HistoryView,
    RisksView,
    WorkflowDesktopMixin,
    AIDesktopMixin,
):
    """Behavior contract for the native desktop shell; shell owns initialization."""

