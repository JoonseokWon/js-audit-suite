"""The ledger follows Excel's worksheet ceiling; other module contracts stay scoped."""
EXCEL_DATA_ROWS=1048575
MAX_SOURCE_BYTES=256*1024**2
MAX_EXPANDED_BYTES=1024**3
MAX_WORKBOOK_ROWS=2000000
LEDGER_LIMITS={'총계정원장':EXCEL_DATA_ROWS}

# These describe integrated entry points, not unrelated standalone engine limits.
SMALL_MODULES={'금융상품','매출','감가상각','확장검사'}
ESTIMATE_MODULES={'리스','대손충당금','재고평가','종업원급여','미기록부채·비용이연'}
ANALYTIC_MODULES={'GLA','FIA','현금분석'}


def module_limits(module):
    value=dict(data_rows=10000,max_source_bytes=MAX_SOURCE_BYTES,row_limits={},
        scope='헤더 1행 제외 물리 데이터 행 위치. 빈 행·숨김 행도 위치 한도에 포함.')
    if module=='원장·리드':
        value.update(data_rows=EXCEL_DATA_ROWS,row_limits=dict(LEDGER_LIMITS),
            default_sheet_rows=10000,scope='총계정원장 1,048,575행, 나머지 시트 10,000행. '
            '헤더 제외 물리행 기준·전체 워크북 2,000,000행·압축해제 1GB.')
    elif module in SMALL_MODULES:
        value['data_rows']=1000
        if module=='금융상품':value['max_source_bytes']=20*1024**2
        elif module=='감가상각':value['max_source_bytes']=10*1024**2
    elif module=='실무자료·원장':
        value.update(max_source_bytes=20*1024**2,raw_source_rows=EXCEL_DATA_ROWS,
            raw_source_bytes=MAX_SOURCE_BYTES,
            scope='정형 Excel 양식 시트별 10,000행/20MB. JSON 원본 행은 최대1,048,575행·다른표10,000행/20MB. '
            'ERP 원본 열 가져오기는 최대1,048,575행/256MB이며 실제 처리 가능량은 각 형식 한도와 별도.')
    elif module in {'유형자산증감','감사표본선정','금융기관조회','주석구성대사','분류검토','현금흐름표연결'}:
        value['max_source_bytes']=20*1024**2
    elif module=='원천증빙':
        value.update(max_source_bytes=40*1024**2,scope='원천 패키지40MB·개별파일20MB·시트10,000행·압축해제100MB.')
    elif module=='재무제표·주석':
        value.update(max_source_bytes=2*1024**2,scope='JSON 2MB·표별10,000행. Excel 양식 입력 모듈과 구분.')
    elif module=='계정별증빙연습':
        value.update(data_rows=None,max_source_bytes=2*1024**2,scope='JSON 2MB·정의된 사례 규격. 일반 Excel 행수 한도를 적용하지 않음.')
    elif module not in ESTIMATE_MODULES|ANALYTIC_MODULES:
        raise ValueError('지원하지 않는 입력 모듈: '+str(module))
    return value


def module_limit_text(module):
    value=module_limits(module);rows=value['data_rows'];size=value['max_source_bytes']//1024**2
    if module=='원장·리드':return f'원장·리드: 총계정원장 {rows:,}행·다른 시트 10,000행 / {size}MB. '+value['scope']
    if module=='실무자료·원장':return '실무자료·원장: '+value['scope']
    if module in {'원천증빙','재무제표·주석','계정별증빙연습'}:return module+': '+value['scope']
    return f'{module}: '+(f'시트별 {rows:,}행(헤더 제외) / ' if rows is not None else '')+f'{size}MB. '+value['scope']
