"""Program-rendered recorded metadata/facts; never rewritten model narrative."""
from common import dumps
from .headers import identity
from .versions import FIELDS

_KINDS={'exception':'프로그램 예외 기록','ledger_reconciliation':'원장 대사 기록',
    'run_summary':'자동검사 실행 기록','calculation_row':'프로그램 계산표 발췌',
    'raw_xlsx_row':'등록 원본 행 발췌·진위 미검증','raw_json':'등록 JSON 발췌·진위 미검증',
    'source_copy':'등록 사본 정보·외부 수령 미검증','engagement':'업무 기본정보',
    'procedure_definition':'선택 절차 정의',
    'misstatement_record':'사람 입력 왜곡표시 기록·회계적 관련성 미검증',
    'human_assertion_risk_assessment':'사람 입력 주장별 위험평가·판단 미검증',
    'human_risk_response':'사람 입력 위험대응 계획·회계적 관련성 미검증',
    'human_actual_performance':'사람 입력 수행기록·실제 수행 미검증',
    'human_workpaper_connection':'사람 선택 조서 연결·근거 충분성 미검증'}


def render(packet,claims):
    current=identity(packet);refs=[ref['id'] for ref in packet['references']]
    metadata=[r['id'] for r in packet['references'] if r['kind'] in ('engagement','procedure_definition')]
    links=list(dict.fromkeys(claim['reference_id'] for claim in claims)) or metadata or refs[:1]
    lines=[]
    for claim in claims:
        status='원문 상태 필드 없음' if claim['status'] is None else dumps(claim['status'])
        lines.append(f"[{claim['reference_id']}] {_KINDS.get(claim['reference_kind'],'등록 근거 기록')}; "
            f"종류={claim['reference_kind']}; 상태={status}; 경로={dumps(claim['value_path'])}; "
            f"원문값={dumps(claim['value'])}; 단위={dumps(claim['unit'])}")
    label='[프로그램 고정 정보·근거 기록 / 모델 자유서술 아님]\n'
    header=f"회사: {current['company_name']} ({current['company_code']})\n기간: {current['start_date']}~{current['end_date']}\n절차: {current['procedure_id']} · {current['procedure_title']}"
    human=packet['contract']['human_performance']
    human_text=('사용자의 수행기록이 있으나 실제 수행은 프로그램이 검증하지 않았습니다.'
        if human['state']=='user_recorded_unverified' else '사용자의 실제 수행일·수행내용 기록이 없습니다.')
    fields={'purpose':label+header,
        'risk':label+'아래는 근거에 기록된 항목입니다. 회계적 위험평가·증거의 충분성은 사람이 판단해야 합니다.\n'+'\n'.join(lines),
        'scope':label+header+'\n선택된 등록 자료와 계산·대사 발췌 범위입니다. 전체 모집단·자료의 진실성을 인증하지 않습니다.',
        'performed':label+'프로그램이 표시한 근거 종류·상태·원문값:\n'+'\n'.join(lines)+'\n'+human_text+' 실사·조회 발송·회신 진위·외부 증빙 수령을 확인했다고 해석할 수 없습니다.',
        'conclusion':label+'사람의 감사판단·결론은 자동 작성하지 않았습니다. 예외와 미확인 사항을 직접 확인하세요. 모델의 미검증 제안은 별도로 격리하며 이 본문에 자동 합치지 않습니다.'}
    if current['synthetic']:
        fields={key:value+'\nSYNTHETIC ONLY / 실제 감사증거·감사결론 아님' for key,value in fields.items()}
    citations={field:list(metadata or links) if field in ('purpose','scope') else list(links) for field in FIELDS}
    return fields,citations
