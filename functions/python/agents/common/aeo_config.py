"""AEO Answer-First 서론 구조 적용 대상 설정.

정보성 글(정책·시사·지역·활동)에는 서론 첫 문단에 핵심 결론을 배치하여
AI 답변 엔진(AEO)이 서론만 추출해도 독자 질문에 답이 되도록 한다.
감성·서사형(일상소통), 톤 조율형(초당적), 행사형(오프라인)은 적용하지 않는다.
"""

AEO_ANSWER_FIRST_METHODS = frozenset({
    'logical_writing',     # policy_proposal
    'critical_writing',    # current_affairs
    'diagnostic_writing',  # current_affairs (진단형)
    'analytical_writing',  # local_issues
    'direct_writing',      # activity_report
})


def uses_aeo_answer_first(writing_method: str) -> bool:
    """writing_method가 AEO answer-first 서론 구조 대상인지 판별."""
    return writing_method in AEO_ANSWER_FIRST_METHODS
