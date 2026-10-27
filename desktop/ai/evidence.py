"""Read-only, human-readable navigation of the exact bounded AI evidence packet."""
import json
from tkinter import ttk
from desktop_display import create_scrolled_text
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree
from .request_policy import build_packet

KIND_LABELS={
    'raw_xlsx_row':'원본 Excel 행','raw_json':'원본 입력 행',
    'calculation_row':'계산 결과 행','calculation_policy':'계산 정책',
    'run_summary':'자동검사 요약','ledger_reconciliation':'원장 대사',
    'exception':'예외·미확인','workpaper':'현재 조서',
    'procedure_definition':'절차 정의','scope_limits':'지원 범위',
}


def reference_rows(packet):
    rows=[]
    for ref in packet.get('references',[]):
        detail=json.dumps(ref.get('data',{}),ensure_ascii=False,separators=(',',':'))
        rows.append({'근거ID':ref['id'],'구분':KIND_LABELS.get(ref['kind'],ref['kind']),
                     '내용 요약':detail[:240]+('…' if len(detail)>240 else ''),
                     '자료ID':ref.get('source_id',''),'검사ID':ref.get('run_id','')})
    return rows


def packet_summary(packet):
    e=packet['engagement'];p=packet['procedure'];refs=packet.get('references',[])
    unselected=packet.get('unselected_sources',{}).get('count',0)
    omitted=len(packet.get('truncation',[]))
    return (f"{e['company_name']} · {e['company_code']} · {e['start_date']} ~ {e['end_date']}\n"
            f"{p['id']} · {p['title']} / 선택 근거 {len(refs)}개 · 미선택 자료 {unselected}개 · 생략 기록 {omitted}개\n"
            '아래 근거만 모델에 전달해요. 파일의 진위·자료 전체의 완전성이나 실제 감사 수행을 인증하지 않아요.')


def wrapping_label(parent,**options):
    options.setdefault('wraplength',760);options.setdefault('justify','left')
    label=ttk.Label(parent,**options);label.audit_managed_wrap=True
    label.bind('<Configure>',lambda event:label.configure(wraplength=max(1,event.width)))
    return label


def build_evidence_frame(parent,packet):
    """Display original row/calculation/exception IDs without opening external files."""
    outer=ttk.Frame(parent,padding=10)
    wrapping_label(outer,text=packet_summary(packet)).pack(fill='x',pady=(0,10))
    listing=tree(outer,['근거ID','구분','내용 요약','자료ID','검사ID'],6)
    listing.column('근거ID',width=80);listing.column('구분',width=130)
    listing.column('내용 요약',width=380)
    refs=packet.get('references',[])
    for index,row in enumerate(reference_rows(packet)):
        listing.insert('', 'end',iid=str(index),values=list(row.values()))
    wrapping_label(outer,text='행을 선택하면 원본 시트·행, 계산값·차이와 자료/검사 식별자를 확인할 수 있어요.',
                   style='Muted.TLabel').pack(fill='x',pady=(10,4))
    detail=create_scrolled_text(outer,height=7,wrap='word')
    detail.audit_container.pack(fill='both',expand=True)
    def select(_=None):
        picked=listing.selection()
        if not picked:return
        detail.configure(state='normal');detail.delete('1.0','end')
        detail.insert('1.0',json.dumps(refs[int(picked[0])],ensure_ascii=False,indent=2))
        detail.configure(state='disabled')
    listing.bind('<<TreeviewSelect>>',select)
    detail.configure(state='disabled')
    if refs:listing.selection_set('0');select()
    outer.reference_tree=listing;outer.reference_detail=detail
    return outer


def open_current_evidence(host):
    host.guard()
    if not host.current_pid:host.open_workpaper_draft()
    if host.dirty():
        from common import AuditError
        raise AuditError('수정 중인 조서를 먼저 저장한 뒤 생성 근거를 확인하세요.')
    packet=build_packet(host.ws,host.current_pid,host.ai_catalog)
    win=host.ai_window('AI 생성 근거 · 원본과 대사');host.ai_evidence_win=win
    footer=FlowFrame(win);footer.pack(side='bottom',fill='x',padx=10,pady=10)
    footer.add(ttk.Button(footer,text='닫기',command=win.destroy))
    from .inventory import build_inventory_frame
    notebook=ttk.Notebook(win);notebook.pack(fill='both',expand=True)
    body=build_evidence_frame(notebook,packet);notebook.add(body,text='원본·대사 근거')
    inventory=build_inventory_frame(notebook,packet);notebook.add(inventory,text='계산표 포함·생략 범위')
    win.inventory_body=inventory
    win.packet=packet;win.evidence_body=body
    return win
