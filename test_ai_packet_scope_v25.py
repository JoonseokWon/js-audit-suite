"""Bounded metadata, protected excerpts and truthful omitted human-record scope."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from common import digest,dumps
from ai_contract import attach_contract
from ai_contract.packet_scope import profile_excerpt,compact_attempts
from ai_contract.linked_records import add_references,HUMAN_KINDS
import test_ai_links_v25 as linked_fixture


class PacketScopeTests(unittest.TestCase):
    def test_profile_keeps_materiality_current_scope_and_full_omitted_hash(self):
        profile={'materiality':{'overall_materiality':100},'actor':'SYNTHETIC ONLY',
            'scope':[{'procedure_id':f'A{i:02}','applicable':True} for i in range(20)]}
        result=profile_excerpt(profile,'A04')
        self.assertEqual(result['materiality'],profile['materiality'])
        self.assertEqual(result['scope'],[profile['scope'][4]])
        self.assertEqual(result['scope_excerpt']['omitted'],19)
        self.assertEqual(result['scope_excerpt']['full_record_hash'],digest(profile))

    def test_overlapping_attempt_counts_are_not_reported_as_final_omissions(self):
        records=[{'kind':'raw_xlsx_row','available':7,'included':2,'omitted':5},
                 {'kind':'raw_xlsx_row','omitted':3,'reason':'overlapping budget attempt'}]
        result=compact_attempts(records)[0]
        self.assertEqual(result['initial_omitted_sum'],5)
        self.assertEqual(result['additional_omitted_sum'],3)
        self.assertNotIn('omitted',result);self.assertNotIn('included',result)
        self.assertEqual(result['full_attempt_manifest_hash'],digest(records))

    def test_each_kind_anchor_precedes_optional_records_and_full_MS_scope_is_not_claimed(self):
        helper=linked_fixture.LinkedHumanRecordsTests();ws,p,ref=helper.setup_packet(limit=6)
        risk=[{'kind':kind,'procedure_id':'A04','data':{'id':kind}} for kind in HUMAN_KINDS[:-1]]
        risk.insert(1,{'kind':HUMAN_KINDS[0],'procedure_id':'A04','data':{'id':'optional-same-kind'}})
        ms=[{'kind':'misstatement_record','data':{'id':str(i),'procedure_ids':['A04']}} for i in range(40)]
        with patch('audit_links.packet',return_value={'references':risk}),patch('misstatements.packet',return_value={'references':ms,
            'inventory':{'available':80,'included':40,'omitted':40,'manifest_hash':'a'*64}}):
            add_references(ws,'A04',p,ref)
        self.assertTrue(set(HUMAN_KINDS)<={r['kind'] for r in p['references']})
        scope=p['linked_human_records']['misstatements']
        self.assertEqual((scope['available_references'],scope['included_references'],scope['omitted_references']),(40,1,39))
        self.assertEqual(scope['source_inventory']['available'],80)
        self.assertEqual(scope['source_inventory']['omitted'],40)
        self.assertEqual(scope['full_reference_manifest_hash'],digest(ms))

    def test_omitted_complete_performance_input_is_not_misreported_as_absent(self):
        helper=linked_fixture.LinkedHumanRecordsTests()
        records=[{'kind':'human_actual_performance','procedure_id':'A04','data':{'id':'partial','performed':'','performed_date':''}},
                 {'kind':'human_actual_performance','procedure_id':'A04','data':{'id':'complete','performed':'SYNTHETIC ONLY','performed_date':'2026-12-31'}}]
        # First original ref plus one anchor leaves no slot for the second input.
        ws,p,ref=helper.setup_packet(limit=2)
        with patch('audit_links.packet',return_value={'references':records}),patch('misstatements.packet',return_value={'references':[]}):
            add_references(ws,'A04',p,ref)
        attach_contract(p)
        self.assertEqual(p['contract']['human_performance']['state'],'user_recorded_unverified')
        self.assertFalse(p['contract']['human_performance']['physical_performance_verified'])
        self.assertEqual(p['linked_human_records']['audit_links']['human_performance_inventory']['recorded_inputs'],1)
        self.assertEqual(p['linked_human_records']['audit_links']['omitted_references'],1)

    def test_full_integrated_case_retains_raw_calc_and_all_human_anchors_within_24k(self):
        from v25_demo import actual_case
        import ai_contract.source_read as reader
        import ai_contract.raw_anchor as anchor
        with tempfile.TemporaryDirectory() as tmp:
            ws,_=actual_case(Path(tmp),lambda ok,name:self.assertTrue(ok,name))
            current_sales=ws.latest()['매출']['source_id'];original=reader.read_source_tables
            with patch.object(anchor,'read_source_tables',wraps=original) as reserved,patch.object(reader,'read_source_tables',wraps=original) as ordinary:
                packet=ws.ai_packet('A04',limits={'max_chars':24000,'max_references':70,'rows_per_table':3,'max_tables':8,'cell_chars':300})
            self.assertEqual(reserved.call_count,1)
            self.assertEqual(reserved.call_args.args[1],current_sales)
            self.assertTrue(all(call.args[1]!=current_sales for call in ordinary.call_args_list))
            kinds=[r['kind'] for r in packet['references']]
            for kind in ('raw_xlsx_row','calculation_row','human_assertion_risk_assessment',
                         'human_risk_response','human_actual_performance','misstatement_record'):
                self.assertIn(kind,kinds)
            self.assertEqual(kinds.count('exception'),4);self.assertEqual(kinds.count('misstatement_record'),2)
            self.assertEqual(packet['contract']['human_performance']['state'],'user_recorded_unverified')
            self.assertLessEqual(len(dumps(packet)),24000)
            self.assertFalse(ws.ai_drafts);self.assertFalse(ws.ai_approvals)


if __name__=='__main__':unittest.main()
