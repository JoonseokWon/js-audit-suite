"""Reserve an actual original excerpt before optional human-record expansions."""
from common import AuditError,cancelled,json
from .source_read import read_source_tables


def reserve(ws,source_ids,ref,cache,priority,event=None):
    for sid in source_ids:
        cancelled(event);source=ws.sources[sid];path=ws.root/source['file']
        if path.suffix.lower()=='.xlsx':
            tables,_=read_source_tables(ws,sid,path,event);cache[sid]=tables
            for name in sorted(tables,key=priority):
                if not tables[name]:continue
                row=tables[name][0]
                rid=ref('raw_xlsx_row',{'sheet':name,'row':row.get('_row'),'values':row,
                    'book':'','dataset_id':''},source_id=sid,sha256=source['sha256'],
                    workbook_sha256=source['sha256'])
                if not rid:raise AuditError('최소 원문 행과 필수 AI 근거가 문자 한도를 초과했습니다. 관련 범위를 줄이세요.')
                return rid,(sid,name,row.get('_row'))
        elif path.suffix.lower()=='.json':
            data=json.loads(path.read_text(encoding='utf-8'))
            rid=ref('raw_json',data,source_id=sid,sha256=source['sha256'])
            if not rid:raise AuditError('최소 원문 JSON과 필수 AI 근거가 문자 한도를 초과했습니다. 관련 범위를 줄이세요.')
            return rid,(sid,'json',None)
    return None,None
