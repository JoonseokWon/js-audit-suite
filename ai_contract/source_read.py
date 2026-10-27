"""Reuse the current accepted ledger's existing limits, never other modules'."""
from common import read_xlsx
from input_limits import LEDGER_LIMITS


def read_source_tables(ws,source_id,path,event=None):
    ledger=ws.latest().get('원장·리드')
    limits=LEDGER_LIMITS if ledger and ledger.get('source_id')==source_id else None
    return read_xlsx(path,event=event,row_limits=limits)
