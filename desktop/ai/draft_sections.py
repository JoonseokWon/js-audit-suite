"""Verified application content and unverified model proposals are separate views."""
from export_support.text import display_text


def sections(draft,labels):
    structured=draft.get('contract_version')=='ai-structured-2'
    def render(fields,citations):
        return display_text('\n\n'.join(label+'\n'+str(fields.get(key,''))+'\n근거: '+
               ', '.join(citations.get(key,[])) for key,label in labels.items()))
    if structured:
        return [
            ('프로그램 근거 기록 · 적용 대상','프로그램이 식별·근거 종류·구조화된 주장에 따라 렌더링한 기계적 사실이에요. '
             '자료의 진위·증거 충분성·사람의 판단을 인증하지 않아요.\n\n'+
             render(draft.get('verified_fields',{}),draft.get('verified_citations',{}))),
            ('미검증 AI 제안 · 자동 적용 안 함','아래 문장은 실제 모델의 제안이며 사실성이 검증되지 않았어요. '
             '현재 조서에 적용 버튼으로 이 제안을 자동으로 넣지 않아요. 근거·회계적 의미를 직접 확인하고 필요한 내용을 직접 수정·작성하세요.\n\n'+
             render(draft.get('unverified_proposals',draft.get('fields',{})),draft.get('proposal_citations',draft.get('citations',{}))))]
    return [('이전 형식 원문 · 조회 전용','이전 형식의 초안·원문을 보존해 보여줘요. 새 조서에 재적용하거나 새 내용 승인을 할 수 없어요. '
             '현재 근거로 구조화된 새 초안을 생성하세요.\n\n'+render(draft.get('fields',{}),draft.get('citations',{})))]
