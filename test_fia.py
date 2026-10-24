"""Literal metadata scenarios and policy boundaries tied to an actual GL."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import json
import unittest

import fia
import ledger
from common import AuditError
from fia.samples import normal_tables
from tools.analytics_fixtures import load_base, write_input

CONTEXT = {'회사코드': 'SYNTH01', '시작일': '2026-01-01', '기준일': '2026-12-31'}


class FIATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory(prefix='fia-tests-')
        cls.folder = Path(cls.tmp.name)
        cls.base = load_base()
        cls.ledger = ledger.analyze(cls.base)
        cls.samples = fia.write_samples(cls.folder / 'samples')
        cls.first = cls.base['총계정원장'][0]['전표ID']

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, prefix):
        case = next(c for c in self.samples['cases'] if c['id'].startswith(prefix))
        return fia.analyze(self.folder / 'samples' / case['file'], CONTEXT, self.ledger)

    def run_mutation(self, change, current=None):
        data = normal_tables(self.base)
        change(data)
        path = write_input(self.folder / (self._testMethodName + '.xlsx'), fia.SCHEMA, data, self.base)
        return fia.analyze(path, CONTEXT, self.ledger if current is None else current)

    def set_journal(self, data, **kwargs):
        for row in data['전표메타']:
            if row['전표ID'] == self.first:
                row.update(kwargs)

    def set_setting(self, data, key, value):
        next(r for r in data['FIA설정'] if r['항목'] == key)['값'] = value

    def assert_blocked_without_risk(self, result):
        self.assertGreater(result['blocking'], 0)
        self.assertFalse(result['detail']['분석완료'])
        self.assertFalse(result['tables'].get('검토후보'))

    def test_22_literal_file_expectations(self):
        self.assertEqual(len(self.samples['cases']), 22)
        for case in self.samples['cases']:
            with self.subTest(case=case['id']):
                r = self.run_case(case['id'])
                self.assertEqual(bool(r['blocking']), case['blocking'])
                self.assertEqual(bool(r['review']), case['review'])
                self.assertLessEqual(set(case['required_codes']), {i['code'] for i in r['issues']})
                if case['blocking']:
                    self.assert_blocked_without_risk(r)

    def test_normal_metadata_covers_all_82_rows_and_posting_is_separate(self):
        r = self.run_case('FIA_01_')
        self.assertEqual(r['metrics']['원장행수'], 82)
        self.assertTrue(r['detail']['현재원장연결'])
        self.assertTrue(r['detail']['분석완료'])
        self.assertEqual(r['tables']['검토후보'], [])
        self.assertEqual(len(r['tables']['규칙적용']), 8)
        self.assertTrue(all(x['상태'] == '조건해당없음' for x in r['tables']['규칙적용']))
        first = r['tables']['전표메타대사'][0]
        self.assertEqual(first['전기일'], '2026-12-31')
        self.assertEqual(first['입력시각'], '2027-01-05T10:00:00+09:00')

    def test_candidates_include_rule_raw_positions_and_followup(self):
        r = self.run_case('FIA_03_')
        row = r['tables']['검토후보'][0]
        self.assertEqual(row['규칙ID'], 'FIA_SELF_APPROVAL')
        self.assertEqual(row['규칙버전'], 'FIA-1.0')
        for key in ('후보ID', '사유', '전표ID', '원본행', '메타행', '후속절차', '조건', '우선순위'):
            self.assertTrue(row[key])
        self.assertIsNone(r['detail']['작성자'])
        self.assertIsNone(r['detail']['검토자'])
        self.assertIsNone(r['detail']['결론'])
        self.assertFalse(r['detail']['부정확정'])
        self.assertFalse(r['detail']['수정승인'])

    def test_no_current_ledger_blocks_every_risk_rule(self):
        normal = self.samples['normal']
        r = fia.analyze(normal, CONTEXT, None)
        self.assert_blocked_without_risk(r)
        self.assertIn('AN_LEDGER_REQUIRED', [i['code'] for i in r['issues']])
        self.assertFalse(r['detail']['현재원장연결'])

    def test_current_ledger_stale_result_blocks(self):
        stale = deepcopy(self.ledger)
        stale['tables']['리드스케줄'][0]['조정전'] += 1
        r = fia.analyze(self.samples['normal'], CONTEXT, stale)
        self.assert_blocked_without_risk(r)
        self.assertIn('AN_CURRENT_STALE', [i['code'] for i in r['issues']])

    def test_unrecognized_type_never_assumed_manual(self):
        r = self.run_case('FIA_13_')
        rule = next(x for x in r['tables']['규칙적용'] if x['규칙ID'] == 'FIA_MANUAL_CONCENTRATION')
        self.assertEqual(rule['상태'], '미확인')
        self.assertGreater(rule['미확인수'], 0)
        self.assertNotIn('FIA_MANUAL_CONCENTRATION', [i['code'] for i in r['issues']])

    def test_missing_department_is_unconfirmed_and_not_made_up(self):
        r = self.run_case('FIA_19_')
        first = r['tables']['전표메타대사'][0]
        self.assertIsNone(first['부서'])
        self.assertIsNone(first['원천시스템'])
        rule = next(x for x in r['tables']['규칙적용'] if x['규칙ID'] == 'FIA_METADATA_SCOPE')
        self.assertEqual(rule['상태'], '미확인')
        self.assertFalse(r['tables']['검토후보'])

    def test_input_and_approval_originals_are_preserved(self):
        r = self.run_case('FIA_15_')
        raw = r['tables']['입력_전표메타'][0]
        self.assertEqual(raw['승인시각'], '2027-01-04T10:05:00+09:00')
        self.assertEqual(r['detail']['설정']['선승인허용'], '예')
        self.assertTrue(r['source']['sha256'])

    def test_close_boundary_equal_is_not_after_close(self):
        def change(data):
            self.set_setting(data, '마감시각', '2027-01-05T10:00:00+09:00')
        r = self.run_mutation(change)
        self.assertFalse(r['review'])

    def test_close_boundary_one_second_later_is_candidate(self):
        def change(data):
            self.set_setting(data, '마감시각', '2027-01-05T09:59:59+09:00')
        r = self.run_mutation(change)
        self.assertIn('FIA_POST_CLOSE', [i['code'] for i in r['issues']])

    def test_business_start_inclusive(self):
        r = self.run_mutation(lambda d: self.set_journal(d, 입력시각='2027-01-05T09:00:00+09:00', 승인시각='2027-01-05T09:05:00+09:00'))
        self.assertFalse(r['review'])

    def test_business_end_exclusive(self):
        r = self.run_mutation(lambda d: self.set_journal(d, 입력시각='2027-01-05T18:00:00+09:00', 승인시각='2027-01-05T18:05:00+09:00'))
        self.assertIn('FIA_OUTSIDE_HOURS', [i['code'] for i in r['issues']])

    def test_equivalent_utc_timestamps_same_result(self):
        r = self.run_mutation(lambda d: self.set_journal(d, 입력시각='2027-01-05T01:00:00Z', 승인시각='2027-01-05T01:05:00Z'))
        self.assertFalse(r['blocking'])
        self.assertFalse(r['review'])

    def test_misleading_equal_local_clock_uses_absolute_timestamp(self):
        r = self.run_mutation(lambda d: self.set_journal(d, 입력시각='2027-01-05T10:00:00-05:00', 승인시각='2027-01-05T10:05:00-05:00'))
        self.assertIn('FIA_OUTSIDE_HOURS', [i['code'] for i in r['issues']])

    def test_manual_threshold_requires_count_amount_and_ratio(self):
        def change(data):
            self.set_journal(data, 전표유형='수동')
        r = self.run_mutation(change)
        self.assertNotIn('FIA_MANUAL_CONCENTRATION', [i['code'] for i in r['issues']])

    def test_manual_concentration_counts_journals_not_82_lines(self):
        r = self.run_case('FIA_06_')
        rows = [x for x in r['tables']['검토후보'] if x['규칙ID'] == 'FIA_MANUAL_CONCENTRATION']
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]['전표ID'].split(';')), len({r['전표ID'] for r in self.base['총계정원장']}))

    def test_reclassification_missing_is_not_none_or_zero_equivalent(self):
        r = self.run_mutation(lambda d: self.set_journal(d, 재분류그룹=None))
        rule = next(x for x in r['tables']['규칙적용'] if x['규칙ID'] == 'FIA_RECLASS_REPEAT')
        self.assertEqual(rule['상태'], '미확인')
        self.assertNotIn('FIA_RECLASS_REPEAT', [i['code'] for i in r['issues']])

    def test_approval_time_on_pending_is_flagged(self):
        r = self.run_mutation(lambda d: self.set_journal(d, 승인상태='대기'))
        self.assertIn('FIA_TIMESTAMP_ORDER', [i['code'] for i in r['issues']])

    def test_configuration_duplicate_missing_and_unknown_block(self):
        changes = [lambda d: d['FIA설정'].append(deepcopy(d['FIA설정'][0])),
                   lambda d: d['FIA설정'].pop(),
                   lambda d: d['FIA설정'].append({'항목': '미지원', '값': '무시 금지'})]
        for change in changes:
            with self.subTest(change=change):
                self.assert_blocked_without_risk(self.run_mutation(change))

    def test_configuration_version_offset_workhours_and_bool_controls(self):
        for key, value in [('규칙버전', 'FIA-999'), ('업무시간대', 'Asia/Seoul'), ('업무시간대', '+14:30'), ('업무종료', '08:00'), ('수동집중비율', True), ('수동집중비율', 101), ('반복재분류최소횟수', 1), ('선승인허용', None)]:
            with self.subTest(key=key, value=value):
                self.assert_blocked_without_risk(self.run_mutation(lambda d: self.set_setting(d, key, value)))

    def test_invalid_or_missing_metadata_timestamp_blocks(self):
        for value in (None, '2027-01-05', '2027-02-30T10:00:00+09:00', True):
            with self.subTest(value=value):
                self.assert_blocked_without_risk(self.run_mutation(lambda d: self.set_journal(d, 입력시각=value)))

    def test_cancel_does_not_return_success(self):
        event = Event()
        event.set()
        with self.assertRaisesRegex(AuditError, '취소'):
            fia.analyze(self.samples['normal'], CONTEXT, self.ledger, event)

    def test_explicit_unknown_optional_labels_not_treated_as_real_groups(self):
        r = self.run_mutation(lambda d: self.set_journal(d, 부서='미확인', 원천시스템='미확인', 재분류그룹='미확인'))
        rules = {r['규칙ID']: r for r in r['tables']['규칙적용']}
        self.assertEqual(rules['FIA_METADATA_SCOPE']['상태'], '미확인')
        self.assertEqual(rules['FIA_RECLASS_REPEAT']['상태'], '미확인')
        self.assertFalse(r['tables']['검토후보'])

    def test_required_user_or_approved_identity_cannot_be_unknown_placeholder(self):
        for key in ('입력자', '승인자'):
            with self.subTest(key=key):
                self.assert_blocked_without_risk(self.run_mutation(lambda d: self.set_journal(d, **{key: '미확인'})))

    def test_cases_json_expected_values_not_passed_into_input(self):
        manifest = json.loads((self.folder / 'samples' / 'cases.json').read_text('utf-8'))
        self.assertEqual(manifest['schema_version'], 'fia-cases-1')
        self.assertEqual(len(manifest['cases']), 22)
        self.assertNotIn('expected', fia.SCHEMA)


if __name__ == '__main__':
    unittest.main(verbosity=2)
