"""Deterministic numeric/response rejection checks, not actual model inference."""
import copy
from decimal import Decimal
import unittest
from unittest.mock import patch
from ai_quality import numeric_support_report
import ai_provider as ai
from test_ai_provider import packet, draft, ollama_response


class NumericSupportTests(unittest.TestCase):
    def response(self, value, second=None):
        p=packet();p['references'][0]['data']={'금액':value}
        if second is not None:p['references'].append({'id':'REF002','kind':'raw_json',
            'company_code':'JS_ELEC','data':{'금액':second}})
        v=draft(p);return p,v

    def test_matching_comma_amount_and_period(self):
        p,v=self.response(90000);v['fields']['scope']+=' 2026년 자료의 90,000원 차이를 기계적으로 비교한다.'
        self.assertTrue(ai.validate_draft_response(p,v['fields'],v['citations']))

    def test_fabricated_number_is_rejected(self):
        p,v=self.response(90000);v['fields']['conclusion']+=' 미확인 차이는 999,999원이다.'
        with self.assertRaisesRegex(ai.AIProviderError,'수치'):
            ai.validate_draft_response(p,v['fields'],v['citations'])

    def test_context_year_cannot_back_currency_amount(self):
        p,v=self.response(90000);v['fields']['scope']+=' 잔액 2026원.'
        with self.assertRaisesRegex(ai.AIProviderError,'수치'):
            ai.validate_draft_response(p,v['fields'],v['citations'])

    def test_cited_date_cannot_back_a_currency_amount(self):
        p,v=self.response('2026-12-31');v['fields']['scope']+=' 잔액 2026원.'
        with self.assertRaisesRegex(ai.AIProviderError,'수치'):
            ai.validate_draft_response(p,v['fields'],v['citations'])

    def test_iso_and_korean_period_dates_are_equivalent(self):
        p,v=self.response(90000);v['fields']['scope']+=' 2026년1월1일부터 2026년12월31일까지의 자료.'
        self.assertTrue(ai.validate_draft_response(p,v['fields'],v['citations']))

    def test_existing_uncited_number_is_not_support(self):
        p,v=self.response(90000,99000);v['fields']['scope']+=' 99,000원 발췌자료.'
        with self.assertRaisesRegex(ai.AIProviderError,'수치'):
            ai.validate_draft_response(p,v['fields'],v['citations'])
        v['citations']['scope'].append('REF002')
        self.assertTrue(ai.validate_draft_response(p,v['fields'],v['citations']))

    def test_scaled_units_are_normalized_without_new_calculation(self):
        for value,phrase in [(90000,'9만원'),(Decimal('0.15'),'15%'),(150000000,'1.5억원')]:
            p,v=self.response(str(value));v['fields']['scope']+=' '+phrase+' 항목 발췌.'
            with self.subTest(phrase=phrase):
                self.assertTrue(ai.validate_draft_response(p,v['fields'],v['citations']))

    def test_negative_sign_is_preserved(self):
        p,v=self.response(-90000);v['fields']['scope']+=' -90,000원 발췌.'
        self.assertTrue(ai.validate_draft_response(p,v['fields'],v['citations']))
        v['fields']['scope']=v['fields']['scope'].replace('-90,000','90,000')
        with self.assertRaisesRegex(ai.AIProviderError,'수치'):
            ai.validate_draft_response(p,v['fields'],v['citations'])

    def test_fullwidth_fabricated_amount_does_not_bypass(self):
        p,v=self.response(90000);v['fields']['scope']+=' ９９９，９９９원 발췌.'
        with self.assertRaisesRegex(ai.AIProviderError,'수치'):
            ai.validate_draft_response(p,v['fields'],v['citations'])

    def test_presence_report_does_not_claim_semantic_verification(self):
        p,v=self.response(90000);before=copy.deepcopy(v)
        report=numeric_support_report(p,v['fields'],v['citations'])
        self.assertTrue(report['passed']);self.assertIn('semantic',report['scope'])
        self.assertEqual(v,before)

    def test_local_model_identity_must_match_request(self):
        response=ollama_response();response['model']='another-local-model'
        with patch.object(ai,'_post_json',return_value=response):
            with self.assertRaisesRegex(ai.AIProviderError,'응답 모델'):
                ai.generate_draft(packet(),{})

    def test_unconfirmed_question_noun_is_not_a_completed_performance_claim(self):
        p,v=self.response(90000)
        v['fields']['conclusion']+=' 추가 검토 대상은 실제 수령 및 실사 수행 여부임.'
        self.assertTrue(ai.validate_draft_response(p,v['fields'],v['citations']))

    def test_question_phrase_does_not_excuse_stated_completed_performance(self):
        p,v=self.response(90000)
        v['fields']['conclusion']+=' 실사 수행 여부를 확인했다.'
        with self.assertRaisesRegex(ai.AIProviderError,'단정'):
            ai.validate_draft_response(p,v['fields'],v['citations'])


if __name__=='__main__':unittest.main()
