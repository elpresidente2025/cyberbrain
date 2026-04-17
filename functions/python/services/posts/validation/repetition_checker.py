"""??/?? ?? ??."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from ._shared import _strip_html

ALLOWED_ENDINGS: List[re.Pattern[str]] = [
    re.compile(r"입니다\.?$"),
    re.compile(r"습니다\.?$"),
    re.compile(r"됩니다\.?$"),
    re.compile(r"했습니다\.?$"),
    re.compile(r"되었습니다\.?$"),
    re.compile(r"였습니다\.?$"),
    re.compile(r"었습니다\.?$"),
    re.compile(r"해야\s*합니다\.?$"),
    re.compile(r"되어야\s*합니다\.?$"),
    re.compile(r"필요합니다\.?$"),
    re.compile(r"바랍니다\.?$"),
    re.compile(r"생각합니다\.?$"),
    re.compile(r"봅니다\.?$"),
    re.compile(r"압니다\.?$"),
    re.compile(r"느낍니다\.?$"),
    re.compile(r"[까요까]\?$"),
    re.compile(r"[습읍]니까\?$"),
    re.compile(r"라고\s*합니다\.?$"),
    re.compile(r"답니다\.?$"),
]

def extract_sentences(text: str) -> List[str]:
    plain_text = _strip_html(text)
    if not plain_text:
        return []
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.?!])\s+", plain_text)
        if sentence and len(sentence.strip()) > 10
    ]


def is_allowed_ending(sentence: str) -> bool:
    return any(pattern.search(sentence or "") for pattern in ALLOWED_ENDINGS)


def _collect_bribery_violations(plain_text: str) -> List[Dict[str, Any]]:
    violations: list[Dict[str, Any]] = []
    for item in ViolationDetector.check_bribery_risk(plain_text):
        matches = item.get("matches") or []
        sentence = matches[0] if matches else ""
        violations.append(
            {
                "sentence": sentence,
                "type": "BRIBERY",
                "reason": item.get("reason") or "기부행위 금지 위반 위험",
            }
        )
    return violations


def _collect_fact_violations(plain_text: str) -> List[Dict[str, Any]]:
    violations: list[Dict[str, Any]] = []
    for item in ViolationDetector.check_fact_claims(plain_text):
        matches = item.get("matches") or item.get("claims") or []
        sentence = matches[0] if matches else ""
        severity = str(item.get("severity") or "").upper()
        violations.append(
            {
                "sentence": sentence,
                "type": "FACT_CRITICAL" if severity == "CRITICAL" else "FACT_WARNING",
                "reason": item.get("reason") or "허위사실/비방 위험",
            }
        )
    return violations


async def detect_election_law_violation_hybrid(
    content: str,
    status: str | None,
    title: str = "",
    *,
    model_name: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    """형사 위험(기부행위·허위사실·후보자비방)만 검증한다."""
    if not status:
        return {"passed": True, "violations": [], "skipped": True}

    election_stage = get_election_stage(status)
    full_text = f"{title or ''} {content or ''}"
    plain_text = _strip_html(full_text)
    violations: list[Dict[str, Any]] = []
    violations.extend(_collect_bribery_violations(plain_text))
    violations.extend(_collect_fact_violations(plain_text))

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "status": status,
        "stage": election_stage.get("name"),
        "stats": {
            "violationCount": len(violations),
        },
    }


# ============================================================================
# 휴리스틱 품질 검증
# ============================================================================


def detect_sentence_repetition(content: str) -> Dict[str, Any]:
    plain_text = _strip_html(content)
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.?!])\s+", plain_text)
        if sentence and len(sentence.strip()) > 20
    ]
    normalized = [re.sub(r"\s+", "", sentence).lower() for sentence in sentences]
    counts: Dict[str, Dict[str, Any]] = {}
    repeated_sentences: list[str] = []

    for idx, sentence in enumerate(normalized):
        if sentence not in counts:
            counts[sentence] = {"count": 0, "original": sentences[idx]}
        counts[sentence]["count"] += 1

    for value in counts.values():
        if value["count"] >= 2:
            original = str(value["original"])
            repeated_sentences.append(f"\"{original[:50]}...\" ({value['count']}회 반복)")

    return {"passed": len(repeated_sentences) == 0, "repeatedSentences": repeated_sentences}


def detect_phrase_repetition(content: str) -> Dict[str, Any]:
    plain_text = _strip_html(content)
    words = [word for word in re.split(r"\s+", plain_text) if word]
    phrase_count: Dict[str, int] = {}

    for n in range(3, 7):
        for idx in range(0, len(words) - n + 1):
            phrase = " ".join(words[idx : idx + n])
            if len(phrase) < 10:
                continue
            phrase_count[phrase] = phrase_count.get(phrase, 0) + 1

    over_limit = sorted(
        [(phrase, count) for phrase, count in phrase_count.items() if count >= 3],
        key=lambda item: len(item[0]),
        reverse=True,
    )

    covered: set[str] = set()
    repeated_phrases: list[str] = []
    raw_repeated_phrases: list[Dict[str, Any]] = []
    for phrase, count in over_limit:
        if any(existing.find(phrase) >= 0 for existing in covered):
            continue
        covered.add(phrase)
        repeated_phrases.append(f"\"{phrase[:40]}{'...' if len(phrase) > 40 else ''}\" ({count}회 반복)")
        raw_repeated_phrases.append({"phrase": phrase, "count": count})

    return {
        "passed": len(repeated_phrases) == 0,
        "repeatedPhrases": repeated_phrases,
        "rawRepeatedPhrases": raw_repeated_phrases,
    }


def _replace_repetition_tail(
    content: str,
    pattern: re.Pattern[str],
    *,
    keep: int = 2,
) -> tuple[str, int]:
    """패턴 반복이 keep회를 초과하면 뒤에서부터 변형 치환한다."""
    matches = list(pattern.finditer(content or ""))
    if len(matches) <= keep:
        return str(content or ""), 0

    working = str(content or "")
    replaced = 0
    to_replace = list(reversed(matches[keep:]))
    for idx, match in enumerate(to_replace):
        phrase = match.group(0)
        time_match = re.search(r"(오전|오후)\s*\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?", phrase)
        time_token = time_match.group(0) if time_match else "해당 시간"
        location_match = re.search(r"(서면|부산)\s*영광도서", phrase)
        location_token = location_match.group(0) if location_match else "행사 현장"
        replacement = (
            f"행사 당일 {time_token}, {location_token} 현장에서"
            if idx == 0
            else "행사 당일 현장에서"
        )
        start, end = match.span()
        working = working[:start] + replacement + working[end:]
        replaced += 1

    return working, replaced


def _replace_location_postposition_repetition(
    content: str,
    pattern: re.Pattern[str],
    *,
    keep: int = 2,
) -> tuple[str, int]:
    """장소+조사(…영광도서에서) 반복을 변형해 동일 n-gram을 줄인다."""
    matches = list(pattern.finditer(content or ""))
    if len(matches) <= keep:
        return str(content or ""), 0

    working = str(content or "")
    replaced = 0
    suffixes = ("현장에서", "행사장에서", "공간에서")
    to_replace = list(reversed(matches[keep:]))

    for idx, match in enumerate(to_replace):
        phrase = match.group(0)
        city_match = re.search(r"(서면|부산)\s*영광도서", phrase, re.IGNORECASE)
        location_token = f"{city_match.group(1)} 영광도서" if city_match else "행사 현장"
        replacement = f"{location_token} {suffixes[idx % len(suffixes)]}"
        start, end = match.span()
        working = working[:start] + replacement + working[end:]
        replaced += 1

    return working, replaced


def _replace_anchor_phrase_repetition(
    content: str,
    pattern: re.Pattern[str],
    replacements: Sequence[str],
    *,
    keep: int = 2,
) -> tuple[str, int]:
    """앵커 구문 반복이 keep회를 초과하면 뒤에서부터 유의어로 치환한다."""
    matches = list(pattern.finditer(content or ""))
    if len(matches) <= keep:
        return str(content or ""), 0

    replacement_pool = [item for item in (replacements or []) if str(item).strip()]
    if not replacement_pool:
        return str(content or ""), 0

    working = str(content or "")
    replaced = 0
    to_replace = list(reversed(matches[keep:]))
    for idx, match in enumerate(to_replace):
        replacement = replacement_pool[idx % len(replacement_pool)]
        start, end = match.span()
        working = working[:start] + replacement + working[end:]
        replaced += 1

    return working, replaced


def _dedupe_repeated_sentences_in_paragraphs(
    content: str,
    *,
    min_sentence_len: int = 20,
    keep: int = 1,
) -> tuple[str, int]:
    """문단 단위로 긴 문장 중복을 제거해 반복 게이트 실패를 완화한다."""
    raw_content = str(content or "")
    if not raw_content:
        return raw_content, 0

    seen: Dict[str, int] = {}
    removed = 0

    def replace_paragraph(match: re.Match[str]) -> str:
        nonlocal removed
        inner = str(match.group(1) or "")
        plain_inner = re.sub(r"<[^>]*>", " ", inner)
        plain_inner = re.sub(r"\s+", " ", plain_inner).strip()
        if not plain_inner:
            return ""

        sentences = [
            sentence.strip()
            for sentence in re.findall(r"[^.!?。]+[.!?。]?", plain_inner)
            if sentence and sentence.strip()
        ]
        if not sentences:
            return match.group(0)

        kept: list[str] = []
        for sentence in sentences:
            normalized = re.sub(r"\s+", " ", sentence).strip()
            if len(normalized) < min_sentence_len:
                kept.append(normalized)
                continue

            key = re.sub(r"\s+", "", normalized).lower()
            count = seen.get(key, 0)
            if count >= keep:
                removed += 1
                continue
            seen[key] = count + 1
            kept.append(normalized)

        if not kept:
            return ""
        return f"<p>{' '.join(kept).strip()}</p>"

    updated = re.sub(
        r"<p\b[^>]*>([\s\S]*?)</p\s*>",
        replace_paragraph,
        raw_content,
        flags=re.IGNORECASE,
    )
    updated = re.sub(r"\n{3,}", "\n\n", updated).strip()
    return updated, removed


def enforce_repetition_requirements(content: str) -> Dict[str, Any]:
    """반복 품질 위반을 최소 보정으로 완화한다.

    현재는 행사 일시+장소 결합 구문, 장소+조사 반복, 상투 앵커 구문을 우선적으로 줄인다.
    """
    base = str(content or "")
    working = base
    actions: list[Dict[str, Any]] = []

    event_datetime_location_pattern = re.compile(
        r"\d{1,2}\s*월\s*\d{1,2}\s*일(?:\([^)]+\))?\s*"
        r"(?:오전|오후)\s*\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?\s*,?\s*"
        r"(?:서면|부산)(?:\s*영광도서)?\s*에서",
        re.IGNORECASE,
    )
    working, replaced = _replace_repetition_tail(working, event_datetime_location_pattern, keep=2)
    if replaced > 0:
        actions.append(
            {
                "type": "event_datetime_phrase_dedupe",
                "replaced": replaced,
                "keep": 2,
            }
        )

    location_postposition_pattern = re.compile(
        r"(?:서면|부산)\s*영광도서\s*에서",
        re.IGNORECASE,
    )
    working, location_replaced = _replace_location_postposition_repetition(
        working,
        location_postposition_pattern,
        keep=2,
    )
    if location_replaced > 0:
        actions.append(
            {
                "type": "location_postposition_dedupe",
                "replaced": location_replaced,
                "keep": 2,
            }
        )

    anchor_phrase_rules = [
        {
            "name": "부산항 부두 노동자의",
            "pattern": re.compile(r"부산항\s*부두\s*노동자의", re.IGNORECASE),
            "replacements": ("부산항 노동자 가정의", "부산항 현장 노동자 집안의"),
        },
        {
            "name": "시민 여러분과 함께",
            "pattern": re.compile(r"시민\s*여러분과\s*함께", re.IGNORECASE),
            "replacements": ("시민과 함께", "여러분과 함께", "지역사회와 함께"),
        },
    ]
    for rule in anchor_phrase_rules:
        working, anchor_replaced = _replace_anchor_phrase_repetition(
            working,
            rule["pattern"],
            rule["replacements"],
            keep=2,
        )
        if anchor_replaced > 0:
            actions.append(
                {
                    "type": "anchor_phrase_dedupe",
                    "phrase": rule["name"],
                    "replaced": anchor_replaced,
                    "keep": 2,
                }
            )

    working, sentence_removed = _dedupe_repeated_sentences_in_paragraphs(
        working,
        min_sentence_len=20,
        keep=1,
    )
    if sentence_removed > 0:
        actions.append(
            {
                "type": "sentence_dedupe",
                "removed": sentence_removed,
                "keep": 1,
            }
        )

    sentence_result = detect_sentence_repetition(working)
    phrase_result = detect_phrase_repetition(working)
    near_dup_result = detect_near_duplicate_sentences(working)
    issues: list[str] = []
    if not sentence_result.get("passed", True):
        issues.append(f"⚠️ 문장 반복 감지: {', '.join(sentence_result.get('repeatedSentences', []))}")
    if not phrase_result.get("passed", True):
        issues.append(f"⚠️ 구문 반복 감지: {', '.join(phrase_result.get('repeatedPhrases', []))}")
    if not near_dup_result.get("passed", True):
        summary = ", ".join(
            f"\"{pair['a']}\" ≈ \"{pair['b']}\" ({pair['similarity']}%)"
            for pair in (near_dup_result.get("similarPairs") or [])[:3]
        )
        issues.append(f"⚠️ 유사 문장 감지: {summary}")

    return {
        "content": working,
        "edited": working != base,
        "actions": actions,
        "passed": len(issues) == 0,
        "issues": issues,
        "details": {
            "repetition": sentence_result,
            "phrase": phrase_result,
            "nearDuplicate": near_dup_result,
        },
    }


def detect_near_duplicate_sentences(content: str, threshold: float = 0.6) -> Dict[str, Any]:
    plain_text = _strip_html(content)
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.?!])\s+", plain_text)
        if sentence and len(sentence.strip()) > 25
    ]
    word_sets: list[set[str]] = []
    for sentence in sentences:
        words = [word for word in re.split(r"\s+", re.sub(r"[.?!,]", "", sentence)) if len(word) >= 2]
        word_sets.append(set(words))

    similar_pairs: list[Dict[str, Any]] = []
    for i in range(len(sentences)):
        for j in range(i + 1, len(sentences)):
            set_a = word_sets[i]
            set_b = word_sets[j]
            if len(set_a) < 3 or len(set_b) < 3:
                continue
            intersection = len(set_a.intersection(set_b))
            union = len(set_a.union(set_b))
            similarity = (intersection / union) if union else 0
            if similarity < threshold:
                continue
            if similarity >= 0.95:
                continue
            similar_pairs.append(
                {
                    "a": sentences[i][:50] + ("..." if len(sentences[i]) > 50 else ""),
                    "b": sentences[j][:50] + ("..." if len(sentences[j]) > 50 else ""),
                    "similarity": round(similarity * 100),
                }
            )

    return {"passed": len(similar_pairs) == 0, "similarPairs": similar_pairs}

