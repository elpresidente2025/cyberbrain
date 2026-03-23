"""??? ?? ??/?? ???."""

from __future__ import annotations

import re
from typing import List

from ..keyword_insertion_policy import (
    LOCATION_CONTEXT_TOKENS,
    UNSAFE_LOCATION_ATTACH_TOKENS,
    UNSAFE_LOCATION_CONTEXT_TOKENS,
    is_greeting_sentence as _policy_is_greeting_sentence,
    is_location_context_text as _policy_is_location_context_text,
    is_terminal_sentence as _policy_is_terminal_sentence,
    is_unsafe_location_context as _policy_is_unsafe_location_context,
    normalize_plain as _policy_normalize_plain,
)

from ._shared import _strip_html
from .keyword_common import (
    KEYWORD_INJECTION_RISK_MARKERS,
    KEYWORD_INJECTION_RISK_NUMERIC_TOKEN_PATTERN,
    KEYWORD_INJECTION_RISK_PERSON_ROLE_PATTERN,
    count_keyword_occurrences,
)

def _is_location_keyword(keyword: str) -> bool:
    normalized = str(keyword or "").strip()
    if not normalized:
        return False
    location_tokens = (
        "영광도서",
        "도서관",
        "광장",
        "센터",
        "공원",
        "시청",
        "구청",
        "동",
    )
    return any(token in normalized for token in location_tokens)


LOCATION_EVENT_CONTEXT_TOKENS = LOCATION_CONTEXT_TOKENS
LOCATION_UNSAFE_CONTEXT_TOKENS = UNSAFE_LOCATION_CONTEXT_TOKENS
LOCATION_UNSAFE_ATTACH_TOKENS = UNSAFE_LOCATION_ATTACH_TOKENS


def _is_event_context_text(text: str, keyword: str = "") -> bool:
    return _policy_is_location_context_text(text, keyword=keyword)


def _is_unsafe_location_context(text: str) -> bool:
    return _policy_is_unsafe_location_context(text)


def _is_non_editable_sentence(text: str) -> bool:
    normalized = _policy_normalize_plain(text)
    if not normalized:
        return True
    if _policy_is_greeting_sentence(normalized):
        return True
    if _policy_is_terminal_sentence(normalized):
        return True
    return False


def _is_keyword_injection_risky_paragraph(text: str) -> bool:
    plain = re.sub(r"\s+", " ", _strip_html(str(text or ""))).strip()
    if not plain:
        return True
    if re.search(r"\d+\.\s+\d", plain):
        return True
    if "의 입니다" in plain or "상대장" in plain:
        return True

    numeric_tokens = KEYWORD_INJECTION_RISK_NUMERIC_TOKEN_PATTERN.findall(plain)
    person_role_tokens = KEYWORD_INJECTION_RISK_PERSON_ROLE_PATTERN.findall(plain)
    if len(numeric_tokens) >= 3 and len(person_role_tokens) >= 2:
        return True
    if (
        len(numeric_tokens) >= 2
        and len(person_role_tokens) >= 1
        and any(marker in plain for marker in KEYWORD_INJECTION_RISK_MARKERS)
    ):
        return True
    return False


def _is_unnatural_location_phrase(text: str, keyword: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    normalized_keyword = str(keyword or "").strip()
    if not normalized or not normalized_keyword or not _is_location_keyword(normalized_keyword):
        return False
    if _is_event_context_text(normalized, keyword=normalized_keyword):
        return False

    token_pattern = "|".join(re.escape(token) for token in LOCATION_UNSAFE_ATTACH_TOKENS)
    around_kw = re.compile(
        rf"(?:{re.escape(normalized_keyword)}\s*(?:{token_pattern})|(?:{token_pattern})\s*{re.escape(normalized_keyword)})",
        re.IGNORECASE,
    )
    return bool(around_kw.search(normalized))


def _try_contextual_location_replacement(section_html: str, keyword: str) -> tuple[str, bool]:
    raw_section = str(section_html or "")
    normalized_keyword = str(keyword or "").strip()
    if not raw_section or not normalized_keyword:
        return raw_section, False

    plain_section = _policy_normalize_plain(raw_section)
    if not _is_event_context_text(plain_section, keyword=normalized_keyword):
        return raw_section, False

    before_count = count_keyword_occurrences(raw_section, normalized_keyword)
    area_match = re.match(r"(서면|부산)\s*", normalized_keyword)
    area = area_match.group(1) if area_match else ""

    substitutions: List[tuple[str, str]] = []
    if area:
        substitutions.extend(
            [
                (rf"{re.escape(area)}\s*영광도서\s*현장에서", f"{normalized_keyword} 현장에서"),
                (rf"{re.escape(area)}\s*영광도서\s*에서", f"{normalized_keyword}에서"),
                (rf"{re.escape(area)}\s*영광도서", normalized_keyword),
            ]
        )
    substitutions.extend(
        [
            (r"영광도서\s*현장에서", f"{normalized_keyword} 현장에서"),
            (r"영광도서\s*에서", f"{normalized_keyword}에서"),
            (r"영광도서", normalized_keyword),
        ]
    )

    paragraph_matches = list(re.finditer(r"<p\b[^>]*>([\s\S]*?)</p\s*>", raw_section, re.IGNORECASE))
    if not paragraph_matches:
        return raw_section, False

    for paragraph_match in paragraph_matches:
        paragraph_inner = str(paragraph_match.group(1) or "")
        paragraph_plain = _policy_normalize_plain(paragraph_inner)
        if not paragraph_plain:
            continue
        if not _is_event_context_text(paragraph_plain, keyword=normalized_keyword):
            continue
        if _is_unsafe_location_context(paragraph_plain):
            continue
        if _is_non_editable_sentence(paragraph_plain):
            continue

        for pattern, replacement in substitutions:
            updated_inner, changed = re.subn(
                pattern,
                replacement,
                paragraph_inner,
                count=1,
                flags=re.IGNORECASE,
            )
            if changed <= 0:
                continue
            candidate = (
                raw_section[: paragraph_match.start(1)]
                + updated_inner
                + raw_section[paragraph_match.end(1) :]
            )
            if _is_unnatural_location_phrase(candidate, normalized_keyword):
                continue
            after_count = count_keyword_occurrences(candidate, normalized_keyword)
            if after_count > before_count:
                return candidate, True

    return raw_section, False
