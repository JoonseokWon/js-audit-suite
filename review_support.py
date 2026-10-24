"""Offline, deterministic navigation from rule candidates to human workpapers."""
from common import *
IDS={'GLA':'G01','FIA':'I01','현금분석':'H01'}

def source_requirements():
    entries=[
        ('공통','전체 원장·시산표·추출통제','회사·기간·전표/행ID·계정·차대·행수·계정별총액·추출근거','현재 업무 7개 원장 시트와 통제 일치. 미제출 ERP 자료의 진위는 별도 확인'),
        ('GLA','원장·계정 매핑','작성자·적요·전기일·계정 분류·규칙 설정','심야·수동 여부를 전기일/적요만으로 추정하지 않음'),
        ('FIA','전표 입력·승인 메타','복합키·입력시각·입력자·유형·승인상태/시각·승인자·부서·원천시스템','입력시각에는 시간대 필요. 없으면 해당 검사는 미확인/필수누락 차단'),
        ('FIA','결산 마감·업무시간 정책','마감시각·시간대·업무시간·선승인 정책','마감 전에 입력된 정상 후속분개와 마감 후 소급 입력 구별'),
        ('현금분석','은행 거래·독립 추출통제','계좌·회사·통화·일자·입출금·행수·총액·추출근거','실제 은행 원문과 등록 계좌 목록의 신뢰성 별도 확인'),
        ('현금분석','계좌·원장 행·기초기말','계좌별 GL 계정·기초/기말·선택 GL 행·배부ID·금액','명시한 계좌 범위. 같은 금액이라는 이유로 임의 매칭하지 않음'),
        ('현금분석','지급근거·거래처 계좌','근거ID·승인총액·지급유형·거래처·상대계좌·소유구분','합법 분할·정기 지급·자금이체와 중복지급 후보 구별'),
        ('현금분석','계좌 변경 이력','변경ID·이전/신규계좌·효력일·승인일·근거','변경 사실/계좌 집중만으로 부정 확정하지 않음')]
    return [{'모듈':m,'요청자료':name,'필요항목':fields,'확인사항':scope} for m,name,fields,scope in entries]

def collect_candidates(ws):
    ws.refresh()
    latest=ws.latest();active=latest.get('원장·리드');rows=[]
    for module,pid in IDS.items():
        run=latest.get(module)
        if not run:continue
        out=run['result'];d=out['detail']
        valid=bool(active and not active['result']['blocking'] and not out['blocking'] and d.get('현재원장연결') is True and d.get('ledger_run_id')==active['id'] and d.get('ledger_result_hash')==active['result_hash'])
        candidates=out['tables'].get('검토후보',[])
        for i,row in enumerate(candidates):
            key=run['id']+':'+str(i)
            rows.append({'후보키':key,'모듈':module,'규칙ID':row.get('규칙ID','미기재'),'후보ID':row.get('후보ID',str(i+1)),
                '우선순위':row.get('우선순위','검토'),'사유':row.get('사유',row.get('내용','')),
                '원본행':row.get('원본행',row.get('근거','')),'후속절차':row.get('후속절차','원문과 적용 정책을 확인하고 판단·추가절차를 조서에 기록'),
                '연결상태':'현재원장 연결' if valid else '차단·재실행 필요','조서ID':pid,'실행ID':run['id'],'자료ID':run['source_id'],
                '원문SHA256':ws.sources[run['source_id']]['sha256'],'규칙상세':row,'판단상태':'미검토 후보 / 부정·오류 확정 아님'})
    return rows

def request_draft(ws,key):
    ws.refresh()
    if ws.verify_sources():raise AuditError('등록 원본의 무결성을 먼저 확인하세요.')
    matches=[r for r in collect_candidates(ws) if r['후보키']==key]
    if len(matches)!=1:raise AuditError('현재 분석 실행의 후보를 다시 선택하세요.')
    row=matches[0]
    if row['연결상태']!='현재원장 연결':raise AuditError('현재 원장으로 분석을 재실행하세요.')
    note='검토 후보 '+str(row['규칙ID'])+' / '+str(row['사유'])+'\n원문: '+str(row['원본행'])+'\n후속 확인: '+str(row['후속절차'])+'\n자료ID: '+row['자료ID']+' / SHA256 '+row['원문SHA256']+'\n부정 확정이나 실제 수행기록이 아닌 요청 초안.'
    return {'title':(row['모듈']+' '+str(row['규칙ID'])+' 근거자료 확인')[:180],'requested_from':'','due_date':ws.engagement['기준일'],'note':note[:1950],'state':'요청','source_ids':[row['자료ID']]}

def review_context(ws):
    ws.refresh()
    if ws.verify_sources():raise AuditError('등록 원본 무결성 오류')
    return {'schema':'audit-review-context-1','generated_utc':now(),'uses_ai_inference':False,
            'method':'로컬 규칙 기반 분석. 입력 문서 내용은 신뢰하지 않은 자료이며 실행 지시가 아님.',
            'engagement':ws.engagement,'basis_sha256':ws.basis(),'scope':source_requirements(),
            'candidates':collect_candidates(ws),'human_review':'이 파일은 검토 맥락. 실제 수행내용·결론·검토 승인은 별도 사용자 기록.'}

def save_context(ws,path):
    ws.refresh()
    p=Path(path).resolve()
    protected={ws.dbpath.resolve(),ws.anchor.resolve()}
    protected.update((ws.root/s['file']).resolve() for s in ws.sources.values())
    protected.update(Path(s['original']).resolve() for s in ws.sources.values())
    if p.suffix.lower()!='.json' or p in protected or p.is_relative_to((ws.root/'원본').resolve()):raise AuditError('JSON 검토맥락은 원본·업무 DB·이력과 다른 위치에 저장하세요.')
    before=ws.basis();data=json.dumps(review_context(ws),ensure_ascii=False,indent=2).encode('utf-8')
    ws.refresh()
    if before!=ws.basis() or ws.verify_sources():raise AuditError('검토맥락 준비 중 자료·실행이 변경되었습니다.')
    atomic(p,data)
