"""Composition of the small ai UI controllers."""
from .state import AIState
from .jobs import AIJobs
from .dialogs import AIDialogs
from .settings import AISettings

class AIDesktopMixin(AIState,AIJobs,AIDialogs,AISettings):
    pass
