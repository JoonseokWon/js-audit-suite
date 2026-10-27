"""Canonical table hashes without a second full JSON string in memory."""
import hashlib
import json
from common import plain


def canonical_hash(value):
    hasher=hashlib.sha256()
    encoder=json.JSONEncoder(ensure_ascii=False,sort_keys=True,separators=(',',':'),
                             allow_nan=False,default=plain)
    def feed(item):
        for chunk in encoder.iterencode(plain(item)):hasher.update(chunk.encode('utf-8'))
    if isinstance(value,(list,tuple)):
        # Normalize only one row at a time. This retains common.digest's exact
        # key conversion while avoiding a second copy of the entire table.
        hasher.update(b'[')
        for index,item in enumerate(value):
            if index:hasher.update(b',')
            feed(item)
        hasher.update(b']')
    else:feed(value)
    return hasher.hexdigest()
