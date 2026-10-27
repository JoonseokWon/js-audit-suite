"""Scrollable misstatement register; entry point for the common desktop shell."""
from tkinter import ttk
import misstatements as ms
from common import dumps
from desktop.widgets.flow import FlowFrame
from .shared import Dialog, table, selected, action
from .editor import edit_record, group_records
from .correction import reconfirm, correction


def open_dialog(host):
    dialog=Dialog(host,'왜곡표시 검토·집계')
    dialog.note('자동검토후보 → 원인 조사·사람 판단 → 수정·미수정 기록 → 실제 GL 반영 대사 → F03 조서 작성·별도 검토 순으로 진행하세요. 합계는 상반 오류를 상계하지 않으며 명백히 사소한 항목도 자동 삭제하지 않습니다.')
    rows=ms.candidates(dialog.ws);snap=ms.snapshot_rows(dialog.ws);records=snap['records']
    tabs=ttk.Notebook(dialog.body);tabs.pack(fill='both',expand=True,padx=10,pady=8)
    candidate_tab=ttk.Frame(tabs);record_tab=ttk.Frame(tabs);tabs.add(candidate_tab,text='자동검토후보');tabs.add(record_tab,text='사람 검토기록')
    candidates=table(candidate_tab,('모듈','항목','차이값','단위'))
    for index,row in enumerate(rows):candidates.insert('','end',iid=str(index),values=(row['module'],row['label'],row['observed_delta'],row['unit']))
    register=table(record_tab,('기록ID','확인금액','해당여부','수정검증'))
    for index,row in enumerate(records):register.insert('','end',iid=str(index),values=(row['id'],row['amount'],row['assessment'],row['verification_state']))
    def launch(call):
        dialog.close(force=True);return call()
    def candidate_record():
        row=selected(candidates,rows)
        return launch(lambda:edit_record(host,candidate=row))
    candidate_buttons=FlowFrame(candidate_tab);candidate_buttons.pack(fill='x',padx=10)
    candidate_buttons.add(ttk.Button(candidate_buttons,text='후보 근거 보기',command=lambda:action(dialog,lambda:details(dialog,selected(candidates,rows)))))
    candidate_buttons.add(ttk.Button(candidate_buttons,text='선택 후보 검토기록 작성',command=lambda:action(dialog,candidate_record)))
    record_buttons=FlowFrame(record_tab);record_buttons.pack(fill='x',padx=10)
    for title,call in (('기록·근거 보기',lambda row:details(dialog,row)),
                       ('판단·금액 수정',lambda row:launch(lambda:edit_record(host,row))),
                       ('변경자료 재확인',lambda row:launch(lambda:reconfirm(host,row))),
                       ('실제 GL 반영 대사',lambda row:launch(lambda:correction(host,row)))):
        record_buttons.add(ttk.Button(record_buttons,text=title,command=lambda fn=call:action(dialog,lambda:fn(selected(register,records)))))
    dialog.note('금액 집계(잠정 포함): '+dumps(snap['summary']))
    dialog.note('동일원천·금액 연결 제안 '+str(len(ms.duplicate_suggestions(rows)))+'건. 제안만으로 중복 차감하지 않습니다.')
    pending=' / '.join(dict.fromkeys(r['message'] for r in ms.status(dialog.ws)['blockers']))
    dialog.note('다음 확인사항: '+(pending or '미해결 입력·버전 점검사항이 없습니다. 실제 감사완료 인증은 아닙니다.'))
    dialog.button('새 검토기록',lambda:launch(lambda:edit_record(host)))
    dialog.button('동일 오류 연결 판단',lambda:launch(lambda:group_records(host)))
    dialog.finish();return dialog


def details(dialog,row):
    # Same head-pinned dialog and native wrapped text; no giant one-line JSON cell.
    detail=Dialog(dialog.host,'선택 항목의 근거·상태')
    detail.note('원본 자료ID·실행ID·행 해시와 사람 기록을 확인하세요. 자동후보는 감사오류 확정이 아닙니다.')
    field=detail.text('detail','기록 전체',__import__('json').dumps(row,ensure_ascii=False,indent=2),height=22)
    field.configure(state='disabled');detail.finish();return detail
