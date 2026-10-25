"""Process guidance follows saved evidence and human records without changing them."""
from copy import deepcopy
import unittest
from desktop.progress import summarize_progress


def synthetic_state():
    record = {key: 'SYNTHETIC ONLY' for key in
              ('purpose', 'risk', 'scope', 'performed', 'conclusion', 'performed_date', 'preparer')}
    record.update(evidence_ids=['S1'], current_state='검토기록완료', ai_required=True, ai_approved=True)
    return {
        'has_workspace': True, 'source_count': 1,
        'latest': {'원장·리드': {'result': {'blocking': 0}}},
        'cross': [{'상태': '일치'}], 'required': ['C01'],
        'procedures': {'C01': record}, 'requests': [], 'notes': [],
        'archive_matches_current': False,
        'workflow': {
            'active': True, 'locked': False, 'blockers': [],
            'profile': {'materiality': {'overall_materiality': 100},
                        'scope': [{'procedure_id': 'C01', 'applicable': True}]},
            'risks': [{'id': 'R1', 'procedure_ids': ['C01']}],
            'procedure_links': [{'procedure_id': 'C01', 'risk_ids': ['R1'], 'evidence_ids': ['S1'],
                                 'performed': 'SYNTHETIC ONLY', 'performed_date': '2026-10-25',
                                 'performer': '합성수행자'}],
        },
    }


class BentoProgressTests(unittest.TestCase):
    def summarize_without_change(self, state):
        before = deepcopy(state)
        result = summarize_progress(state)
        self.assertEqual(state, before)
        return result

    def test_empty_workspace_has_no_completed_stage_and_starts_with_selection(self):
        result = self.summarize_without_change({})
        self.assertEqual(result['current']['id'], 'company')
        self.assertFalse(any(row['complete'] for row in result['stages']))
        self.assertEqual([row['id'] for row in result['next_steps']], ['company', 'plan', 'data'])

    def test_completed_analysis_cannot_replace_missing_human_audit_plan(self):
        state = synthetic_state()
        state['workflow'].update(active=False, profile=None, risks=[], procedure_links=[])
        result = self.summarize_without_change(state)
        self.assertEqual(result['current']['id'], 'plan')
        self.assertFalse(next(row for row in result['stages'] if row['id'] == 'plan')['complete'])
        self.assertNotIn('data', [row['id'] for row in result['next_steps']])
        self.assertNotIn('reconcile', [row['id'] for row in result['next_steps']])

    def test_remaining_work_tracks_risks_performance_review_ai_approval_and_archive(self):
        state = synthetic_state()
        state['workflow']['risks'] = []
        self.assertEqual(self.summarize_without_change(state)['current']['id'], 'risk')
        state['workflow']['risks'] = [{'id': 'R1', 'procedure_ids': ['C01']}]
        state['procedures']['C01']['performed'] = ''
        self.assertEqual(self.summarize_without_change(state)['current']['id'], 'workpaper')
        state['procedures']['C01'].update(performed='합성 수행기록', current_state='작성중')
        self.assertEqual(self.summarize_without_change(state)['current']['id'], 'review')
        state['procedures']['C01'].update(current_state='검토기록완료', ai_approved=False)
        self.assertEqual(self.summarize_without_change(state)['current']['id'], 'review')
        state['procedures']['C01']['ai_approved'] = True
        self.assertEqual(self.summarize_without_change(state)['current']['id'], 'archive')
        state['workflow']['locked'] = True
        self.assertEqual(self.summarize_without_change(state)['current']['id'], 'archive')
        state['archive_matches_current'] = True
        result = self.summarize_without_change(state)
        self.assertEqual(result['current']['id'], 'confirmed')
        self.assertEqual(result['next_steps'], [])
        state['procedures']['C01']['current_state'] = '자료변경·재검토'
        self.assertEqual(self.summarize_without_change(state)['current']['id'], 'workpaper')


if __name__ == '__main__':
    unittest.main()
