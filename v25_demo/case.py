"""Synthetic input simulation before an optional real model call; calls no model."""
from pathlib import Path
import audit_links as links
import misstatements as ms
from common import atomic, dumps

ACTOR = 'SYNTHETIC ONLY / 가상 사람 입력 모사'
RISK = 'V25-SALES-ACCURACY'
RESPONSE = 'V25-RESPONSE-A04'


def _profile():
    return {'audit_framework': 'KSA_200_720', 'audit_framework_reason': ACTOR + ' / 적용 선택 모사',
            'form_framework': 'KIFRS', 'materiality': {'benchmark_name': ACTOR + ' / 가상 매출',
                'benchmark_amount': 100000, 'materiality_rate': '0.01', 'performance_rate': '0.5', 'trivial_rate': '0'},
            'scope': [{'procedure_id': pid, 'applicable': True, 'reason': ACTOR + ' / 선택 절차 입력 모사'} for pid in ('A04', 'F03')]}


def paper(ws, pid, *, review=False):
    value = {'id': pid, 'title': ACTOR + ' / ' + pid, 'purpose': ACTOR + ' / 매출 차이와 원본 관련성 검토 모사',
             'risk': ACTOR + ' / 송장 정확성 및 매출 완전성 위험', 'scope': ACTOR + ' / SI01 및 독립 원장·매출 자료',
             'performed': ACTOR + ' / 합성 자료 대사 및 판단 입력을 모사. 실제 감사증거 검사 아님.',
             'conclusion': ACTOR + ' / 7원 과대 송장이 오류인 가정의 상태전이. 실제 회계적 결론 아님.',
             'performed_date': '2026-12-31', 'preparer': ACTOR + ' / 작성자', 'evidence_ids': list(ws.sources), 'excluded': False}
    ws.save_procedure(value)
    if review:
        ws.request_review(pid); ws.review(pid, ACTOR + ' / 별도 검토자', ACTOR + ' / 별도 내용 검토 입력 모사')


def actual_case(out, check):
    from ai_quality.case_v25 import create_case
    out = Path(out); ws, manifest = create_case(out, check)
    ws.save_workflow_profile(_profile(), ACTOR)
    risk = {'id': RISK, 'title': ACTOR + ' / 매출 송장 정확성 위험', 'accounts': ['매출', '매출채권'],
            'assertions': ['정확성', '완전성'], 'procedure_ids': ['A04'], 'basis': ws.data_basis(),
            'evidence_ids': list(ws.sources), 'nature': ACTOR + ' / 증빙과 원장 대사', 'timing': ACTOR + ' / 기말',
            'extent': ACTOR + ' / SI01과 대조 원장', 'assessment': ACTOR + ' / 위험 식별 입력 모사'}
    ws.save_workflow_risk(risk, ACTOR)
    ws.save_workflow_procedure({'procedure_id': 'A04', 'risk_ids': [RISK], 'evidence_ids': list(ws.sources),
        'basis': ws.data_basis(), 'nature': ACTOR + ' / 원장·송장 대사', 'timing': ACTOR + ' / 기말', 'extent': ACTOR + ' / SI01',
        'plan': ACTOR + ' / 직접 대사 계획', 'performed': ACTOR + ' / 가상 수행내용 입력 모사',
        'performed_date': '2026-12-31', 'performer': ACTOR + ' / 가상 수행자'}, ACTOR)
    assertions = [{'category': '거래', 'assertion': value} for value in ('정확성', '완전성')]
    assessment = links.save_assessment(ws, {'risk_id': RISK, 'assertions': assertions, 'inherent_rating': '높음',
        'inherent_reason': ACTOR + ' / 송장 차이 가정', 'control_rating': '보통', 'control_reason': ACTOR + ' / 가상 통제 평가',
        'significant_risk': False, 'significant_reason': ACTOR + ' / 유의적위험 여부 입력 모사'}, ACTOR)
    selected = []
    for run in ws.latest().values():
        selected.append({'source_id': run['source_id'], 'company_code': ws.context['회사코드'],
            'start_date': ws.context['시작일'], 'end_date': ws.context['기준일'],
            'locator': ACTOR + (' / 총계정원장 J-S1' if run['module'] == '원장·리드' else ' / invoices SI01'),
            'relevance': ACTOR + ' / 가상 원장·송장의 정확성 및 완전성 대사'})
    links.save_response(ws, {'id': RESPONSE, 'risk_id': RISK, 'procedure_id': 'A04', 'assertions': assertions,
        'nature': ACTOR + ' / 독립 원장·송장 대사', 'timing': ACTOR + ' / 기말', 'extent': ACTOR + ' / SI01',
        'sources': selected, 'run_ids': [r['id'] for r in ws.latest().values()]}, ACTOR)
    links.save_performance(ws, {'response_id': RESPONSE, 'performed': ACTOR + ' / 원본·결과 대사 가상 입력',
        'performed_date': '2026-12-31', 'performer': ACTOR + ' / 수행자', 'sufficiency': '충분',
        'sufficiency_reason': ACTOR + ' / 충분성 판단 입력의 상태전이이며 실제 감사판단 아님'}, ACTOR)
    candidates = [row for row in ms.candidates(ws) if row['module'] == '매출' and row['identity'].get('invoice_id') == 'SI01' and abs(row.get('amount') or 0) == 7]
    check(bool(candidates), 'v25_independent_seven_won_candidate_has_invoice_SI01')
    values = {'description': ACTOR + ' / 동일 SI01 7원 과대 가정', 'assessment': '왜곡표시', 'classification': '사실', 'amount': 7,
        'correction_state': '미수정', 'company_position': '이견있음', 'company_note': ACTOR + ' / 회사 이견 가상 입력',
        'period': '당기', 'qualitative': '있음', 'qualitative_note': ACTOR + ' / 통제우회 정성적 고려 가정',
        'tax_effect': 0, 'tax_basis': ACTOR + ' / 세효과 0 가정',
        'account_impacts': [{'account_code': code, 'fs_line': title, 'direction': '감소', 'amount': 7} for code, title in (('1100', '매출채권'), ('4000', '매출'))],
        'candidate_ids': [candidates[0]['id']], 'evidence_ids': [r['source_id'] for r in ws.latest().values()],
        'procedure_ids': ['A04', 'F03'], 'judgment': ACTOR + ' / 7원 과대 송장을 오류로 가정한 상태전이. 실제 오류 확정 아님.'}
    records = [ms.save_record(ws, values, ACTOR) for _ in range(2)]
    check(ms.snapshot_rows(ws)['summary'][0]['gross_amount'] == 14, 'v25_ungrouped_two_candidates_are_not_auto_deduplicated')
    group = ms.save_group(ws, {'member_ids': [r['id'] for r in records], 'primary_id': records[0]['id'],
        'reason': ACTOR + ' / 동일 SI01을 두 절차에서 기록했다고 가정한 동일오류 판단'}, ACTOR)
    snap = ms.snapshot_rows(ws)
    check(snap['summary'][0]['gross_amount'] == 7 and snap['summary'][0]['count'] == 1, 'v25_explicit_group_counts_seven_won_once')
    check(len(snap['account_impacts']) >= 4, 'v25_all_member_account_impacts_are_preserved')
    paper(ws, 'F03', review=True)
    check(not ws.procedures.get('A04') and not ws.ai_approvals, 'v25_A04_waits_for_AI_without_automatic_content_approval')
    check(ws.procedure_state(ws.procedures['F03']) == '검토기록완료', 'v25_F03_has_only_explicit_synthetic_separate_review')
    meta = {'schema': 'v25-integrated-synthetic-case-1', 'risk_id': RISK, 'response_id': RESPONSE,
            'assessment_revision': assessment['revision'], 'misstatement_ids': [r['id'] for r in records],
            'group_id': group['id'], 'expected_gross': 7, 'expected_count': 1, 'actual_model_calls': 0,
            'actual_human_approvals': 0, 'scope': ACTOR + ' / 실제 감사판단·수행·승인 아님'}
    atomic(out/'통합_합성사례.json', dumps(meta).encode('utf-8'))
    return ws, {**manifest, 'v25': meta}
