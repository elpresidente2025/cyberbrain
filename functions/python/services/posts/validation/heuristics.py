"""???? ?? ? ??/?? ??."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence

from agents.common.fact_guard import find_unsupported_numeric_tokens

from ._shared import _strip_html
from .repetition_checker import detect_near_duplicate_sentences, detect_phrase_repetition, detect_sentence_repetition, extract_sentences
from .title_quality import validate_title_quality


def detect_ai_writing_patterns(content: str) -> Dict[str, Any]:
    """BLACKLIST_PATTERNS 기준으로 AI 투 패턴을 감지한다.

    Returns:
        {
            "score": 0-100,   # 패턴 밀도 기반 점수 (높을수록 AI 투)
            "detected": [...], # 감지된 패턴 목록
            "passed": bool,   # score <= 30 이면 True
        }
    """
    from agents.common.natural_tone import BLACKLIST_PATTERNS

    ai_categories = [
        'structural_enumeration',
        'excessive_emphasis',
        'symmetric_overuse',
        'formal_closing',
    ]

    plain = re.sub(r'<[^>]+>', '', content)
    word_count = max(len(plain), 1)

    detected: list[str] = []
    hit_count = 0

    for cat in ai_categories:
        patterns = BLACKLIST_PATTERNS.get(cat, [])
        for p in patterns:
            if p in plain:
                detected.append(p)
                hit_count += plain.count(p)

    # 1000자당 히트 수 기준으로 0-100 점수
    score = min(100, int(hit_count / word_count * 1000 * 10))

    return {
        "score": score,
        "detected": detected,
        "passed": score <= 30,
    }


def run_heuristic_validation_sync(
    content: str,
    status: str,
    title: str = "",
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    options = options or {}
    fact_allowlist = options.get("factAllowlist")

    issues: list[str] = []

    repetition_result = detect_sentence_repetition(content)
    if not repetition_result.get("passed", True):
        issues.append(f"⚠️ 문장 반복 감지: {', '.join(repetition_result.get('repeatedSentences', []))}")

    phrase_result = detect_phrase_repetition(content)
    if not phrase_result.get("passed", True):
        issues.append(f"⚠️ 구문 반복 감지: {', '.join(phrase_result.get('repeatedPhrases', []))}")

    near_dup_result = detect_near_duplicate_sentences(content)
    if not near_dup_result.get("passed", True):
        summary = ", ".join(
            f"\"{pair['a']}\" ≈ \"{pair['b']}\" ({pair['similarity']}%)"
            for pair in (near_dup_result.get("similarPairs") or [])[:3]
        )
        issues.append(f"⚠️ 유사 문장 감지: {summary}")

    election_result = {"passed": True, "violations": [], "items": []}

    fact_check_result = None
    if fact_allowlist:
        content_check = find_unsupported_numeric_tokens(content, fact_allowlist)
        title_check = find_unsupported_numeric_tokens(title, fact_allowlist) if title else {"passed": True, "unsupported": []}
        fact_check_result = {"content": content_check, "title": title_check}

    ai_writing_result = detect_ai_writing_patterns(content)
    if not ai_writing_result.get("passed", True):
        detected = ", ".join(ai_writing_result.get("detected", [])[:5])
        issues.append(f"⚠️ AI 투 표현 감지: {detected}")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "details": {
            "repetition": repetition_result,
            "electionLaw": election_result,
            "factCheck": fact_check_result,
            "ai_writing": ai_writing_result,
        },
    }


async def run_heuristic_validation(
    content: str,
    status: str,
    title: str = "",
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    options = options or {}
    user_keywords = list(options.get("userKeywords") or [])
    fact_allowlist = options.get("factAllowlist")

    issues: list[str] = []

    repetition_result = detect_sentence_repetition(content)
    if not repetition_result.get("passed", True):
        issues.append(f"⚠️ 문장 반복 감지: {', '.join(repetition_result.get('repeatedSentences', []))}")

    phrase_result = detect_phrase_repetition(content)
    if not phrase_result.get("passed", True):
        issues.append(f"⚠️ 구문 반복 감지: {', '.join(phrase_result.get('repeatedPhrases', []))}")

    near_dup_result = detect_near_duplicate_sentences(content)
    if not near_dup_result.get("passed", True):
        summary = ", ".join(
            f"\"{pair['a']}\" ≈ \"{pair['b']}\" ({pair['similarity']}%)"
            for pair in (near_dup_result.get("similarPairs") or [])[:3]
        )
        issues.append(f"⚠️ 유사 문장 감지: {summary}")

    election_result = {"passed": True, "violations": [], "items": []}

    title_result = validate_title_quality(
        title,
        user_keywords=user_keywords,
        content=content,
        options={"strictFacts": bool(fact_allowlist)},
    )
    if not title_result.get("passed", True):
        blocking_title_issues = [
            issue.get("description")
            for issue in (title_result.get("issues") or [])
            if issue.get("severity") in {"critical", "high"}
        ]
        if blocking_title_issues:
            issues.append(f"⚠️ 제목 품질 문제: {', '.join(blocking_title_issues)}")

    fact_check_result = None
    if fact_allowlist:
        content_check = find_unsupported_numeric_tokens(content, fact_allowlist)
        title_check = find_unsupported_numeric_tokens(title, fact_allowlist) if title else {"passed": True, "unsupported": []}
        fact_check_result = {"content": content_check, "title": title_check}

    ai_writing_result = detect_ai_writing_patterns(content)
    if not ai_writing_result.get("passed", True):
        detected = ", ".join(ai_writing_result.get("detected", [])[:5])
        issues.append(f"⚠️ AI 투 표현 감지: {detected}")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "details": {
            "repetition": repetition_result,
            "electionLaw": election_result,
            "titleQuality": title_result,
            "factCheck": fact_check_result,
            "ai_writing": ai_writing_result,
        },
    }


# ============================================================================
# 초당적 협력 / 핵심 문구 / 비판 대상 검증
# ============================================================================


BIPARTISAN_FORBIDDEN_PHRASES = [
    "정신을 이어받아",
    "뜻을 받들어",
    "배워야 합니다",
    "배울 점",
    "깊은 울림",
    "용기에 박수",
    "귀감이 됩니다",
    "본받아야",
    "존경합니다",
    "멘토",
    "스승",
    "깊은 감명",
    "우리보다 낫다",
    "우리보다 훨씬 낫다",
    "우리는 저렇게 못한다",
    "정책이 100% 맞다",
    "전적으로 동의한다",
    "완전히 옳다",
    "정치인 중 최고",
    "유일하게 믿을 수 있다",
    "가장 훌륭하다",
    "개인적으로 좋아한다",
    "헌신적인 노력",
    "헌신적인 모습",
]


def detect_bipartisan_forbidden_phrases(content: str) -> Dict[str, Any]:
    violations: list[str] = []
    corrected = content or ""

    for phrase in BIPARTISAN_FORBIDDEN_PHRASES:
        if phrase not in corrected:
            continue
        violations.append(phrase)
        if phrase == "귀감이 됩니다":
            corrected = corrected.replace(phrase, "주목할 만합니다")
        elif phrase == "배워야 합니다":
            corrected = corrected.replace(phrase, "참고할 수 있습니다")
        elif phrase == "깊은 감명":
            corrected = corrected.replace(phrase, "관심")
        elif "헌신적인" in phrase:
            corrected = corrected.replace(phrase, "꾸준한 노력")
        else:
            corrected = corrected.replace(phrase, "")

    corrected = re.sub(r"\s+", " ", corrected)
    corrected = re.sub(r"\s+\.", ".", corrected).strip()
    return {"hasForbidden": len(violations) > 0, "violations": violations, "correctedContent": corrected}


def calculate_praise_proportion(content: str, rival_names: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    rival_names = list(rival_names or [])
    if not rival_names:
        return {"percentage": 0, "exceedsLimit": False, "rivalMentions": 0}

    sentences = extract_sentences(content or "")
    rival_mention_sentences = 0
    for sentence in sentences:
        if any(name in sentence for name in rival_names):
            rival_mention_sentences += 1

    percentage = round((rival_mention_sentences / len(sentences)) * 100) if sentences else 0
    return {
        "percentage": percentage,
        "exceedsLimit": percentage > 15,
        "rivalMentions": rival_mention_sentences,
        "totalSentences": len(sentences),
    }


def validate_bipartisan_praise(content: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    options = options or {}
    rival_names = list(options.get("rivalNames") or [])
    category = str(options.get("category") or "")

    if ("bipartisan" not in category) and ("초당적" not in category):
        return {"passed": True, "issues": [], "correctedContent": content}

    issues: list[str] = []
    forbidden_result = detect_bipartisan_forbidden_phrases(content or "")
    if forbidden_result["hasForbidden"]:
        issues.append(
            f"⚠️ 초당적 협력 금지 표현 감지 및 자동 수정: {', '.join(forbidden_result['violations'])}"
        )

    proportion_result = calculate_praise_proportion(forbidden_result["correctedContent"], rival_names)
    if proportion_result.get("exceedsLimit"):
        issues.append(
            f"⚠️ 경쟁자 칭찬 비중 초과: {proportion_result['percentage']}% "
            f"({proportion_result['rivalMentions']}/{proportion_result['totalSentences']} 문장) - 권장 15% 이하"
        )

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "correctedContent": forbidden_result["correctedContent"],
        "details": {"forbiddenPhrases": forbidden_result, "praiseProportion": proportion_result},
    }


def validate_key_phrase_inclusion(content: str, required_phrases: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    required_phrases = list(required_phrases or [])
    if not content or not required_phrases:
        return {"passed": True, "missing": [], "included": [], "details": {}}

    plain_content = _strip_html(content)
    included: list[Dict[str, str]] = []
    missing: list[str] = []
    details: Dict[str, Any] = {}

    for phrase in required_phrases:
        if not phrase or len(phrase) < 5:
            continue
        exact_match = phrase in plain_content
        core_words = [
            word
            for word in re.split(r"\s+", re.sub(r"[.?!,~]", "", phrase))
            if len(word) >= 4 and not re.match(r"^(있습니다|없습니다|합니다|입니다|것입니다|아닙니다)$", word)
        ]
        core_word_matches = [word for word in core_words if word in plain_content]
        paraphrase_match = bool(core_words) and len(core_word_matches) >= (len(core_words) + 1) // 2

        details[phrase] = {
            "exactMatch": exact_match,
            "paraphraseMatch": paraphrase_match,
            "coreWords": core_words,
            "coreWordMatches": core_word_matches,
            "included": exact_match or paraphrase_match,
        }

        if exact_match or paraphrase_match:
            included.append({"phrase": phrase, "matchType": "exact" if exact_match else "paraphrase"})
        else:
            missing.append(phrase)

    has_exact_match = any(item.get("matchType") == "exact" for item in included)
    all_included = len(missing) == 0
    passed = all_included and (len(required_phrases) <= 1 or has_exact_match)

    return {
        "passed": passed,
        "missing": missing,
        "included": included,
        "hasExactMatch": has_exact_match,
        "details": details,
        "message": (
            None
            if passed
            else (
                f"핵심 문구 누락: {', '.join(f'\"{item[:30]}...\"' for item in missing)}"
                if missing
                else "원문 그대로 인용된 문구가 없습니다. 최소 1개는 원문 인용이 필요합니다."
            )
        ),
    }


def validate_criticism_target(content: str, responsibility_target: str) -> Dict[str, Any]:
    if not content or not responsibility_target:
        return {"passed": True, "targetMentioned": False, "count": 0}

    plain_content = re.sub(r"<[^>]*>", " ", content)
    target_parts = [part for part in re.split(r"\s+", responsibility_target) if part]
    target_name = target_parts[0] if target_parts else responsibility_target
    escaped_name = re.escape(target_name)

    matches = re.findall(escaped_name, plain_content)
    count = len(matches)
    count_passed = count >= 2

    intent_reversal_patterns = [
        re.compile(rf"{escaped_name}[^.]*(?:협력|존중|함께|노력|인정|공로|성과)"),
        re.compile(rf"(?:협력|존중|함께)하여[^.]*{escaped_name}"),
        re.compile(rf"{escaped_name}[^.]*(?:의\s*노력|과\s*협력|과\s*함께|을\s*존중)"),
    ]

    intent_reversal_count = 0
    intent_reversal_matches: list[str] = []
    for pattern in intent_reversal_patterns:
        detected = pattern.findall(plain_content)
        intent_reversal_count += len(detected)
        intent_reversal_matches.extend(detected)

    criticism_patterns = [
        re.compile(rf"{escaped_name}[^.]*(?:역부족|한계|문제|책임|비판|실패|부족)"),
        re.compile(rf"(?:역부족|한계|문제|책임|비판|실패|부족)[^.]*{escaped_name}"),
    ]
    criticism_context_count = sum(len(pattern.findall(plain_content)) for pattern in criticism_patterns)
    has_intent_reversal = intent_reversal_count > 0 and intent_reversal_count > criticism_context_count
    passed = count_passed and (not has_intent_reversal)

    message = None
    if not count_passed:
        message = f"비판 대상 \"{target_name}\" 언급 부족 (현재 {count}회, 최소 2회 필요)"
    elif has_intent_reversal:
        message = (
            f"🔴 의도 역전 감지: 비판 대상 \"{target_name}\"이(가) 긍정적 맥락(협력/존중/함께)으로 언급됨. "
            f"원본의 비판적 논조를 유지하세요. [감지된 표현: {', '.join(intent_reversal_matches[:2])}]"
        )

    return {
        "passed": passed,
        "targetMentioned": count > 0,
        "count": count,
        "targetName": target_name,
        "hasIntentReversal": has_intent_reversal,
        "intentReversalCount": intent_reversal_count,
        "criticismContextCount": criticism_context_count,
        "message": message,
    }
