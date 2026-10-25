"""Create a separate JS electronics example without replacing selected work."""
from uuid import uuid4
from common import AuditError


def open_example(host):
    if host.busy:raise AuditError('진행 중인 작업이 끝난 뒤 예제를 열어 주세요.')
    if not host.check_navigation():return
    import tkinter as tk
    from tkinter import ttk,messagebox
    win=tk.Toplevel(host.root);win.title('새 JS 실무절차 예제');win.transient(host.root)
    win.audit_display=host.display
    px=host.display.px
    body=ttk.Frame(win,padding=px(24));body.pack(fill='both',expand=True)
    ttk.Label(body,text='JS전자 실무절차 예제',style='Section.TLabel').pack(anchor='w')
    ttk.Label(body,text='가상 20개 전표와 7개 실무절차를 새 업무 폴더에 준비해요. '
        '현재 업무는 예제에 합치지 않아요. 제조업 자료이므로 모회사 JS의 연결재무제표로 표시하지 않아요.',
        wraplength=px(580),style='Muted.TLabel',justify='left').pack(fill='x',pady=(10,12))
    ttk.Label(body,text='불러온 뒤 입력자료·계산정책은 각 절차에서 확인하세요. '
        '프로그램이 조서 수행·판단·승인·검토를 완료하지 않아요.',
        wraplength=px(580),justify='left').pack(fill='x',pady=(0,18))
    def create():
        from onboarding.fixtures import create_demo
        base=host.sector_home.parent/'실무절차예제'/('JS전자_'+uuid4().hex[:12])
        create_demo(base)
        host.open_workspace(base);host.navigate('자료·검사')
        host.status.set('새 JS전자 실무절차 예제를 열었어요. 입력 확인이 필요한 항목은 실무절차 입력·검사에서 확인하세요.')
        win.destroy()
    ttk.Button(body,text='새 예제 업무 만들기',style='Primary.TButton',command=lambda:host.call(create)).pack(side='right')
    ttk.Button(body,text='닫기',command=win.destroy).pack(side='right',padx=(0,px(10)))
    win.grab_set()
