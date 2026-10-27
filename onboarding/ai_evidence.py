"""Reserve bounded actual input and calculation rows for the selected procedure."""
from common import digest,json


def excerpt(row):
    if not isinstance(row,dict):return row
    keys=list(row)[:12]
    value={key:row[key] for key in keys}
    if len(keys)<len(row):value['_생략항목수']=len(row)-len(keys);value['_전체행해시']=digest(row)
    return value


def reserve(ws,module,chosen,ref):
    protected=set()
    selected=next((r for r in chosen if r['module']==module),None)
    if not selected:return protected
    tables=selected['result']['tables']
    names=sorted((name for name,rows in tables.items() if rows and not name.startswith('입력_')),
                 key=lambda name:(not any(word in name for word in ('대사','금액','증감','현금')),name))
    if names:
        name=names[0]
        rid=ref('calculation_row',{'table':name,'row':excerpt(tables[name][0]),
            'scope':'실제 계산표 첫 행 발췌. 표 전체 검사와 별도'},
            run_id=selected['id'],result_hash=selected['result_hash'],
            table_row=1,row_hash=digest(tables[name][0]))
        if rid:protected.add(rid)
    source=ws.sources[selected['source_id']];path=ws.root/source['file']
    if path.suffix.lower()=='.json':
        payload=json.loads(path.read_text(encoding='utf-8'))
        priority=('source_rows','asset_movements','population','institution_sources',
                  'note_movements','classification_items','cash_allocations')
        names=sorted((key for key,rows in payload.items() if isinstance(rows,list) and rows),
                     key=lambda key:(priority.index(key) if key in priority else len(priority),key))
        if names:
            key=names[0];rows=payload[key]
            rid=ref('raw_json',{'table':key,'row':excerpt(rows[0]),'available_rows':len(rows),
                'included_rows':1,'table_hash':digest(rows),'scope':'현재 입력 원문 첫 행 발췌; 나머지 행은 로컬 원본 확인'},
                source_id=source['id'],sha256=source['sha256'])
            if rid:protected.add(rid)
    return protected
