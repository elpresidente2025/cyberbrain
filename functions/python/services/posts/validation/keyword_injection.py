"""??? ?? ??/??."""

from __future__ import annotations

from difflib import SequenceMatcher
import logging
import re
from typing import Any, Mapping, Optional

from agents.common.role_keyword_policy import should_block_role_keyword, should_render_role_keyword_as_intent

from ..keyword_insertion_policy import SENTENCE_FOCUS_TOKENS

from ._shared import _strip_html
from .keyword_common import count_keyword_occurrences
from .keyword_context import (
    _is_event_context_text,
    _is_keyword_injection_risky_paragraph,
    _is_location_keyword,
    _is_non_editable_sentence,
    _is_unnatural_location_phrase,
    _is_unsafe_location_context,
    _try_contextual_location_replacement,
)
from .keyword_reference import (
    _append_sentence_to_paragraph,
    _build_role_keyword_reference_sentence,
    _is_role_keyword,
    _should_block_role_keyword_reference_sentence,
)


logger = logging.getLogger(__name__)
_WORDISH_CHAR_RE = re.compile(r"[0-9A-Za-z가-힣]")
_ALLOWED_TOKEN_PARTICLE_RE = re.compile(
    r"^(?:께서는|께서|에게|으로서|로서|으로|로|에서|에는|에는서|은|는|이|가|을|를|의|에|와|과|도|만|보다|까지|부터)(?![0-9A-Za-z가-힣])"
)


def _normalize_sentence_surface(text: Any) -> str:
    plain = _strip_html(str(text or ""))
    plain = re.sub(r"[\"'“”‘’()\[\]]", " ", plain)
    plain = re.sub(r"\s+", " ", plain).strip(" .,!?:;")
    return plain


def _split_sentence_units(text: Any) -> list[str]:
    normalized = _normalize_sentence_surface(text)
    if not normalized:
        return []
    units = [
        str(part or "").strip()
        for part in re.split(r"(?<=[.!?。])\s+|\n+", normalized)
        if str(part or "").strip()
    ]
    return units or [normalized]


def _sentence_similarity(a: Any, b: Any) -> float:
    left = _normalize_sentence_surface(a)
    right = _normalize_sentence_surface(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _preview_text(text: Any, limit: int = 160) -> str:
    plain = _normalize_sentence_surface(text)
    if len(plain) <= limit:
        return plain
    return f"{plain[:limit].rstrip()}..."


def _is_wordish_char(char: str) -> bool:
    return bool(char and _WORDISH_CHAR_RE.fullmatch(char))


def _find_boundary_safe_token_span(text: Any, token: Any) -> tuple[int, int]:
    source = str(text or "")
    target = str(token or "").strip()
    if not source or not target:
        return -1, -1

    pattern = re.compile(re.escape(target))
    for match in pattern.finditer(source):
        start, end = match.span()
        left_char = source[start - 1] if start > 0 else ""
        right_char = source[end] if end < len(source) else ""
        if _is_wordish_char(left_char):
            continue
        if _is_wordish_char(right_char):
            suffix = source[end:]
            if not _ALLOWED_TOKEN_PARTICLE_RE.match(suffix):
                continue
        return start, end
    return -1, -1


def _find_similar_sentence_in_content(
    candidate_sentence: Any,
    content: Any,
    *,
    threshold: float = 0.88,
    exclude_sentences: Optional[list[str]] = None,
) -> str:
    normalized_candidate = _normalize_sentence_surface(candidate_sentence)
    if not normalized_candidate or len(normalized_candidate) < 20:
        return ""

    excluded = {
        _normalize_sentence_surface(sentence)
        for sentence in (exclude_sentences or [])
        if _normalize_sentence_surface(sentence)
    }
    for sentence in _split_sentence_units(content):
        normalized_sentence = _normalize_sentence_surface(sentence)
        if not normalized_sentence or normalized_sentence in excluded:
            continue
        if _sentence_similarity(normalized_candidate, normalized_sentence) >= threshold:
            return sentence
    return ""

def _rewrite_sentence_with_keyword(
    sentence: str,
    keyword: str,
    variant_index: int = 0,
    *,
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
) -> str:
    _ = variant_index
    normalized_sentence = re.sub(r"\s+", " ", str(sentence or "")).strip()
    normalized_keyword = str(keyword or "").strip()
    if not normalized_sentence or not normalized_keyword:
        return normalized_sentence
    if normalized_keyword in normalized_sentence:
        return normalized_sentence
    if should_block_role_keyword(role_keyword_policy, normalized_keyword):
        return normalized_sentence
    if _is_role_keyword(normalized_keyword) and should_render_role_keyword_as_intent(role_keyword_policy, normalized_keyword):
        return normalized_sentence
    if _is_role_keyword(normalized_keyword):
        return normalized_sentence

    if _is_location_keyword(normalized_keyword):
        # 위치 키워드는 일반 명사 앞 강제 삽입 시 비문이 잘 발생하므로,
        # 문장 리라이트 경로를 비활성화하고
        # 1) 문맥 치환, 2) 행사형 보강 문장 경로만 사용한다.
        return normalized_sentence

    anchor_tokens = (
        "출판기념회",
        "행사",
        "일정",
        "현장",
        "참여",
        "소통",
        "대화",
        "문제",
        "과제",
        "쟁점",
        "해법",
        "계획",
        "설명",
        "논의",
        "비전",
        "해법",
    )

    for token in anchor_tokens:
        if token not in normalized_sentence:
            continue
        start, end = _find_boundary_safe_token_span(normalized_sentence, token)
        if start < 0:
            logger.info(
                "Keyword sentence rewrite skipped: keyword=%s token=%s reason=unsafe_anchor_boundary sentence=%s",
                normalized_keyword,
                token,
                _preview_text(normalized_sentence),
            )
            continue
        rewritten = (
            normalized_sentence[:start]
            + f"{normalized_keyword} {token}"
            + normalized_sentence[end:]
        )
        if _is_unnatural_location_phrase(rewritten, normalized_keyword):
            continue
        logger.info(
            "Keyword sentence rewrite applied: keyword=%s token=%s before=%s after=%s",
            normalized_keyword,
            token,
            _preview_text(normalized_sentence),
            _preview_text(rewritten),
        )
        return rewritten

    # 템플릿형 접두/접속 문장은 사용하지 않는다 (자연 문장 유지)
    return normalized_sentence



def _inject_keyword_into_section(
    section_html: str,
    keyword: str,
    section_type: str,
    variant_index: int = 0,
    *,
    allow_reference_fallback: bool = False,
    existing_content: str = "",
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
    section_index: Optional[int] = None,
) -> tuple[str, bool, str]:
    raw_section = str(section_html or "")
    normalized_keyword = str(keyword or "").strip()
    if not raw_section or not normalized_keyword:
        return raw_section, False, ""
    if should_block_role_keyword(role_keyword_policy, normalized_keyword):
        return raw_section, False, ""

    before_count = count_keyword_occurrences(raw_section, normalized_keyword)
    if _is_location_keyword(normalized_keyword):
        replaced_section, replaced = _try_contextual_location_replacement(raw_section, normalized_keyword)
        if replaced:
            return replaced_section, True, f"{normalized_keyword} (문맥 치환)"

    paragraph_matches = list(re.finditer(r"<p\b[^>]*>([\s\S]*?)</p\s*>", raw_section, re.IGNORECASE))
    if not paragraph_matches:
        # 섹션 구조가 없으면 무리한 템플릿 보정 없이 통과시킨다.
        return raw_section, False, ""

    if str(section_type or "").startswith("body"):
        paragraph_indexes = list(range(len(paragraph_matches)))
    elif section_type == "conclusion":
        paragraph_indexes = list(reversed(range(len(paragraph_matches))))
    else:
        paragraph_indexes = list(range(len(paragraph_matches)))

    focus_tokens = SENTENCE_FOCUS_TOKENS

    for paragraph_index in paragraph_indexes:
        paragraph_match = paragraph_matches[paragraph_index]
        paragraph_inner = str(paragraph_match.group(1) or "")
        if _is_keyword_injection_risky_paragraph(paragraph_inner):
            continue
        sentence_matches = list(re.finditer(r"[^.!?。]+[.!?。]?", paragraph_inner))
        if not sentence_matches:
            continue

        ranked_sentences = sorted(
            sentence_matches,
            key=lambda m: (
                0
                if any(token in re.sub(r"\s+", " ", m.group(0)).strip() for token in focus_tokens)
                else 1,
                -len(re.sub(r"\s+", " ", m.group(0)).strip()),
            ),
        )

        for sentence_match in ranked_sentences:
            original_sentence = re.sub(r"\s+", " ", sentence_match.group(0)).strip()
            if not original_sentence:
                continue
            if len(original_sentence) < 14:
                continue
            if _is_non_editable_sentence(original_sentence):
                continue
            if _is_location_keyword(normalized_keyword):
                if not _is_event_context_text(original_sentence, keyword=normalized_keyword):
                    continue
                if _is_unsafe_location_context(original_sentence):
                    continue
            if "존경하는" in original_sentence and "안녕하십니까" in original_sentence:
                continue
            rewritten_sentence = _rewrite_sentence_with_keyword(
                original_sentence,
                normalized_keyword,
                variant_index,
                role_keyword_policy=role_keyword_policy,
            )
            if not rewritten_sentence or rewritten_sentence == original_sentence:
                continue
            if _find_similar_sentence_in_content(
                rewritten_sentence,
                existing_content or raw_section,
                exclude_sentences=[original_sentence],
            ):
                continue

            sentence_start = sentence_match.start()
            sentence_end = sentence_match.end()
            updated_inner = (
                paragraph_inner[:sentence_start]
                + rewritten_sentence
                + paragraph_inner[sentence_end:]
            )
            candidate = (
                raw_section[: paragraph_match.start(1)]
                + updated_inner
                + raw_section[paragraph_match.end(1) :]
            )
            if count_keyword_occurrences(candidate, normalized_keyword) > before_count:
                logger.info(
                    "Keyword section rewrite applied: keyword=%s section=%s type=%s before=%s after=%s",
                    normalized_keyword,
                    section_index if section_index is not None else "unknown",
                    str(section_type or ""),
                    _preview_text(original_sentence),
                    _preview_text(rewritten_sentence),
                )
                return candidate, True, rewritten_sentence

    if allow_reference_fallback and _is_role_keyword(normalized_keyword):
        reference_sentence = _build_role_keyword_reference_sentence(
            normalized_keyword,
            str(section_type or ""),
            variant_index,
            role_keyword_policy=role_keyword_policy,
        )
        if reference_sentence:
            if _should_block_role_keyword_reference_sentence(
                reference_sentence,
                context_html=raw_section,
                keyword=normalized_keyword,
                role_keyword_policy=role_keyword_policy,
            ):
                return raw_section, False, ""
            if _find_similar_sentence_in_content(reference_sentence, existing_content or raw_section):
                return raw_section, False, ""
            for paragraph_index in paragraph_indexes:
                paragraph_match = paragraph_matches[paragraph_index]
                paragraph_inner = str(paragraph_match.group(1) or "")
                plain_paragraph = _strip_html(paragraph_inner)
                if not plain_paragraph or len(plain_paragraph) < 20:
                    continue
                if _is_keyword_injection_risky_paragraph(plain_paragraph):
                    continue
                if normalized_keyword in plain_paragraph:
                    continue

                updated_inner = _append_sentence_to_paragraph(paragraph_inner, reference_sentence)
                if updated_inner == paragraph_inner:
                    continue
                candidate = (
                    raw_section[: paragraph_match.start(1)]
                    + updated_inner
                    + raw_section[paragraph_match.end(1) :]
                )
                if count_keyword_occurrences(candidate, normalized_keyword) > before_count:
                    logger.info(
                        "Keyword section reference fallback applied: keyword=%s section=%s type=%s sentence=%s",
                        normalized_keyword,
                        section_index if section_index is not None else "unknown",
                        str(section_type or ""),
                        _preview_text(reference_sentence),
                    )
                    return candidate, True, reference_sentence

    # 신규 문장 보강 없이, 기존 문맥 리라이트가 불가능하면 실패를 반환한다.
    return raw_section, False, ""

