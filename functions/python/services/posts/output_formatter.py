"""Final output formatting utilities for Python post generation pipeline.

This module ports the last-mile output shaping logic that was previously done
in Node.js (`functions/handlers/posts.js` + `content-processor.js`) so Python
pipeline results can be returned as final-ready drafts.
"""

from __future__ import annotations

import re
from typing import Any, Dict


SIGNATURE_MARKERS = [
    "부산의 준비된 신상품",
    "부산경제는 이재성",
]

DIAGNOSTIC_TAIL_MARKERS = [
    "불확실성과 추가 확인 필요 사항",
    "불확실성과 추가 확인 필요",
    "불확실성 및 추가 확인 필요",
    "불확실성",
    "추가 확인 필요 사항",
    "추가 확인 필요",
    "추가 확인",
    "주석",
    "진단 요약",
]

CLOSING_MARKERS = [
    "감사합니다",
    "감사드립니다",
    "고맙습니다",
    "부탁드립니다",
    "드림",
]

CLOSING_PARAGRAPH_RE = re.compile(
    r"<p[^>]*>[^<]*(감사합니다|감사드립니다|고맙습니다|부탁드립니다|드림)[^<]*</p>",
    re.IGNORECASE,
)


def _find_last_index(text: str, markers: list[str]) -> int:
    max_index = -1
    for marker in markers:
        idx = text.rfind(marker)
        if idx > max_index:
            max_index = idx
    return max_index


def _find_first_index(text: str, markers: list[str], start_index: int = 0) -> int:
    found = -1
    for marker in markers:
        idx = text.find(marker, start_index)
        if idx != -1 and (found == -1 or idx < found):
            found = idx
    return found


def _trim_from_index(text: str, cut_index: int) -> str:
    if cut_index < 0:
        return text
    paragraph_start = text.rfind("<p", 0, cut_index)
    if paragraph_start != -1:
        tag_end = text.find(">", paragraph_start)
        if tag_end != -1 and tag_end < cut_index:
            return text[:paragraph_start].strip()
    return text[:cut_index].strip()


def strip_generated_slogan(content: str, slogan: str = "") -> str:
    if not content:
        return content

    slogan_lines = [
        line.strip()
        for line in str(slogan or "").splitlines()
        if line and line.strip()
    ]
    markers = list(dict.fromkeys([*SIGNATURE_MARKERS, *slogan_lines]))
    if not markers:
        return content

    escaped = "|".join(re.escape(m) for m in markers)
    paragraph_re = re.compile(rf"<p[^>]*>[^<]*(?:{escaped})[^<]*</p>\s*", re.IGNORECASE)
    line_re = re.compile(rf"(?:^|\n)\s*(?:{escaped})\s*(?=\n|$)", re.IGNORECASE)

    updated = paragraph_re.sub("", content)
    updated = line_re.sub("\n", updated)
    updated = re.sub(r"\n{3,}", "\n\n", updated)
    return updated.strip()


def trim_trailing_diagnostics(content: str, allow_diagnostic_tail: bool = False) -> str:
    if not content:
        return content

    signature_index = _find_last_index(content, SIGNATURE_MARKERS)
    if signature_index != -1:
        tail = content[signature_index:]
        close_match = re.search(r"</p>|</div>|</section>|</article>", tail, re.IGNORECASE)
        if close_match:
            cut_index = signature_index + close_match.end()
        else:
            line_break = re.search(r"[\r\n]", tail)
            cut_index = len(content) if not line_break else signature_index + line_break.start()
        return content[:cut_index].strip()

    if not allow_diagnostic_tail:
        start_index = int(len(content) * 0.65)
        tail_index = _find_first_index(content, DIAGNOSTIC_TAIL_MARKERS, start_index)
        if tail_index != -1:
            return _trim_from_index(content, tail_index)

    return content


def trim_after_closing(content: str) -> str:
    if not content:
        return content

    last_match = None
    for match in CLOSING_PARAGRAPH_RE.finditer(content):
        last_match = match
    if last_match is not None:
        return content[: last_match.end()].strip()

    last_index = -1
    last_marker = ""
    for marker in CLOSING_MARKERS:
        idx = content.rfind(marker)
        if idx > last_index:
            last_index = idx
            last_marker = marker

    if last_index != -1:
        end_index = last_index + len(last_marker)
        line_end = content.find("\n", end_index)
        cut_index = end_index if line_end == -1 else line_end
        return content[:cut_index].strip()

    return content


def insert_donation_info(content: str, info: str) -> str:
    if not content or not info:
        return content
    html = (
        '<p style="text-align: center; font-size: 0.9em; color: #666; margin: 1em 0;">'
        f'{str(info).strip().replace("\n", "<br>")}'
        "</p>"
    )
    trimmed = content.strip()
    return f"{trimmed}\n{html}" if trimmed else html


def insert_slogan(content: str, slogan: str) -> str:
    if not content or not slogan:
        return content
    html = (
        '<p style="text-align: center; font-weight: bold; margin: 1.5em 0;">'
        f'{str(slogan).strip().replace("\n", "<br>")}'
        "</p>"
    )
    trimmed = content.strip()
    return f"{trimmed}\n{html}" if trimmed else html


def count_without_space(content: str) -> int:
    plain = re.sub(r"<[^>]*>", "", str(content or ""))
    plain = re.sub(r"\s", "", plain)
    return len(plain)


def build_keyword_validation(keyword_result: Dict[str, Any] | None) -> Dict[str, Dict[str, Any]]:
    details = ((keyword_result or {}).get("details") or {}).get("keywords") or {}
    if not isinstance(details, dict):
        return {}

    mapped: Dict[str, Dict[str, Any]] = {}
    for keyword, info in details.items():
        if not isinstance(info, dict):
            continue
        keyword_text = str(keyword or "").strip()
        if not keyword_text:
            continue

        expected = int(info.get("expected") or 0)
        max_count = int(info.get("max") or expected or 0)
        count = int(info.get("coverage") or info.get("count") or 0)
        is_valid = bool(info.get("valid") is True)

        if is_valid:
            status = "valid"
        elif count < expected:
            status = "insufficient"
        elif max_count > 0 and count > max_count:
            status = "spam_risk"
        else:
            status = "insufficient"

        mapped[keyword_text] = {
            "count": count,
            "expected": expected,
            "max": max_count,
            "status": status,
            "type": str(info.get("type") or ""),
        }

    return mapped


def finalize_output(
    content: str,
    *,
    slogan: str = "",
    slogan_enabled: bool = False,
    donation_info: str = "",
    donation_enabled: bool = False,
    allow_diagnostic_tail: bool = False,
    keyword_result: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    updated = str(content or "")

    # Remove accidental slogan-like tail first, then trim non-content artifacts.
    updated = strip_generated_slogan(updated, slogan if slogan_enabled else "")
    updated = trim_trailing_diagnostics(updated, allow_diagnostic_tail=allow_diagnostic_tail)
    updated = trim_after_closing(updated)

    # Keep wordCount parity with previous JS behavior: count before appending
    # donation/slogan blocks.
    word_count = count_without_space(updated)

    if donation_enabled and str(donation_info or "").strip():
        updated = insert_donation_info(updated, donation_info)
    if slogan_enabled and str(slogan or "").strip():
        updated = insert_slogan(updated, slogan)

    return {
        "content": updated,
        "wordCount": word_count,
        "keywordValidation": build_keyword_validation(keyword_result),
    }


__all__ = [
    "strip_generated_slogan",
    "trim_trailing_diagnostics",
    "trim_after_closing",
    "insert_donation_info",
    "insert_slogan",
    "count_without_space",
    "build_keyword_validation",
    "finalize_output",
]

