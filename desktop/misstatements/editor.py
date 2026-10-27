"""Human assessment editor; candidate amounts are not prefilled as errors."""
import misstatements as ms
from misstatements import schema as s
from .shared import Dialog, lines
from .accounts import AccountTable


def edit_record(host,record=None,candidate=None):
    record=record or {};dialog=Dialog(host,'왜곡표시 검토기록')
    dialog.note('차이를 조사한 뒤 해당 여부·금액·분류를 직접 입력하세요. 자동후보 금액을 감사오류로 확정하거나 전표를 만들지 않습니다. 이름 입력은 본인인증·전자서명이 아닙니다.')
    dialog.text('description','차이·검토사항',record.get('description',''))
    for key,label,choices in (
        ('assessment','왜곡표시 해당 여부',s.ASSESSMENTS),
        ('classification','왜곡표시 분류',s.CLASSIFICATIONS),
        ('correction_state','수정·미수정',s.CORRECTIONS),
        ('company_position','회사 확인·이견',s.COMPANY),
        ('period','귀속 구분',s.PERIODS),('qualitative','정성적 중요성 검토',s.QUALITATIVE)):
        dialog.entry(key,label,record.get(key,''),choices)
    for key,label in (('amount','확인한 왜곡표시 금액(원, 부호 포함)'),('tax_effect','세효과(원, 없으면 0을 직접 입력)')):
        dialog.entry(key,label,'' if record.get(key) is None else record[key])
    for key,label in (('judgment','원인·회계처리 판단 근거'),('company_note','회사 이견·협의 내용'),
                      ('qualitative_note','정성적 중요성 사유'),('tax_basis','세효과 검토 근거'),
                      ('projection_basis','추정·투영 방법·모집단 근거')):
        dialog.text(key,label,record.get(key,''))
    AccountTable(dialog,'account_impacts','재무제표 계정별 영향: 각 행을 추가하세요. 여러 계정영향의 합을 전체 오류금액으로 합산하지 않습니다.',record.get('account_impacts',[]))
    candidate_ids=record.get('candidate_ids',[candidate['id']] if candidate else [])
    evidence_ids=record.get('evidence_ids',[candidate['source_id']] if candidate else [])
    for key,label,value in (('candidate_ids','연결 자동후보 ID(한 줄에 하나)',candidate_ids),
                            ('procedure_ids','관련 조서 ID(F03 포함, 한 줄에 하나)',record.get('procedure_ids',['F03']))):
        dialog.text(key,label,'\n'.join(value),height=3)
    dialog.selection('evidence_ids','연결 원본 증거(여러 자료 선택 가능)',
                     [(sid,source['name']+' / '+sid) for sid,source in dialog.ws.sources.items()],evidence_ids,height=5)
    dialog.entry('actor','기록자(직접 입력)')
    def save():
        dialog.fields['account_impacts'].require_committed()
        value={key:dialog.value(key) for key in s.FIELDS if key in dialog.fields}
        for key in ('candidate_ids','procedure_ids'):value[key]=lines(value[key])
        if record:value['id']=record['id']
        return ms.save_record(dialog.ws,value,dialog.value('actor'),expected_head=dialog.head)
    dialog.button('검토기록 저장',lambda:dialog.save(save,'왜곡표시 검토기록을 저장했습니다. 내용 승인·별도 검토는 F03에서 진행하세요.'))
    dialog.finish();return dialog


def group_records(host):
    dialog=Dialog(host,'동일 오류 연결 판단')
    dialog.note('같은 금액·자료라는 이유만으로 중복으로 확정하지 않습니다. 사람이 동일 오류로 확인한 기록의 ID와 대표기록을 명시하세요. 회원별 계정영향과 원자료는 계속 보존됩니다.')
    for key,label in (('id','기존 그룹ID(새 그룹은 공란)'),('primary_id','금액을 1회 계수할 대표기록 ID'),('actor','판단 기록자')):
        dialog.entry(key,label)
    dialog.entry('active','연결 상태','연결',('연결','해제'))
    for key,label in (('member_ids','회원기록 ID(한 줄에 하나)'),('reason','동일 오류 판단 근거'),
                      ('amount_resolution','금액·방향이 다를 때 대표금액 선택 근거')):dialog.text(key,label)
    def save():
        value={key:dialog.value(key) for key in ('primary_id','reason','amount_resolution')}
        value['member_ids']=lines(dialog.value('member_ids'))
        value['active']=dialog.value('active')=='연결'
        if dialog.value('id'):value['id']=dialog.value('id')
        return ms.save_group(dialog.ws,value,dialog.value('actor'),expected_head=dialog.head)
    dialog.button('동일 오류 판단 저장',lambda:dialog.save(save,'동일 오류 연결 판단을 기록했습니다. F03 조서를 갱신하세요.'))
    dialog.finish();return dialog
