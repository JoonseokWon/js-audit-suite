"""Read-only replay and independent data/profile pins; no automatic judgments."""
from copy import deepcopy
from common import AuditError, digest

EVENTS = {'misstatement_record', 'misstatement_group',
          'misstatement_verification', 'misstatement_reconfirm'}


def state(ws):
    out = {name:{} for name in ('records', 'groups', 'verifications', 'reconfirmations')}
    names = {'misstatement_record':'records', 'misstatement_group':'groups',
             'misstatement_verification':'verifications', 'misstatement_reconfirm':'reconfirmations'}
    for event in ws.events:
        if event['kind'] in names:
            item = event['data']; key = item['id'] if event['kind'] in (
                'misstatement_record', 'misstatement_group') else item['record_id']
            out[names[event['kind']]][key] = item
    return out


def input_basis(ws):
    """Exclude our own events and workpaper edits to avoid self-invalidating pins."""
    return {'data_basis':ws.data_basis(), 'profile_hash':digest(ws.workflow_profile)}


def basis(ws):
    events = [event for event in ws.events if event['kind'] in EVENTS]
    return digest(events) if events else None


def list_records(ws):
    return deepcopy(list(state(ws)['records'].values()))


def get_record(ws, record_id):
    try:return deepcopy(state(ws)['records'][record_id])
    except KeyError as exc:raise AuditError('없는 왜곡표시 검토기록 ID') from exc


def current(ws, record, replay=None):
    replay = replay or state(ws)
    reconfirm = replay['reconfirmations'].get(record['id'], {})
    pin = reconfirm.get('input_basis') if reconfirm.get('record_revision') == record['revision'] else record['input_basis']
    return pin == input_basis(ws)


def ledger_ref(ws):
    run = ws.latest().get('원장·리드')
    return ({key:run[key] for key in ('id', 'source_id', 'result_hash')}
            if run else None)
