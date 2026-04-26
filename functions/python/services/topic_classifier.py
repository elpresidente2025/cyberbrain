from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from agents.common.constants import (
    CATEGORY_TO_WRITING_METHOD,
    SUBCATEGORY_TO_WRITING_METHOD,
    detect_personal_reflection_topic,
)

logger = logging.getLogger(__name__)

DEFAULT_CATEGORY = "daily-communication"
DEFAULT_SUBCATEGORY = ""
DEFAULT_CONFIDENCE = 0.5

AUTO_CATEGORY_ALIASES = {
    "",
    "auto",
    "general",
    "default",
    "일반",
    "자동",
    "자동분류",
}

CATEGORY_ALIASES = {
    "daily-communication": "daily-communication",
    "일상소통": "daily-communication",
    "일상 소통": "daily-communication",
    "activity-report": "activity-report",
    "활동보고": "activity-report",
    "활동 보고": "activity-report",
    "의정활동보고": "activity-report",
    "의정활동 보고": "activity-report",
    "policy-proposal": "policy-proposal",
    "정책및비전": "policy-proposal",
    "정책 및 비전": "policy-proposal",
    "educational-content": "educational-content",
    "정책설명": "educational-content",
    "정책 설명": "educational-content",
    "정책해설": "educational-content",
    "정책 해설": "educational-content",
    "current-affairs": "current-affairs",
    "시사논평": "current-affairs",
    "시사 논평": "current-affairs",
    "논평": "current-affairs",
    "local-issues": "local-issues",
    "지역현안": "local-issues",
    "지역 현안": "local-issues",
    "bipartisan-cooperation": "bipartisan-cooperation",
    "초당적협력": "bipartisan-cooperation",
    "초당적 협력": "bipartisan-cooperation",
    "offline-engagement": "offline-engagement",
    "오프라인접점": "offline-engagement",
    "오프라인 접점": "offline-engagement",
}

WRITING_METHOD_TO_CATEGORY = {
    "emotional_writing": "daily-communication",
    "direct_writing": "activity-report",
    "logical_writing": "policy-proposal",
    "critical_writing": "current-affairs",
    "diagnostic_writing": "current-affairs",
    "analytical_writing": "local-issues",
    "bipartisan_writing": "bipartisan-cooperation",
    "offline_writing": "offline-engagement",
}

CATEGORY_PATTERNS = {
    "daily-communication": (
        r"감사",
        r"축하",
        r"격려",
        r"응원",
        r"추모",
        r"기념",
        r"일상",
        r"소통",
        r"인사",
        r"소회",
        r"다짐",
        r"경선\s*마무리",
        r"다시\s*시작",
        r"보답하겠습니다",
        r"함께해\s*주십시오",
    ),
    "activity-report": (
        r"활동보고",
        r"의정활동",
        r"현장\s*방문",
        r"간담회",
        r"국정감사",
        r"법안",
        r"조례",
        r"발의",
        r"예산\s*확보",
        r"처리\s*결과",
        r"추진\s*현황",
        r"성과",
    ),
    "policy-proposal": (
        r"공약",
        r"비전",
        r"정책\s*제안",
        r"로드맵",
        r"추진하겠습니다",
        r"도입하겠습니다",
        r"확대하겠습니다",
        r"개혁",
        r"해법",
        r"정책",
        r"바우처\s*(?:지급|도입|지원|확대|사업|제도)",
        r"지역화폐\s*(?:도입|확대|공약|활성화|정책|지원|장려|사용\s*확대)",
        r"(?:참여|자립|청년|가족돌봄)\s*수당",
        r"창업\s*(?:지원|생태계|육성|보육)",
        r"재취업\s*(?:지원|교육|정책|프로그램)",
        r"청년\s*(?:지원\s*정책|일자리\s*정책|주거\s*지원|이음망|자립)",
        r"돌봄\s*(?:서비스\s*확대|정책|지원\s*강화)",
        r"공공\s*(?:주택\s*공급|의료\s*강화|교육\s*지원)",
    ),
    "educational-content": (
        r"쉽게\s*설명",
        r"설명드리",
        r"안내드리",
        r"정리해\s*드리",
        r"가이드",
        r"Q\s*&\s*A",
        r"무엇이\s*달라",
        r"어떻게\s*바뀌",
        r"신청\s*방법",
        r"지원\s*대상",
        r"절차",
        r"준비\s*서류",
    ),
    "current-affairs": (
        r"논평",
        r"비판",
        r"반박",
        r"허위사실",
        r"팩트체크",
        r"입장",
        r"왜\s*문제",
        r"책임",
        r"논란",
        r"진단",
        r"원인",
        r"구조적\s*문제",
    ),
    "local-issues": (
        r"지역\s*현안",
        r"민원",
        r"교통",
        r"주차",
        r"도로",
        r"안전",
        r"생활\s*불편",
        r"동네",
        r"마을",
        r"상권",
        r"공원",
        r"현장\s*점검",
    ),
    "bipartisan-cooperation": (
        r"초당적",
        r"여야\s*협력",
        r"여야\s*합의",
        r"초당\s*협력",
        r"소신\s*발언",
        r"당을\s*넘어",
        r"진영\s*넘어",
        r"정파.*넘어",
        r"야당.*인정",
        r"협력\s*제안",
    ),
    "offline-engagement": (
        r"출판기념회",
        r"행사\s*안내",
        r"행사\s*초대",
        r"참석\s*후기",
        r"방문\s*후기",
        r"간담회\s*후기",
        r"토크\s*콘서트",
        r"타운홀",
        r"오프라인",
        r"일정\s*공지",
        r"행사\s*개최",
        r"행사\s*참석",
    ),
}

CURRENT_AFFAIRS_DIAGNOSIS_PATTERNS = (
    r"진단",
    r"원인",
    r"구조",
    r"분석",
    r"점검",
    r"왜\s*이런\s*문제가",
    r"무엇이\s*문제",
)

POLICY_EXPLANATION_PATTERNS = (
    r"설명",
    r"안내",
    r"정리",
    r"가이드",
    r"Q\s*&\s*A",
    r"신청\s*방법",
    r"지원\s*대상",
    r"절차",
    r"준비\s*서류",
    r"무엇이\s*달라",
)

SUBSTANTIVE_POLICY_PATTERNS = (
    r"공약",
    r"비전",
    r"정책",
    r"해법",
    r"도입하겠습니다",
    r"추진하겠습니다",
    r"확대하겠습니다",
    r"모색하겠습니다",
    r"실현하겠습니다",
    r"검토하겠습니다",
    r"활성화",
)

SUBSTANTIVE_ACTIVITY_PATTERNS = (
    r"의정활동",
    r"입법활동",
    r"조례",
    r"발의",
    r"가결",
    r"예산\s*확보",
    r"간담회",
    r"현장\s*방문",
    r"처리\s*결과",
    r"추진\s*현황",
    r"성과",
)

POLICY_COMMITMENT_PATTERNS = (
    r"하겠습니다",
    r"해내겠습니다",
    r"추진하겠습니다",
    r"도입하겠습니다",
    r"확대하겠습니다",
    r"모색하겠습니다",
    r"검토하겠습니다",
    r"실현하겠습니다",
    r"만들겠습니다",
)

SUPPORT_APPEAL_STRONG_PATTERNS = (
    r"지지해\s*주세요",
    r"지지해\s*주십시오",
    r"지지\s*부탁",
    r"한\s*표\s*부탁",
    r"투표\s*부탁",
    r"기회를\s*주세요",
    r"기회를\s*주십시오",
    r"꼭\s*지지해",
    r"소중한\s*한\s*표",
)

SUPPORT_APPEAL_WEAK_PATTERNS = (
    r"함께해\s*주세요",
    r"함께해\s*주십시오",
    r"응원해\s*주세요",
    r"응원해\s*주십시오",
    r"선택해\s*주세요",
    r"선택해\s*주십시오",
    r"믿어\s*주세요",
    r"믿어\s*주십시오",
    r"힘을\s*모아",
    r"힘이\s*되어",
    r"힘을\s*보태",
    r"약속드립",
    r"맡겨\s*주(?:세요|십시오)?",
    r"힘을\s*실어\s*주",
    r"도와\s*주(?:세요|십시오)?",
)

SUPPORT_APPEAL_CONTEXT_AMPLIFIERS = (
    r"예비후보",
    r"청년\s*후보",
    r"후보\s*등록",
    r"출마\s*(?:를|를\s*선언|를\s*결심|합니다|했습니다)",
    r"선거\s*(?:에서|를\s*앞두고|를\s*향해|운동)",
)


def _detect_support_appeal(stance_text: str, policy_signal_score: int) -> bool:
    """지지 호소(support_appeal) 서브카테고리 해당 여부 판정.

    강한 신호 1개 OR (약한 신호 + 문맥 증폭자)의 합이 2 이상이면 True.
    강한 신호는 명시적 지지 호소이므로 정책 점수와 무관하게 우선 감지.
    약한 신호는 정책 신호가 3 이상이면 정책 글로 판단하여 False.
    후보 문맥(amp) 단독으로도 정책 신호가 낮으면(≤1) True — CTA 없는 후보 주제 대응.
    """
    if _pattern_score(stance_text, SUPPORT_APPEAL_STRONG_PATTERNS) >= 1:
        return True
    if policy_signal_score >= 3:
        return False
    weak = _pattern_score(stance_text, SUPPORT_APPEAL_WEAK_PATTERNS)
    amp = min(_pattern_score(stance_text, SUPPORT_APPEAL_CONTEXT_AMPLIFIERS), 1)
    if amp >= 1 and policy_signal_score <= 1:
        return True
    return weak + amp >= 2


def normalize_requested_category(raw_category: Any, raw_sub_category: Any = "") -> tuple[str, str]:
    sub_category = str(raw_sub_category or "").strip()
    normalized = str(raw_category or "").strip()
    lowered = normalized.lower()

    if lowered in AUTO_CATEGORY_ALIASES:
        return "auto", sub_category

    if sub_category == "current_affairs_diagnosis":
        return "current-affairs", sub_category
    if sub_category == "policy_explanation":
        return "educational-content", sub_category

    alias = CATEGORY_ALIASES.get(normalized) or CATEGORY_ALIASES.get(lowered)
    if alias:
        return alias, sub_category

    mapped = WRITING_METHOD_TO_CATEGORY.get(lowered)
    if mapped:
        if lowered == "diagnostic_writing" and not sub_category:
            sub_category = "current_affairs_diagnosis"
        return mapped, sub_category

    if normalized in CATEGORY_TO_WRITING_METHOD:
        return normalized, sub_category

    return "auto", sub_category


def _writing_method_for(category: str, sub_category: str = "") -> str:
    if sub_category and sub_category in SUBCATEGORY_TO_WRITING_METHOD:
        return SUBCATEGORY_TO_WRITING_METHOD[sub_category]
    return CATEGORY_TO_WRITING_METHOD.get(category, CATEGORY_TO_WRITING_METHOD[DEFAULT_CATEGORY])


def _build_result(
    *,
    category: str,
    sub_category: str = "",
    confidence: float = DEFAULT_CONFIDENCE,
    source: str = "default",
) -> Dict[str, Any]:
    normalized_category, normalized_sub_category = normalize_requested_category(category, sub_category)
    if normalized_category == "auto":
        normalized_category = DEFAULT_CATEGORY
        normalized_sub_category = DEFAULT_SUBCATEGORY
    return {
        "category": normalized_category,
        "subCategory": normalized_sub_category,
        "writingMethod": _writing_method_for(normalized_category, normalized_sub_category),
        "confidence": round(float(confidence), 3),
        "source": source,
    }


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _extract_stance_text(payload: Dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""

    stance_text = _normalize_text(payload.get("stanceText"))
    if stance_text:
        return stance_text

    instructions = payload.get("instructions")
    if isinstance(instructions, list) and instructions:
        return _normalize_text(instructions[0])
    if isinstance(instructions, str):
        return _normalize_text(instructions)

    return ""


def _pattern_score(text: str, patterns: tuple[str, ...]) -> int:
    if not text:
        return 0
    return sum(1 for pattern in patterns if re.search(pattern, text, re.IGNORECASE))


def _score_categories(text: str) -> dict[str, int]:
    return {
        category: _pattern_score(text, patterns)
        for category, patterns in CATEGORY_PATTERNS.items()
    }


def _best_scored_category(text: str) -> Optional[tuple[str, int, int]]:
    scores = _score_categories(text)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return None
    best_category, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if best_score <= 0:
        return None
    return best_category, best_score, second_score


def _detect_sub_category(category: str, stance_text: str) -> str:
    if category == "current-affairs":
        if _pattern_score(stance_text, CURRENT_AFFAIRS_DIAGNOSIS_PATTERNS) >= 1:
            return "current_affairs_diagnosis"
    if category == "educational-content":
        if _pattern_score(stance_text, POLICY_EXPLANATION_PATTERNS) >= 1:
            return "policy_explanation"
    return ""


def quick_classify(topic: str) -> Optional[Dict[str, Any]]:
    normalized_topic = _normalize_text(topic)
    best = _best_scored_category(normalized_topic)
    if not best:
        return None

    best_category, best_score, second_score = best
    if best_score == 1 and second_score == 1:
        return None

    confidence = 0.68 + min(best_score, 4) * 0.06
    if best_score >= second_score + 2:
        confidence += 0.08
    elif best_score == second_score:
        confidence -= 0.08

    return _build_result(
        category=best_category,
        confidence=max(0.55, min(confidence, 0.92)),
        source="keyword",
    )


async def classify_with_llm(topic: str) -> Dict[str, Any]:
    from agents.common.gemini_client import generate_content_async, get_client

    normalized_topic = _normalize_text(topic)
    if not normalized_topic:
        return _build_result(category=DEFAULT_CATEGORY, confidence=DEFAULT_CONFIDENCE, source="default")

    if not get_client():
        logger.info("Topic classifier client unavailable; using default category")
        return _build_result(category=DEFAULT_CATEGORY, confidence=DEFAULT_CONFIDENCE, source="default")

    prompt = f"""당신은 정치인 블로그 원고의 메인 카테고리를 분류하는 편집자입니다.

아래 주제를 보고 가장 적합한 category 하나만 고르세요.

[허용 category]
- daily-communication: 감사, 축하, 격려, 추모, 일상 공유
- activity-report: 의정활동, 현장 방문, 간담회, 법안·조례 발의, 예산 확보, 성과 보고
- policy-proposal: 공약, 비전, 정책 제안, 제도 개선안, 해법 제시
- educational-content: 정책·법령·조례 설명, 신청 절차 안내, 시민 가이드
- current-affairs: 논평, 반박, 현안 진단, 입장 표명
- local-issues: 지역 현안, 민원, 교통, 주차, 안전, 생활 불편 분석
- bipartisan-cooperation: 초당적 협력, 여야 합의, 소신 발언 인정, 진영을 넘어선 정치
- offline-engagement: 행사 주최/초대, 참석 후기, 일정 공지, 출판기념회, 토크콘서트

[주제]
{normalized_topic}

JSON만 출력하세요.
{{"category":"선택한 category","confidence":0.0}}"""

    try:
        response_text = await generate_content_async(
            prompt,
            model_name="gemini-2.5-flash",
            temperature=0.1,
            max_output_tokens=80,
            response_mime_type="application/json",
        )
        cleaned = str(response_text or "").replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned)
        category = str(parsed.get("category") or "").strip()
        confidence = float(parsed.get("confidence") or 0.76)
        return _build_result(
            category=category,
            confidence=max(0.55, min(confidence, 0.9)),
            source="llm_topic",
        )
    except Exception as exc:
        logger.warning("LLM topic classification failed: %s", exc)
        return _build_result(category=DEFAULT_CATEGORY, confidence=DEFAULT_CONFIDENCE, source="default")


def refine_with_stance(primary: Dict[str, Any], stance_text: str, *, topic: str = "") -> Dict[str, Any]:
    normalized_stance = _normalize_text(stance_text)
    # support_appeal 감지는 topic+stance 합산으로 — "예비후보" 등 신호가 topic에만 있는 케이스 대응
    _combined_for_appeal = _normalize_text(f"{topic}\n{normalized_stance}".strip()) if topic else normalized_stance
    if len(_combined_for_appeal) < 8 and len(normalized_stance) < 8:
        return primary

    category = str(primary.get("category") or DEFAULT_CATEGORY)
    confidence = float(primary.get("confidence") or DEFAULT_CONFIDENCE)
    source = str(primary.get("source") or "default")

    explanation_score = _pattern_score(normalized_stance, POLICY_EXPLANATION_PATTERNS)
    diagnosis_score = _pattern_score(normalized_stance, CURRENT_AFFAIRS_DIAGNOSIS_PATTERNS)
    policy_signal_score = _pattern_score(normalized_stance, SUBSTANTIVE_POLICY_PATTERNS)
    activity_signal_score = _pattern_score(normalized_stance, SUBSTANTIVE_ACTIVITY_PATTERNS)
    policy_commitment_score = _pattern_score(normalized_stance, POLICY_COMMITMENT_PATTERNS)
    best = _best_scored_category(normalized_stance)

    if detect_personal_reflection_topic("", normalized_stance):
        if policy_signal_score >= 2 or policy_commitment_score >= 2:
            pass  # policy signal이 강하면 personal_reflection 오버라이드 차단
        else:
            if _detect_support_appeal(_combined_for_appeal, policy_signal_score):
                return _build_result(
                    category="daily-communication",
                    sub_category="support_appeal",
                    confidence=max(confidence, 0.86),
                    source=f"{source}+stance_support_appeal",
                )
            return _build_result(
                category="daily-communication",
                confidence=max(confidence, 0.86),
                source=f"{source}+stance_reflection",
            )

    if category == "daily-communication" and _detect_support_appeal(_combined_for_appeal, policy_signal_score):
        return _build_result(
            category="daily-communication",
            sub_category="support_appeal",
            confidence=max(confidence, 0.84),
            source=f"{source}+stance_support_appeal",
        )

    if category == "current-affairs" and diagnosis_score >= 1:
        return _build_result(
            category="current-affairs",
            sub_category="current_affairs_diagnosis",
            confidence=max(confidence, 0.84),
            source=f"{source}+stance",
        )

    if category in {"current-affairs", "daily-communication"} and diagnosis_score <= 0:
        if policy_signal_score >= 2 and policy_commitment_score >= 1:
            return _build_result(
                category="policy-proposal",
                confidence=max(confidence, 0.82),
                source=f"{source}+stance",
            )
        if activity_signal_score >= 3:
            return _build_result(
                category="activity-report",
                confidence=max(confidence, 0.8),
                source=f"{source}+stance",
            )

    if category in {"policy-proposal", "educational-content"}:
        if explanation_score >= 2:
            return _build_result(
                category="educational-content",
                sub_category="policy_explanation",
                confidence=max(confidence, 0.82),
                source=f"{source}+stance",
            )
        if category == "educational-content" and explanation_score >= 1:
            return _build_result(
                category="educational-content",
                sub_category="policy_explanation",
                confidence=max(confidence, 0.78),
                source=f"{source}+stance",
            )

    if not best:
        return primary

    best_category, best_score, _second_score = best
    swappable_pairs = {
        frozenset({"daily-communication", "activity-report"}),
        frozenset({"daily-communication", "local-issues"}),
        frozenset({"activity-report", "local-issues"}),
        frozenset({"policy-proposal", "educational-content"}),
        frozenset({"current-affairs", "local-issues"}),
    }

    if (
        best_category != category
        and frozenset({best_category, category}) in swappable_pairs
        and (best_score >= 3 or (best_score >= 2 and confidence < 0.78))
    ):
        refined_sub_category = _detect_sub_category(best_category, normalized_stance)
        return _build_result(
            category=best_category,
            sub_category=refined_sub_category,
            confidence=max(confidence, 0.8),
            source=f"{source}+stance",
        )

    detected_sub_category = _detect_sub_category(category, normalized_stance)
    if detected_sub_category:
        return _build_result(
            category=category,
            sub_category=detected_sub_category,
            confidence=max(confidence, 0.8),
            source=f"{source}+stance",
        )

    return primary


async def classify_topic(topic: str, stance_text: str = "") -> Dict[str, Any]:
    normalized_topic = _normalize_text(topic)
    if not normalized_topic:
        return _build_result(category=DEFAULT_CATEGORY, confidence=DEFAULT_CONFIDENCE, source="default")

    primary = quick_classify(normalized_topic)
    if not primary:
        primary = await classify_with_llm(normalized_topic)

    return refine_with_stance(primary, stance_text, topic=normalized_topic)


async def resolve_request_intent(topic: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    requested_category, requested_sub_category = normalize_requested_category(
        payload.get("category"),
        payload.get("subCategory"),
    )

    if requested_category != "auto":
        result = _build_result(
            category=requested_category,
            sub_category=requested_sub_category,
            confidence=1.0,
            source="explicit",
        )
        # subCategory가 명시됐으면 사용자 의도 존중. 비어 있을 때만 support_appeal 신호 검사.
        # daily-communication 문맥에서만 검사 — 다른 카테고리에 support_appeal subCategory 오염 방지.
        # topic+stanceText 합산 검사, 단 policy_score는 stanceText만으로 계산 (topic의 "정책" 단어에 의한 오억제 방지).
        if not requested_sub_category and requested_category == "daily-communication":
            stance_text = _extract_stance_text(payload)
            combined = _normalize_text(f"{topic}\n{stance_text}".strip())
            if combined:
                _stance_only = _normalize_text(stance_text)
                policy_score = _pattern_score(_stance_only, SUBSTANTIVE_POLICY_PATTERNS) if _stance_only else 0
                if _detect_support_appeal(combined, policy_score):
                    result = {**result, "subCategory": "support_appeal", "source": "explicit+topic_stance_support_appeal"}
                    result["writingMethod"] = _writing_method_for(requested_category, "support_appeal")
        return result

    stance_text = _extract_stance_text(payload)
    return await classify_topic(topic, stance_text=stance_text)
