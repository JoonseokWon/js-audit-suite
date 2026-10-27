"""Compare actual GL journal movement, independent of acceptance/overlay labels."""
from collections import defaultdict
import uuid
from common import AuditError, now, num, day
from human_input import text
from .schema import payload, ids, evidence
from .state import state, input_basis, current


def _actual(run, journals):
    values=defaultdict(int);rows=[]
    for row in run['result']['tables'].get('입력_총계정원장',[]):
        if row['전표ID'] in journals:
            values[row['계정코드']]+=num(row['차변'])-num(row['대변'])
            rows.append(dict(row))
    return values,rows


def verify_correction(ws,value,actor,*,expected_head=None):
    before=ws.assert_writeable(expected_head=expected_head)
    raw=payload(value,('record_id','ledger_run_id','journal_ids','account_checks',
                       'evidence_ids','conclusion','performed_date'),
                ('record_id','ledger_run_id','journal_ids','account_checks',
                 'evidence_ids','conclusion','performed_date'))
    replay=state(ws);record=replay['records'].get(raw['record_id'])
    if not record or record['assessment']!='왜곡표시' or record['correction_state']!='수정':
        raise AuditError('사람이 왜곡표시·수정으로 기록한 항목에만 수정 반영 대사를 연결하세요.')
    if not current(ws,record,replay):raise AuditError('자료 변경 후 왜곡표시 기록을 먼저 명시적으로 재확인하세요.')
    baseline=record.get('baseline_ledger');latest=ws.latest().get('원장·리드')
    if not baseline or not latest or latest['id']!=raw['ledger_run_id']:raise AuditError('수정 전 원장과 현재 원장 실행을 명시 연결하세요.')
    old=ws.runs.get(baseline['id'])
    if not old or old['result_hash']!=baseline['result_hash']:raise AuditError('수정 전 원장 실행 해시 불일치')
    if old['result']['blocking'] or latest['result']['blocking'] or latest.get('cancelled'):
        raise AuditError('원장 완전성 차단/취소를 해결한 뒤 수정 반영을 검증하세요.')
    journals=ids(raw['journal_ids'],'실제 수정전표ID')
    if not journals:raise AuditError('실제 원장에서 조사할 수정전표ID를 명시하세요.')
    checks=raw['account_checks']
    if not isinstance(checks,list) or not checks or len(checks)>500:raise AuditError('계정별 예상 원장변동 목록 필요')
    expected={}
    for item in checks:
        row=payload(item,('account_code','expected_movement'),('account_code','expected_movement'))
        key=text(row['account_code'],'계정코드')
        if key in expected:raise AuditError('원장변동 계정 중복')
        expected[key]=num(row['expected_movement'])
    if not any(expected.values()) or sum(expected.values()):raise AuditError('수정 전표의 예상 계정변동은 0이 아닌 차대 균형이어야 합니다.')
    if not {r['account_code'] for r in record['account_impacts']}<=set(expected):raise AuditError('기록한 재무제표 계정영향을 모두 원장변동 대사에 포함하세요.')
    linked=evidence(ws,raw['evidence_ids'])
    if not {old['source_id'],latest['source_id']}<=set(linked):raise AuditError('수정 전·현재 실제 원장 원본을 증거로 함께 연결하세요.')
    earlier,before_rows=_actual(old,journals);later,after_rows=_actual(latest,journals)
    comparisons=[{'account_code':key,'expected_movement':expected.get(key,0),
                  'before':earlier.get(key,0),'after':later.get(key,0),
                  'actual_movement':later.get(key,0)-earlier.get(key,0),
                  'difference':later.get(key,0)-earlier.get(key,0)-expected.get(key,0)}
                 for key in sorted(set(expected)|set(earlier)|set(later))]
    reflected=latest['id']!=old['id'] and bool(after_rows) and all(row['difference']==0 for row in comparisons)
    data={'record_id':record['id'],'record_revision':record['revision'],
          'input_basis':input_basis(ws),'baseline_ledger':baseline,
          'ledger_run_id':latest['id'],'result_hash':latest['result_hash'],
          'journal_ids':journals,'comparisons':comparisons,'before_rows':before_rows,'after_rows':after_rows,
          'reflected':reflected,'evidence_ids':linked,'actor':text(actor,'수정 반영 확인 기록자'),
          'conclusion':text(raw['conclusion'],'사람의 수정 검증 범위·결론'),
          'performed_date':day(raw['performed_date']).isoformat(),'at':now(),'revision':uuid.uuid4().hex,
          'scope':'선택 실제 GL 전표의 계정별 순변동 수치대사. 회사 조정 수용·승인조정표시는 실제 GL 반영 증거가 아닙니다.'}
    ws._append('misstatement_verification',data,expected_head=before);ws.refresh();return data


def verification_state(ws,record,replay=None):
    replay=replay or state(ws);check=replay['verifications'].get(record['id'])
    if not check:return '미확인'
    ledger=ws.latest().get('원장·리드',{})
    fresh=(check['record_revision']==record['revision'] and check['input_basis']==input_basis(ws)
           and check['ledger_run_id']==ledger.get('id') and check['result_hash']==ledger.get('result_hash'))
    if not fresh:return '자료·기록변경·재확인필요'
    return '선택GL변동일치' if check['reflected'] else '선택GL변동불일치·미반영'
