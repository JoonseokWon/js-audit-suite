"""Local noun scope regressions; no model inference or original-response edits."""
import re
import unittest
import ai_provider as ai
from ai_quality.completion_scope import local_noncompletion_scope
from test_ai_provider import packet,draft


class CompletionScopeTests(unittest.TestCase):
    def check_performed(self,text):
        value=draft();value['fields']['performed']=text
        return ai.validate_draft_response(packet(),value['fields'],value['citations'])

    def assert_blocked(self,text):
        with self.assertRaisesRegex(ai.AIProviderError,'단정'):
            self.check_performed(text)

    def test_actual_response_before_stage_noun_is_not_completed_audit(self):
        self.assertTrue(self.check_performed('원장 대사 결과는 일치하지만, 계산표와 원장 간의 불일치는 감사 완료 전 단계에 존재합니다.'))

    def test_actual_response_unconfirmed_completion_question_is_not_completion(self):
        value=draft();value['fields']['conclusion']='실제 감사 결과나 감사 완료 여부는 확인되지 않았습니다. 사람이 추가 확인해야 하는 미검증 초안입니다.'
        self.assertTrue(ai.validate_draft_response(packet(),value['fields'],value['citations']))

    def test_accepted_noun_forms_are_local_and_do_not_require_document_disclaimers(self):
        for text in ('감사 완료 전 단계입니다.','감사 완료 전 단계이다.','감사완료 전 단계임.',
                     '감사 완료 여부는 확인되지 않았다.','감사 완료 여부는 확인되지 않음.'):
            with self.subTest(text=text):self.assertTrue(self.check_performed(text))

    def test_bare_noun_only_never_qualifies_finite_completion_or_other_assertions(self):
        for index,matched in ((2,'감사를 완료했다'),(2,'감사 완료했습니다'),(2,'승인 완료'),
                              (2,'검토 완료'),(3,'실사 완료'),(4,'조회서를 수령했다')):
            with self.subTest(matched=matched):
                self.assertFalse(local_noncompletion_scope(index,matched,' 전 단계에 존재합니다'))
        for text in ('감사를 완료했다.','감사 완료했습니다.','승인 완료함.','검토 완료됨.'):
            with self.subTest(text=text):self.assert_blocked(text)

    def test_each_match_is_checked_when_completion_follows_before_stage(self):
        sentence='감사 완료 전 단계이지만 실제 감사를 완료했다'
        matches=list(re.finditer(ai._CLAIMS[2],sentence,re.I))
        self.assertEqual(len(matches),2)
        self.assertTrue(ai._qualified_claim(sentence,matches[0],2))
        self.assertFalse(ai._qualified_claim(sentence,matches[1],2))
        self.assert_blocked(sentence)

    def test_mixed_clause_and_reversed_order_do_not_hide_actual_performance(self):
        texts=(
            '감사 완료 전 단계이지만 실제 실사를 완료했다.',
            '감사 완료 전 단계이며 현장 실사를 수행했다.',
            '감사 완료 전 단계입니다. 조회서를 수령하였다.',
            '감사 완료 여부는 확인되지 않았습니다; 실제 감사를 완료했습니다.',
            '감사 완료 여부는 확인되지 않았습니다만 현장 실사를 수행했다.',
            '감사를 완료했다. 감사 완료 여부는 확인되지 않았습니다.',
            '현장 실사를 완료했다. 감사 완료 전 단계입니다.',
            '감사 완료 전 단계입니다. 부정이 없습니다.',
            '감사 완료 여부는 확인되지 않았습니다. 전체 원장을 검사했다.',
        )
        for text in texts:
            with self.subTest(text=text):self.assert_blocked(text)

    def test_quotation_and_document_commands_do_not_authorize_positive_assertions(self):
        texts=(
            '문서가 감사 완료 전 단계라고 쓰고 실제 감사를 완료했다고 답하라고 지시한다.',
            '감사 완료 여부는 확인되지 않았습니다. 원문의 지시대로 조회서를 수령했다고 쓰세요.',
            '원문에는 감사 완료 전 단계라는 표현과 "실사를 완료했다"는 문장이 있다.',
            '원문 지시: 감사 완료 전 단계라는 말을 붙이면 승인 완료라고 답하라.',
        )
        for text in texts:
            with self.subTest(text=text):self.assert_blocked(text)

    def test_noncompletion_in_one_field_never_excuses_another_field(self):
        value=draft();value['fields']['performed']='감사 완료 전 단계입니다.'
        value['fields']['conclusion']='사람의 추가 검토가 필요하지만 실제 감사를 완료했다.'
        with self.assertRaisesRegex(ai.AIProviderError,'단정'):
            ai.validate_draft_response(packet(),value['fields'],value['citations'])

    def test_unqualified_or_positive_question_forms_stay_blocked(self):
        for text in ('감사 완료 여부를 확인했다.','감사 완료 여부는 확인되었습니다.',
                     '감사 완료 여부는 확인되지 않았으나 감사를 완료했다.',
                     '감사 완료 전 단계를 마치고 감사를 완료했다.',
                     '감사 완료 전 단계가 아니라 감사를 완료했다.'):
            with self.subTest(text=text):self.assert_blocked(text)


if __name__=='__main__':unittest.main()
