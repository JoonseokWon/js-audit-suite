"""Append-only, explicit human records. A saved draft need not assert an error."""
import uuid
from common import AuditError, now
from human_input import text
from . import schema as s
from .candidates import candidates
from .state import state, input_basis, ledger_ref


def save_record(ws, value, actor, *, expected_head=None):
    before=ws.assert_writeable(expected_head=expected_head)
    actor=text(actor,'왜곡표시 검토기록자')
    raw=s.payload(value,s.FIELDS,('description',));replay=state(ws)
    rid=s.identity(raw.get('id') or 'MS-'+uuid.uuid4().hex)
    previous=replay['records'].get(rid,{})
    if raw.get('id') and not previous:raise AuditError('기존 기록 수정은 존재하는 ID로 하세요.')
    record={'id':rid,'description':text(raw['description'],'차이·검토사항 설명')}
    for field,choices in (('assessment',s.ASSESSMENTS),('classification',s.CLASSIFICATIONS),
                           ('correction_state',s.CORRECTIONS),('company_position',s.COMPANY),
                           ('period',s.PERIODS),('qualitative',s.QUALITATIVE)):
        record[field]=s.choice(raw.get(field,''),choices,field)
    for field in ('company_note','qualitative_note','tax_basis','judgment','projection_basis'):
        record[field]=s.optional(raw.get(field,''),field)
    for field in ('amount','tax_effect'):record[field]=s.optional_num(raw.get(field))
    record['account_impacts']=s.impacts(raw.get('account_impacts',[]))
    record['evidence_ids']=s.evidence(ws,raw.get('evidence_ids',[]))
    record['procedure_ids']=s.procedures(ws,raw.get('procedure_ids',['F03']))
    record['candidate_ids']=s.ids(raw.get('candidate_ids',[]),'자동검토후보ID')
    available={row['id']:row for row in candidates(ws)}
    available.update({row['id']:row for row in previous.get('candidate_refs',[])})
    if any(key not in available for key in record['candidate_ids']):raise AuditError('현재 또는 이전 연결근거에 없는 자동후보ID')
    pin_keys=('id','run_id','table','row_index','row_hash','column','module','source_id',
              'sha256','result_hash','unit','amount','observed_delta')
    # The untouched result row stays in the immutable run. Human records pin it;
    # they do not copy arbitrary external text into an authored XML-safe event.
    record['candidate_refs']=[{field:available[key][field] for field in pin_keys} for key in record['candidate_ids']]
    if any(row['source_id'] not in record['evidence_ids'] for row in record['candidate_refs']):
        raise AuditError('자동검토후보의 원본자료를 증거에 함께 연결하세요.')
    run_ids=list(dict.fromkeys(row['run_id'] for row in record['candidate_refs']))
    ledger=ledger_ref(ws)
    for ref in (previous.get('baseline_ledger'),ledger):
        if ref and ref['id'] not in run_ids:run_ids.append(ref['id'])
    record['run_refs']=[{key:ws.runs[rid][key] for key in ('id','source_id','result_hash')} for rid in run_ids]
    record.update(actor=actor,at=now(),revision=uuid.uuid4().hex,input_basis=input_basis(ws),
                  baseline_ledger=previous.get('baseline_ledger') or ledger,
                  company_code=ws.context['회사코드'],start_date=ws.context['시작일'],
                  cutoff_date=ws.context['기준일'], scope='사람 입력 기록. 이름은 본인인증·전자서명이 아닙니다.')
    ws._append('misstatement_record',record,expected_head=before);ws.refresh();return record


def reconfirm_record(ws, record_id, actor, reason, *, expected_head=None):
    before=ws.assert_writeable(expected_head=expected_head)
    replay=state(ws)
    if record_id not in replay['records']:raise AuditError('없는 왜곡표시 검토기록 ID')
    record=replay['records'][record_id]
    if ws.verify_sources():raise AuditError('등록한 원본 사본 변경/누락')
    data={'record_id':record_id,'record_revision':record['revision'],'input_basis':input_basis(ws),
          'current_ledger':ledger_ref(ws),'current_source_ids':list(ws.sources),
          'actor':text(actor,'재확인 기록자'),'reason':text(reason,'변경자료 재확인 근거'),
          'at':now(),'revision':uuid.uuid4().hex}
    ws._append('misstatement_reconfirm',data,expected_head=before);ws.refresh();return data
