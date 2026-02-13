"""개인화 힌트 생성 유틸리티.

Node.js `functions/services/posts/personalization.js` 포팅.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# Node.js `functions/utils/posts/constants.js` 포팅
POLICY_NAMES = {
    "economy": "경제정책",
    "education": "교육정책",
    "welfare": "복지정책",
    "environment": "환경정책",
    "security": "안보정책",
    "culture": "문화정책",
}

FAMILY_STATUS_MAP = {
    "미혼": "싱글 생활의 경험을 가진",
    "기혼(자녀 있음)": "자녀 양육 가정의 경험을 가진",
    "기혼(자녀 없음)": "가정을 꾸리며",
    "한부모": "한부모 가정의 경험을 가진",
}

CAREER_RELEVANCE = {
    "교육자": ["교육", "학생", "학교", "교사"],
    "사업가": ["경제", "중소상공인", "영업", "창업"],
    "공무원": ["행정", "정책", "공공서비스"],
    "의료인": ["의료", "건강", "코로나", "보건"],
    "법조인": ["법", "제도", "정의", "권리"],
}

POLITICAL_EXPERIENCE_MAP = {
    "초선": "초선 의원으로서 신선한 관점에서",
    "재선": "의정 경험을 바탕으로",
    "3선이상": "다선 의정 경험으로",
    "정치 신인": "새로운 시각에서",
}

COMMITTEE_KEYWORDS = {
    "교육위원회": ["교육", "학생", "학교", "대학"],
    "보건복지위원회": ["복지", "의료", "건강", "연금"],
    "국토교통위원회": ["교통", "주거", "도로", "건설"],
    "환경노동위원회": ["환경", "노동", "일자리"],
    "여성가족위원회": ["여성", "가족", "육아", "출산"],
}

LOCAL_CONNECTION_MAP = {
    "토박이": "지역 토박이로서",
    "오래 거주": "오랫동안 이 지역에 거주해",
    "이주민": "이 지역에서 새로운 삶을 시작한 고향으로 일구",
    "귀농": "고향으로 돌아온",
}


def _build_style_guide_prompt(style_fingerprint: Dict[str, Any], compact: bool = False) -> str:
    """stylometry 모듈이 없을 때 사용하는 경량 스타일 가이드 생성기."""
    if not style_fingerprint:
        return ""

    metadata = style_fingerprint.get("analysisMetadata") or {}
    confidence = float(metadata.get("confidence") or 0)
    if confidence < 0.5:
        return ""

    phrases = style_fingerprint.get("characteristicPhrases") or {}
    sentence_patterns = style_fingerprint.get("sentencePatterns") or {}
    vocab = style_fingerprint.get("vocabularyProfile") or {}
    tone = style_fingerprint.get("toneProfile") or {}

    if compact:
        signatures = (phrases.get("signatures") or [])[:3]
        tone_tags: list[str] = []
        if float(tone.get("formality") or 0) > 0.6:
            tone_tags.append("격식체")
        if float(tone.get("directness") or 0) > 0.6:
            tone_tags.append("직접적")
        if float(tone.get("optimism") or 0) > 0.6:
            tone_tags.append("희망적")
        avg_length = sentence_patterns.get("avgLength") or 45
        base = "[문체] "
        if signatures:
            base += f"표현: {', '.join(f'\"{s}\"' for s in signatures)}. "
        if tone_tags:
            base += f"어조: {'/'.join(tone_tags)}. "
        base += f"문장 {avg_length}자 내외."
        return base

    sections: list[str] = []
    signature_phrases = (phrases.get("signatures") or [])[:5]
    emphatics = (phrases.get("emphatics") or [])[:3]
    if signature_phrases or emphatics:
        all_phrases = signature_phrases + emphatics
        sections.append(f"1. 특징적 표현: {', '.join(f'\"{item}\"' for item in all_phrases)}")

    avg_len = sentence_patterns.get("avgLength") or 45
    starters = (sentence_patterns.get("preferredStarters") or [])[:3]
    clause = sentence_patterns.get("clauseComplexity") or "medium"
    sentence_lines = [f"- 문장 길이: {avg_len}자 내외", f"- 복잡도: {clause}"]
    if starters:
        sentence_lines.insert(1, f"- 시작 표현: {', '.join(f'\"{s}\"' for s in starters)}")
    sections.append("2. 문장 구조:\n  " + "\n  ".join(sentence_lines))

    frequent_words = (vocab.get("frequentWords") or [])[:5]
    if frequent_words:
        sections.append(
            "3. 어휘 선택:\n"
            f"  - 선호 단어: {', '.join(frequent_words)}\n"
            f"  - 전문성: {vocab.get('technicalLevel') or 'accessible'}"
        )

    tone_desc: list[str] = []
    if float(tone.get("formality") or 0) > 0.6:
        tone_desc.append("격식체")
    elif float(tone.get("formality") or 0) < 0.4:
        tone_desc.append("친근체")
    if float(tone.get("directness") or 0) > 0.6:
        tone_desc.append("직접적")
    if float(tone.get("optimism") or 0) > 0.6:
        tone_desc.append("희망적")
    if tone_desc:
        sections.append(f"4. 어조: {', '.join(tone_desc)}")

    if not sections:
        return ""
    return "\n".join(sections)


def generate_personalized_hints(bio_metadata: Dict[str, Any] | None) -> str:
    """Bio 메타데이터 기반 개인화 힌트 생성."""
    if not bio_metadata:
        return ""

    hints: list[str] = []
    political_stance = bio_metadata.get("politicalStance") or {}

    if (political_stance.get("progressive") or 0) > 0.7:
        hints.append("보수보다 혁신을 강조하는 진보적 관점으로 작성")
    elif (political_stance.get("conservative") or 0) > 0.7:
        hints.append("안정성과 전통 가치를 중시하는 보수적 관점으로 작성")
    elif (political_stance.get("moderate") or 0) > 0.8:
        hints.append("균형잡힌 중도적 관점에서 다양한 의견을 수용하여 작성")

    comm_style = bio_metadata.get("communicationStyle") or {}
    if comm_style.get("tone") == "warm":
        hints.append("따뜻하고 친근한 어조 사용")
    elif comm_style.get("tone") == "formal":
        hints.append("격식있고 전문적인 어조 사용")

    if comm_style.get("approach") == "inclusive":
        hints.append("모든 계층을 포용하는 수용적 표현")
    elif comm_style.get("approach") == "collaborative":
        hints.append("협력과 소통을 강조하는 협업적 표현")

    policy_focus = bio_metadata.get("policyFocus") or {}
    if policy_focus:
        top_policy = sorted(
            policy_focus.items(),
            key=lambda item: float((item[1] or {}).get("weight") or 0),
            reverse=True,
        )[0]
        top_policy_key, top_policy_info = top_policy
        if float((top_policy_info or {}).get("weight") or 0) > 0.6:
            hints.append(f"{POLICY_NAMES.get(top_policy_key, top_policy_key)} 관점에서 표현")

    local_connection = bio_metadata.get("localConnection") or {}
    if float(local_connection.get("strength") or 0) > 0.8:
        hints.append("지역현안과 주민들의 실제 경험을 구체적으로 반영")
        local_keywords = local_connection.get("keywords") or []
        if local_keywords:
            hints.append(f"지역 용어 사용: {', '.join(local_keywords[:3])}")

    prefs = ((bio_metadata.get("generationProfile") or {}).get("likelyPreferences")) or {}
    if float(prefs.get("includePersonalExperience") or 0) > 0.8:
        hints.append("개인적 경험과 사례를 풍부하게 포함")
    if float(prefs.get("useStatistics") or 0) > 0.7:
        hints.append("구체적인 숫자와 데이터를 적극적으로 사용")
    if float(prefs.get("focusOnFuture") or 0) > 0.7:
        hints.append("미래 비전과 발전 방향을 제시")

    return " | ".join(hints)


def _get_age_sensitive_family_expression(family_status: str, age_decade: str | None) -> str:
    if family_status == "기혼(자녀 있음)":
        if age_decade in {"20대", "30대"}:
            return "어린 자녀를 키우는"
        if age_decade == "40대":
            return "자녀를 키우는"
        if age_decade in {"50대", "60대", "70대 이상"}:
            return ""
        return ""

    if family_status == "한부모":
        return FAMILY_STATUS_MAP.get("한부모", "")

    return ""


def get_relevant_personal_info(
    user_profile: Dict[str, Any] | None,
    category: str,
    topic_lower: str,
) -> Dict[str, Any]:
    """카테고리/주제에 맞는 개인정보만 선별."""
    if not user_profile:
        return {}

    result: Dict[str, Any] = {}

    if category == "daily-communication" or any(
        token in topic_lower for token in ("교육", "육아", "복지")
    ):
        family_status = user_profile.get("familyStatus")
        if family_status:
            result["family"] = _get_age_sensitive_family_expression(
                family_status,
                user_profile.get("ageDecade"),
            )

    background_career = user_profile.get("backgroundCareer")
    if background_career:
        relevant_keywords = CAREER_RELEVANCE.get(background_career, [])
        if any(keyword in topic_lower for keyword in relevant_keywords):
            result["background"] = f"{background_career} 출신으로"

    if category in {"activity-report", "policy-proposal"}:
        political_experience = user_profile.get("politicalExperience")
        if political_experience == "정치 신인":
            result["experience"] = POLITICAL_EXPERIENCE_MAP["정치 신인"]
        elif political_experience in {"초선", "재선", "3선이상"}:
            result["experience"] = POLITICAL_EXPERIENCE_MAP.get(political_experience)

    committees = [value for value in (user_profile.get("committees") or []) if value]
    if committees:
        relevant_committees: list[str] = []
        for committee in committees:
            keywords = COMMITTEE_KEYWORDS.get(committee, [])
            if any(keyword in topic_lower for keyword in keywords):
                relevant_committees.append(committee)
        if relevant_committees:
            result["committees"] = relevant_committees

    if category == "local-issues" or any(token in topic_lower for token in ("지역", "우리 동네")):
        local_connection = user_profile.get("localConnection")
        if local_connection:
            result["connection"] = LOCAL_CONNECTION_MAP.get(local_connection, "")

    return result


def generate_persona_hints(user_profile: Dict[str, Any] | None, category: str, topic: str) -> str:
    """프로필 기반 페르소나 힌트 생성."""
    if not user_profile:
        return ""

    topic_lower = (topic or "").lower()
    relevant_info = get_relevant_personal_info(user_profile, category, topic_lower)
    hints: list[str] = []

    if relevant_info.get("family"):
        hints.append(relevant_info["family"])
    if relevant_info.get("background"):
        hints.append(relevant_info["background"])
    if relevant_info.get("experience"):
        hints.append(relevant_info["experience"])
    if relevant_info.get("committees"):
        hints.append(f"{', '.join(relevant_info['committees'])} 활동 경험을 바탕으로")
    if relevant_info.get("connection"):
        hints.append(relevant_info["connection"])

    persona = " ".join(item for item in hints if item)
    return f"[작성 관점: {persona}]" if persona else ""


def generate_style_hints(style_fingerprint: Dict[str, Any] | None, options: Dict[str, Any] | None = None) -> str:
    """Style Fingerprint 기반 문체 힌트 생성."""
    if not style_fingerprint:
        return ""

    options = options or {}
    confidence = float(((style_fingerprint.get("analysisMetadata") or {}).get("confidence")) or 0)
    if confidence < 0.5:
        logger.info("[Style] 신뢰도 낮음(%.2f) - 문체 가이드 생략", confidence)
        return ""

    compact = bool(options.get("compact", False))
    style_guide = _build_style_guide_prompt(style_fingerprint, compact=compact)
    if style_guide:
        logger.info("[Style] 문체 가이드 생성 완료 (%s자)", len(style_guide))
    return style_guide


def generate_all_personalization_hints(params: Dict[str, Any] | None) -> Dict[str, str]:
    """개인화 힌트 통합 생성."""
    params = params or {}
    bio_metadata = params.get("bioMetadata")
    style_fingerprint = params.get("styleFingerprint")
    user_profile = params.get("userProfile")
    category = params.get("category", "")
    topic = params.get("topic", "")

    bio_hints = generate_personalized_hints(bio_metadata)
    persona_hints = generate_persona_hints(user_profile, category, topic)
    style_guide = generate_style_hints(style_fingerprint, {"compact": False})

    personalized_hints = " | ".join(
        hint.strip() for hint in (bio_hints, persona_hints) if isinstance(hint, str) and hint.strip()
    )
    return {
        "personalizedHints": personalized_hints,
        "styleGuide": style_guide,
    }


# JS 호환 별칭
generatePersonalizedHints = generate_personalized_hints
generatePersonaHints = generate_persona_hints
getRelevantPersonalInfo = get_relevant_personal_info
generateStyleHints = generate_style_hints
generateAllPersonalizationHints = generate_all_personalization_hints


__all__ = [
    "generate_personalized_hints",
    "generate_persona_hints",
    "get_relevant_personal_info",
    "generate_style_hints",
    "generate_all_personalization_hints",
    "generatePersonalizedHints",
    "generatePersonaHints",
    "getRelevantPersonalInfo",
    "generateStyleHints",
    "generateAllPersonalizationHints",
]

