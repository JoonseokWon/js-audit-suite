"""Independent new synthetic copies preserve the completed baseline and original response."""
from pathlib import Path
from copy import deepcopy
import shutil
from common import AuditError, digest
from workspace import Workspace
import audit_links as links
import misstatements as ms
from .case import ACTOR, RISK


def verify_changes(ws, packet, response, out, check):
    from demo_case import load_manifest
    out = Path(out); paths = {}; base_events = deepcopy(ws.events); head = ws.head
    def branch(name):
        target = out/('무효화_합성사본_' + name)
        if target.exists():
            raise AuditError('무효화 검증 사본은 새 경로만 사용합니다.')
        shutil.copytree(ws.root, target); copy = Workspace(target); paths[name] = str(target)
        return copy
    edited = branch('본문수정'); p = dict(edited.procedures['A04'])
    p['conclusion'] += '\n' + ACTOR + ' / 승인 이후 본문 수정 입력 모사'; edited.save_procedure(p)
    check(not edited.ai_status('A04')['approved'], 'v25_text_edit_invalidates_prior_synthetic_content_approval')
    check(any(r['code'] == 'WORKPAPER_CHANGED' for r in links.status(edited)['blockers']), 'v25_text_edit_invalidates_bound_workpaper_fingerprint')
    assessed = branch('위험재평가'); existing = links.refresh(assessed)['assessments'][RISK]
    fields = ('risk_id', 'assertions', 'inherent_rating', 'inherent_reason', 'control_rating', 'control_reason', 'significant_risk', 'significant_reason')
    value = {key: deepcopy(existing[key]) for key in fields}; value['control_reason'] = ACTOR + ' / 새로운 통제평가 입력 모사'
    links.save_assessment(assessed, value, ACTOR)
    check(not assessed.ai_status('A04')['approved'] and assessed.ai_status('A04')['stale'], 'v25_human_risk_change_invalidates_previous_AI_basis_and_approval')
    check(any(r['code'] == 'RESPONSE_STALE' for r in links.status(assessed)['blockers']), 'v25_human_risk_change_requires_response_and_workpaper_reconnection')
    check(all(ms.record_status(assessed, r['id'])['current'] for r in ms.list_records(assessed)),
          'v25_risk_only_change_does_not_falsely_reclassify_misstatement_data_basis')
    changed = branch('원장재실행'); entry = load_manifest(changed.root)['inputs']['ledger_clean']
    before = len(changed.ai_drafts); changed.execute(entry['module'], entry['path'])
    check(changed.ai_status('A04')['stale'] and not changed.ai_status('A04')['approved'], 'v25_ledger_rerun_invalidates_prior_AI_basis_and_approval')
    check(all(not ms.record_status(changed, r['id'])['current'] for r in ms.list_records(changed)), 'v25_ledger_rerun_requires_misstatement_reconfirmation')
    check(any(r['code'] == 'RESPONSE_STALE' for r in links.status(changed)['blockers']), 'v25_ledger_rerun_invalidates_risk_response_source_and_run_connections')
    try:
        changed.record_ai_draft(packet, response, ACTOR + ' / 오래된 응답 재저장 거절 시험')
    except AuditError:
        pass
    else:
        raise AssertionError('v25_old_response_must_not_be_saved_after_ledger_change')
    check(len(changed.ai_drafts) == before, 'v25_old_received_response_is_not_saved_again_after_basis_change')
    for child in (edited, assessed, changed):
        check(child.events[:len(base_events)] == base_events, 'v25_' + child.root.name + '_preserves_all_prior_events')
        check(sum(e['kind'] == 'ai_content_approval' for e in child.events) == 1, 'v25_' + child.root.name + '_creates_no_new_approval')
    ws.refresh()
    check(ws.head == head and digest(ws.events) == digest(base_events) and ws.ai_status('A04')['approved'],
          'v25_completed_baseline_is_preserved_while_negative_cases_use_separate_copies')
    return paths
