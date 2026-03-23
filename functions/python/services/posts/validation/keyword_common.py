"""??? ?? ??? ?? ???."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from agents.common.editorial import KEYWORD_SPEC
from agents.common.role_keyword_policy import ROLE_KEYWORD_PATTERN as COMMON_ROLE_KEYWORD_PATTERN, ROLE_SURFACE_PATTERN as COMMON_ROLE_SURFACE_PATTERN

ROLE_KEYWORD_PATTERN = COMMON_ROLE_KEYWORD_PATTERN
ROLE_SURFACE_PATTERN = COMMON_ROLE_SURFACE_PATTERN
KEYWORD_REFERENCE_MARKERS: tuple[str, ...] = ("검색어", "키워드", "표현", "문구")
KEYWORD_REFERENCE_VERBS: tuple[str, ...] = ("거론", "언급", "주목")
LOW_SIGNAL_KEYWORD_TOKENS: tuple[str, ...] = (
    "관심",
    "이슈",
    "흐름",
    "행보",
    "경쟁",
    "비교",
    "우위",
    "약진",
    "경쟁력",
    "차별화",
    "가능성",
    "지지",
    "차별점",
    "가상대결",
    "양자대결",
    "대결",
    "검색어",
    "키워드",
    "표현",
    "문구",
    "거론",
    "언급",
    "주목",
    "후보군",
)
ROLE_FALLBACK_LABELS: tuple[tuple[str, str], ...] = (
    ("도지사", "상대 지사"),
    ("지사", "상대 지사"),
    ("시장", "상대 시장"),
    ("위원장", "상대 위원장"),
    ("대표", "상대 대표"),
    ("장관", "상대 장관"),
)
KEYWORD_INJECTION_RISK_PERSON_ROLE_PATTERN = re.compile(
    r"[가-힣]{2,8}\s*(?:현\s*|전\s*)?(?:국회의원|의원|도지사|지사|시장|위원장|대표|장관|예비후보|후보)",
    re.IGNORECASE,
)
KEYWORD_INJECTION_RISK_NUMERIC_TOKEN_PATTERN = re.compile(
    r"\d{1,4}(?:\.\d+)?(?:%|명|일|월|년)?",
    re.IGNORECASE,
)
KEYWORD_INJECTION_RISK_MARKERS: tuple[str, ...] = (
    "후보군",
    "적합도",
    "가상대결",
    "양자대결",
    "대결",
    "오차 범위",
)
PERSON_ROLE_REDUCTION_PATTERN_TEMPLATE = (
    r"{keyword}\s*(?P<modifier>(?:현|전)\s*)?"
    r"(?P<role>(?:[가-힣]{{1,8}}도지사|도지사|지사|국회의원|[가-힣]{{1,8}}시장|시장|의원|위원장|대표|장관|예비후보|후보))"
)

def count_keyword_occurrences(content: str, keyword: str) -> int:
    clean_content = re.sub(r"<[^>]*>", "", content or "")
    escaped = re.escape(keyword or "")
    if not escaped:
        return 0
    return len(re.findall(escaped, clean_content))


def build_keyword_variants(keyword: str) -> List[str]:
    trimmed = str(keyword or "").strip()
    if not trimmed:
        return []
    parts = [part for part in re.split(r"\s+", trimmed) if part]
    variants: list[str] = []
    if len(parts) >= 2:
        first = parts[0]
        rest = " ".join(parts[1:])
        variants.append(f"{first}의 {rest}")
        variants.append(f"{rest} {first}")
    deduped: list[str] = []
    seen: set[str] = set()
    for item in variants:
        if item and item != trimmed and item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def count_keyword_coverage(content: str, keyword: str) -> int:
    if not keyword:
        return 0
    keywords = [keyword, *build_keyword_variants(keyword)]
    return sum(count_keyword_occurrences(content, item) for item in keywords)


def _count_user_keyword_exact_non_overlap(content: str, user_keywords: Sequence[str]) -> Dict[str, int]:
    clean_content = re.sub(r"<[^>]*>", "", str(content or ""))
    normalized_keywords = [str(item or "").strip() for item in (user_keywords or []) if str(item or "").strip()]
    if not clean_content or not normalized_keywords:
        return {}

    counts: Dict[str, int] = {keyword: 0 for keyword in normalized_keywords}
    occupied_spans: list[tuple[int, int]] = []
    ordered_keywords = sorted(
        list(enumerate(normalized_keywords)),
        key=lambda item: (-len(item[1]), item[0]),
    )

    def _is_overlapping(start: int, end: int) -> bool:
        for occupied_start, occupied_end in occupied_spans:
            if start < occupied_end and occupied_start < end:
                return True
        return False

    for _, keyword in ordered_keywords:
        escaped = re.escape(keyword)
        if not escaped:
            continue
        for match in re.finditer(escaped, clean_content):
            start, end = match.span()
            if start >= end or _is_overlapping(start, end):
                continue
            occupied_spans.append((start, end))
            counts[keyword] = int(counts.get(keyword) or 0) + 1

    return counts


def _normalize_user_keyword(keyword: Any) -> str:
    return re.sub(r"\s+", " ", str(keyword or "")).strip()


def _keyword_tokens(keyword: Any) -> tuple[str, ...]:
    normalized = _normalize_user_keyword(keyword)
    if not normalized:
        return ()
    return tuple(part for part in normalized.split(" ") if part)


def _split_keyword_sentence_units(text: Any) -> list[str]:
    normalized = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", str(text or ""))).strip()
    if not normalized:
        return []
    units = [
        str(part or "").strip()
        for part in re.split(r"(?<=[.!?。])\s+|\n+", normalized)
        if str(part or "").strip()
    ]
    return units or [normalized]


def count_keyword_sentence_reflections(text: Any, keyword: Any) -> int:
    tokens = tuple(re.sub(r"\s+", "", token) for token in _keyword_tokens(keyword) if token)
    if len(tokens) < 2:
        return 0

    total = 0
    for unit in _split_keyword_sentence_units(text):
        compact_unit = re.sub(r"\s+", "", unit)
        if compact_unit and all(token in compact_unit for token in tokens):
            total += 1
    return total


def _contains_token_subsequence(longer: Sequence[str], shorter: Sequence[str]) -> bool:
    if not longer or not shorter or len(shorter) >= len(longer):
        return False
    window = len(shorter)
    for start in range(len(longer) - window + 1):
        if tuple(longer[start : start + window]) == tuple(shorter):
            return True
    return False


def find_shadowed_user_keywords(user_keywords: Sequence[str] | None) -> Dict[str, List[str]]:
    normalized_keywords: list[str] = []
    seen: set[str] = set()
    for item in user_keywords or []:
        keyword = _normalize_user_keyword(item)
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        normalized_keywords.append(keyword)

    shadowed: Dict[str, List[str]] = {}
    token_cache = {keyword: _keyword_tokens(keyword) for keyword in normalized_keywords}
    for keyword in normalized_keywords:
        keyword_tokens = token_cache.get(keyword) or ()
        if not keyword_tokens:
            continue
        for other in normalized_keywords:
            if keyword == other:
                continue
            other_tokens = token_cache.get(other) or ()
            if not other_tokens:
                continue
            if _contains_token_subsequence(other_tokens, keyword_tokens):
                matches = shadowed.setdefault(keyword, [])
                if other not in matches:
                    matches.append(other)
    return shadowed


def _count_keyword_occurrences_in_h2(content: str, keyword: str) -> int:
    if not content or not keyword:
        return 0
    total = 0
    for match in re.finditer(r"<h2\b[^>]*>([\s\S]*?)</h2\s*>", str(content), re.IGNORECASE):
        inner = str(match.group(1) or "")
        total += count_keyword_occurrences(inner, keyword)
    return total


def _count_keyword_occurrences_in_paragraphs(content: str, keyword: str) -> int:
    if not content or not keyword:
        return 0
    paragraphs = list(re.finditer(r"<p\b[^>]*>([\s\S]*?)</p\s*>", str(content), re.IGNORECASE))
    if not paragraphs:
        return count_keyword_occurrences(str(content), keyword)
    total = 0
    for match in paragraphs:
        inner = str(match.group(1) or "")
        total += count_keyword_occurrences(inner, keyword)
    return total


def _count_user_keyword_exact_non_overlap_in_body(
    content: str, user_keywords: Sequence[str]
) -> Dict[str, int]:
    """<p> 태그 본문만 대상으로 비중첩 카운팅.

    긴 키워드가 짧은 키워드의 위치를 선점하므로
    'A B'와 'A'가 공존할 때 'A B' 위치는 'A' 카운트에서 제외된다.
    """
    paragraphs = list(re.finditer(r"<p\b[^>]*>([\s\S]*?)</p\s*>", str(content or ""), re.IGNORECASE))
    if not paragraphs:
        body_text = re.sub(r"<[^>]*>", " ", str(content or ""))
    else:
        body_text = " ".join(re.sub(r"<[^>]*>", " ", m.group(1) or "") for m in paragraphs)
    return _count_user_keyword_exact_non_overlap(body_text, user_keywords)


def _keyword_user_threshold(keyword_count: int) -> tuple[int, int]:
    if keyword_count >= 2:
        user_min_count = int(KEYWORD_SPEC['perKeywordMin'])
        user_max_count = int(KEYWORD_SPEC['perKeywordMax'])
    else:
        user_min_count = int(KEYWORD_SPEC['singleKeywordMin'])
        user_max_count = int(KEYWORD_SPEC['singleKeywordMax'])
    return user_min_count, user_max_count


def _parse_keyword_sections(content: str) -> List[Dict[str, Any]]:
    sections: list[Dict[str, Any]] = []
    h2_matches = list(re.finditer(r"<h2[^>]*>[\s\S]*?<\/h2>", content or "", re.IGNORECASE))

    if not h2_matches:
        return [
            {
                "type": "single",
                "startIndex": 0,
                "endIndex": len(content or ""),
                "content": content or "",
            }
        ]

    first_h2_start = h2_matches[0].start()
    if first_h2_start > 0:
        sections.append(
            {
                "type": "intro",
                "startIndex": 0,
                "endIndex": first_h2_start,
                "content": (content or "")[:first_h2_start],
            }
        )

    for idx, match in enumerate(h2_matches):
        start_index = match.start()
        end_index = h2_matches[idx + 1].start() if idx < len(h2_matches) - 1 else len(content or "")
        section_type = "conclusion" if idx == len(h2_matches) - 1 else f"body{idx + 1}"
        sections.append(
            {
                "type": section_type,
                "startIndex": start_index,
                "endIndex": end_index,
                "content": (content or "")[start_index:end_index],
            }
        )

    return sections


def _section_priority(section_type: str) -> int:
    if section_type.startswith("body"):
        return 0
    if section_type == "conclusion":
        return 1
    if section_type == "intro":
        return 2
    return 3


