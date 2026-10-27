"""Bounded excerpts from this engagement's explicitly linked human records."""
from copy import deepcopy
from common import digest
from .aggregate import snapshot_rows

SCOPE='사람 입력 기록의 발췌. 자동후보는 오류확정이 아니며 회계적 판단·수정반영 결론의 충분성은 미검증입니다.'


def packet(ws,pid):
    snap=snapshot_rows(ws)
    records=[r for r in snap['records'] if pid in r['procedure_ids'] and
             r['company_code']==ws.context['회사코드'] and
             r['start_date']==ws.context['시작일'] and r['cutoff_date']==ws.context['기준일']]
    references=[]
    fields=('id','company_code','start_date','cutoff_date','procedure_ids',
            'description','assessment','classification','amount','correction_state',
            'company_position','period','qualitative','tax_effect','current',
            'verification_state','group_id','counted','below_trivial','missing')
    for record in records[:40]:
        data={key:deepcopy(record[key]) for key in fields}
        data['description']=data['description'][:600];data['scope']=SCOPE
        data['input_basis']=deepcopy(record['input_basis']);data['record_revision']=record['revision']
        data['evidence_pins']=[{'source_id':sid,'sha256':ws.sources[sid]['sha256']} for sid in record['evidence_ids']]
        data['run_refs']=deepcopy(record['run_refs'])
        ref={'kind':'misstatement_record','record_id':record['id'],'data':data}
        if record['evidence_ids']:
            sid=record['evidence_ids'][0];ref.update(source_id=sid,sha256=ws.sources[sid]['sha256'])
        if record['run_refs']:
            run=record['run_refs'][0];ref.update(run_id=run['id'],result_hash=run['result_hash'])
        references.append(ref)
    return {'references':references,'scope':SCOPE,'inventory':{'available':len(records),
            'included':len(references),'omitted':max(0,len(records)-len(references)),
            'manifest_hash':digest(records),'policy':'최대 40건·설명 600자 발췌. 원기록 전체는 Excel·증적JSON에 보존.'}}
