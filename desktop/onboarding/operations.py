"""Immutable input staging followed by the existing background execution path."""
from pathlib import Path
from uuid import uuid4
from common import AuditError,atomic,dumps,sha
from onboarding.confirmation import confirm_input
from onboarding.workbooks import save_ledger


def execute_inputs(dialog,confirm_adjustments=False):
    host=dialog.host;ws=dialog.ws
    if host.ws is not ws:raise AuditError('선택한 업무가 바뀌었습니다. 창을 다시 여세요.')
    ws.assert_writeable(expected_head=dialog.head)
    if not host.check_navigation():return
    if not dialog.actor.get().strip() or not dialog.reason.get().strip():raise AuditError('입력 확인자와 확인 사유를 입력하세요.')
    for path,expected in dialog.paths:
        if sha(path)!=expected:raise AuditError('불러온 원본이 변경됐습니다. 다시 불러와 확인하세요.')
    sources=[]
    for path,_ in dialog.paths:
        source_id=ws.add_source(path,'실무절차 가져오기 원본',dialog.area.get())
        sources.append(ws.sources[source_id])
    module=dialog.area.get()
    data=confirm_input(module,dialog.payload,dialog.actor.get(),dialog.reason.get(),sources,
                       confirm_adjustments=confirm_adjustments)
    base=ws.root/'입력준비'/uuid4().hex;base.mkdir(parents=True)
    path=base/(module+'.json');atomic(path,dumps(data).encode('utf-8'))
    jobs=[]
    if module=='실무자료·원장' and '원장·리드' not in ws.latest():
        from onboarding.erp import prepare_ledger
        core=base/'정규화_원장.xlsx';save_ledger(prepare_ledger(data,ws.context),core)
        jobs.append(('원장·리드',core))
    jobs.append((module,path))
    host.module.set(module);host.file.set(str(path));dialog.win.destroy();host.launch(jobs)
