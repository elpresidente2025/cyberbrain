"""AEO Answer-First 서론 구조 및 변증법 매크로 구조 설정.

정보성 글(정책·시사·지역·활동)에는 서론 첫 문단에 핵심 결론을 배치하여
AI 답변 엔진(AEO)이 서론만 추출해도 독자 질문에 답이 되도록 한다.
감성·서사형(일상소통), 톤 조율형(초당적), 행사형(오프라인)은 적용하지 않는다.

논증·설득이 본질인 글(정책·시사·진단·지역현안)에는 변증법 매크로 구조를 적용:
결론→근거→예상 반론+재반론→상위 원칙→결론 반복
활동보고(direct_writing)는 보고 구조이므로 변증법 비대상.
"""

from __future__ import annotations

from typing import Any, Dict, List

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


# ── 결론 아키타입: 변증법 AEO 카테고리별 결론 3문단 구조 ──────────
CONCLUSION_ARCHETYPES = {
    'pledge': {
        'label': '다짐형',
        'p1': '핵심 주제어와 본문 핵심 앵커 1개를 함께 넣어 결론을 재확인하십시오.',
        'p2': '본문에 나온 실행수단 2개 이상을 이름으로 묶어 실행 다짐·약속을 서술하십시오.',
        'p3': '독자(시민·당원) 호소보다 성과 확인 방식·보완 약속을 먼저 쓰고 짧은 인삿말로 마감하십시오.',
    },
    'diagnosis': {
        'label': '진단형',
        'p1': '핵심 주제어와 본문 핵심 앵커 1개를 함께 넣어 진단·판단을 재확인하십시오.',
        'p2': '본문에 나온 원인·수치·사례를 이름으로 다시 짚고 대안을 제시하십시오.',
        'p3': '독자(시민·당원) 호소보다 책임 있는 후속 확인 방식을 먼저 쓰고 짧은 인삿말로 마감하십시오.',
    },
    'action': {
        'label': '행동형',
        'p1': '핵심 주제어와 현장 앵커 1개를 함께 넣어 문제의식을 재확인하십시오.',
        'p2': '본문에 나온 행동 계획·후속 조치 2개 이상을 이름으로 서술하십시오.',
        'p3': '독자(시민·당원) 호소보다 현장 확인·보완 약속을 먼저 쓰고 짧은 인삿말로 마감하십시오.',
    },
}

# writing_method → 결론 아키타입 매핑
CONCLUSION_ARCHETYPE_MAP = {
    'logical_writing': 'pledge',       # policy-proposal
    'critical_writing': 'diagnosis',   # current-affairs
    'diagnostic_writing': 'diagnosis', # current-affairs (진단)
    'analytical_writing': 'action',    # local-issues
}


def get_conclusion_archetype(writing_method: str) -> Dict[str, str] | None:
    """writing_method에 해당하는 결론 아키타입을 반환. 비대상이면 None."""
    key = CONCLUSION_ARCHETYPE_MAP.get(writing_method)
    if key is None:
        return None
    return CONCLUSION_ARCHETYPES[key]


def uses_aeo_answer_first(writing_method: str) -> bool:
    """writing_method가 AEO answer-first 서론 구조 대상인지 판별."""
    return writing_method in AEO_ANSWER_FIRST_METHODS


def uses_dialectical_structure(writing_method: str) -> bool:
    """writing_method가 변증법 매크로 구조 대상인지 판별."""
    return writing_method in AEO_DIALECTICAL_METHODS


def paragraph_contract_for_writing_method(writing_method: str) -> Dict[str, int | bool]:
    """writing_method별 섹션 문단 계약을 반환.

    AEO 대상은 답변형·논증형 구조를 안정적으로 만들기 위해 섹션당 3문단을 목표로 한다.
    감성·소회·행사형처럼 AEO 대상이 아닌 글은 2~3문단을 허용한다. 개인의 다짐이나 소회
    글에 변증법적 3문단 구조를 강제하면 장르가 무너지고 최종 구조 게이트가 불필요하게 실패한다.
    """
    is_aeo = uses_aeo_answer_first(writing_method)
    if is_aeo:
        return {
            "is_aeo": True,
            "paragraphs_per_section": 3,
            "section_paragraph_min": 3,
            "section_paragraph_max": 4,
        }
    return {
        "is_aeo": False,
        "paragraphs_per_section": 2,
        "section_paragraph_min": 2,
        "section_paragraph_max": 3,
    }


def paragraph_contract_from_length_spec(length_spec: Dict[str, Any] | None) -> Dict[str, int | bool]:
    """length_spec에서 섹션 문단 계약을 읽어 표준 형태로 보정한다.

    기존 테스트와 호출부 호환을 위해 `is_aeo`가 없으면 AEO 계약(3~4문단)을 기본값으로 둔다.
    비AEO 호출부는 `_build_length_spec()`에서 `is_aeo=False`를 명시한다.
    """
    spec = length_spec if isinstance(length_spec, dict) else {}
    if "is_aeo" in spec:
        is_aeo = bool(spec.get("is_aeo"))
    else:
        writing_method = str(spec.get("writing_method") or "")
        is_aeo = uses_aeo_answer_first(writing_method) if writing_method else True

    base = paragraph_contract_for_writing_method("logical_writing" if is_aeo else "emotional_writing")

    def _to_int(value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(maximum, parsed))

    target = _to_int(
        spec.get("paragraphs_per_section"),
        int(base["paragraphs_per_section"]),
        2,
        4,
    )
    min_p = _to_int(
        spec.get("section_paragraph_min"),
        int(base["section_paragraph_min"]),
        2,
        4,
    )
    max_p = _to_int(
        spec.get("section_paragraph_max"),
        int(base["section_paragraph_max"]),
        min_p,
        4,
    )
    if max_p < min_p:
        max_p = min_p

    return {
        "is_aeo": is_aeo,
        "paragraphs_per_section": target,
        "section_paragraph_min": min_p,
        "section_paragraph_max": max_p,
    }


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
            "개별 정책이 아니라 그 정책이 실현하는 상위 목표를 선언하십시오. "
            "반드시 프롬프트의 <political_philosophy> 블록(core_values, leadership_principles, "
            "balanced_approach)에서 이 주제와 가장 관련 깊은 가치·원칙을 골라 "
            "구체적으로 인용·연결하십시오. 추상적 미사여구가 아니라 "
            "해당 철학이 이 정책과 어떻게 맞닿는지를 논증해야 합니다."
        ),
    })

    return roles
