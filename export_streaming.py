"""Write-only builder retains the v2.3 large-ledger path and exact evidence JSON."""
import json
from common import plain
from input_limits import EXCEL_DATA_ROWS


def chunks(value,size=28000,xml_safe=False):
    # ASCII escapes make every legacy code point XML-safe and exactly reversible.
    encoder=json.JSONEncoder(ensure_ascii=xml_safe,sort_keys=True,separators=(',',':'),allow_nan=False,default=plain)
    buffer=''
    for token in encoder.iterencode(value):
        buffer+=token
        while len(buffer)>=size:yield buffer[:size];buffer=buffer[size:]
    if buffer:yield buffer


def bounded_json(value):
    """Compatibility name; the display builder splits instead of truncating."""
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False,default=plain)


def create_builder(priority,numeric,rates,quantities):
    from export_support.builder import create_builder as shared
    return shared(priority,numeric,rates,quantities,write_only=True,max_rows=EXCEL_DATA_ROWS)
