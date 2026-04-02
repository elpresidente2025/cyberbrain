"""??? ?? ?? ??/??."""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional, Sequence

from ._shared import _strip_html
from .keyword_common import (
    LOW_SIGNAL_KEYWORD_TOKENS,
    ROLE_FALLBACK_LABELS,
    _count_user_keyword_exact_non_overlap,
    _normalize_user_keyword,
    count_keyword_occurrences,
)
from .keyword_reference import (
    _build_generic_role_reference,
    _build_keyword_replacement_pool,
    _build_person_role_reduction_candidates,
    _build_person_role_reduction_pattern,
    _extract_person_name_from_keyword,
    _is_keyword_reference_sentence,
    _looks_like_compact_person_keyword,
    _normalize_reduced_reference_particles,
    _normalize_sentence_for_compare,
    _protect_shadowed_keywords,
    _restore_shadowed_keywords,
)

_SELF_IDENTIFICATION_ROLE_FRAGMENT = r"(?:\s*(?:전\s*)?(?:국회의원|의원|지사|도지사|시장|위원장|대표|장관|예비후보|후보))?"


def _extract_sentence_window(text: str, start: int, end: int) -> str:
    base = str(text or "")
    if not base:
        return ""

    left = 0
    for match in re.finditer(r"(?<!\d)[.!?。](?!\d)", base[: max(0, start)]):
        left = match.end()

    right = len(base)
    right_match = re.search(r"(?<!\d)[.!?。](?!\d)", base[max(0, end) :])
    if right_match:
        right = max(0, end) + right_match.end()

    return base[left:right]


def _looks_like_self_identification_sentence(text: str, keyword: str) -> bool:
    normalized_keyword = _normalize_user_keyword(keyword)
    plain = re.sub(r"\s+", " ", _strip_html(text)).strip()
    if not plain or not normalized_keyword or normalized_keyword not in plain:
        return False

    identity_patterns = (
        re.compile(
            rf"(?:^|[,;:]\s*|[\"'“”‘’]\s*){re.escape(normalized_keyword)}"
            rf"{_SELF_IDENTIFICATION_ROLE_FRAGMENT}\s*입니다[.!?。]?$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"{re.escape(normalized_keyword)}{_SELF_IDENTIFICATION_ROLE_FRAGMENT}\s*입니다[.!?。]?$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?:[가-힣]{{1,10}})?(?:국회의원|의원|지사|도지사|시장|위원장|대표|장관|예비후보|후보)\s+"
            rf"{re.escape(normalized_keyword)}\s*(?:으로서|로서)",
            re.IGNORECASE,
        ),
    )
    return any(pattern.search(plain) for pattern in identity_patterns)


def _match_within_self_identification_sentence(text: str, start: int, end: int, keyword: str) -> bool:
    return _looks_like_self_identification_sentence(
        _extract_sentence_window(text, start, end),
        keyword,
    )


def _replace_last_keyword_occurrences(
    content: str,
    keyword: str,
    remove_count: int,
    *,
    shadowed_by: Optional[Sequence[str]] = None,
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
) -> tuple[str, int]:
    """정확 일치 기준 과다 키워드를 뒤에서부터 치환해 개수를 줄인다."""
    if not content or not keyword or remove_count <= 0:
        return str(content or ""), 0

    normalized_keyword = _normalize_user_keyword(keyword)
    protected, protected_mapping = _protect_shadowed_keywords(str(content or ""), shadowed_by)
    working = protected
    replaced = 0
    keyword_person_name = _extract_person_name_from_keyword(normalized_keyword)
    keyword_role_surface = ""
    if keyword_person_name and normalized_keyword != keyword_person_name:
        keyword_role_surface = normalized_keyword[len(keyword_person_name) :].strip()
    replacement_pool = _build_keyword_replacement_pool(
        normalized_keyword,
        role_keyword_policy=role_keyword_policy,
    )
    bare_pattern = re.compile(re.escape(normalized_keyword))

    while replaced < remove_count:
        rewritten = False
        if keyword_role_surface:
            exact_matches = [
                match
                for match in bare_pattern.finditer(working)
                if not _match_within_self_identification_sentence(
                    working,
                    match.start(),
                    match.end(),
                    normalized_keyword,
                )
            ]
            if exact_matches:
                start, end = exact_matches[-1].span()
                exact_replacements = _build_person_role_reduction_candidates(
                    normalized_keyword,
                    keyword_role_surface,
                    preserve_full_name=True,
                    role_keyword_policy=role_keyword_policy,
                )
                if exact_replacements:
                    working = working[:start] + exact_replacements[0] + working[end:]
                    replaced += 1
                    rewritten = True
        if rewritten:
            continue

        role_pattern = _build_person_role_reduction_pattern(keyword_person_name or normalized_keyword)
        matches = (
            [
                match
                for match in role_pattern.finditer(working)
                if not _match_within_self_identification_sentence(
                    working,
                    match.start(),
                    match.end(),
                    normalized_keyword,
                )
            ]
            if role_pattern is not None
            else []
        )
        if matches:
            match = matches[-1]
            start, end = match.span()
            role_surface = f"{str(match.group('modifier') or '').strip()} {str(match.group('role') or '').strip()}".strip()
            role_replacements = _build_person_role_reduction_candidates(
                keyword_person_name or normalized_keyword,
                role_surface,
                preserve_full_name=False,
                role_keyword_policy=role_keyword_policy,
            )
            replacement = (
                role_replacements[0]
                if role_replacements
                else _build_generic_role_reference(role_surface)
            )
            if start < 0 or end > len(working) or start >= end:
                break
            working = working[:start] + replacement + working[end:]
            replaced += 1
            rewritten = True
        if rewritten:
            continue

        for role, fallback in ROLE_FALLBACK_LABELS:
            pattern = re.compile(rf"{re.escape(normalized_keyword)}\s*{role}")
            matches = [
                match
                for match in pattern.finditer(working)
                if not _match_within_self_identification_sentence(
                    working,
                    match.start(),
                    match.end(),
                    normalized_keyword,
                )
            ]
            if not matches:
                continue
            start, end = matches[-1].span()
            if start < 0 or end > len(working) or start >= end:
                continue
            working = working[:start] + fallback + working[end:]
            replaced += 1
            rewritten = True
            break
        if rewritten:
            continue

        matches = [
            match
            for match in bare_pattern.finditer(working)
            if not _match_within_self_identification_sentence(
                working,
                match.start(),
                match.end(),
                normalized_keyword,
            )
        ]
        if not matches:
            break
        start, end = matches[-1].span()
        if start < 0 or end > len(working) or start >= end:
            break
        if not replacement_pool:
            break
        replacement = replacement_pool[(replaced if replaced >= 0 else 0) % len(replacement_pool)]
        working = working[:start] + replacement + working[end:]
        replaced += 1

    working = _normalize_reduced_reference_particles(working)
    restored = _restore_shadowed_keywords(working, protected_mapping)
    return restored, replaced


def _cleanup_sentence_removed_paragraph(paragraph_inner: str) -> str:
    cleaned = str(paragraph_inner or "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;!?])", r"\1", cleaned)
    return cleaned.strip()



def _is_poll_fact_sentence_for_keyword_reduction(sentence: Any) -> bool:
    normalized = _normalize_sentence_for_compare(sentence)
    if not normalized:
        return False

    has_metric_signal = bool(
        re.search(
            r"(?:\d+(?:\.\d+)?\s*(?:%|%p|명|포인트)|±\s*\d+(?:\.\d+)?\s*(?:%p|포인트))",
            normalized,
            re.IGNORECASE,
        )
    )
    has_poll_signal = any(
        token in normalized
        for token in (
            "여론조사",
            "조사",
            "지지율",
            "응답률",
            "표본오차",
            "오차 범위",
            "정당 지지율",
            "표본수",
        )
    )
    has_matchup_signal = any(
        token in normalized
        for token in (
            "가상대결",
            "양자대결",
            "맞대결",
            "대결",
            "접전",
        )
    )
    return bool(has_metric_signal and (has_poll_signal or has_matchup_signal)) or bool(
        has_matchup_signal and has_poll_signal
    )


def _score_keyword_sentence_for_reduction(sentence: str, keyword: str) -> int:
    normalized = _normalize_sentence_for_compare(sentence)
    if not normalized:
        return 9
    if _is_keyword_reference_sentence(normalized, keyword):
        return 0

    score = 4
    has_poll_fact_signal = _is_poll_fact_sentence_for_keyword_reduction(normalized)
    if any(token in normalized for token in LOW_SIGNAL_KEYWORD_TOKENS):
        score = min(score, 1)
    if len(normalized) < 40:
        score = min(score, 2)
    if has_poll_fact_signal:
        score += 4
    if any(token in normalized for token in ("가상대결", "양자대결", "대결")):
        score += 2
    if _looks_like_compact_person_keyword(keyword) and not has_poll_fact_signal:
        if any(token in normalized for token in ("우위", "약진", "경쟁력", "차별화", "가능성", "비전", "정책", "성원", "지지")):
            score = min(score, 0)
    if any(token in normalized for token in ("후원", "영수증", "계좌")):
        score += 4
    return score


def _rewrite_sentence_to_reduce_keyword(
    sentence_html: str,
    keyword: str,
    *,
    shadowed_by: Optional[Sequence[str]] = None,
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
) -> str:
    original = str(sentence_html or "")
    normalized_keyword = _normalize_user_keyword(keyword)
    if not original or not normalized_keyword:
        return original
    if _looks_like_self_identification_sentence(original, normalized_keyword):
        return original

    protected, protected_mapping = _protect_shadowed_keywords(original, shadowed_by)
    rewritten = protected
    poll_fact_sentence = _is_poll_fact_sentence_for_keyword_reduction(_strip_html(rewritten))

    role_fragment = r"(?:\s*(?:전\s*)?(?:국회의원|의원|지사|도지사|시장|위원장|대표|장관|예비후보|후보))?"
    first_person_negation_patterns = (
        re.compile(
            rf"{re.escape(normalized_keyword)}(?:이|가|은|는)?\s+아닌\s+(?P<speaker>저는|제가|저의|제)",
        ),
        re.compile(
            rf"{re.escape(normalized_keyword)}(?:이|가|은|는)?\s+아니라\s+(?P<speaker>저는|제가|저의|제)",
        ),
        re.compile(
            rf"{re.escape(normalized_keyword)}\s*(?:과|와)\s+달리\s+(?P<speaker>저는|제가)",
        ),
    )
    first_person_competitor_clause_patterns = (
        re.compile(
            rf"{re.escape(normalized_keyword)}{role_fragment}\s*(?:과|와)\s+비교했(?:을\s+)?때\s*,?\s*",
            re.IGNORECASE,
        ),
        re.compile(
            rf"{re.escape(normalized_keyword)}{role_fragment}\s*(?:과|와)의?\s+경쟁을\s+통해\s*",
            re.IGNORECASE,
        ),
        re.compile(
            rf"{re.escape(normalized_keyword)}{role_fragment}\s*이\s+제시하지\s+못(?:한|하는)\s+",
            re.IGNORECASE,
        ),
    )

    if not poll_fact_sentence:
        for pattern in first_person_negation_patterns:
            rewritten, count = pattern.subn(lambda match: str(match.group("speaker") or ""), rewritten, count=1)
            if count > 0:
                rewritten = re.sub(r"\s{2,}", " ", rewritten).strip()
                rewritten = _restore_shadowed_keywords(rewritten, protected_mapping)
                return rewritten if rewritten else original

        plain_rewritten = _strip_html(rewritten)
        if re.search(r"(?:저는|제가|저의|제)\s*", plain_rewritten):
            for pattern in first_person_competitor_clause_patterns:
                updated_text, count = pattern.subn("", rewritten, count=1)
                if count > 0:
                    updated_text = re.sub(r"^\s*,\s*", "", updated_text)
                    updated_text = re.sub(r"\s{2,}", " ", updated_text).strip()
                    updated_text = _normalize_reduced_reference_particles(updated_text)
                    updated_text = _restore_shadowed_keywords(updated_text, protected_mapping)
                    return updated_text if updated_text else original

    if not poll_fact_sentence and _is_keyword_reference_sentence(_strip_html(rewritten), normalized_keyword):
        if re.search(
            rf"[\"']?{re.escape(normalized_keyword)}[\"']?\s*(검색어|키워드|표현|문구)",
            rewritten,
        ):
            rewritten = re.sub(
                rf"[\"']?{re.escape(normalized_keyword)}[\"']?\s*(검색어|키워드|표현|문구)",
                r"관련 \1",
                rewritten,
                count=1,
            )
        else:
            rewritten = _restore_shadowed_keywords(rewritten, protected_mapping)
            return rewritten if rewritten else original

    replacements = 0
    keyword_person_name = _extract_person_name_from_keyword(normalized_keyword)
    keyword_role_surface = ""
    if keyword_person_name and normalized_keyword != keyword_person_name:
        keyword_role_surface = normalized_keyword[len(keyword_person_name) :].strip()
        for replacement in _build_person_role_reduction_candidates(
            normalized_keyword,
            keyword_role_surface,
            preserve_full_name=True,
            role_keyword_policy=role_keyword_policy,
        ):
            rewritten_candidate, count = re.subn(
                re.escape(normalized_keyword),
                replacement,
                rewritten,
                count=1,
            )
            if count > 0:
                rewritten = rewritten_candidate
                replacements += count
                break

    role_pattern = _build_person_role_reduction_pattern(keyword_person_name or normalized_keyword)
    if replacements == 0 and role_pattern is not None:
        def _replace_role_match(match: re.Match[str]) -> str:
            role_surface = f"{str(match.group('modifier') or '').strip()} {str(match.group('role') or '').strip()}".strip()
            candidates = _build_person_role_reduction_candidates(
                keyword_person_name or normalized_keyword,
                role_surface,
                preserve_full_name=False,
                role_keyword_policy=role_keyword_policy,
            )
            return candidates[0] if candidates else _build_generic_role_reference(role_surface)

        rewritten, count = role_pattern.subn(_replace_role_match, rewritten)
        replacements += count

    if replacements == 0 and re.search(re.escape(normalized_keyword), rewritten):
        replacement_pool = _build_keyword_replacement_pool(
            normalized_keyword,
            role_keyword_policy=role_keyword_policy,
        )
        if not replacement_pool:
            rewritten = _restore_shadowed_keywords(rewritten, protected_mapping)
            return rewritten if rewritten else original
        if poll_fact_sentence:
            replacement_pool = [
                candidate
                for candidate in replacement_pool
                if candidate not in {"상대", "관련 사안", "이 사안"}
            ]
            if not replacement_pool:
                rewritten = _restore_shadowed_keywords(rewritten, protected_mapping)
                return rewritten if rewritten else original
        bare_fallback = replacement_pool[0]
        rewritten, count = re.subn(
            re.escape(normalized_keyword),
            bare_fallback,
            rewritten,
        )
        replacements += count

    rewritten = _normalize_reduced_reference_particles(rewritten)
    rewritten = re.sub(r"\s{2,}", " ", rewritten).strip()
    rewritten = _restore_shadowed_keywords(rewritten, protected_mapping)
    return rewritten if replacements > 0 else original


def _remove_low_signal_keyword_sentence_once(
    content: str,
    keyword: str,
    user_keywords: Sequence[str],
    *,
    shadowed_by: Optional[Sequence[str]] = None,
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    working = str(content or "")
    normalized_keyword = _normalize_user_keyword(keyword)
    if not working or not normalized_keyword:
        return {"content": working, "edited": False}

    paragraph_matches = list(re.finditer(r"<p\b[^>]*>([\s\S]*?)</p\s*>", working, re.IGNORECASE))
    if not paragraph_matches:
        return {"content": working, "edited": False}

    candidates: list[Dict[str, Any]] = []
    for paragraph_index in reversed(range(len(paragraph_matches))):
        paragraph_match = paragraph_matches[paragraph_index]
        paragraph_inner = str(paragraph_match.group(1) or "")
        sentence_matches = list(re.finditer(r"[^.!?。]+[.!?。]?", paragraph_inner))
        for sentence_index in reversed(range(len(sentence_matches))):
            sentence_match = sentence_matches[sentence_index]
            sentence_html = str(sentence_match.group(0) or "")
            sentence_plain = _strip_html(sentence_html)
            if normalized_keyword not in sentence_plain:
                continue
            if _looks_like_self_identification_sentence(sentence_html, normalized_keyword):
                continue

            contribution = int(
                _count_user_keyword_exact_non_overlap(sentence_plain, user_keywords).get(normalized_keyword) or 0
            )
            if contribution <= 0:
                continue

            candidates.append(
                {
                    "priority": _score_keyword_sentence_for_reduction(sentence_plain, normalized_keyword),
                    "isPollFact": _is_poll_fact_sentence_for_keyword_reduction(sentence_plain),
                    "contribution": contribution,
                    "paragraphIndex": paragraph_index,
                    "sentenceIndex": sentence_index,
                    "paragraphStart": paragraph_match.start(),
                    "paragraphEnd": paragraph_match.end(),
                    "innerStart": paragraph_match.start(1),
                    "innerEnd": paragraph_match.end(1),
                    "sentenceStart": sentence_match.start(),
                    "sentenceEnd": sentence_match.end(),
                    "sentence": sentence_plain,
                    "sentenceHtml": sentence_html,
                    "paragraphInner": paragraph_inner,
                }
            )

    if not candidates:
        return {"content": working, "edited": False}

    ordered_candidates = sorted(
        candidates,
        key=lambda item: (
            int(item.get("priority") or 9),
            -int(item.get("contribution") or 0),
            -int(item.get("paragraphIndex") or 0),
            -int(item.get("sentenceIndex") or 0),
        ),
    )

    current_count = int(_count_user_keyword_exact_non_overlap(working, user_keywords).get(normalized_keyword) or 0)
    for candidate in ordered_candidates:
        rewritten_sentence = _rewrite_sentence_to_reduce_keyword(
            str(candidate.get("sentenceHtml") or ""),
            normalized_keyword,
            shadowed_by=shadowed_by,
            role_keyword_policy=role_keyword_policy,
        )
        if not rewritten_sentence or rewritten_sentence == str(candidate.get("sentenceHtml") or ""):
            continue

        paragraph_inner = str(candidate.get("paragraphInner") or "")
        sentence_start = int(candidate.get("sentenceStart") or 0)
        sentence_end = int(candidate.get("sentenceEnd") or 0)
        updated_inner = (
            paragraph_inner[:sentence_start]
            + rewritten_sentence
            + paragraph_inner[sentence_end:]
        )
        updated_content = (
            working[: int(candidate.get("innerStart") or 0)]
            + updated_inner
            + working[int(candidate.get("innerEnd") or 0) :]
        )
        reduced_count = int(
            _count_user_keyword_exact_non_overlap(updated_content, user_keywords).get(normalized_keyword) or 0
        )
        if reduced_count >= current_count:
            continue
        return {
            "content": updated_content,
            "edited": updated_content != working,
            "rewrittenSentence": _strip_html(rewritten_sentence),
            "originalSentence": str(candidate.get("sentence") or ""),
            "contribution": int(candidate.get("contribution") or 0),
            "priority": int(candidate.get("priority") or 9),
            "mode": "rewrite",
        }

    removable_candidates = [item for item in ordered_candidates if not bool(item.get("isPollFact"))]
    if not removable_candidates:
        return {"content": working, "edited": False}

    candidate = removable_candidates[0]

    paragraph_inner = str(candidate.get("paragraphInner") or "")
    sentence_start = int(candidate.get("sentenceStart") or 0)
    sentence_end = int(candidate.get("sentenceEnd") or 0)
    updated_inner = _cleanup_sentence_removed_paragraph(
        paragraph_inner[:sentence_start] + paragraph_inner[sentence_end:]
    )

    if _strip_html(updated_inner):
        updated_content = (
            working[: int(candidate.get("innerStart") or 0)]
            + updated_inner
            + working[int(candidate.get("innerEnd") or 0) :]
        )
    else:
        updated_content = working[: int(candidate.get("paragraphStart") or 0)] + working[
            int(candidate.get("paragraphEnd") or 0) :
        ]

    return {
        "content": updated_content,
        "edited": updated_content != working,
        "removedSentence": str(candidate.get("sentence") or ""),
        "contribution": int(candidate.get("contribution") or 0),
        "priority": int(candidate.get("priority") or 9),
        "mode": "remove",
    }


def _reduce_excess_user_keyword_mentions(
    content: str,
    keyword: str,
    user_keywords: Sequence[str],
    *,
    target_max: int,
    shadowed_by: Optional[Sequence[str]] = None,
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    working = str(content or "")
    normalized_keyword = _normalize_user_keyword(keyword)
    shadowed = [_normalize_user_keyword(item) for item in (shadowed_by or []) if _normalize_user_keyword(item)]
    target_max = max(0, int(target_max))
    if not working or not normalized_keyword:
        return {
            "content": working,
            "edited": False,
            "replaced": 0,
            "removedSentences": 0,
            "currentCount": 0,
            "targetMax": target_max,
            "shadowedBy": shadowed,
        }

    removed_sentences = 0
    removed_sentence_fragments: list[str] = []
    rewritten_sentences = 0
    rewritten_sentence_fragments: list[str] = []
    current_count = int(_count_user_keyword_exact_non_overlap(working, user_keywords).get(normalized_keyword) or 0)

    for _ in range(max(0, current_count - target_max)):
        current_count = int(_count_user_keyword_exact_non_overlap(working, user_keywords).get(normalized_keyword) or 0)
        if current_count <= target_max:
            break
        sentence_reduction = _remove_low_signal_keyword_sentence_once(
            working,
            normalized_keyword,
            user_keywords,
            shadowed_by=shadowed,
            role_keyword_policy=role_keyword_policy,
        )
        if not sentence_reduction.get("edited"):
            break
        working = str(sentence_reduction.get("content") or working)
        if str(sentence_reduction.get("mode") or "") == "rewrite":
            rewritten_sentences += 1
            rewritten_sentence = _normalize_sentence_for_compare(sentence_reduction.get("rewrittenSentence") or "")
            if rewritten_sentence:
                rewritten_sentence_fragments.append(rewritten_sentence[:80])
        else:
            removed_sentences += 1
            removed_sentence = _normalize_sentence_for_compare(sentence_reduction.get("removedSentence") or "")
            if removed_sentence:
                removed_sentence_fragments.append(removed_sentence[:80])

    current_count = int(_count_user_keyword_exact_non_overlap(working, user_keywords).get(normalized_keyword) or 0)
    replaced = 0
    if current_count > target_max:
        working, replaced = _replace_last_keyword_occurrences(
            working,
            normalized_keyword,
            current_count - target_max,
            shadowed_by=shadowed,
            role_keyword_policy=role_keyword_policy,
        )
        current_count = int(_count_user_keyword_exact_non_overlap(working, user_keywords).get(normalized_keyword) or 0)

    return {
        "content": working,
        "edited": working != str(content or ""),
        "replaced": replaced,
        "removedSentences": removed_sentences,
        "removedSentenceFragments": removed_sentence_fragments,
        "rewrittenSentences": rewritten_sentences,
        "rewrittenSentenceFragments": rewritten_sentence_fragments,
        "currentCount": current_count,
        "targetMax": target_max,
        "shadowedBy": shadowed,
    }
