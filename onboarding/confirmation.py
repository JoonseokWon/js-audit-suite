"""Explicit input confirmation, separate from audit judgments and workpaper approval."""
from copy import deepcopy
from common import AuditError,digest,now,text
from onboarding.integration import engine,fields


def confirm_input(module,payload,actor,reason,original_sources=(),*,confirm_adjustments=False):
    actor=text(actor,'입력 확인자');reason=text(reason,'입력 확인 사유')
    data=deepcopy(payload)
    if module=='실무자료·원장' and confirm_adjustments:
        from collections import defaultdict
        from onboarding.erp.schema import adjustment_hash
        groups=defaultdict(list)
        for row in data.get('adjustments',[]):groups[row['adjustment_id']].append(row)
        data['adjustment_approvals']=[{'adjustment_id':key,'actor':actor,'reason':reason,
            'input_hash':adjustment_hash(rows)} for key,rows in groups.items()
            if {row['status'] for row in rows}=={'승인'}]
    provider=engine(module)
    prepare=getattr(provider,'prepare_approval',None)
    if prepare:
        data=prepare(module,data) if isinstance(provider.APPROVAL_FIELDS,dict) else prepare(data)
    if original_sources:data['_origin_sources']=[{'id':s['id'],'sha256':s['sha256']} for s in original_sources]
    data['approval']={'actor':actor,'reason':reason,'at':now(),
        'input_hash':digest({key:data.get(key) for key in fields(module)})}
    data['approval']['envelope_hash']=digest({k:v for k,v in data.items() if k!='approval'})
    return data
