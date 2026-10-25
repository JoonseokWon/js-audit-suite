"""Account-specific, evidence-linked mechanical support before human review."""
from .shared import APPROVAL_FIELDS, area_name


def approval_fields(area):
    return APPROVAL_FIELDS[area_name(area)]


def analyze(area, payload, context, ledger_result, event=None):
    from . import assets, sampling, confirmations, notes, classification
    area = area_name(area)
    engine = dict(zip(APPROVAL_FIELDS, (assets, sampling, confirmations, notes, classification)))[area]
    return engine.analyze(payload, context, ledger_result, event)


def sample(area, context):
    from .samples import build
    return build(area_name(area), context)


def negative_cases(area, context):
    from .samples import negatives
    return negatives(area_name(area), context)


from .labels import FIELD_LABELS
from .schema import TABLE_FIELDS


def prepare_approval(area, payload, ledger_result=None):
    """Refresh population metadata only after the UI's explicit human action.

    Never rebase ledger identity, edit numeric/policy inputs or create approval.
    """
    from .shared import population_hash
    area = area_name(area)
    payload['policy']['population_hash'] = population_hash(area, payload)
    return payload
