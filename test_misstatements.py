"""Human classification, gross totals, duplicate groups and immutable pins."""
from copy import deepcopy
from common import AuditError, digest
from workspace import Workspace
import misstatements as ms
from test_misstatements_support import Case, ACTOR, profile


class MisstatementTests(Case):
    def test_legacy_empty_and_candidate_views_do_not_mutate_basis_or_history(self):
        before=(self.ws.head,self.ws.basis(),deepcopy(self.ws.events))
        self.assertFalse(ms.status(self.ws)['active']);self.assertEqual(ms.basis(self.ws),None)
        ms.candidates(self.ws);ms.snapshot_rows(self.ws);ms.packet(self.ws,'F03')
        self.assertEqual((self.ws.head,self.ws.basis(),self.ws.events),before)

    def test_new_review_draft_does_not_fill_human_judgment_or_approval(self):
        record=ms.save_record(self.ws,{'description':'차이 조사 대기'},ACTOR)
        for key in ('assessment','classification','correction_state','company_position','period','qualitative','judgment'):
            self.assertEqual(record[key],'')
        self.assertIsNone(record['amount']);self.assertIsNone(record['tax_effect'])
        self.assertFalse(self.ws.procedures);self.assertFalse(self.ws.ai_approvals)
        self.assertTrue(ms.record_status(self.ws,record['id'])['current'])
        self.assertFalse(ms.record_status(self.ws,record['id'])['complete'])

    def test_positive_and_negative_unadjusted_errors_never_net_and_trivial_kept(self):
        self.ws.save_workflow_profile(profile(),ACTOR)
        a=ms.save_record(self.ws,self.record_value(qualitative='있음',qualitative_note='가상 경영진 보상 영향'),ACTOR)
        b=ms.save_record(self.ws,self.record_value(amount=-100),ACTOR)
        snapshot=ms.snapshot_rows(self.ws);summary=snapshot['summary'][0]
        self.assertEqual((summary['gross_amount'],summary['positive_amount'],summary['negative_amount_abs']),(200,100,100))
        self.assertNotIn('net_amount',summary)
        self.assertEqual(len(snapshot['account_impacts']),4)
        self.assertTrue(all(r['below_trivial'] for r in snapshot['records']))
        self.assertTrue(all(r['counted'] for r in snapshot['records']))

    def test_group_only_after_explicit_human_choice_and_keeps_every_account_impact(self):
        a=ms.save_record(self.ws,self.record_value(),ACTOR)
        b=ms.save_record(self.ws,self.record_value(),ACTOR)
        self.assertEqual(ms.snapshot_rows(self.ws)['summary'][0]['gross_amount'],200)
        group=ms.save_group(self.ws,{'member_ids':[a['id'],b['id']],'primary_id':a['id'],
            'reason':'SYNTHETIC ONLY 동일 송장을 서로 다른 절차에서 조사'},ACTOR)
        snapshot=ms.snapshot_rows(self.ws)
        self.assertEqual(snapshot['summary'][0]['gross_amount'],100)
        self.assertEqual(snapshot['summary'][0]['count'],1)
        self.assertEqual(len(snapshot['account_impacts']),4)
        self.assertEqual(sum(r['counted'] for r in snapshot['records']),1)
        self.assertEqual(group['primary_id'],a['id'])

    def test_different_amounts_require_primary_amount_reason_and_changed_group_is_pending(self):
        a=ms.save_record(self.ws,self.record_value(),ACTOR)
        b=ms.save_record(self.ws,self.record_value(amount=-100),ACTOR)
        value={'member_ids':[a['id'],b['id']],'primary_id':a['id'],'reason':'가상 중복 주장'}
        head=self.ws.head
        with self.assertRaisesRegex(AuditError,'자동 상계'):ms.save_group(self.ws,value,ACTOR)
        self.assertEqual(head,self.ws.head)
        group=ms.save_group(self.ws,{**value,'amount_resolution':'SYNTHETIC ONLY 반대 방향 원천을 포함한 동일오류 판단'},ACTOR)
        ms.save_record(self.ws,{**self.record_value(amount=101),'id':a['id']},ACTOR)
        self.assertTrue(ms.snapshot_rows(self.ws)['group_problems'])
        self.assertEqual(ms.snapshot_rows(self.ws)['summary'][0]['gross_amount'],201)

    def test_human_can_dissolve_wrong_group_without_erasing_original_judgment(self):
        a=ms.save_record(self.ws,self.record_value(),ACTOR)
        b=ms.save_record(self.ws,self.record_value(),ACTOR)
        value={'member_ids':[a['id'],b['id']],'primary_id':a['id'],'reason':'SYNTHETIC ONLY 최초 중복 판단'}
        group=ms.save_group(self.ws,value,ACTOR);old_events=deepcopy(self.ws.events)
        ms.save_group(self.ws,{**value,'id':group['id'],'active':False,
                              'reason':'SYNTHETIC ONLY 다른 송장임을 재확인하여 해제'},ACTOR)
        self.assertEqual(ms.snapshot_rows(self.ws)['summary'][0]['gross_amount'],200)
        self.assertEqual(self.ws.events[:len(old_events)],old_events)
        self.assertFalse(ms.snapshot_rows(self.ws)['groups'][0]['active'])

    def test_period_classification_tax_and_company_disagreement_preserved_separately(self):
        a=ms.save_record(self.ws,self.record_value(period='기초',classification='판단',tax_effect=-20),ACTOR)
        b=ms.save_record(self.ws,self.record_value(classification='추정투영',projection_basis='가상 모집단 10건·독립 투영'),ACTOR)
        snapshot=ms.snapshot_rows(self.ws)
        self.assertEqual(len(snapshot['summary']),2)
        self.assertEqual(sum(row.get('tax_negative_abs',0) for row in snapshot['summary']),20)
        self.assertEqual(ms.get_record(self.ws,a['id'])['company_note'],'SYNTHETIC ONLY 회사의 이견 보존')
        self.assertFalse(ms.record_status(self.ws,b['id'])['missing'])

    def test_non_misstatement_not_counted_but_reason_and_evidence_remain(self):
        record=ms.save_record(self.ws,self.record_value(assessment='왜곡표시아님',amount=None),ACTOR)
        self.assertEqual(ms.snapshot_rows(self.ws)['summary'],[])
        self.assertTrue(ms.get_record(self.ws,record['id'])['judgment'])

    def test_profile_or_source_change_requires_explicit_reconfirmation_and_reopen_preserves_history(self):
        record=ms.save_record(self.ws,self.record_value(),ACTOR);events=deepcopy(self.ws.events)
        self.ws.save_workflow_profile(profile(),ACTOR)
        self.assertFalse(ms.record_status(self.ws,record['id'])['current'])
        self.assertEqual(self.ws.events[:len(events)],events)
        ms.reconfirm_record(self.ws,record['id'],ACTOR,'SYNTHETIC ONLY 변경 중요성 재확인')
        self.assertTrue(ms.record_status(self.ws,record['id'])['current'])
        path=self.base/'추가증빙.txt';path.write_text('가상 원본',encoding='utf-8');self.ws.add_source(path,'가상 추가자료')
        self.assertFalse(ms.record_status(self.ws,record['id'])['current'])
        reopened=Workspace(self.ws.root)
        self.assertEqual(ms.list_records(reopened),ms.list_records(self.ws))
        self.assertEqual(ms.basis(reopened),ms.basis(self.ws))

    def test_invalid_xml_unknown_evidence_or_stale_head_rejected_without_partial_events(self):
        head=self.ws.head
        for value,actor in (({'description':'검토\x0b'},ACTOR),({'description':'검토'},ACTOR+'\x0b'),
                             ({**self.record_value(),'evidence_ids':['unknown']},ACTOR)):
            with self.assertRaises(AuditError):ms.save_record(self.ws,value,actor)
            self.assertEqual(self.ws.refresh().head,head)
        ms.save_record(self.ws,{'description':'검토중'},ACTOR)
        after=self.ws.head
        with self.assertRaises(AuditError):ms.save_record(self.ws,{'description':'다른기록'},ACTOR,expected_head=head)
        self.assertEqual(self.ws.refresh().head,after)

    def test_packet_only_explicit_same_engagement_procedure_and_manifest_covers_all(self):
        a=ms.save_record(self.ws,self.record_value(),ACTOR)
        b=ms.save_record(self.ws,self.record_value(procedure_ids=['F03']),ACTOR)
        packet=ms.packet(self.ws,'A04')
        self.assertEqual([r['record_id'] for r in packet['references']],[a['id']])
        self.assertEqual(packet['references'][0]['kind'],'misstatement_record')
        self.assertEqual(packet['inventory']['available'],1)
        self.assertEqual(ms.packet(self.ws,'A12')['references'],[])
        self.assertEqual(ms.packet(self.ws,'F03')['inventory']['available'],2)

    def test_bounded_packet_reports_omission_and_full_snapshot_keeps_all_long_records(self):
        for index in range(41):
            ms.save_record(self.ws,self.record_value(description=str(index)+'가'*1800),ACTOR)
        head=self.ws.head;packet=ms.packet(self.ws,'F03');snapshot=ms.snapshot_rows(self.ws)
        self.assertEqual(packet['inventory']['available'],41)
        self.assertEqual(packet['inventory']['included'],40)
        self.assertEqual(packet['inventory']['omitted'],1)
        self.assertEqual(len(snapshot['records']),41)
        self.assertGreater(len(snapshot['records'][0]['description']),600)
        self.assertEqual(len(packet['references'][0]['data']['description']),600)
        self.assertTrue(packet['inventory']['manifest_hash'])
        self.assertTrue(packet['references'][0]['data']['run_refs'])
        self.assertEqual(self.ws.head,head)
