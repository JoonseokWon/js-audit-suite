"""Explicit reconfirmation and actual GL correction comparison forms."""
import misstatements as ms
from .shared import Dialog, lines
from .accounts import AccountTable


def reconfirm(host,record):
    dialog=Dialog(host,'변경자료 재확인')
    dialog.note('원기록과 과거 증거는 보존됩니다. 변경한 자료·중요성에 비추어 이 검토기록을 다시 확인한 근거를 입력하세요. 수정 반영 대사는 별도로 다시 수행해야 합니다.')
    dialog.note('기록ID: '+record['id']);dialog.entry('actor','재확인 기록자');dialog.text('reason','변경 내용·확인 범위·판단 근거')
    dialog.button('재확인 기록 저장',lambda:dialog.save(lambda:ms.reconfirm_record(
        dialog.ws,record['id'],dialog.value('actor'),dialog.value('reason'),expected_head=dialog.head),
        '변경자료 재확인 기록을 저장했습니다.'))
    dialog.finish();return dialog


def correction(host,record):
    dialog=Dialog(host,'실제 원장 수정 반영 대사')
    dialog.note('회사 수정 수용 기록이나 승인조정표시와 구분하여 실제 총계정원장의 선택 전표를 수정 전 원장과 비교합니다. 다른 거래의 영향·수정의 충분성은 사람이 별도로 확인하세요.')
    dialog.note('기록ID: '+record['id'])
    ledger=dialog.ws.latest().get('원장·리드',{})
    dialog.entry('ledger_run_id','현재 원장 실행ID',ledger.get('id',''))
    dialog.text('journal_ids','실제 수정전표 ID(한 줄에 하나)',height=3)
    AccountTable(dialog,'account_checks','계정별 예상 GL 변동: 실제 GL 차변−대변 순변동을 입력하고 계정행을 추가하세요. 재무제표 표시계정의 증가·감소와 구분합니다.',[],movement=True)
    dialog.selection('evidence_ids','수정 전·현재 원장과 확인증거(여러 자료 선택 가능)',
                     [(sid,source['name']+' / '+sid) for sid,source in dialog.ws.sources.items()],height=5)
    dialog.entry('performed_date','실제 확인일(YYYY-MM-DD)')
    dialog.text('conclusion','사람의 검증 범위·결론');dialog.entry('actor','확인 기록자')
    def save():
        dialog.fields['account_checks'].require_committed()
        value={key:dialog.value(key) for key in ('ledger_run_id','performed_date','conclusion')}
        value.update(record_id=record['id'],journal_ids=lines(dialog.value('journal_ids')),
                     evidence_ids=dialog.value('evidence_ids'),account_checks=dialog.value('account_checks'))
        return ms.verify_correction(dialog.ws,value,dialog.value('actor'),expected_head=dialog.head)
    dialog.button('실제 원장 대사 기록',lambda:dialog.save(save,'선택 수정전표의 실제 GL 변동 대사 결과를 기록했습니다.'))
    dialog.finish();return dialog
