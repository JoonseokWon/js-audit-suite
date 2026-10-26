"""Workspace switcher and a small action toolbar with explicit commands."""
import tkinter as tk
from tkinter import ttk
from desktop.widgets.flow import FlowFrame
from desktop.widgets.navigation import ROUTES


def build_header(host,parent):
    px=host.display.px
    frame=ttk.Frame(parent,padding=(px(22),px(12)))
    frame.pack(fill='x')
    line=FlowFrame(frame)
    line.pack(fill='x')
    host.company_bar=line
    company=ttk.Frame(line)
    company.columnconfigure(1,weight=1)
    ttk.Label(company,text='현재 회사',style='Muted.TLabel').grid(
        row=0,column=0,sticky='w',padx=(0,px(12)))
    host.sector_name=tk.StringVar(value='회사를 선택하세요')
    host.sector_box=ttk.Combobox(company,textvariable=host.sector_name,
                      values=[c['name'] for c in host.sector_options],state='readonly',width=16)
    host.sector_box.grid(row=0,column=1,sticky='ew')
    line.add(company)
    host.sector_box.bind('<<ComboboxSelected>>',lambda _:host.call(
        lambda:host.select_sector(host.sector_options[host.sector_box.current()]['code'])))
    host.more_button=line.add(ttk.Menubutton(line,text='더보기',style='Quiet.TButton'))
    host.more_menu=tk.Menu(host.more_button,tearoff=False)
    host.more_button.configure(menu=host.more_menu)
    host.sector_new=host.more_button  # Keep the established busy-state control contract.
    host.sector_cancel=line.add(ttk.Button(line,text='준비 중단',state='disabled',command=host.cancel.set))
    host.sector_cancel.flow_align_end=True
    host.sector_description=tk.StringVar(value='JS는 업종 없는 모회사예요. 회사별 자료는 따로 보관해요.')
    text=ttk.Label(frame,textvariable=host.sector_description,style='Muted.TLabel',
                   anchor='w',justify='left',wraplength=px(640))
    text.audit_managed_wrap=True
    text.pack(fill='x',pady=(px(7),px(10)))
    text.bind('<Configure>',lambda event:text.configure(wraplength=max(1,event.width)))
    host.company_description_label=text
    bar=FlowFrame(frame)
    bar.pack(fill='x')
    host.toolbar=bar
    host.workpaper_button=bar.add(ttk.Button(bar,text='조서 초안 열기',style='Primary.TButton',
                    command=lambda:host.call(host.open_workpaper_draft)))
    host.workflow_button=bar.add(ttk.Button(bar,text='감사계획',style='Secondary.TButton',
                    command=lambda:host.call(host.open_workflow_view)))
    host.draft_export_button=bar.add(ttk.Button(bar,text='초안 Excel 저장',style='Secondary.TButton',
                    command=lambda:host.export_dialog(False)))
    zoom=ttk.Frame(bar)
    zoom.flow_align_end=True
    bar.add(zoom)
    ttk.Label(zoom,text='글자 배율',style='Muted.TLabel').grid(
        row=0,column=0,sticky='w',padx=(0,px(8)))
    host.ui_zoom=tk.StringVar(value='100%')
    host.zoom_box=ttk.Combobox(zoom,textvariable=host.ui_zoom,
        values=['90%','100%','110%','125%','150%','175%'],state='readonly',width=6)
    host.zoom_box.grid(row=0,column=1,sticky='ew')
    host.zoom_box.bind('<<ComboboxSelected>>',lambda _:host.call(
        lambda:host.set_ui_zoom(int(host.ui_zoom.get().rstrip('%')))))
    for label,fn in (
        ('새 업무 만들기',host.new_dialog),('저장된 업무 열기',host.open_dialog),
        ('선택 회사의 새 예제 업무 만들기',lambda:host.call(host.new_sector)),
        ('로우데이터 확인',lambda:host.call(host.open_raw_data)),
        ('입력양식·예제 복사',host.copy_templates),('계정별 증빙연습',host.case_dialog),
        ('검토완료 Excel 저장',lambda:host.export_dialog(True)),
        ('AI 설정',lambda:host.call(host.open_ai_settings))):
        host.more_menu.add_command(label=label,command=fn)
    host.more_menu.add_separator()
    from desktop.onboarding.manager import open_workbench
    from desktop.onboarding.examples import open_example
    host.more_menu.add_command(label='실무절차 입력·검사',command=lambda:host.call(lambda:open_workbench(host)))
    host.more_menu.add_command(label='새 JS 실무절차 예제',command=lambda:host.call(lambda:open_example(host)))
    from desktop.demo import open_demo_creator,open_demo_guide
    host.more_menu.add_command(label='새 JS전자 감사 시연',command=lambda:host.call(lambda:open_demo_creator(host)))
    host.more_menu.add_command(label='JS전자 시연 진행 안내',command=lambda:host.call(lambda:open_demo_guide(host)))
    from desktop.chrome.tools import open_cashflow
    host.more_menu.add_command(label='현금흐름표 별도 도구',command=lambda:host.call(lambda:open_cashflow(host)))
    screens=tk.Menu(host.more_menu,tearoff=False)
    for key,label,_ in ROUTES:
        screens.add_command(label=label,command=lambda route=key:host.navigate(route))
    host.more_menu.add_cascade(label='화면 이동',menu=screens)
    return frame
