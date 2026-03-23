"""개인화 힌트 생성 유틸리티.

Node.js `functions/services/posts/personalization.js` 포팅.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from .personalization_constants import (
    CAREER_RELEVANCE,
    COMMITTEE_KEYWORDS,
    FAMILY_STATUS_MAP,
    LOCAL_CONNECTION_MAP,
    POLICY_NAMES,
    POLITICAL_EXPERIENCE_MAP,
    STYLE_GUIDE_CLOSING_ENDING_RE,
    STYLE_GUIDE_EMOTION_MARKERS,
    STYLE_GUIDE_LABEL_PREFIX_RE,
    STYLE_GUIDE_MEANING_MARKERS,
    STYLE_GUIDE_NARRATIVE_MARKERS,
    STYLE_GUIDE_POLICY_MARKERS,
    STYLE_GUIDE_POSITIONING_MARKERS,
    STYLE_GUIDE_SENTENCE_SPLIT_RE,
    STYLE_GUIDE_SOURCE_PREFIX_RE,
    STYLE_GUIDE_TRANSITION_PREFIXES,
)

logger = logging.getLogger(__name__)


def _normalize_guide_sentence(text: Any) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    normalized = STYLE_GUIDE_SOURCE_PREFIX_RE.sub("", normalized)
    normalized = STYLE_GUIDE_LABEL_PREFIX_RE.sub("", normalized)
    return normalized.strip(" -")


def _truncate_guide_sentence(text: Any, max_length: int = 90) -> str:
    normalized = _normalize_guide_sentence(text)
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max(1, max_length - 1)].rstrip() + "…"


def _split_guide_sentences(text: str, *, limit: int = 40) -> List[str]:
    if not text or not isinstance(text, str):
        return []
    return [
        item for item in (
            _normalize_guide_sentence(part)
            for part in STYLE_GUIDE_SENTENCE_SPLIT_RE.split(text)
        )
        if len(item) >= 18
    ][:limit]


def _collect_guide_examples(
    sentences: List[str],
    predicate,
    used: set[str],
    *,
    limit: int = 2,
) -> List[str]:
    results: List[str] = []
    for sentence in sentences:
        key = sentence.lower()
        if key in used or not predicate(sentence):
            continue
        used.add(key)
        results.append(_truncate_guide_sentence(sentence))
        if len(results) >= limit:
            break
    return results


def _dedupe_guide_examples(items: List[str], *, limit: int | None = None) -> List[str]:
    results: List[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = _normalize_guide_sentence(item)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(normalized)
        if limit is not None and len(results) >= limit:
            break
    return results


def _contains_style_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _build_style_role_pairs(
    left_items: List[str],
    right_items: List[str],
    *,
    left_key: str,
    right_key: str,
    max_pairs: int = 2,
) -> List[Dict[str, str]]:
    pairs: List[Dict[str, str]] = []
    for idx, left in enumerate(left_items[:max_pairs]):
        if not left:
            continue
        right = right_items[idx] if idx < len(right_items) else (right_items[0] if right_items else "")
        if not right:
            continue
        pairs.append({left_key: left, right_key: right})
    return pairs


def _build_source_role_examples(source_examples: Dict[str, Any], example_patterns: List[str]) -> Dict[str, Any]:
    transition_examples = _dedupe_guide_examples(
        list(source_examples.get("transitionExamples") or []) + list(example_patterns or []),
        limit=2,
    )
    concretization_examples = _dedupe_guide_examples(list(source_examples.get("concretizationExamples") or []))
    positioning_examples = _dedupe_guide_examples(list(source_examples.get("positioningExamples") or []))
    emotion_examples = _dedupe_guide_examples(list(source_examples.get("emotionExamples") or []))

    narrative_candidates = [
        item
        for item in _dedupe_guide_examples(
            list(source_examples.get("transitionExamples") or [])
            + list(source_examples.get("concretizationExamples") or [])
            + positioning_examples
        )
        if _contains_style_marker(item, STYLE_GUIDE_NARRATIVE_MARKERS)
    ]
    policy_candidates = [
        item
        for item in _dedupe_guide_examples(list(example_patterns or []) + positioning_examples + emotion_examples)
        if _contains_style_marker(item, STYLE_GUIDE_POLICY_MARKERS)
    ]
    evidence_candidates = [
        item
        for item in _dedupe_guide_examples(concretization_examples + list(source_examples.get("transitionExamples") or []))
        if re.search(r"\d", item) or _contains_style_marker(item, ("부산", "시민", "현장", "기업", "경제"))
    ]
    meaning_candidates = [
        item
        for item in _dedupe_guide_examples(list(example_patterns or []) + positioning_examples + emotion_examples)
        if _contains_style_marker(item, STYLE_GUIDE_MEANING_MARKERS)
    ]
    closing_examples = _dedupe_guide_examples(
        emotion_examples + [item for item in example_patterns if STYLE_GUIDE_CLOSING_ENDING_RE.search(item)],
        limit=2,
    )

    return {
        "declarationBridgeExamples": transition_examples,
        "narrativeToPolicyPairs": _build_style_role_pairs(
            narrative_candidates,
            policy_candidates,
            left_key="narrative",
            right_key="policy",
        ),
        "evidenceToMeaningPairs": _build_style_role_pairs(
            evidence_candidates,
            meaning_candidates,
            left_key="evidence",
            right_key="meaning",
        ),
        "closingExamples": closing_examples,
    }


def _extract_style_guide_examples(style_fingerprint: Dict[str, Any], source_text: str = "") -> Dict[str, Any]:
    sentences = _split_guide_sentences(source_text)
    if not sentences:
        return {
            "transitionExamples": [],
            "concretizationExamples": [],
            "shortExample": "",
            "longExample": "",
            "positioningExamples": [],
            "emotionExamples": [],
        }

    phrases = style_fingerprint.get("characteristicPhrases") or {}
    sentence_patterns = style_fingerprint.get("sentencePatterns") or {}
    vocab = style_fingerprint.get("vocabularyProfile") or {}
    rhetoric = style_fingerprint.get("rhetoricalDevices") or {}
    used: set[str] = set()

    transition_tokens = [
        _normalize_guide_sentence(item)
        for item in [*(phrases.get("transitions") or []), *(sentence_patterns.get("preferredStarters") or []), *STYLE_GUIDE_TRANSITION_PREFIXES]
        if _normalize_guide_sentence(item)
    ]
    vocab_tokens = [
        _normalize_guide_sentence(item)
        for item in [*(vocab.get("localTerms") or []), *(vocab.get("frequentWords") or []), *(vocab.get("preferredVerbs") or [])]
        if _normalize_guide_sentence(item)
    ]
    emotion_tokens = [
        _normalize_guide_sentence(item)
        for item in [*(phrases.get("emphatics") or []), *(phrases.get("conclusions") or []), *STYLE_GUIDE_EMOTION_MARKERS]
        if _normalize_guide_sentence(item)
    ]
    signature_tokens = [
        _normalize_guide_sentence(item)
        for item in (phrases.get("signatures") or [])
        if _normalize_guide_sentence(item)
    ]

    transition_examples = _collect_guide_examples(
        sentences,
        lambda sentence: any(token in sentence for token in transition_tokens),
        used,
        limit=2,
    )
    concretization_examples = _collect_guide_examples(
        sentences,
        lambda sentence: bool(re.search(r"\d", sentence))
        or any(token in sentence for token in vocab_tokens)
        or (24 <= len(sentence) <= 95 and bool(re.search(r"(일자리|골목|아이|항만|주거|교육|복지|경제)", sentence))),
        used,
        limit=2,
    )
    positioning_examples = _collect_guide_examples(
        sentences,
        lambda sentence: any(token in sentence for token in signature_tokens)
        or (
            bool(re.match(r"^(?:저는|저 이|저는 바로|이재성은|저는 부산)", sentence))
            and any(token in sentence for token in STYLE_GUIDE_POSITIONING_MARKERS)
        ),
        used,
        limit=2,
    )
    emotion_examples = _collect_guide_examples(
        sentences,
        lambda sentence: any(token in sentence for token in emotion_tokens),
        used,
        limit=2,
    )
    short_example = (_collect_guide_examples(sentences, lambda sentence: len(sentence) <= 38, used, limit=1) or [""])[0]
    long_example = (_collect_guide_examples(sentences, lambda sentence: len(sentence) >= 58, used, limit=1) or [""])[0]

    if not transition_examples:
        for item in (rhetoric.get("examplePatterns") or [])[:2]:
            normalized = _truncate_guide_sentence(item)
            key = normalized.lower()
            if not normalized or key in used:
                continue
            used.add(key)
            transition_examples.append(normalized)
            if len(transition_examples) >= 2:
                break

    return {
        "transitionExamples": transition_examples,
        "concretizationExamples": concretization_examples,
        "shortExample": short_example,
        "longExample": long_example,
        "positioningExamples": positioning_examples,
        "emotionExamples": emotion_examples,
    }


def _compose_style_guide_prompt(
    *,
    transitions: List[str],
    example_patterns: List[str],
    signature_phrases: List[str],
    emphatics: List[str],
    conclusions: List[str],
    starters: List[str],
    endings: List[str],
    frequent_words: List[str],
    preferred_verbs: List[str],
    preferred_adjectives: List[str],
    local_terms: List[str],
    unique_features: List[str],
    tone: Dict[str, Any],
    vocab: Dict[str, Any],
    sentence_patterns: Dict[str, Any],
    analysis: Dict[str, Any],
    style_fingerprint: Dict[str, Any],
    source_examples: Dict[str, Any],
    compact: bool,
) -> str:
    role_examples = _build_source_role_examples(source_examples, example_patterns)

    if compact:
        tone_tags: list[str] = []
        if float(tone.get("formality") or 0) > 0.6:
            tone_tags.append("격식체")
        if float(tone.get("directness") or 0) > 0.6:
            tone_tags.append("직접적")
        if float(tone.get("optimism") or 0) > 0.6:
            tone_tags.append("낙관적")
        avg_length = sentence_patterns.get("avgLength") or 45
        base = "[문체] "
        if signature_phrases:
            base += f"표현: {', '.join(f'\"{s}\"' for s in signature_phrases[:3])}. "
        if transitions:
            base += f"전환: {', '.join(f'\"{s}\"' for s in transitions[:2])}. "
        if example_patterns:
            base += f"전개 예시: {', '.join(f'\"{s}\"' for s in example_patterns[:2])}. "
        if source_examples.get("transitionExamples"):
            base += f"실제 문장: {', '.join(f'\"{s}\"' for s in source_examples['transitionExamples'][:2])}. "
        if role_examples.get("closingExamples"):
            base += f"마감: {', '.join(f'\"{s}\"' for s in role_examples['closingExamples'][:1])}. "
        if tone_tags:
            base += f"어조: {'/'.join(tone_tags)}. "
        base += f"문장 {avg_length}자 내외."
        return base

    sections: list[str] = []

    def append_section(title: str, lines: List[str]) -> None:
        if not lines:
            return
        sections.append(f"{len(sections) + 1}. {title}:\n  " + "\n  ".join(lines))

    role_lines: list[str] = []
    if role_examples.get("declarationBridgeExamples"):
        role_lines.append(
            "- 선언 뒤 연결: "
            + ", ".join(f'"{item}"' for item in role_examples["declarationBridgeExamples"])
        )
    if role_examples.get("narrativeToPolicyPairs"):
        role_lines.append(
            "- 개인 서사 -> 정책 전환: "
            + " / ".join(
                f'서사 "{item["narrative"]}" | 선언 "{item["policy"]}"'
                for item in role_examples["narrativeToPolicyPairs"]
                if item.get("narrative") and item.get("policy")
            )
        )
    if role_examples.get("evidenceToMeaningPairs"):
        role_lines.append(
            "- 수치/증거 -> 의미 해석: "
            + " / ".join(
                f'근거 "{item["evidence"]}" | 해석 "{item["meaning"]}"'
                for item in role_examples["evidenceToMeaningPairs"]
                if item.get("evidence") and item.get("meaning")
            )
        )
    if role_examples.get("closingExamples"):
        role_lines.append(
            "- 문단 마감: "
            + ", ".join(f'"{item}"' for item in role_examples["closingExamples"])
        )
    append_section("문장 역할별 실제 예시", role_lines)

    if transitions or example_patterns or source_examples.get("transitionExamples"):
        transition_lines: list[str] = []
        if transitions:
            transition_lines.append(f"- 선언 뒤 연결: {', '.join(f'\"{item}\"' for item in transitions)}")
        if example_patterns:
            transition_lines.append(f"- 실제 전개 예시: {', '.join(f'\"{item}\"' for item in example_patterns)}")
        if source_examples.get("transitionExamples"):
            transition_lines.append(
                f"- 실제 사용자 문장: {', '.join(f'\"{item}\"' for item in source_examples['transitionExamples'])}"
            )
        append_section("전환 패턴", transition_lines)

    avg_len = sentence_patterns.get("avgLength") or 45
    clause = sentence_patterns.get("clauseComplexity") or "medium"
    concretization_lines = [
        f"- 추상 주장을 풀어내는 문장 길이: {avg_len}자 내외",
        f"- 절 복잡도: {clause}",
        f"- 사실/정책 설명 수준: {vocab.get('technicalLevel') or 'accessible'}",
    ]
    concretization_vocab = local_terms or frequent_words
    if concretization_vocab:
        concretization_lines.append(f"- 생활/현장 어휘: {', '.join(concretization_vocab)}")
    if preferred_verbs:
        concretization_lines.append(f"- 행동 동사: {', '.join(preferred_verbs)}")
    if source_examples.get("concretizationExamples"):
        concretization_lines.append(
            f"- 실제 사용자 문장: {', '.join(f'\"{item}\"' for item in source_examples['concretizationExamples'])}"
        )
    append_section("구체화 패턴", concretization_lines)

    rhythm_lines = [f"- 문장 길이: {avg_len}자 내외", f"- 문장 복잡도: {clause}"]
    if starters:
        rhythm_lines.append(f"- 선호 시작어: {', '.join(f'\"{s}\"' for s in starters)}")
    if endings:
        rhythm_lines.append(f"- 문단/문장 마감: {', '.join(endings)}")
    if source_examples.get("shortExample"):
        rhythm_lines.append(f"- 짧은 실제 문장: \"{source_examples['shortExample']}\"")
    if source_examples.get("longExample"):
        rhythm_lines.append(f"- 긴 실제 문장: \"{source_examples['longExample']}\"")
    append_section("리듬 패턴", rhythm_lines)

    vocab_lines: list[str] = []
    if preferred_verbs:
        vocab_lines.append(f"- 반복 동사: {', '.join(preferred_verbs)}")
    if frequent_words:
        vocab_lines.append(f"- 생활 명사/전달 어휘: {', '.join(frequent_words)}")
    if local_terms:
        vocab_lines.append(f"- 지역/현장 어휘: {', '.join(local_terms)}")
    if signature_phrases or emphatics or preferred_adjectives:
        cluster_items = signature_phrases + emphatics + preferred_adjectives
        vocab_lines.append(f"- 시그니처 표현: {', '.join(f'\"{item}\"' for item in cluster_items[:6])}")
    append_section("선호 어휘 클러스터", vocab_lines)

    positioning_lines: list[str] = []
    dominant_style = str(analysis.get("dominantStyle") or "").strip()
    if dominant_style:
        positioning_lines.append(f"- 기본 자기 포지셔닝: {dominant_style}")
    if unique_features:
        positioning_lines.append(f"- 구별되는 정체성 요소: {', '.join(unique_features)}")
    if signature_phrases:
        positioning_lines.append(f"- 자기 소개/선언 표현: {', '.join(f'\"{item}\"' for item in signature_phrases[:3])}")
    if source_examples.get("positioningExamples"):
        positioning_lines.append(
            f"- 실제 자기 선언 문장: {', '.join(f'\"{item}\"' for item in source_examples['positioningExamples'])}"
        )
    append_section("화자 포지셔닝 방식", positioning_lines)

    tone_desc: list[str] = []
    if float(tone.get("formality") or 0) > 0.6:
        tone_desc.append("격식체")
    elif float(tone.get("formality") or 0) < 0.4:
        tone_desc.append("구어체")
    if float(tone.get("directness") or 0) > 0.6:
        tone_desc.append("직접적")
    if float(tone.get("optimism") or 0) > 0.6:
        tone_desc.append("낙관적")
    emotion_lines: list[str] = []
    if tone_desc:
        emotion_lines.append(f"- 어조: {', '.join(tone_desc)}")
    tone_description = str(tone.get("toneDescription") or "").strip()
    if tone_description:
        emotion_lines.append(f"- 감정 표현 설명: {tone_description}")
    if emphatics or conclusions:
        emotion_lines.append(f"- 확신/마감 표현: {', '.join(f'\"{item}\"' for item in (emphatics + conclusions)[:5])}")
    if source_examples.get("emotionExamples"):
        emotion_lines.append(
            f"- 실제 감정/선언 문장: {', '.join(f'\"{item}\"' for item in source_examples['emotionExamples'])}"
        )
    append_section("감정 표현 방식", emotion_lines)

    ai_alternatives = style_fingerprint.get("aiAlternatives") or {}
    alternative_lines: list[str] = []
    for raw_key, raw_value in list(ai_alternatives.items())[:4]:
        source = str(raw_key or "").replace("instead_of_", "").replace("_", " ").strip()
        target = str(raw_value or "").strip()
        if source and target:
            alternative_lines.append(f'- "{source}" 대신 "{target}"')
    append_section("AI 상투어 대체", alternative_lines)

    return "\n".join(sections)


def _build_style_guide_prompt(style_fingerprint: Dict[str, Any], compact: bool = False, source_text: str = "") -> str:
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
    rhetoric = style_fingerprint.get("rhetoricalDevices") or {}
    analysis = style_fingerprint.get("analysisMetadata") or {}

    transitions = [item for item in (phrases.get("transitions") or []) if item][:4]
    example_patterns = [item for item in (rhetoric.get("examplePatterns") or []) if item][:3]
    signature_phrases = [item for item in (phrases.get("signatures") or []) if item][:4]
    emphatics = [item for item in (phrases.get("emphatics") or []) if item][:3]
    conclusions = [item for item in (phrases.get("conclusions") or []) if item][:3]
    starters = [item for item in (sentence_patterns.get("preferredStarters") or []) if item][:3]
    endings = [item for item in (sentence_patterns.get("endingPatterns") or []) if item][:3]
    frequent_words = [item for item in (vocab.get("frequentWords") or []) if item][:5]
    preferred_verbs = [item for item in (vocab.get("preferredVerbs") or []) if item][:4]
    preferred_adjectives = [item for item in (vocab.get("preferredAdjectives") or []) if item][:3]
    local_terms = [item for item in (vocab.get("localTerms") or []) if item][:4]
    unique_features = [item for item in (analysis.get("uniqueFeatures") or []) if item][:3]
    source_examples = _extract_style_guide_examples(style_fingerprint, source_text)

    return _compose_style_guide_prompt(
        transitions=transitions,
        example_patterns=example_patterns,
        signature_phrases=signature_phrases,
        emphatics=emphatics,
        conclusions=conclusions,
        starters=starters,
        endings=endings,
        frequent_words=frequent_words,
        preferred_verbs=preferred_verbs,
        preferred_adjectives=preferred_adjectives,
        local_terms=local_terms,
        unique_features=unique_features,
        tone=tone,
        vocab=vocab,
        sentence_patterns=sentence_patterns,
        analysis=analysis,
        style_fingerprint=style_fingerprint,
        source_examples=source_examples,
        compact=compact,
    )


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
    style_guide = _build_style_guide_prompt(
        style_fingerprint,
        compact=compact,
        source_text=str(options.get("sourceText") or ""),
    )
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
    style_guide = generate_style_hints(
        style_fingerprint,
        {
            "compact": False,
            "sourceText": params.get("bioContent") or user_profile.get("bio") or "",
        },
    )

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
