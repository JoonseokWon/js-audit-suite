"""Lossless compact wire form; the UI expands column names before display."""
from copy import deepcopy
from common import AuditError

COLUMNS=('run','table','available','included','omitted','hash','reasons')
REASONS={'I':'input_source_only','T':'table_limit','R':'row_limit','B':'reference_or_character_budget'}


def compact_manifest(manifest):
    result={k:deepcopy(v) for k,v in manifest.items() if k not in ('schema','tables')}
    result.update(schema='calculation-inventory-2',columns=list(COLUMNS),reason_codes=REASONS,
        tables=[[row[k] if k!='reasons' else
                {code:row[k][name] for code,name in REASONS.items() if name in row[k]}
                for k in COLUMNS] for row in manifest['tables']])
    return result


def table_rows(manifest):
    if manifest.get('schema')=='calculation-inventory-1':return deepcopy(manifest['tables'])
    if (manifest.get('schema')!='calculation-inventory-2' or manifest.get('columns')!=list(COLUMNS)
            or manifest.get('reason_codes')!=REASONS):raise AuditError('계산표 명세 형식 오류')
    result=[]
    for values in manifest['tables']:
        if not isinstance(values,list) or len(values)!=len(COLUMNS):raise AuditError('계산표 명세 열 오류')
        row=dict(zip(COLUMNS,values));reasons=row['reasons']
        if not isinstance(reasons,dict) or set(reasons)-set(REASONS):raise AuditError('계산표 생략 사유 오류')
        row['reasons']={REASONS[k]:v for k,v in reasons.items()};result.append(row)
    return result
