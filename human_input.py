"""Validate the original human string before any existing whitespace trimming."""
from common import text as normalized_text
from export_support.text import require_xml_text


def text(value,label='값'):
    require_xml_text(value,label)
    return normalized_text(value,label)
