"""제목 생성 프롬프트 빌더.

Node.js `functions/prompts/builders/title-generation.js` 호환 API.
핵심 로직은 기존 `agents.common.title_generation` 구현을 재사용한다.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional, Sequence

from agents.common.title_generation import (
    TITLE_TYPES,
    are_keywords_similar as _are_keywords_similar,
    build_title_prompt as _build_title_prompt,
    calculate_title_quality_score as _calculate_title_quality_score,
    detect_content_type as _detect_content_type,
    extract_numbers_from_content as _extract_numbers_from_content,
    generate_and_validate_title as _generate_and_validate_title,
    get_election_compliance_instruction as _get_election_compliance_instruction,
    get_keyword_strategy_instruction as _get_keyword_strategy_instruction,
    validate_theme_and_content as _validate_theme_and_content,
)


KEYWORD_POSITION_GUIDE: Dict[str, Dict[str, str]] = {
    "front": {
        "range": "0-8자",
        "weight": "100%",
        "use": "지역명, 정책명, 핵심 주제",
        "example": '"분당구 청년 기본소득" -> "분당구"가 검색 가중치 최고',
    },
    "middle": {
        "range": "9-17자",
        "weight": "80%",
        "use": "구체적 수치, LSI 키워드",
        "example": '"월 50만원", "주거·일자리"',
    },
    "end": {
        "range": "18-35자",
        "weight": "60%",
        "use": "행동 유도, 긴급성, 신뢰성 신호",
        "example": '"신청 마감 3일 전", "5대 성과"',
    },
}


def detect_content_type(content_preview: str, category: str) -> str:
    return _detect_content_type(content_preview, category)


def extract_numbers_from_content(content: str) -> Dict[str, Any]:
    return _extract_numbers_from_content(content)


def get_election_compliance_instruction(status: str) -> str:
    return _get_election_compliance_instruction(status)


def are_keywords_similar(kw1: str, kw2: str) -> bool:
    return _are_keywords_similar(kw1, kw2)


def get_keyword_strategy_instruction(
    user_keywords: Sequence[str] | None,
    keywords: Sequence[str] | None,
) -> str:
    return _get_keyword_strategy_instruction(list(user_keywords or []), list(keywords or []))


def build_title_prompt(
    params: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> str:
    payload = dict(params or {})
    if kwargs:
        payload.update(kwargs)
    return _build_title_prompt(payload)


def build_title_prompt_with_type(
    type_id: str,
    params: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> str:
    payload = dict(params or {})
    if kwargs:
        payload.update(kwargs)
    payload["_forcedType"] = type_id
    return _build_title_prompt(payload)


def get_title_guideline_for_template(
    user_keywords: Sequence[str] | None = None,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    options = options or {}
    user_keywords = list(user_keywords or [])

    author_name = str(options.get("authorName") or "")
    category = str(options.get("category") or "")
    primary_kw = user_keywords[0] if user_keywords else ""
    is_commentary_category = category in {"current-affairs", "bipartisan-cooperation"}
    author = author_name or "이재성"

    return f"""<title_quality_conditions platform="naver-blog">

<requirements priority="must" description="위반 시 재생성">
  <rule id="length_max">35자 이내 (네이버 검색결과 35자 초과 시 잘림)</rule>
  <rule id="numbers_only">숫자는 본문에 실제 등장한 것만 사용 (날조 금지)</rule>
  <rule id="topic_core">주제 핵심 요소 반영 필수</rule>
  <rule id="no_ellipsis">말줄임표("...") 절대 금지</rule>
</requirements>

<recommendations priority="should" description="품질 향상">
  <rule id="optimal_length">18-30자 (클릭률 최고 구간)</rule>
  <rule id="keyword_position">{f'키워드 "{primary_kw}"를 제목 앞 8자 안에 배치' if primary_kw else '핵심 키워드를 제목 앞 8자 안에 배치'}</rule>
  <rule id="concrete_numbers">구체적 숫자 포함 (274명, 85억 등)</rule>
  {f'<rule id="speaker_pattern">화자 연결 패턴: "{author}이 본", "칭찬한 {author}"</rule>' if is_commentary_category else ''}
</recommendations>

<optional priority="could" description="서사적 긴장감">
  <description>읽은 뒤 "그래서?" "왜?"가 떠오르는 제목이 좋다. 기법을 억지로 넣지 말고 자연스러운 호기심을 만들 것.</description>
  <rule type="must-not">선언형("~바꾼다", "~이끈다") 금지</rule>
  <rule type="must">정보 요소 3개 이하</rule>
</optional>

<examples type="good" description="18-30자">
  <example length="20">부산 지방선거, 왜 이 남자가 뛰어들었나</example>
  <example length="21">부산 지방선거에 뛰어든 부두 노동자의 아들</example>
  <example length="17">부산 지방선거, {author}은 왜 다른가</example>
  <example length="22">부산 지방선거, {author}이 경제에 거는 한 수</example>
  <example length="19">부산 청년이 떠나는 도시, {author}의 답은</example>
</examples>

<examples type="bad">
  <example problem="선언형 - 답을 다 알려줌">부산 지방선거, AI 전문가 {author}이 경제를 바꾼다</example>
  <example problem="키워드 나열 - 문장 아님">{author} 부산 지방선거, AI 3대 강국?</example>
  <example problem="낚시 자극 - 구체성 없음">결국 터졌습니다... 충격적 현실</example>
</examples>

</title_quality_conditions>"""


def validate_theme_and_content(topic: str, content: str, title: str = "") -> Dict[str, Any]:
    return _validate_theme_and_content(topic, content, title)


def calculate_title_quality_score(
    title: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return _calculate_title_quality_score(title, dict(params or {}))


async def generate_and_validate_title(
    generate_fn: Callable[[str], Awaitable[str]],
    params: Optional[Dict[str, Any]] = None,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return await _generate_and_validate_title(generate_fn, dict(params or {}), dict(options or {}))


# JS 호환 별칭
buildTitlePrompt = build_title_prompt
buildTitlePromptWithType = build_title_prompt_with_type
detectContentType = detect_content_type
extractNumbersFromContent = extract_numbers_from_content
getElectionComplianceInstruction = get_election_compliance_instruction
getKeywordStrategyInstruction = get_keyword_strategy_instruction
areKeywordsSimilar = are_keywords_similar
getTitleGuidelineForTemplate = get_title_guideline_for_template
validateThemeAndContent = validate_theme_and_content
calculateTitleQualityScore = calculate_title_quality_score
generateAndValidateTitle = generate_and_validate_title


__all__ = [
    "TITLE_TYPES",
    "KEYWORD_POSITION_GUIDE",
    "build_title_prompt",
    "build_title_prompt_with_type",
    "detect_content_type",
    "extract_numbers_from_content",
    "get_election_compliance_instruction",
    "get_keyword_strategy_instruction",
    "are_keywords_similar",
    "get_title_guideline_for_template",
    "validate_theme_and_content",
    "calculate_title_quality_score",
    "generate_and_validate_title",
    "buildTitlePrompt",
    "buildTitlePromptWithType",
    "detectContentType",
    "extractNumbersFromContent",
    "getElectionComplianceInstruction",
    "getKeywordStrategyInstruction",
    "areKeywordsSimilar",
    "getTitleGuidelineForTemplate",
    "validateThemeAndContent",
    "calculateTitleQualityScore",
    "generateAndValidateTitle",
]

