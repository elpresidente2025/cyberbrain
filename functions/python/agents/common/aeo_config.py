"""AEO Answer-First 서론 구조 및 변증법 매크로 구조 설정.

정보성 글(정책·시사·지역·활동)에는 서론 첫 문단에 핵심 결론을 배치하여
AI 답변 엔진(AEO)이 서론만 추출해도 독자 질문에 답이 되도록 한다.
감성·서사형(일상소통), 톤 조율형(초당적), 행사형(오프라인)은 적용하지 않는다.

논증·설득이 본질인 글(정책·시사·진단·지역현안)에는 변증법 매크로 구조를 적용:
결론→근거→예상 반론+재반론→상위 원칙→결론 반복
활동보고(direct_writing)는 보고 구조이므로 변증법 비대상.
"""

from __future__ import annotations

from typing import List, Dict

AEO_ANSWER_FIRST_METHODS = frozenset({
    'logical_writing',     # policy_proposal
    'critical_writing',    # current_affairs
    'diagnostic_writing',  # current_affairs (진단형)
    'analytical_writing',  # local_issues
    'direct_writing',      # activity_report
})

# 변증법 매크로 구조 적용 대상 — AEO 대상 중 논증·설득형만
AEO_DIALECTICAL_METHODS = frozenset({
    'logical_writing',     # policy_proposal
    'critical_writing',    # current_affairs
    'diagnostic_writing',  # current_affairs (진단형)
    'analytical_writing',  # local_issues
})


def uses_aeo_answer_first(writing_method: str) -> bool:
    """writing_method가 AEO answer-first 서론 구조 대상인지 판별."""
    return writing_method in AEO_ANSWER_FIRST_METHODS


def uses_dialectical_structure(writing_method: str) -> bool:
    """writing_method가 변증법 매크로 구조 대상인지 판별."""
    return writing_method in AEO_DIALECTICAL_METHODS


def build_dialectical_roles(body_sections: int) -> List[Dict[str, str]]:
    """body_sections 수에 따른 위치별 논증 역할 매핑.

    매핑 규칙:
    - body[1] ~ body[N-2]: evidence (근거)
    - body[N-1]: counterargument_rebuttal (예상 반론 + 재반론)
    - body[N]: higher_principle (상위 원칙)

    Returns:
        [{"order": 1, "role": "evidence", "guide": "..."}, ...]
    """
    if body_sections < 3:
        # 본론 2개 이하면 변증법 구조 불가 — 전부 evidence로 처리
        return [
            {"order": i, "role": "evidence",
             "guide": "서론에서 선언한 결론을 뒷받침하는 근거·수치·사례를 제시하십시오."}
            for i in range(1, body_sections + 1)
        ]

    roles: List[Dict[str, str]] = []

    # evidence 섹션들 (첫째 ~ 끝에서 셋째)
    for i in range(1, body_sections - 1):
        roles.append({
            "order": i,
            "role": "evidence",
            "guide": "서론에서 선언한 결론을 뒷받침하는 근거·수치·사례를 제시하십시오.",
        })

    # counterargument + rebuttal (끝에서 둘째)
    roles.append({
        "order": body_sections - 1,
        "role": "counterargument_rebuttal",
        "guide": (
            "예상되는 반대 논리·우려·비판을 먼저 인정한 뒤, "
            "사실·수치·논리로 재반론하여 극복하십시오."
        ),
    })

    # higher principle (마지막)
    roles.append({
        "order": body_sections,
        "role": "higher_principle",
        "guide": (
            "이 논의가 속한 더 큰 가치·원칙·비전으로 격상하십시오. "
            "개별 정책이 아니라 그 정책이 실현하는 상위 목표를 선언하십시오."
        ),
    })

    return roles
