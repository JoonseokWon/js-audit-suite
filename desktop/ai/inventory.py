"""Show final packet row coverage; hashes do not imply the model read all rows."""
from tkinter import ttk
from desktop.widgets.tables import tree
from .evidence import wrapping_label

REASONS={'input_source_only':'입력표 내용 미선택','table_limit':'표 개수 한도',
         'row_limit':'표별 행 한도','reference_or_character_budget':'근거 수·문자 한도'}


def inventory_rows(packet):
    from ai_evidence_inventory import table_rows
    inventory=packet.get('calculation_inventory',{});runs=inventory.get('runs',[]);rows=[]
    for item in table_rows(inventory) if inventory else []:
        index=item['run'];run=runs[index] if type(index) is int and 0<=index<len(runs) else {}
        reasons=', '.join(REASONS.get(key,key)+' '+str(value)+'행' for key,value in item.get('reasons',{}).items())
        rows.append({'모듈':run.get('module','미확인'),'계산표':item['table'],'전체 결과행':item['available'],
                     '포함행':item['included'],'생략행':item['omitted'],'생략 사유':reasons,'전체 표 SHA256':item['hash']})
    return rows


def build_inventory_frame(parent,packet):
    frame=ttk.Frame(parent,padding=10);inventory=packet.get('calculation_inventory')
    if not inventory:
        wrapping_label(frame,text='이전 근거 패킷에는 표별 포함·생략 명세가 없어요. 현재 근거로 다시 생성해 확인하세요.').pack(fill='x')
        return frame
    wrapping_label(frame,text=(f"계산 결과 {inventory['available']:,}행 중 고유 발췌 {inventory['included']:,}행, "
        f"생략 {inventory['omitted']:,}행.\n"+inventory['scope']+
        '\n전체 표 해시는 동일성 확인용이며 모델이 생략 행의 내용을 읽었다는 뜻이 아니에요.')).pack(fill='x',pady=(0,12))
    columns=['모듈','계산표','전체 결과행','포함행','생략행','생략 사유','전체 표 SHA256']
    listing=tree(frame,columns,12)
    for index,row in enumerate(inventory_rows(packet)):listing.insert('','end',iid=str(index),values=list(row.values()))
    for key in ('전체 결과행','포함행','생략행'):listing.column(key,width=105,anchor='e')
    listing.column('계산표',width=180);listing.column('생략 사유',width=260);listing.column('전체 표 SHA256',width=440)
    frame.inventory_tree=listing
    return frame
