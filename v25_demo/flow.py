"""One accepted response → synthetic edit/approval/review → exact export → stale cases."""
from pathlib import Path
import hashlib
import json
from workspace import Workspace
import audit_links as links
import misstatements as ms
from .case import ACTOR, RESPONSE
from .excel import verify_export
from .changes import verify_changes


def complete_actual(ws, packet, response, out, check):
    out = Path(out); original = response['raw_response']; parsed = json.loads(original)
    proposals = parsed['proposals']; checks = []
    def verify(ok, name):
        check(ok, name); checks.append(name)
    verify(packet['procedure']['id'] == 'A04', 'v25_complete_targets_own_A04_procedure')
    verify(packet['contract']['human_performance']['state'] == 'user_recorded_unverified', 'v25_saved_synthetic_performance_is_recorded_but_never_authenticated')
    did = ws.record_ai_draft(packet, response, ACTOR + ' / AI 응답 기록')
    verify(not ws.procedures.get('A04') and not ws.ai_approvals, 'v25_received_model_response_never_auto_applies_or_approves')
    ws.apply_ai_draft(did, ACTOR + ' / 초안 적용')
    verify(all(ws.procedures['A04'][key] == value for key, value in response['verified_fields'].items()), 'v25_only_program_fact_records_are_applied_to_workpaper')
    verify(not ws.ai_status('A04')['approved'] and not ws.procedures['A04'].get('performed_date'), 'v25_application_never_creates_human_date_or_content_approval')
    verify(all(ws.procedures['A04'][key] != value for key, value in proposals.items()), 'v25_free_model_proposals_remain_separate_and_unapplied')
    marker = ACTOR + ' / SI01의 7원 차이는 가상 송장 과대 가정의 조사·판단 입력 모사이며 실제 감사판단 아님.'
    p = dict(ws.procedures['A04']); p['performed'] += '\n' + ACTOR + ' / 원본과 실행 결과 대사의 실제 수행 입력을 모사. 실제 고객 증거 검사 아님.'
    p['conclusion'] += '\n' + marker; p['performed_date'] = '2026-12-31'
    p['evidence_ids'] = [run['source_id'] for run in ws.latest().values()]; ws.save_procedure(p)
    verify(not ws.ai_status('A04')['approved'], 'v25_explicit_synthetic_human_edit_remains_unapproved_until_separate_action')
    ws.approve_ai_content('A04', ACTOR + ' / 내용 승인 상태전이', ACTOR + ' / 저장한 내용·원문·근거를 직접 확인한 입력 모사. 실제 사람 승인 아님.')
    verify(ws.ai_status('A04')['approved'] and not ws.procedures['A04'].get('reviewed_at'), 'v25_synthetic_content_approval_is_distinct_from_workpaper_review')
    ws.request_review('A04'); ws.review('A04', ACTOR + ' / 작성자와 다른 검토자', ACTOR + ' / 별도 검토 입력 모사. 실제 감사 검토 아님.')
    records = ms.list_records(ws)
    links.bind_workpaper(ws, RESPONSE, {'workpaper_id': 'A04', 'note_ids': [], 'f03_id': 'F03',
                                      'misstatement_ids': [r['id'] for r in records]}, ACTOR)
    verify(not links.status(ws)['blockers'], 'v25_current_synthetic_risk_performance_F03_and_misstatement_links_are_connected')
    verify(not ms.status(ws)['blockers'], 'v25_misstatement_register_has_explicit_synthetic_classification_group_and_F03_review')
    reopened = Workspace(ws.root)
    verify(reopened.ai_drafts[did]['raw_response'] == original and reopened.ai_drafts[did]['unverified_proposals'] == proposals,
           'v25_reopen_preserves_exact_original_and_quarantined_model_proposals')
    verify(reopened.ai_status('A04')['approved'] and reopened.procedure_state(reopened.procedures['A04']) == '검토기록완료',
           'v25_explicit_synthetic_content_approval_and_separate_review_survive_reopen')
    target = verify_export(reopened, did, original, out, verify)
    paths = verify_changes(reopened, packet, response, out, verify)
    approvals = sum(e['kind'] == 'ai_content_approval' for e in reopened.events)
    verify(approvals == 1, 'v25_exactly_one_new_synthetic_content_approval_event_not_inherited_copy_counts')
    return {'draft_id': did, 'workspace': str(reopened.root), 'export': str(target), 'stale_workspaces': paths,
            'synthetic_approval_events': approvals, 'actual_human_approvals': 0,
            'raw_response_utf8_sha256': hashlib.sha256(original.encode('utf-8')).hexdigest(),
            'integration_checks': checks, 'human_approval_scope': 'SYNTHETIC ONLY state transitions; no actual human audit performance, judgment, approval or review',
            'physical_IME_verified': False, 'physical_DPI_verified': False, 'actual_Office_render_verified': False}
