"""Prepare a fresh example without writing to the selected engagement."""
from uuid import uuid4
import tkinter as tk
from tkinter import ttk
from common import AuditError
from desktop.ai.evidence import wrapping_label
from desktop.widgets.flow import FlowFrame


def open_demo_creator(host):
    if host.busy:raise AuditError('현재 작업이 끝난 뒤 감사 시연을 열어 주세요.')
    if not host.check_navigation():return
    win=host.ai_window('JS전자 감사 시연 · 새 업무',760,480)
    host.demo_creator_win=win
    body=ttk.Frame(win,padding=24);body.pack(fill='both',expand=True)
    wrapping_label(body,text='JS전자 감사 시연',style='Title.TLabel').pack(fill='x')
    wrapping_label(body,text='가상 JS전자 자료로 원장·매출 누락을 찾고, 로컬 AI 초안을 검토·수정해 Excel로 내보내요.',
                   style='Muted.TLabel').pack(fill='x',pady=(12,16))
    wrapping_label(body,text='새 폴더에 입력자료와 정상 대조자료를 만들어요. 오류 재현을 위한 자동검사는 실행하지만 '
                   '현재 회사 업무를 바꾸거나 사람의 수행·판단·승인·검토를 대신 기록하지 않아요.').pack(fill='x',pady=(0,16))
    wrapping_label(body,text='AI 모델 준비와 생성은 별도 버튼으로 실행해요. 예제를 여는 것만으로 모델을 호출하지 않아요.').pack(fill='x')
    footer=FlowFrame(body);footer.pack(side='bottom',fill='x',pady=(20,0))
    def create():
        from demo_case import create_demo
        if host.busy:raise AuditError('진행 중인 작업이 끝난 뒤 다시 실행하세요.')
        if not host.check_navigation():return
        folder=host.sector_home.parent/'감사시연'/('JS전자_'+uuid4().hex[:12])
        def complete(result):
            from .guide import open_demo_guide
            ws,_=result
            host.open_workspace(ws.root);host.navigate('자료·검사')
            host.status.set('별도 JS전자 감사 시연을 열었어요. 오류 결과와 원본을 먼저 확인하세요.')
            open_demo_guide(host)
        win.destroy();host.status.set('별도 JS전자 시연자료와 오류 검사를 준비하고 있어요…')
        host.launch_ai_job(lambda:create_demo(folder),complete)
    win.create_button=footer.add(ttk.Button(footer,text='새 시연 업무 만들기',style='Primary.TButton',
                                        command=lambda:host.call(create)))
    footer.add(ttk.Button(footer,text='닫기',command=win.destroy))
    return win
