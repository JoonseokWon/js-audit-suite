"""Compatibility façade; implementation lives in desktop.ai."""
from desktop.ai.shared import *
from desktop.ai.mixin import AIDesktopMixin
from desktop.ai import shared as _shared
_shared.install_facade(__name__,"desktop.ai")
