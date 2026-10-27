"""User inputs and isolated synthetic integration flows; no model calls."""
from .factory import create_demo, load_extension
from .case import actual_case


def complete_actual(ws, packet, response, out, check):
    from .flow import complete_actual as complete
    return complete(ws, packet, response, out, check)
