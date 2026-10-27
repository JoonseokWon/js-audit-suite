"""A human may identify duplicate findings; suggestions never change totals."""
import uuid
from common import AuditError, now
from human_input import text
from .schema import payload, ids, identity, optional
from .state import state, input_basis


def save_group(ws, value, actor, *, expected_head=None):
    before=ws.assert_writeable(expected_head=expected_head)
    if ws.verify_sources():raise AuditError('등록한 원본 사본 변경/누락')
    raw=payload(value,('id','member_ids','primary_id','reason','amount_resolution','active'),
                ('member_ids','primary_id','reason'))
    replay=state(ws);members=ids(raw['member_ids'],'동일오류 회원ID')
    if len(members)<2 or any(key not in replay['records'] for key in members):raise AuditError('동일오류 그룹은 기존 기록 2개 이상을 명시하세요.')
    primary=identity(raw['primary_id'])
    if primary not in members:raise AuditError('금액 대표기록은 그룹 회원이어야 합니다.')
    gid=identity(raw.get('id') or 'MG-'+uuid.uuid4().hex)
    if raw.get('id') and gid not in replay['groups']:raise AuditError('없는 동일오류 그룹ID')
    active=raw.get('active',True)
    if type(active) is not bool:raise AuditError('동일오류 연결/해제 여부는 명시값이어야 합니다.')
    if not active and gid not in replay['groups']:raise AuditError('해제할 기존 동일오류 그룹ID 필요')
    for group in replay['groups'].values():
        if active and group.get('active',True) and group['id']!=gid and set(group['member_ids']) & set(members):raise AuditError('기록이 다른 동일오류 그룹에 이미 연결돼 있습니다.')
    resolution=optional(raw.get('amount_resolution',''),'서로 다른 금액·방향의 대표금액 판단')
    values={(replay['records'][key]['amount'],replay['records'][key]['tax_effect']) for key in members}
    if active and len(values)>1 and not resolution:raise AuditError('금액·방향이 다른 기록은 대표금액 판단 근거를 명시하세요. 자동 상계하지 않습니다.')
    data={'id':gid,'member_ids':members,'primary_id':primary,
          'member_revisions':{key:replay['records'][key]['revision'] for key in members},
          'reason':text(raw['reason'],'동일오류 판단 근거'),'amount_resolution':resolution,
          'input_basis':input_basis(ws),'active':active,'actor':text(actor,'동일오류 판단 기록자'),
          'at':now(),'revision':uuid.uuid4().hex,
          'scope':'사람이 동일오류로 연결한 대표금액 1건만 계수. 회원별 계정영향·근거는 모두 보존.'}
    ws._append('misstatement_group',data,expected_head=before);ws.refresh();return data


def group_current(ws, group, replay):
    return (group['input_basis']==input_basis(ws) and all(
        replay['records'].get(key,{}).get('revision')==revision
        for key,revision in group['member_revisions'].items()))
