"""Preserve each engine's actual bounds and explain physical row-limit errors."""
from pathlib import Path
from zipfile import ZipFile,BadZipFile
from common import AuditError, read_xlsx, cancelled
from input_limits import module_limits


def _overflow(path,limits,event):
    from xlsx_reader import sheet_paths
    from defusedxml.ElementTree import iterparse
    try:
        with ZipFile(path) as book:
            for filename,name in sheet_paths(book).items():
                maximum=limits['row_limits'].get(name,limits.get('default_sheet_rows',limits['data_rows']))
                with book.open(filename) as stream:
                    stack=[]
                    for action,row in iterparse(stream,events=('start','end')):
                        if action=='start':stack.append(row);continue
                        if row.tag.rsplit('}',1)[-1]=='row':
                            cancelled(event);number=int(row.get('r','0'))
                            if number>maximum+1:return name,number,maximum
                            row.clear()
                            if len(stack)>1:stack[-2].remove(row)
                        stack.pop()
    except AuditError:raise
    except (ValueError,KeyError,OSError,BadZipFile):return None
    return None


def read_module_xlsx(module,path,schema=None,event=None):
    limits=module_limits(module);path=Path(path)
    if path.stat().st_size>limits['max_source_bytes']:
        raise AuditError(f'{module}: 파일 {path.stat().st_size:,}바이트 / 지원 {limits["max_source_bytes"]//1024**2}MB 한도 초과')
    try:
        return read_xlsx(path,schema,event,max_rows=limits.get('default_sheet_rows',limits['data_rows']),
            row_limits=limits['row_limits'])
    except AuditError as exc:
        if any(t in str(exc) for t in ('물리 행 순서/한도','입력 한도 초과')):
            found=_overflow(path,limits,event)
            if found:
                name,number,maximum=found
                raise AuditError(f'{module} / {name}: 데이터 물리행 위치 {number-1:,}행 '
                    f'(Excel 행 {number:,}, 헤더 1행 제외), 지원 한도 {maximum:,}행. '
                    '빈 행·숨김 행도 물리 위치에 포함되며 행을 잘라 처리하지 않습니다.') from exc
        raise AuditError(module+': '+str(exc)) from exc
