"""Saved-state guide; buttons navigate or stage inputs, never approve or judge."""
import hashlib
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from common import AuditError
from desktop.ai.evidence import wrapping_label
from desktop_display import ScrollableFrame
from desktop.widgets.flow import FlowFrame
from desktop.widgets.cards import BentoCard


def checked_input(ws,manifest,key):
    item=manifest['inputs'].get(key)
    if not isinstance(item,dict):raise AuditError('시연 입력자료를 찾지 못했어요.')
    path=Path(item['path'])
    if not path.resolve().is_relative_to(ws.root.resolve()) or not path.is_file():
        raise AuditError('시연 업무 폴더 안의 입력자료만 선택할 수 있어요.')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
        raise AuditError('시연 원본이 변경됐어요. 수정한 자료는 별도 사본으로 등록하세요.')
    return item


class DemoGuide:
    def __init__(self,host):
        from demo_case import load_manifest
        host.guard();self.host=host;self.ws=host.ws
        self.manifest=load_manifest(self.ws.root)
        self.win=host.ai_window('JS전자 감사 시연 · 현재 단계',980,820)
        host.demo_guide_win=self.win;self.win.controller=self
        footer=FlowFrame(self.win);footer.pack(side='bottom',fill='x',padx=12,pady=12)
        footer.add(ttk.Button(footer,text='상태 새로고침',command=lambda:host.call(self.refresh)))
        footer.add(ttk.Button(footer,text='닫기',command=self.win.destroy))
        scroll=ScrollableFrame(self.win);scroll.pack(fill='both',expand=True)
        self.scroll=scroll;body=scroll.inner
        wrapping_label(body,text='JS전자 · 입력부터 조서 출력까지',style='Title.TLabel').pack(fill='x',padx=16,pady=(16,8))
        wrapping_label(body,text='오류 재현을 위한 자동검사 결과와 실제 사람의 수행·승인은 구분해요. '
                       'AI 초안을 생성하거나 적용해도 내용 승인과 별도 검토가 완료되지는 않아요.',
                       style='Muted.TLabel').pack(fill='x',padx=16,pady=(0,12))
        self.next_text=tk.StringVar()
        wrapping_label(body,textvariable=self.next_text,style='Section.TLabel').pack(fill='x',padx=16,pady=(0,12))
        self.stage_frame=ttk.Frame(body);self.stage_frame.pack(fill='x',padx=8)
        self.build_actions(body)
        self.refresh()

    def current(self):
        self.host.guard()
        if self.host.ws is not self.ws:raise AuditError('업무가 변경됐어요. 현재 시연 업무에서 안내를 다시 여세요.')
        return self.ws

    def refresh(self):
        from demo_case import case_status
        ws=self.current();status=case_status(ws);self.status=status
        self.next_text.set('다음에 할 일 · '+str(status.get('next_step','현재 자료와 기록을 확인하세요.')))
        for child in self.stage_frame.winfo_children():child.destroy()
        for index,stage in enumerate(status.get('stages',[]),1):
            card=BentoCard(self.stage_frame,f"{index:02} · {stage['title']}",stage.get('detail',''))
            card.pack(fill='x',pady=(0,8))
            wrapping_label(card.body,text=str(stage.get('state','미확인')),style='Muted.TLabel').pack(fill='x')
        self.win.demo_status=status

    def build_actions(self,body):
        card=BentoCard(body,'필요한 화면 열기','버튼은 화면 이동·파일 선택만 해요. 검사 실행·내용 승인·검토는 각 화면에서 직접 진행하세요.')
        card.pack(fill='x',padx=8,pady=(8,16))
        actions=FlowFrame(card.body);actions.pack(fill='x');self.actions=actions
        specs=(('오류 검사 결과',self.results),('매출 조서·AI',self.workpaper),
               ('조서 생성 근거',self.evidence),('AI 설정',self.host.open_ai_settings),
               ('초안 Excel 저장',lambda:self.host.export_dialog(False)))
        self.buttons={}
        for label,action in specs:
            self.buttons[label]=actions.add(ttk.Button(actions,text=label,command=lambda fn=action:self.host.call(lambda:self.perform(fn))))
        row=FlowFrame(card.body);row.pack(fill='x',pady=(12,0));self.input_actions=row
        for label,key in (('오류 원장 선택','ledger_error'),('정상 원장 선택','ledger_clean'),
                          ('오류 매출 선택','sales_error'),('정상 매출 선택','sales_clean')):
            self.buttons[label]=row.add(ttk.Button(row,text=label,command=lambda k=key:self.host.call(lambda:self.prepare_input(k))))
        wrapping_label(card.body,text='정상자료 재검사로 근거가 바뀌면 이전 AI 초안·내용 승인·검토는 다시 확인해야 해요. '
                       '초안 Excel에는 현재의 미완료·예외 상태가 함께 출력돼요.',style='Muted.TLabel').pack(fill='x',pady=(12,0))

    def perform(self,action):
        self.current()
        if not self.host.check_navigation():return
        self.win.destroy();action()

    def prepare_input(self,key):
        self.current()
        if not self.host.check_navigation():return
        from demo_case import load_manifest
        item=checked_input(self.ws,load_manifest(self.ws.root),key)
        self.host.module.set(item['module']);self.host.file.set(str(item['path']))
        self.host.navigate('자료·검사');self.win.destroy()
        self.host.status.set('시연 입력자료를 선택했어요. 내용을 확인한 뒤 등록하고 검사하기를 직접 누르세요.')

    def results(self):
        self.host.result_module.set('매출');self.host.choose_result_module();self.host.navigate('자료·검사')

    def workpaper(self):
        self.host.navigate('절차·조서');self.host.load_procedure(self.manifest.get('target_pid','A04'))
        self.host.status.set('작성자를 입력하고 생성 근거를 확인하세요. AI 초안을 적용한 뒤 직접 수정·저장·내용 승인하세요.')

    def evidence(self):
        self.workpaper()
        from desktop.ai.evidence import open_current_evidence
        open_current_evidence(self.host)


def open_demo_guide(host):
    return DemoGuide(host)
