"""??? ???? ?? ? ???."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from agents.common.role_keyword_policy import should_block_role_keyword

from .keyword_common import (
    _count_keyword_occurrences_in_h2,
    _count_user_keyword_exact_non_overlap,
    _count_user_keyword_exact_non_overlap_in_body,
    _keyword_tokens,
    _keyword_user_threshold,
    _normalize_user_keyword,
    _parse_keyword_sections,
    count_keyword_coverage,
    count_keyword_occurrences,
    count_keyword_sentence_reflections,
    find_shadowed_user_keywords,
)
from .keyword_context import _is_event_context_text, _is_location_keyword, _is_unsafe_location_context
from .keyword_injection import _find_similar_sentence_in_content, _inject_keyword_into_section
from .keyword_reduction import _reduce_excess_user_keyword_mentions
from .keyword_reference import (
    _append_sentence_to_paragraph,
    _build_role_keyword_reference_sentence,
    _should_allow_keyword_reference_fallback,
    _should_block_role_keyword_reference_sentence,
)


logger = logging.getLogger(__name__)

def _section_priority(section_type: str) -> int:
    if section_type.startswith("body"):
        return 0
    if section_type == "conclusion":
        return 1
    if section_type == "intro":
        return 2
    return 3


def _keyword_state_summary(
    keyword_details: Mapping[str, Any],
    keywords: Sequence[str],
) -> list[Dict[str, int | str]]:
    summary: list[Dict[str, int | str]] = []
    for keyword in keywords:
        info = keyword_details.get(keyword) or {}
        summary.append(
            {
                "keyword": keyword,
                "gate": int(info.get("gateCount") or info.get("count") or info.get("coverage") or 0),
                "expected": int(info.get("expected") or 0),
                "body": int(info.get("bodyCount") or 0),
                "bodyExpected": int(info.get("bodyExpected") or 0),
                "exactShortfall": int(info.get("exactShortfall") or 0),
            }
        )
    return summary


def _select_keyword_section_indexes(
    sections: Sequence[Dict[str, Any]],
    keyword: str,
    needed: int,
    *,
    blocked_indexes: Optional[Sequence[int]] = None,
    allow_existing_mentions: bool = False,
) -> List[int]:
    if not sections or needed <= 0:
        return []

    blocked = {int(item) for item in (blocked_indexes or [])}
    indexed = [(idx, section) for idx, section in enumerate(sections) if idx not in blocked]

    def _location_section_penalty(section_content: str) -> int:
        plain = re.sub(r"<[^>]*>", " ", str(section_content or ""))
        plain = re.sub(r"\s+", " ", plain).strip()
        if _is_event_context_text(plain, keyword=keyword):
            return 0
        if _is_unsafe_location_context(plain):
            return 2
        return 1

    if _is_location_keyword(keyword):
        ranked = sorted(
            indexed,
            key=lambda item: (
                count_keyword_occurrences(str(item[1].get("content") or ""), keyword),
                _location_section_penalty(str(item[1].get("content") or "")),
                _section_priority(str(item[1].get("type") or "")),
                item[0],
            ),
        )
    else:
        ranked = sorted(
            indexed,
            key=lambda item: (
                count_keyword_occurrences(str(item[1].get("content") or ""), keyword),
                _section_priority(str(item[1].get("type") or "")),
                item[0],
            ),
        )
    if not ranked:
        return []

    zero_count_indexes = [
        idx
        for idx, section in ranked
        if count_keyword_occurrences(str(section.get("content") or ""), keyword) <= 0
    ]
    if zero_count_indexes:
        return zero_count_indexes[:needed]
    if not allow_existing_mentions:
        return []

    chosen: list[int] = []
    for idx, _section in ranked:
        if idx in chosen:
            continue
        chosen.append(idx)
        if len(chosen) >= needed:
            break
    return chosen[:needed]

def enforce_keyword_requirements(
    content: str,
    user_keywords: Optional[Sequence[str]] = None,
    auto_keywords: Optional[Sequence[str]] = None,
    target_word_count: Optional[int] = None,
    title_text: str = "",
    body_min_overrides: Optional[Mapping[str, int]] = None,
    user_keyword_expected_overrides: Optional[Mapping[str, int]] = None,
    user_keyword_max_overrides: Optional[Mapping[str, int]] = None,
    skip_user_keywords: Optional[Sequence[str]] = None,
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
    max_iterations: int = 2,
) -> Dict[str, Any]:
    working_content = str(content or "")
    user_keywords = [_normalize_user_keyword(item) for item in (user_keywords or []) if _normalize_user_keyword(item)]
    auto_keywords = [item for item in (auto_keywords or []) if item]
    skipped_user_keyword_set = {
        _normalize_user_keyword(item)
        for item in (skip_user_keywords or [])
        if _normalize_user_keyword(item)
    }

    def _keyword_count_snapshot(text: str) -> Dict[str, int]:
        return {
            keyword: count_keyword_occurrences(text, keyword)
            for keyword in user_keywords
        }

    def _finalize_response(payload: Dict[str, Any]) -> Dict[str, Any]:
        if user_keywords:
            logger.info(
                "[enforce_keyword_requirements] exit keyword_counts=%s",
                _keyword_count_snapshot(str(payload.get("content") or "")),
            )
        return payload

    def _has_pending_user_keyword_work(keyword_details: Mapping[str, Any]) -> bool:
        for keyword in user_keywords:
            keyword_info = keyword_details.get(keyword) or {}
            current_count = int(
                keyword_info.get("exclusiveCount")
                or keyword_info.get("count")
                or keyword_info.get("coverage")
                or 0
            )
            max_allowed = int(keyword_info.get("max") or _keyword_user_threshold(len(user_keywords))[1])
            if current_count > max_allowed:
                return True
            if keyword in skipped_user_keyword_set:
                continue

            expected = int(keyword_info.get("expected") or _keyword_user_threshold(len(user_keywords))[0])
            gate_count = int(keyword_info.get("gateCount") or keyword_info.get("count") or keyword_info.get("coverage") or 0)
            deficit = max(0, expected - gate_count)
            body_expected = int(keyword_info.get("bodyExpected") or 0)
            body_count = int(keyword_info.get("bodyCount") or 0)
            body_deficit = max(0, body_expected - body_count)
            exact_shortfall = int(keyword_info.get("exactShortfall") or 0)
            if max(deficit, body_deficit, exact_shortfall) > 0:
                return True
        return False

    initial_result = validate_keyword_insertion(
        working_content,
        user_keywords,
        auto_keywords,
        target_word_count,
        title_text=title_text,
        body_min_overrides=body_min_overrides,
        user_keyword_expected_overrides=user_keyword_expected_overrides,
        user_keyword_max_overrides=user_keyword_max_overrides,
    )
    if not working_content or not user_keywords:
        return _finalize_response({
            "content": working_content,
            "edited": False,
            "insertions": [],
            "keywordResult": initial_result,
        })
    initial_details = (initial_result.get("details") or {}).get("keywords") or {}
    logger.info(
        "[enforce_keyword_requirements] entry keyword_counts=%s",
        _keyword_count_snapshot(working_content),
    )
    logger.info(
        "Keyword enforcement start: states=%s",
        _keyword_state_summary(initial_details, user_keywords),
    )
    initial_exact_preference_pending = any(
        int(((initial_details.get(keyword) or {}).get("exactShortfall")) or 0) > 0
        for keyword in user_keywords
        if keyword not in skipped_user_keyword_set
    )
    initial_user_repair_pending = _has_pending_user_keyword_work(initial_details)
    if not initial_user_repair_pending:
        return _finalize_response({
            "content": working_content,
            "edited": False,
            "insertions": [],
            "keywordResult": initial_result,
        })
    if initial_result.get("valid") and not initial_exact_preference_pending:
        return _finalize_response({
            "content": working_content,
            "edited": False,
            "insertions": [],
            "keywordResult": initial_result,
        })

    insertions: list[Dict[str, Any]] = []
    reductions: list[Dict[str, Any]] = []
    rewrite_requests: list[Dict[str, Any]] = []
    per_keyword_insertions: Dict[str, int] = {}
    locked_section_indexes_by_keyword: Dict[str, set[int]] = {}
    current_result = initial_result
    shadowed_map = find_shadowed_user_keywords(user_keywords)

    for iteration in range(max_iterations):
        details = (current_result.get("details") or {}).get("keywords") or {}
        sections = _parse_keyword_sections(working_content)
        if not details or not sections:
            break
        if not _has_pending_user_keyword_work(details):
            break

        logger.info(
            "Keyword enforcement iteration=%s states=%s",
            iteration + 1,
            _keyword_state_summary(details, user_keywords),
        )

        reductions_applied = False
        for keyword in user_keywords:
            keyword_info = details.get(keyword) or {}
            current_count = int(
                keyword_info.get("exclusiveCount")
                or keyword_info.get("count")
                or keyword_info.get("coverage")
                or 0
            )
            max_allowed = int(keyword_info.get("max") or _keyword_user_threshold(len(user_keywords))[1])
            excess = max(0, current_count - max_allowed)
            if excess <= 0:
                continue

            reduced = _reduce_excess_user_keyword_mentions(
                working_content,
                keyword,
                user_keywords,
                target_max=max_allowed,
                shadowed_by=shadowed_map.get(keyword),
                role_keyword_policy=role_keyword_policy,
            )
            reductions.append(
                {
                    "keyword": keyword,
                    "excess": excess,
                    "replaced": int(reduced.get("replaced") or 0),
                    "removedSentences": int(reduced.get("removedSentences") or 0),
                    "rewrittenSentences": int(reduced.get("rewrittenSentences") or 0),
                    "targetMax": max_allowed,
                    "resultCount": int(reduced.get("currentCount") or current_count),
                    "shadowedBy": list(reduced.get("shadowedBy") or []),
                    "removedSentenceFragments": list(reduced.get("removedSentenceFragments") or []),
                    "rewrittenSentenceFragments": list(reduced.get("rewrittenSentenceFragments") or []),
                    "edited": bool(reduced.get("edited")),
                }
            )
            if reduced.get("edited"):
                working_content = str(reduced.get("content") or working_content)
                reductions_applied = True

        if reductions_applied:
            current_result = validate_keyword_insertion(
                working_content,
                user_keywords,
                auto_keywords,
                target_word_count,
                title_text=title_text,
                body_min_overrides=body_min_overrides,
                user_keyword_expected_overrides=user_keyword_expected_overrides,
                user_keyword_max_overrides=user_keyword_max_overrides,
            )
            if current_result.get("valid"):
                break
            continue

        insertion_plan: Dict[int, List[Dict[str, Any]]] = {}
        needs_fix = False

        for keyword in user_keywords:
            if keyword in skipped_user_keyword_set:
                continue
            keyword_info = details.get(keyword) or {}
            expected = int(keyword_info.get("expected") or _keyword_user_threshold(len(user_keywords))[0])
            gate_count = int(keyword_info.get("gateCount") or keyword_info.get("count") or keyword_info.get("coverage") or 0)
            deficit = max(0, expected - gate_count)
            body_expected = int(keyword_info.get("bodyExpected") or 0)
            body_count = int(keyword_info.get("bodyCount") or 0)
            body_deficit = max(0, body_expected - body_count)
            exact_shortfall = int(keyword_info.get("exactShortfall") or 0)
            total_deficit = max(deficit, body_deficit, exact_shortfall)
            if total_deficit <= 0:
                continue

            needs_fix = True
            planned_indexes: list[int] = []
            locked_indexes = set(locked_section_indexes_by_keyword.get(keyword) or set())
            if body_deficit > 0:
                body_sections = [
                    (idx, section)
                    for idx, section in enumerate(sections)
                    if str(section.get("type") or "").startswith("body")
                    and idx not in locked_indexes
                ]
                ranked_body = sorted(
                    body_sections,
                    key=lambda item: (
                        count_keyword_occurrences(str(item[1].get("content") or ""), keyword),
                        item[0],
                    ),
                )
                for section_idx, section in ranked_body:
                    section_count = count_keyword_occurrences(str(section.get("content") or ""), keyword)
                    if section_count > 0:
                        continue
                    planned_indexes.append(section_idx)
                    locked_indexes.add(section_idx)
                    if len(planned_indexes) >= body_deficit:
                        break

            remaining_deficit = max(0, total_deficit - len(planned_indexes))
            if remaining_deficit > 0:
                additional_indexes = _select_keyword_section_indexes(
                    sections,
                    keyword,
                    remaining_deficit,
                    blocked_indexes=locked_indexes,
                    allow_existing_mentions=False,
                )
                planned_indexes.extend(additional_indexes)
                locked_indexes.update(additional_indexes)

            unresolved_deficit = max(0, total_deficit - len(planned_indexes))
            if unresolved_deficit > 0:
                rewrite_requests.append(
                    {
                        "keyword": keyword,
                        "section": -1,
                        "sectionType": "any",
                        "variantIndex": int(per_keyword_insertions.get(keyword, 0)),
                        "strategy": "section_rewrite_required",
                        "reason": "no_safe_target_section",
                        "remainingDeficit": unresolved_deficit,
                    }
                )

            for section_idx in planned_indexes:
                if section_idx < 0 or section_idx >= len(sections):
                    continue
                section = sections[section_idx]
                variant_index = per_keyword_insertions.get(keyword, 0)
                per_keyword_insertions[keyword] = variant_index + 1
                locked_section_indexes_by_keyword.setdefault(keyword, set()).add(section_idx)
                insertion_plan.setdefault(section_idx, []).append(
                    {
                        "keyword": keyword,
                        "section": section_idx,
                        "sectionType": section.get("type"),
                        "variantIndex": variant_index,
                    }
                )

        if not needs_fix or not insertion_plan:
            break

        applied_in_iteration = 0
        for section_idx in sorted(insertion_plan.keys(), reverse=True):
            if section_idx < 0 or section_idx >= len(sections):
                continue
            section = sections[section_idx]
            start_index = int(section.get("startIndex") or 0)
            end_index = int(section.get("endIndex") or 0)
            if end_index < start_index:
                continue

            payload = insertion_plan[section_idx]
            section_content = working_content[start_index:end_index]
            applied_payload: list[Dict[str, Any]] = []
            for item in payload:
                updated_section, edited, applied_sentence = _inject_keyword_into_section(
                    section_content,
                    str(item.get("keyword") or ""),
                    str(item.get("sectionType") or ""),
                    int(item.get("variantIndex") or 0),
                    allow_reference_fallback=_should_allow_keyword_reference_fallback(
                        working_content,
                        str(item.get("keyword") or ""),
                        user_keywords,
                        role_keyword_policy=role_keyword_policy,
                    ),
                    existing_content=working_content,
                    role_keyword_policy=role_keyword_policy,
                    section_index=section_idx,
                )
                if not edited:
                    rewrite_requests.append(
                        {
                            "keyword": str(item.get("keyword") or ""),
                            "section": section_idx,
                            "sectionType": str(item.get("sectionType") or ""),
                            "variantIndex": int(item.get("variantIndex") or 0),
                            "strategy": "section_rewrite_required",
                            "reason": "no_safe_keyword_variant",
                        }
                    )
                    continue
                section_content = updated_section
                item["sentence"] = applied_sentence
                item["strategy"] = "contextual_section_rewrite"
                applied_payload.append(item)
                applied_in_iteration += 1
            if not applied_payload:
                continue
            working_content = working_content[:start_index] + section_content + working_content[end_index:]
            insertions.extend(applied_payload)

        if applied_in_iteration <= 0:
            break

        current_result = validate_keyword_insertion(
            working_content,
            user_keywords,
            auto_keywords,
            target_word_count,
            title_text=title_text,
            body_min_overrides=body_min_overrides,
            user_keyword_expected_overrides=user_keyword_expected_overrides,
            user_keyword_max_overrides=user_keyword_max_overrides,
        )
        current_details = (current_result.get("details") or {}).get("keywords") or {}
        exact_preference_pending = any(
            int(((current_details.get(keyword) or {}).get("exactShortfall")) or 0) > 0
            for keyword in user_keywords
            if keyword not in skipped_user_keyword_set
        )
        if current_result.get("valid") and not exact_preference_pending:
            break

    return _finalize_response({
        "content": working_content,
        "edited": working_content != str(content or ""),
        "insertions": insertions,
        "reductions": reductions,
        "rewriteRequests": rewrite_requests,
        "keywordResult": current_result,
    })


def build_fallback_draft(params: Optional[Dict[str, Any]] = None) -> str:
    params = params or {}
    topic = str(params.get("topic") or "현안").strip()
    full_name = str(params.get("fullName") or "").strip()
    user_keywords = list(params.get("userKeywords") or [])

    greeting = f"존경하는 시민 여러분, {full_name}입니다." if full_name else "존경하는 시민 여러분."
    keyword_sentences = [f"{keyword}와 관련한 현황을 점검합니다." for keyword in user_keywords[:5] if keyword]
    keyword_paragraph = f"<p>{' '.join(keyword_sentences)}</p>" if keyword_sentences else ""

    blocks = [
        f"<p>{greeting} {topic}에 대해 핵심 현황을 정리합니다.</p>",
        "<h2>현안 개요</h2>",
        f"<p>{topic}의 구조적 배경과 최근 흐름을 객관적으로 살펴봅니다.</p>",
        keyword_paragraph,
        "<h2>핵심 쟁점</h2>",
        "<p>원인과 영향을 구분해 사실관계를 정리하고, 논의가 필요한 지점을 확인합니다.</p>",
        "<h2>확인 과제</h2>",
        "<p>추가 확인이 필요한 데이터와 점검 과제를 중심으로 정리합니다.</p>",
        f"<p>{full_name} 드림</p>" if full_name else "",
    ]
    return "\n".join(block for block in blocks if block)


def force_insert_preferred_exact_keywords(
    content: str,
    user_keywords: List[str],
    keyword_validation: Dict[str, Any],
    skip_user_keywords: Optional[Sequence[str]] = None,
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
) -> str:
    """정확 일치 1회 선호가 남은 다중 어절 키워드를 마지막으로 1회만 보강한다."""
    working = str(content or "")
    skipped_user_keyword_set = {
        _normalize_user_keyword(item)
        for item in (skip_user_keywords or [])
        if _normalize_user_keyword(item)
    }
    paragraph_matches = list(re.finditer(r"<p\b[^>]*>([\s\S]*?)</p\s*>", working, re.IGNORECASE))
    if not working or not paragraph_matches:
        return working

    for keyword in (user_keywords or []):
        normalized = _normalize_user_keyword(keyword)
        if not normalized or normalized in skipped_user_keyword_set:
            continue
        if should_block_role_keyword(role_keyword_policy, normalized):
            continue

        info = keyword_validation.get(normalized) if isinstance(keyword_validation, dict) else None
        if not isinstance(info, dict):
            continue
        if int(info.get("exactPreferredMin") or 0) <= 0:
            continue
        if int(info.get("exactShortfall") or 0) <= 0:
            continue
        if count_keyword_occurrences(working, normalized) > 0:
            continue

        inserted = False
        for paragraph_index, paragraph_match in enumerate(paragraph_matches):
            inner = str(paragraph_match.group(1) or "")
            plain = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", inner)).strip()
            if len(plain) < 20 or normalized in plain:
                continue

            section_type = "conclusion" if paragraph_index == len(paragraph_matches) - 1 else "body"
            sentence = _build_role_keyword_reference_sentence(
                normalized,
                section_type,
                0,
                role_keyword_policy=role_keyword_policy,
            )
            if not sentence:
                continue
            if _should_block_role_keyword_reference_sentence(
                sentence,
                context_html=working,
                keyword=normalized,
                role_keyword_policy=role_keyword_policy,
            ):
                continue

            updated_inner = _append_sentence_to_paragraph(inner, sentence)
            if updated_inner == inner:
                continue
            working = (
                working[: paragraph_match.start(1)]
                + updated_inner
                + working[paragraph_match.end(1) :]
            )
            paragraph_matches = list(re.finditer(r"<p\b[^>]*>([\s\S]*?)</p\s*>", working, re.IGNORECASE))
            inserted = True
            break

        if not inserted:
            continue

    return working


def validate_keyword_insertion(
    content: str,
    user_keywords: Optional[Sequence[str]] = None,
    auto_keywords: Optional[Sequence[str]] = None,
    target_word_count: Optional[int] = None,
    title_text: str = "",
    body_min_overrides: Optional[Mapping[str, int]] = None,
    user_keyword_expected_overrides: Optional[Mapping[str, int]] = None,
    user_keyword_max_overrides: Optional[Mapping[str, int]] = None,
) -> Dict[str, Any]:
    _ = target_word_count
    user_keywords = [item for item in (user_keywords or []) if item]
    auto_keywords = [item for item in (auto_keywords or []) if item]
    plain_text = re.sub(r"\s", "", re.sub(r"<[^>]*>", "", content or ""))
    actual_word_count = len(plain_text)

    user_min_count, user_max_count = _keyword_user_threshold(len(user_keywords))
    auto_min_count = 1

    results: Dict[str, Dict[str, Any]] = {}
    all_valid = True
    user_exact_counts = _count_user_keyword_exact_non_overlap(content, user_keywords)
    user_title_exact_counts = _count_user_keyword_exact_non_overlap(title_text or "", user_keywords)
    user_body_exact_counts = _count_user_keyword_exact_non_overlap_in_body(content, user_keywords)

    for keyword in user_keywords:
        content_exact_count = int(user_exact_counts.get(keyword) or 0)
        raw_count = count_keyword_occurrences(content, keyword)
        variant_coverage_count = count_keyword_coverage(content, keyword)
        title_count = int(user_title_exact_counts.get(keyword) or 0)
        h2_count = _count_keyword_occurrences_in_h2(content, keyword)
        body_count = int(user_body_exact_counts.get(keyword) or 0)
        total_exact_count = content_exact_count + title_count
        total_raw_count = raw_count + title_count
        effective_expected = int(user_min_count)
        if isinstance(user_keyword_expected_overrides, Mapping):
            override_expected = user_keyword_expected_overrides.get(keyword)
            if override_expected is not None:
                try:
                    effective_expected = max(0, int(override_expected))
                except (TypeError, ValueError):
                    effective_expected = int(user_min_count)
        effective_max = int(user_max_count)
        if isinstance(user_keyword_max_overrides, Mapping):
            override_max = user_keyword_max_overrides.get(keyword)
            if override_max is not None:
                try:
                    effective_max = max(effective_expected, int(override_max))
                except (TypeError, ValueError):
                    effective_max = max(effective_expected, int(user_max_count))

        derived_body_expected = max(0, int(effective_expected) - int(title_count) - int(h2_count))
        override_value = None
        if isinstance(body_min_overrides, Mapping):
            override_value = body_min_overrides.get(keyword)
        if override_value is not None:
            try:
                derived_body_expected = max(0, int(override_value))
            except (TypeError, ValueError):
                derived_body_expected = max(0, derived_body_expected)
        sentence_coverage_count = (
            count_keyword_sentence_reflections(content, keyword)
            + count_keyword_sentence_reflections(title_text or "", keyword)
        )
        gate_count = max(total_exact_count, sentence_coverage_count)
        coverage_count = max(total_exact_count, variant_coverage_count + title_count, sentence_coverage_count)
        preferred_exact_min = 1 if len(_keyword_tokens(keyword)) >= 2 and effective_expected > 0 else 0
        exact_shortfall = max(0, preferred_exact_min - total_exact_count)
        # 사용자 입력 키워드는 부족 판정은 gate count, 과다 판정은 exact count 기준으로 검증한다.
        is_under_min = gate_count < effective_expected
        is_over_max = total_exact_count > effective_max
        is_under_body_min = body_count < derived_body_expected
        is_valid = (not is_under_min) and (not is_over_max) and (not is_under_body_min)
        results[keyword] = {
            "count": total_exact_count,
            "exactCount": total_raw_count,
            "exclusiveCount": total_exact_count,
            "rawCount": total_raw_count,
            "coverage": coverage_count,
            "gateCount": gate_count,
            "sentenceCoverageCount": sentence_coverage_count,
            "expected": effective_expected,
            "max": effective_max,
            "titleCount": title_count,
            "subheadingCount": h2_count,
            "bodyCount": body_count,
            "bodyExpected": derived_body_expected,
            "contentCount": content_exact_count,
            "contentExactCount": raw_count,
            "underMin": is_under_min,
            "overMax": is_over_max,
            "underBodyMin": is_under_body_min,
            "exactPreferredMin": preferred_exact_min,
            "exactShortfall": exact_shortfall,
            "exactPreferredMet": exact_shortfall <= 0,
            "valid": is_valid,
            "type": "user",
        }
        if not is_valid:
            all_valid = False

    for keyword in auto_keywords:
        exact_count = count_keyword_occurrences(content, keyword)
        coverage_count = count_keyword_coverage(content, keyword)
        is_valid = coverage_count >= auto_min_count
        results[keyword] = {
            "count": coverage_count,
            "exactCount": exact_count,
            "coverage": coverage_count,
            "expected": auto_min_count,
            "valid": is_valid,
            "type": "auto",
        }

    all_keywords = [*user_keywords, *auto_keywords]
    total_keyword_chars = 0
    for keyword in all_keywords:
        occurrences = count_keyword_coverage(content, keyword)
        total_keyword_chars += len(re.sub(r"\s", "", keyword)) * occurrences
    density = (total_keyword_chars / actual_word_count * 100) if actual_word_count else 0

    return {
        "valid": all_valid,
        "details": {
            "keywords": results,
            "density": {
                "value": f"{density:.2f}",
                "valid": True,
                "optimal": 1.5 <= density <= 2.5,
            },
            "wordCount": actual_word_count,
        },
    }



def force_insert_insufficient_keywords(
    content: str,
    user_keywords: List[str],
    keyword_validation: Dict[str, Any],
    skip_user_keywords: Optional[Sequence[str]] = None,
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
) -> str:
    """최종 gate 실패(insufficient) 전용 last-resort 삽입.

    섹션 구조(`<p>` 태그 존재 여부)와 관계없이 콘텐츠 전체에서
    마지막으로 적절한 `<p>` 단락을 찾아 직접 문장을 추가한다.
    `_apply_content_repair()` 예산 체크를 우회하는 최후 안전망.
    """
    working = str(content or "")
    skipped_user_keyword_set = {
        _normalize_user_keyword(item)
        for item in (skip_user_keywords or [])
        if _normalize_user_keyword(item)
    }
    for keyword in (user_keywords or []):
        normalized = _normalize_user_keyword(keyword)
        if not normalized:
            continue
        if normalized in skipped_user_keyword_set:
            continue
        info = keyword_validation.get(normalized) if isinstance(keyword_validation, dict) else None
        if not isinstance(info, dict):
            continue
        if str(info.get("status") or "").strip().lower() != "insufficient":
            continue
        if should_block_role_keyword(role_keyword_policy, normalized):
            continue
        min_required = max(1, int((info or {}).get("expected") or 1))
        sentence = ""
        if _should_allow_keyword_reference_fallback(
            working,
            normalized,
            user_keywords,
            role_keyword_policy=role_keyword_policy,
        ):
            sentence = _build_role_keyword_reference_sentence(
                normalized,
                "body",
                0,
                role_keyword_policy=role_keyword_policy,
            )
        if not sentence:
            continue
        if _should_block_role_keyword_reference_sentence(
            sentence,
            context_html=working,
            keyword=normalized,
            role_keyword_policy=role_keyword_policy,
        ):
            continue
        if _find_similar_sentence_in_content(sentence, working):
            continue

        # min_required 충족할 때까지 반복 삽입 (최대 5회 guard)
        for _attempt in range(5):
            if count_keyword_occurrences(working, normalized) >= min_required:
                break
            p_matches = list(re.finditer(r"<p\b[^>]*>([\s\S]*?)</p\s*>", working, re.IGNORECASE))
            if not p_matches:
                break
            applied = False
            for target_match in reversed(p_matches):
                plain = re.sub(r"<[^>]*>", " ", target_match.group(1) or "")
                plain = re.sub(r"\s+", " ", plain).strip()
                if len(plain) >= 20 and normalized not in plain:
                    inner = str(target_match.group(1) or "")
                    updated_inner = _append_sentence_to_paragraph(inner, sentence)
                    if updated_inner == inner:
                        continue
                    if _find_similar_sentence_in_content(sentence, working, exclude_sentences=[plain]):
                        continue
                    working = (
                        working[: target_match.start(1)]
                        + updated_inner
                        + working[target_match.end(1):]
                    )
                    applied = True
                    break
            if not applied:
                break

    return working
