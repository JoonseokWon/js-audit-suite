"""Independent coverage oracles for final, bounded AI excerpts; no inference."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import unittest
from common import AuditError,digest,dumps
from ai_evidence_inventory import canonical_hash,finalize_packet,inventory,table_rows
from ai_evidence_inventory.encoding import compact_manifest


def fixture():
    tables={'선택표':[{'값':i,'내용':'원본 전체 '+str(i)} for i in range(1,5)],
            '미선택표':[{'값':10},{'값':20}], '입력_원본':[{'값':30}], '빈표':[]}
    run={'id':'R1','module':'테스트','result':{'tables':tables}}
    run['result_hash']=digest(run['result'])
    packet={'limits':{'max_chars':24000,'max_tables':1,'rows_per_table':2},
            'references':[],'truncation':[]}
    return run,packet


def row_ref(run,table,row,rid):
    return {'id':rid,'kind':'calculation_row','run_id':run['id'],
        'result_hash':run['result_hash'],'table_row':row,
        'row_hash':digest(run['result']['tables'][table][row-1]),
        'data':{'table':table,'row':{'내용':'표시 발췌만'}}}


class InventoryTests(unittest.TestCase):
    def test_incremental_hash_matches_existing_canonical_hash(self):
        value={'한글':[Decimal('1.230'),date(2026,10,26),None,True,{'값':'줄\n바꿈'}]}
        self.assertEqual(canonical_hash(value),digest(value))
        for value in ({2:'둘',10:'열'},{1:'먼저','1':'나중'},[{2:Decimal('1.0'),10:date(2026,1,1)}]):
            self.assertEqual(canonical_hash(value),digest(value))

    def test_all_tables_including_fully_omitted_and_empty_are_counted(self):
        run,p=fixture();p['references']=[row_ref(run,'선택표',1,'REF1')]
        p['truncation']=[{'kind':'calculation_row','included':999}]
        final=finalize_packet(p,[run],selected_tables={'R1':['선택표']})
        m=final['calculation_inventory'];by={t['table']:t for t in m['tables']}
        self.assertEqual((m['table_count'],m['available'],m['included'],m['omitted']),(4,7,1,6))
        self.assertEqual(by['선택표']['reasons'],{'row_limit':2,'reference_or_character_budget':1})
        self.assertEqual(by['미선택표']['reasons'],{'table_limit':2})
        self.assertEqual(by['입력_원본']['reasons'],{'input_source_only':1})
        self.assertEqual(by['빈표']['hash'],digest([]))
        self.assertFalse(any(x.get('included')==999 for x in final['truncation']))
        for name,rows in run['result']['tables'].items():self.assertEqual(by[name]['hash'],digest(rows))

    def test_protected_rows_count_once_even_outside_plan_or_beyond_row_limit(self):
        run,p=fixture();p['references']=[row_ref(run,'미선택표',1,'P1'),
            row_ref(run,'선택표',1,'P2'),row_ref(run,'선택표',1,'R3'),
            row_ref(run,'선택표',4,'P4')]
        m=inventory(p,[run],{'R1':['선택표']});by={t['table']:t for t in m['tables']}
        self.assertEqual(m['included'],3);self.assertEqual(m['duplicate_row_references'],1)
        self.assertEqual(by['선택표']['reasons'],{'row_limit':1,'reference_or_character_budget':1})
        self.assertEqual(by['미선택표']['reasons'],{'table_limit':1})

    def test_final_budget_recounts_after_removing_a_reference(self):
        run,p=fixture();p['references']=[row_ref(run,'선택표',1,'REF1'),row_ref(run,'선택표',2,'REF2')]
        p['references'][1]['data']['row']['내용']='긴 표시 '+('x'*2000)
        base=deepcopy(p);base['references']=base['references'][:1]
        smaller=finalize_packet(base,[run],selected_tables={'R1':['선택표']})
        p['limits']['max_chars']=len(dumps(smaller))+450
        final=finalize_packet(p,[run],protected_ids={'REF1'},selected_tables={'R1':['선택표']})
        self.assertLessEqual(len(dumps(final)),p['limits']['max_chars'])
        self.assertEqual([r['id'] for r in final['references']],['REF1'])
        self.assertEqual(final['calculation_inventory']['included'],1)
        self.assertEqual(final['calculation_inventory']['omitted'],6)
        self.assertEqual(final['truncation'][-1]['omitted_references'],1)

    def test_wrong_run_full_row_hash_or_missing_identity_cannot_be_guessed(self):
        run,p=fixture();good=row_ref(run,'선택표',1,'REF1')
        for key,value in [('run_id','OTHER'),('result_hash','bad'),('table_row',None),
                          ('table_row',True),('row_hash',digest({'내용':'표시 발췌만'}))]:
            with self.subTest(key=key,value=value):
                bad={**good,key:value};p['references']=[bad]
                with self.assertRaises(AuditError):inventory(p,[run])

    def test_required_inventory_is_never_silently_dropped_for_budget(self):
        run,p=fixture();p['references']=[row_ref(run,'선택표',1,'REF1')]
        p['limits']['max_chars']=100
        with self.assertRaises(AuditError):finalize_packet(p,[run],{'REF1'})

    def test_compact_form_preserves_every_count_hash_and_reason(self):
        run,p=fixture();p['references']=[row_ref(run,'선택표',1,'REF1')]
        expanded=inventory(p,[run]);encoded=compact_manifest(expanded)
        self.assertEqual(table_rows(encoded),expanded['tables'])
        self.assertEqual(encoded['available'],expanded['available'])
        self.assertLess(len(dumps(encoded)),len(dumps(expanded)))

    def test_duplicate_or_missing_run_ids_cannot_double_count_the_manifest(self):
        run,p=fixture();p['references']=[row_ref(run,'선택표',1,'REF1')]
        with self.assertRaisesRegex(AuditError,'실행ID'):inventory(p,[run,deepcopy(run)])
        with self.assertRaisesRegex(AuditError,'실행ID'):inventory(p,[{**run,'id':None}])

    def test_linked_human_records_use_lossless_compact_inventory_at_24k(self):
        run,p=fixture();p['references']=[row_ref(run,'선택표',1,'REF1')]
        p['linked_human_records']={'audit_links':{'included_reference_ids':[]}}
        expected=inventory(p,[run])
        final=finalize_packet(p,[run])
        self.assertEqual(final['calculation_inventory']['schema'],'calculation-inventory-2')
        self.assertEqual(table_rows(final['calculation_inventory']),expected['tables'])
        self.assertEqual(final['linked_human_records'],p['linked_human_records'])

    def test_raw_attempt_counts_are_not_mislabeled_as_final_inclusion(self):
        run,p=fixture();p['references']=[row_ref(run,'선택표',1,'P1')]
        for index in (2,3):
            p['references'].append({'id':f'RAW{index}','kind':'raw_xlsx_row','source_id':'S1',
                'data':{'sheet':'원본','row':index,'values':{'본문':'x'*2000}}})
        p['truncation']=[{'kind':'raw_xlsx_row','available':2,'included':2,'omitted':0}]
        initial=deepcopy(p);initial['references']=initial['references'][:2]
        smaller=finalize_packet(initial,[run],protected_ids={'P1'})
        p['limits']['max_chars']=len(dumps(smaller))+450
        final=finalize_packet(p,[run],protected_ids={'P1'})
        self.assertEqual(sum(r['kind']=='raw_xlsx_row' for r in final['references']),1)
        attempt=final['truncation'][0]
        self.assertNotIn('included',attempt);self.assertNotIn('omitted',attempt)
        self.assertEqual(attempt['initial_included'],2)
        self.assertIn('초기 발췌 시도',attempt['scope'])


if __name__=='__main__':unittest.main()
