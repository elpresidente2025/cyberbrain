"""Final output formatting utilities for Python post generation pipeline.

This module ports the last-mile output shaping logic that was previously done
in Node.js (`functions/handlers/posts.js` + `content-processor.js`) so Python
pipeline results can be returned as final-ready drafts.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


DOUBLE_QUOTE_NORMALIZATION_MAP = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
    }
)


SIGNATURE_MARKERS = [
    "부산의 준비된 신상품",
    "부산경제는 이재성",
]

DONATION_MARKERS = [
    "후원 안내",
    "후원계좌",
    "예금주",
    "후원금 영수증",
    "영수증 발급 안내",
    "입금 후 성함",
    "번호로 문자",
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
GRATITUDE_CLOSING_MARKERS = (
    "감사합니다",
    "감사드립니다",
    "고맙습니다",
)

CLOSING_PARAGRAPH_RE = re.compile(
    r"<p[^>]*>[^<]*(감사합니다|감사드립니다|고맙습니다|부탁드립니다|드림)[^<]*</p>",
    re.IGNORECASE,
)
INLINE_CLOSING_MARKER_RE = re.compile(
    r"(감사합니다|감사드립니다|고맙습니다|부탁드립니다|드림)\s*([.!?…]+)?",
    re.IGNORECASE,
)

CLOSING_TRIM_MIN_TAIL_RATIO = 0.72
CLOSING_REORDER_MIN_TAIL_RATIO = 0.45
OVER_TRIM_GUARD_MIN_CHARS = 1200
OVER_TRIM_GUARD_KEEP_RATIO = 0.70
TARGET_CHAR_SOFT_UPPER_RATIO = 1.15
TARGET_CHAR_HARD_UPPER_RATIO = 1.25
TAIL_PARAGRAPH_WINDOW = 8
TAIL_DUPLICATE_SIMILARITY = 0.90

TAIL_LOW_PRIORITY_MARKERS = (
    "감사합니다",
    "감사드립니다",
    "고맙습니다",
    "많은 관심",
    "많은 참여",
    "많은 참석",
    "직접 확인",
    "직접 만나",
    "현장에서 만나",
    "소중한 발걸음",
    "초대합니다",
    "오셔서",
    "함께해 주십시오",
)

PARAGRAPH_BLOCK_RE = re.compile(r"<p\b[^>]*>[\s\S]*?</p\s*>", re.IGNORECASE)


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


def _is_tail_segment(total_len: int, start_index: int, ratio: float = CLOSING_TRIM_MIN_TAIL_RATIO) -> bool:
    if total_len <= 0:
        return False
    return start_index >= int(total_len * ratio)


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


def normalize_ascii_double_quotes(text: str) -> str:
    if not text:
        return str(text or "")
    return str(text).translate(DOUBLE_QUOTE_NORMALIZATION_MAP)


BOOK_TITLE_OPEN_WRAPPERS = "<《〈「『\"'“‘"
BOOK_TITLE_CLOSE_WRAPPERS = ">》〉」』\"'”’"
BOOK_TITLE_CANONICAL_OPEN = "『"
BOOK_TITLE_CANONICAL_CLOSE = "』"


def _strip_book_title_wrappers(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    wrapper_pairs = (
        ("<", ">"),
        ("《", "》"),
        ("〈", "〉"),
        ("「", "」"),
        ("『", "』"),
        ("\"", "\""),
        ("'", "'"),
        ("“", "”"),
        ("‘", "’"),
    )
    while True:
        changed = False
        for left, right in wrapper_pairs:
            if text.startswith(left) and text.endswith(right) and len(text) > len(left) + len(right):
                text = text[len(left) : len(text) - len(right)].strip()
                changed = True
        if not changed:
            break
    text = re.sub(r"\s+", " ", text).strip(" ,")
    return text


def _extract_book_title_hint(
    *,
    topic: str = "",
    book_title_hint: str = "",
    context_analysis: Dict[str, Any] | None = None,
    full_name: str = "",
) -> str:
    hint = _strip_book_title_wrappers(book_title_hint)
    if hint:
        return hint

    ctx = context_analysis if isinstance(context_analysis, dict) else {}
    must_preserve = ctx.get("mustPreserve") if isinstance(ctx.get("mustPreserve"), dict) else {}
    explicit = _strip_book_title_wrappers(str(must_preserve.get("bookTitle") or ""))
    if explicit:
        return explicit

    try:
        from agents.common.title_generation import _extract_book_title as _extract_book_title_from_topic

        params: Dict[str, Any] = {}
        if full_name:
            params["fullName"] = str(full_name).strip()
        if ctx:
            params["contextAnalysis"] = ctx
        extracted = _strip_book_title_wrappers(_extract_book_title_from_topic(str(topic or ""), params))
        if extracted:
            return extracted
    except Exception:
        logger.debug("book title hint extraction skipped", exc_info=True)

    return ""


def _is_wrapped_book_title(text: str, start: int, end: int) -> bool:
    left = text[start - 1] if start > 0 else ""
    right = text[end] if end < len(text) else ""
    return bool(left and right and left in BOOK_TITLE_OPEN_WRAPPERS and right in BOOK_TITLE_CLOSE_WRAPPERS)


def normalize_book_title_notation(
    text: str,
    *,
    topic: str = "",
    book_title_hint: str = "",
    context_analysis: Dict[str, Any] | None = None,
    full_name: str = "",
) -> str:
    if not text:
        return str(text or "")

    book_title = _extract_book_title_hint(
        topic=topic,
        book_title_hint=book_title_hint,
        context_analysis=context_analysis,
        full_name=full_name,
    )
    if not book_title:
        return str(text)

    content = str(text)
    escaped = re.escape(book_title)
    canonical = f"{BOOK_TITLE_CANONICAL_OPEN}{book_title}{BOOK_TITLE_CANONICAL_CLOSE}"

    wrapped_pattern = re.compile(
        rf"(?:<\s*{escaped}\s*>|《\s*{escaped}\s*》|〈\s*{escaped}\s*〉|「\s*{escaped}\s*」|『\s*{escaped}\s*』|"
        rf'"\s*{escaped}\s*"|\'\s*{escaped}\s*\'|“\s*{escaped}\s*”|‘\s*{escaped}\s*’)'
    )
    content = wrapped_pattern.sub(canonical, content)

    bare_pattern = re.compile(escaped)
    rebuilt: list[str] = []
    cursor = 0
    for match in bare_pattern.finditer(content):
        start, end = match.span()
        prev_char = content[start - 1] if start > 0 else ""
        next_char = content[end] if end < len(content) else ""
        if _is_wrapped_book_title(content, start, end):
            continue
        if (prev_char and re.match(r"[가-힣A-Za-z0-9]", prev_char)) or (
            next_char and re.match(r"[가-힣A-Za-z0-9]", next_char)
        ):
            continue
        rebuilt.append(content[cursor:start])
        rebuilt.append(canonical)
        cursor = end
    if rebuilt:
        rebuilt.append(content[cursor:])
        content = "".join(rebuilt)

    return content


def _build_addon_markers(slogan: str = "", donation_info: str = "") -> list[str]:
    markers: list[str] = list(DONATION_MARKERS)

    for raw in (slogan, donation_info):
        for token in re.split(r"[\r\n|]+", str(raw or "")):
            normalized = re.sub(r"\s+", " ", token).strip()
            if len(normalized) < 4:
                continue
            if normalized in markers:
                continue
            markers.append(normalized)

    return markers


def strip_generated_addons(content: str, *, slogan: str = "", donation_info: str = "") -> str:
    if not content:
        return content

    # 슬로건/후원 안내는 최종 출력 직전에만 붙인다.
    # 생성/검수 단계에서 섞여 들어온 잔여 문구는 먼저 제거한다.
    updated = strip_generated_slogan(content, slogan)
    markers = _build_addon_markers(slogan=slogan, donation_info=donation_info)
    escaped = "|".join(re.escape(marker) for marker in markers if marker)
    if not escaped:
        return updated.strip()

    marker_re = re.compile(escaped, re.IGNORECASE)

    def _rewrite_paragraph(match: re.Match[str]) -> str:
        attrs = match.group(1) or ""
        inner = match.group(2) or ""
        inner_plain = re.sub(r"<[^>]*>", " ", inner)
        inner_plain = re.sub(r"\s+", " ", inner_plain).strip()
        marker_match = marker_re.search(inner_plain)
        if not marker_match:
            return match.group(0)

        prefix = inner_plain[: marker_match.start()].strip(" \t|:-")
        if len(prefix) >= 6:
            return f"<p{attrs}>{prefix}</p>"
        return ""

    updated = re.sub(
        r"<p([^>]*)>([\s\S]*?)</p\s*>",
        _rewrite_paragraph,
        updated,
        flags=re.IGNORECASE,
    )

    line_re = re.compile(rf"(?:^|\n)[^\n]*?(?:{escaped})[^\n]*(?=\n|$)", re.IGNORECASE)
    updated = line_re.sub("\n", updated)
    updated = re.sub(r"\n{3,}", "\n\n", updated)
    updated = re.sub(r"(<br\s*/?>\s*){3,}", "<br><br>", updated, flags=re.IGNORECASE)
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

    def _contains_gratitude_marker(text: str) -> bool:
        lowered = str(text or "")
        return any(marker in lowered for marker in GRATITUDE_CLOSING_MARKERS)

    def _join_blocks(*blocks: str) -> str:
        parts = [str(block or "").strip() for block in blocks if str(block or "").strip()]
        return "\n".join(parts).strip()

    def _has_visible_text(html_text: str) -> bool:
        plain = re.sub(r"<[^>]*>", "", str(html_text or ""))
        return bool(plain.strip())

    def _remove_nonterminal_gratitude_markers(text: str) -> str:
        matches = list(INLINE_CLOSING_MARKER_RE.finditer(str(text or "")))
        if not matches:
            return str(text or "")

        remove_spans: list[tuple[int, int]] = []
        for idx, match in enumerate(matches):
            marker_text = str(match.group(1) or "")
            if not _contains_gratitude_marker(marker_text):
                continue
            has_later_closing = any(next_match.start() > match.start() for next_match in matches[idx + 1 :])
            if has_later_closing:
                remove_spans.append((match.start(), match.end()))

        if not remove_spans:
            return str(text or "")

        updated = str(text or "")
        for start, end in sorted(remove_spans, reverse=True):
            left = updated[:start]
            right = updated[end:]
            if left.endswith(" ") and right.startswith(" "):
                right = right[1:]
            updated = left + right

        updated = re.sub(r"<p[^>]*>\s*</p\s*>", "", updated, flags=re.IGNORECASE)
        updated = re.sub(r"\s+([,.!?…])", r"\1", updated)
        updated = re.sub(r"\n{3,}", "\n\n", updated)
        return updated.strip()

    content = _remove_nonterminal_gratitude_markers(content)

    def _trim_paragraph_at_closing(paragraph_html: str) -> tuple[str, str]:
        open_end = paragraph_html.find(">")
        close_start = paragraph_html.lower().rfind("</p>")
        if open_end == -1 or close_start == -1 or close_start <= open_end:
            return paragraph_html, ""

        open_tag = paragraph_html[: open_end + 1]
        inner = paragraph_html[open_end + 1 : close_start]
        marker_match = INLINE_CLOSING_MARKER_RE.search(inner)
        if not marker_match:
            return paragraph_html, ""

        marker_text = marker_match.group(0) if marker_match else ""
        trimmed_inner = inner[: marker_match.end()].rstrip()
        remainder_inner = inner[marker_match.end() :].strip()
        if remainder_inner and _contains_gratitude_marker(marker_text):
            # 감사형 마무리가 문단 중간에 나온 경우, 마무리표현을 제거하고 흐름을 유지한다.
            trimmed_inner = inner[: marker_match.start()].rstrip()
        return f"{open_tag}{trimmed_inner}</p>", remainder_inner

    last_match = None
    for match in CLOSING_PARAGRAPH_RE.finditer(content):
        last_match = match
    if last_match is not None:
        prefix = content[: last_match.start()]
        closing_paragraph = content[last_match.start() : last_match.end()]
        trailing = content[last_match.end() :].strip()
        should_enforce = _is_tail_segment(len(content), last_match.start()) or bool(trailing)
        if should_enforce:
            trimmed_paragraph, moved_inner = _trim_paragraph_at_closing(closing_paragraph)

            moved_parts: list[str] = []
            if moved_inner:
                moved_parts.append(f"<p>{moved_inner}</p>")
            if trailing:
                moved_parts.append(trailing)

            moved_block = "\n".join(part for part in moved_parts if part).strip()
            if moved_block:
                # 마무리 문장(감사/부탁) 이후에 붙은 문장은 결말 앞으로 재배치한다.
                if _contains_gratitude_marker(trimmed_paragraph):
                    if _has_visible_text(trimmed_paragraph):
                        rebuilt = f"{prefix.rstrip()}\n{moved_block}\n{trimmed_paragraph}"
                        return rebuilt.strip()
                    return _join_blocks(prefix, moved_block)
                rebuilt = f"{prefix.rstrip()}\n{moved_block}\n{trimmed_paragraph}"
                return rebuilt.strip()
            return f"{prefix}{trimmed_paragraph}".strip()
        return content

    last_index = -1
    last_marker = ""
    for marker in CLOSING_MARKERS:
        idx = content.rfind(marker)
        if idx > last_index:
            last_index = idx
            last_marker = marker

    # Plain-text fallback:
    # If any content exists after the last closing sentence ("감사합니다" 등),
    # move that trailing content before the closing sentence so the draft ends cleanly.
    last_inline_match = None
    for match in INLINE_CLOSING_MARKER_RE.finditer(content):
        last_inline_match = match
    if last_inline_match is not None:
        start = last_inline_match.start()
        end = last_inline_match.end()

        # Consume trailing punctuation/quotes right after the closing marker.
        suffix = content[end:]
        suffix_match = re.match(r'^[\s"\'”’)\]】』〉>]*[.!?…~]*[\s"\'”’)\]】』〉>]*', suffix)
        if suffix_match:
            end += suffix_match.end()

        trailing = content[end:].strip()
        if trailing and _is_tail_segment(len(content), start, ratio=CLOSING_REORDER_MIN_TAIL_RATIO):
            prefix = content[:start].rstrip()
            closing_chunk = content[start:end].strip()
            if _contains_gratitude_marker(closing_chunk):
                # 감사형 마무리가 먼저 나오고 본문이 이어지면, 감사표현을 제거하고 본문 흐름을 유지한다.
                return _join_blocks(prefix, trailing)
            reordered_parts = [part for part in (prefix, trailing, closing_chunk) if part]
            if reordered_parts:
                return "\n".join(reordered_parts).strip()

    if last_inline_match is None and last_index != -1 and _is_tail_segment(len(content), last_index):
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip()
        if not text:
            return default
        return int(float(text))
    except Exception:
        return default


def _looks_over_trimmed(before: str, after: str) -> bool:
    before_len = count_without_space(before)
    if before_len < OVER_TRIM_GUARD_MIN_CHARS:
        return False

    after_len = count_without_space(after)
    return after_len < int(before_len * OVER_TRIM_GUARD_KEEP_RATIO)


def _normalize_plain_text(text: str) -> str:
    plain = re.sub(r"<[^>]*>", " ", str(text or ""))
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain


def _extract_paragraph_blocks(content: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in PARAGRAPH_BLOCK_RE.finditer(str(content or "")):
        html_block = str(match.group(0) or "")
        plain = _normalize_plain_text(html_block)
        blocks.append(
            {
                "start": int(match.start()),
                "end": int(match.end()),
                "html": html_block,
                "plain": plain,
                "chars": count_without_space(html_block),
            }
        )
    return blocks


def _remove_paragraph_blocks(content: str, blocks: list[dict[str, Any]], remove_indices: set[int]) -> str:
    if not remove_indices:
        return content

    cursor = 0
    segments: list[str] = []
    for idx, block in enumerate(blocks):
        start = int(block.get("start") or 0)
        end = int(block.get("end") or start)
        if idx in remove_indices:
            segments.append(content[cursor:start])
            cursor = end
    segments.append(content[cursor:])
    updated = "".join(segments)
    updated = re.sub(r"\n{3,}", "\n\n", updated)
    return updated.strip()


def _looks_tail_duplicate(a: str, b: str) -> bool:
    left = _normalize_plain_text(a)
    right = _normalize_plain_text(b)
    if len(left) < 16 or len(right) < 16:
        return False
    if left == right:
        return True
    if left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= TAIL_DUPLICATE_SIMILARITY


def dedupe_tail_paragraphs(content: str) -> tuple[str, int]:
    blocks = _extract_paragraph_blocks(content)
    if len(blocks) < 2:
        return content, 0

    tail_start = max(0, len(blocks) - TAIL_PARAGRAPH_WINDOW)
    removed: set[int] = set()
    for idx in range(len(blocks) - 1, tail_start - 1, -1):
        if idx in removed:
            continue
        current_plain = str(blocks[idx].get("plain") or "")
        if len(current_plain) < 16:
            continue
        for prev in range(idx - 1, tail_start - 1, -1):
            if prev in removed:
                continue
            prev_plain = str(blocks[prev].get("plain") or "")
            if _looks_tail_duplicate(prev_plain, current_plain):
                removed.add(idx)
                break

    if not removed:
        return content, 0

    updated = _remove_paragraph_blocks(content, blocks, removed)
    return updated, len(removed)


def _split_hint_tokens(text: str) -> list[str]:
    chunks = re.split(r"[\s,./|:;(){}\[\]<>《》「」『』\"'“”‘’]+", str(text or ""))
    tokens = [chunk.strip() for chunk in chunks if len(chunk.strip()) >= 2]
    return tokens


def _collect_protected_tokens(
    *,
    keyword_result: Dict[str, Any] | None = None,
    topic: str = "",
    book_title_hint: str = "",
    context_analysis: Dict[str, Any] | None = None,
) -> list[str]:
    tokens: list[str] = []

    details = ((keyword_result or {}).get("details") or {}).get("keywords") or {}
    if isinstance(details, dict):
        for key, info in details.items():
            if not isinstance(info, dict):
                continue
            if str(info.get("type") or "").strip().lower() != "user":
                continue
            keyword = str(key or "").strip()
            if not keyword:
                continue
            tokens.extend(_split_hint_tokens(keyword))
            tokens.append(keyword)

    ctx = context_analysis if isinstance(context_analysis, dict) else {}
    must_preserve = ctx.get("mustPreserve") if isinstance(ctx.get("mustPreserve"), dict) else {}
    event_location = str(must_preserve.get("eventLocation") or "").strip()
    event_date = str(must_preserve.get("eventDate") or "").strip()
    if event_location:
        tokens.extend(_split_hint_tokens(event_location))
    if event_date:
        tokens.extend(_split_hint_tokens(event_date))

    if book_title_hint:
        tokens.extend(_split_hint_tokens(book_title_hint))
        tokens.append(str(book_title_hint).strip())

    topic_text = str(topic or "")
    date_match = re.search(r"\d{1,2}\s*월(?:\s*\d{1,2}\s*일)?", topic_text)
    if date_match:
        tokens.append(date_match.group(0).strip())

    deduped: list[str] = []
    seen = set()
    for token in tokens:
        normalized = str(token or "").strip()
        if len(normalized) < 2:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _is_paragraph_important(plain: str, protected_tokens: list[str]) -> bool:
    text = str(plain or "")
    if not text:
        return False
    if any(marker in text for marker in SIGNATURE_MARKERS):
        return True
    if any(marker in text for marker in DONATION_MARKERS):
        return True
    if any(token in text for token in protected_tokens):
        return True
    if re.search(r"\d{1,2}\s*월(?:\s*\d{1,2}\s*일)?", text):
        return True
    if re.search(r"(오전|오후)\s*\d{1,2}\s*시", text):
        return True
    return False


def trim_tail_for_length(
    content: str,
    *,
    target_word_count: int | None = None,
    keyword_result: Dict[str, Any] | None = None,
    topic: str = "",
    book_title_hint: str = "",
    context_analysis: Dict[str, Any] | None = None,
) -> tuple[str, int, int, int]:
    target = _safe_int(target_word_count, 0)
    before_chars = count_without_space(content)
    if target <= 0:
        return content, 0, before_chars, before_chars

    soft_upper = max(target, int(target * TARGET_CHAR_SOFT_UPPER_RATIO))
    hard_upper = max(soft_upper, int(target * TARGET_CHAR_HARD_UPPER_RATIO))
    if before_chars <= hard_upper:
        return content, 0, before_chars, before_chars

    blocks = _extract_paragraph_blocks(content)
    if not blocks:
        return content, 0, before_chars, before_chars

    protected_tokens = _collect_protected_tokens(
        keyword_result=keyword_result,
        topic=topic,
        book_title_hint=book_title_hint,
        context_analysis=context_analysis,
    )
    tail_start = max(0, len(blocks) - TAIL_PARAGRAPH_WINDOW)
    removed: set[int] = set()
    current_chars = before_chars

    # 1차: 꼬리 저우선 문단(인사/초대/반복 CTA)을 soft upper까지 우선 정리한다.
    for idx in range(len(blocks) - 1, tail_start - 1, -1):
        if current_chars <= soft_upper:
            break
        plain = str(blocks[idx].get("plain") or "")
        if _is_paragraph_important(plain, protected_tokens):
            continue
        if any(marker in plain for marker in TAIL_LOW_PRIORITY_MARKERS):
            removed.add(idx)
            current_chars -= int(blocks[idx].get("chars") or 0)

    # 2차: hard upper를 넘으면 꼬리의 비핵심 문단을 추가로 정리한다.
    for idx in range(len(blocks) - 1, tail_start - 1, -1):
        if current_chars <= hard_upper:
            break
        if idx in removed:
            continue
        plain = str(blocks[idx].get("plain") or "")
        if _is_paragraph_important(plain, protected_tokens):
            continue
        removed.add(idx)
        current_chars -= int(blocks[idx].get("chars") or 0)

    if not removed:
        return content, 0, before_chars, before_chars

    updated = _remove_paragraph_blocks(content, blocks, removed)
    after_chars = count_without_space(updated)
    return updated, len(removed), before_chars, after_chars


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
        keyword_type = str(info.get("type") or "").strip().lower()
        exact_count = int(info.get("exactCount") or info.get("count") or 0)
        coverage_count = int(info.get("coverage") or exact_count)
        # 사용자 키워드는 exactCount(정확 일치) 기준, 자동 키워드는 coverage 기준을 사용한다.
        count = exact_count if keyword_type == "user" else coverage_count
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
            "type": keyword_type,
            "exactCount": exact_count,
            "coverage": coverage_count,
        }

    return mapped


def _build_self_name_variants(full_name: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(full_name or "")).strip()
    if len(normalized) < 2:
        return []

    variants = [normalized]
    no_space = normalized.replace(" ", "")
    if len(no_space) >= 2 and no_space not in variants:
        variants.append(no_space)
    return variants


def normalize_first_person_voice(content: str, *, full_name: str = "") -> tuple[str, int]:
    text = str(content or "")
    variants = _build_self_name_variants(full_name)
    if not text or not variants:
        return text, 0

    name_group = "|".join(re.escape(item) for item in variants)
    role_group = r"(?:후보|예비후보|시장\s*출마\s*예정자|시장\s*후보|의원|위원장|대표)"
    sentence_end = r"(?=[\s,.;:!?()\[\]\"'“”‘’]|$)"

    rewrites = 0
    updated = text

    # "저 이재성은/저 이재성이" 같은 자기 명시형 1인칭은 허용한다.

    subject_neun = re.compile(
        rf"(?<!저\s)(?<!저는\s)(?:{name_group})(?:\s*{role_group})?\s*(?:은|는|께서는){sentence_end}"
    )
    updated, n = subject_neun.subn("저는", updated)
    rewrites += n

    subject_ga = re.compile(
        rf"(?<!저\s)(?<!제\s)(?<!제가\s)(?:{name_group})(?:\s*{role_group})?\s*(?:이|가|께서){sentence_end}"
    )
    updated, n = subject_ga.subn("제가", updated)
    rewrites += n

    return updated, rewrites


def finalize_output(
    content: str,
    *,
    slogan: str = "",
    slogan_enabled: bool = False,
    donation_info: str = "",
    donation_enabled: bool = False,
    allow_diagnostic_tail: bool = False,
    keyword_result: Dict[str, Any] | None = None,
    topic: str = "",
    book_title_hint: str = "",
    context_analysis: Dict[str, Any] | None = None,
    full_name: str = "",
    target_word_count: int | None = None,
) -> Dict[str, Any]:
    updated = normalize_ascii_double_quotes(content)

    # 생성 단계에서 섞여 들어온 슬로건/후원 안내는 제거하고, 최종 단계에서만 재부착한다.
    updated = strip_generated_addons(
        updated,
        slogan=str(slogan or ""),
        donation_info=str(donation_info or ""),
    )
    before_tail_trim = updated
    updated = trim_trailing_diagnostics(updated, allow_diagnostic_tail=allow_diagnostic_tail)
    after_diagnostic_trim = updated
    updated = trim_after_closing(updated)

    # Guard against accidental hard cut by broad closing markers in the body.
    if _looks_over_trimmed(before_tail_trim, updated):
        logger.warning(
            "Skip aggressive closing trim: before=%s after=%s",
            count_without_space(before_tail_trim),
            count_without_space(updated),
        )
        updated = after_diagnostic_trim
        if _looks_over_trimmed(before_tail_trim, updated):
            logger.warning(
                "Skip diagnostic trim as well: before=%s after=%s",
                count_without_space(before_tail_trim),
                count_without_space(updated),
            )
            updated = before_tail_trim

    updated = normalize_book_title_notation(
        updated,
        topic=topic,
        book_title_hint=book_title_hint,
        context_analysis=context_analysis,
        full_name=full_name,
    )
    updated, perspective_rewrites = normalize_first_person_voice(updated, full_name=full_name)
    if perspective_rewrites > 0:
        logger.info("First-person perspective normalization applied: rewrites=%s", perspective_rewrites)

    updated, dedup_removed = dedupe_tail_paragraphs(updated)
    if dedup_removed > 0:
        logger.info("Tail paragraph dedupe applied: removed=%s", dedup_removed)

    updated, trim_removed, before_chars, after_chars = trim_tail_for_length(
        updated,
        target_word_count=target_word_count,
        keyword_result=keyword_result,
        topic=topic,
        book_title_hint=book_title_hint,
        context_analysis=context_analysis,
    )
    if trim_removed > 0:
        logger.info(
            "Length tail trim applied (공백 제외 기준): target=%s before=%s after=%s removed_paragraphs=%s",
            int(target_word_count or 0),
            before_chars,
            after_chars,
            trim_removed,
        )

    # 최종 wordCount는 '공백 제외' 기준으로 계산한다.
    word_count = count_without_space(updated)

    if donation_enabled and str(donation_info or "").strip():
        updated = insert_donation_info(updated, normalize_ascii_double_quotes(donation_info))
    if slogan_enabled and str(slogan or "").strip():
        updated = insert_slogan(updated, normalize_ascii_double_quotes(slogan))
    updated = normalize_ascii_double_quotes(updated)

    return {
        "content": updated,
        "wordCount": word_count,
        "keywordValidation": build_keyword_validation(keyword_result),
    }


__all__ = [
    "strip_generated_slogan",
    "normalize_ascii_double_quotes",
    "normalize_book_title_notation",
    "strip_generated_addons",
    "trim_trailing_diagnostics",
    "trim_after_closing",
    "insert_donation_info",
    "insert_slogan",
    "count_without_space",
    "build_keyword_validation",
    "finalize_output",
]
