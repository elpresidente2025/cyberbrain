"""??? ??/?? ?? ??."""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional, Sequence

from agents.common.role_keyword_policy import (
    build_role_keyword_intent_text,
    get_person_reference_fact,
    is_role_keyword as is_role_keyword_common,
    should_block_role_keyword,
    should_render_role_keyword_as_intent,
)

from ._shared import _strip_html
from .keyword_common import (
    KEYWORD_REFERENCE_MARKERS,
    KEYWORD_REFERENCE_VERBS,
    PERSON_ROLE_REDUCTION_PATTERN_TEMPLATE,
    ROLE_SURFACE_PATTERN,
    _normalize_user_keyword,
    build_keyword_variants,
)

def _is_role_keyword(keyword: str) -> bool:
    normalized_keyword = re.sub(r"\s+", " ", str(keyword or "")).strip()
    return bool(normalized_keyword and is_role_keyword_common(normalized_keyword))


def _build_role_keyword_reference_sentence(
    keyword: str,
    section_type: str,
    variant_index: int = 0,
    *,
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
) -> str:
    normalized_keyword = re.sub(r"\s+", " ", str(keyword or "")).strip()
    if not normalized_keyword:
        return ""
    if should_block_role_keyword(role_keyword_policy, normalized_keyword):
        return ""

    if _is_role_keyword(normalized_keyword) and should_render_role_keyword_as_intent(
        role_keyword_policy,
        normalized_keyword,
    ):
        context = "conclusion" if str(section_type or "") == "conclusion" else "body"
        return build_role_keyword_intent_text(
            normalized_keyword,
            context=context,
            variant_index=variant_index,
        )

    if str(section_type or "") == "conclusion":
        templates = (
            f"마지막까지 '{normalized_keyword}' 검색어도 함께 주목받고 있습니다.",
            f"이 흐름 속에서 '{normalized_keyword}' 키워드도 계속 거론되고 있습니다.",
            f"끝까지 '{normalized_keyword}' 표현 역시 함께 언급되고 있습니다.",
        )
    else:
        templates = (
            f"온라인에서는 '{normalized_keyword}' 검색어도 함께 거론되고 있습니다.",
            f"시민들 사이에서는 '{normalized_keyword}' 키워드 역시 자주 언급됩니다.",
            f"이 이슈를 두고 '{normalized_keyword}' 표현도 함께 주목받고 있습니다.",
        )
    return templates[variant_index % len(templates)]


def _looks_like_keyword_reference_sentence(sentence: Any) -> bool:
    normalized_sentence = _normalize_sentence_for_compare(sentence)
    if not normalized_sentence:
        return False
    if re.search(
        rf"[가-힣]{{2,8}}\s*{ROLE_SURFACE_PATTERN}\s*(?:출마(?:설|론|가능성)?|후보론|거론)",
        normalized_sentence,
        re.IGNORECASE,
    ):
        return True
    return (
        any(marker in normalized_sentence for marker in KEYWORD_REFERENCE_MARKERS)
        and any(verb in normalized_sentence for verb in KEYWORD_REFERENCE_VERBS)
    )


def _normalize_sentence_for_compare(text: Any) -> str:
    normalized = _strip_html(str(text or ""))
    if not normalized:
        return ""
    normalized = (
        normalized.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"[\"']", "", normalized)
    normalized = re.sub(r"[.!?。]+$", "", normalized).strip()
    return normalized


def _should_block_role_keyword_reference_sentence(
    sentence: Any,
    *,
    context_html: str = "",
    keyword: str = "",
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
) -> bool:
    raw_sentence = str(sentence or "").strip()
    normalized_sentence = _normalize_sentence_for_compare(raw_sentence)
    normalized_keyword = _normalize_user_keyword(keyword)
    if not raw_sentence or not normalized_sentence:
        return True
    if not normalized_keyword:
        return False
    if should_block_role_keyword(role_keyword_policy, normalized_keyword):
        return True
    if not _is_role_keyword(normalized_keyword):
        return False

    plain_sentence = _strip_html(raw_sentence)
    dequoted_sentence = re.sub(r"[\"'“”‘’]", "", plain_sentence)
    if any(marker in normalized_sentence for marker in KEYWORD_REFERENCE_MARKERS):
        return True
    if _looks_like_keyword_reference_sentence(normalized_sentence):
        return True

    intent_pattern = re.compile(
        rf"{re.escape(normalized_keyword)}\s*(?:출마(?:설|론|가능성)?|후보론|거론|언급|주목)",
        re.IGNORECASE,
    )
    if intent_pattern.search(dequoted_sentence):
        return True

    person_name = str(normalized_keyword.split(" ", 1)[0] or "").strip()
    if person_name:
        role_intent_pattern = re.compile(
            rf"{re.escape(person_name)}\s*(?:현\s*|전\s*)?(?:{ROLE_SURFACE_PATTERN})\s*(?:출마(?:설|론|가능성)?|후보론|거론|언급|주목)",
            re.IGNORECASE,
        )
        if role_intent_pattern.search(dequoted_sentence):
            return True

    plain_context = _strip_html(context_html)
    if plain_context:
        if _count_keyword_reference_sentences_in_content(plain_context) >= 1:
            return True
        if person_name:
            normalized_context = _normalize_sentence_for_compare(plain_context)
            context_role_intent_pattern = re.compile(
                rf"{re.escape(person_name)}\s*(?:현\s*|전\s*)?(?:{ROLE_SURFACE_PATTERN}).*(?:출마(?:설|론|가능성)?|후보론|거론|언급|주목)",
                re.IGNORECASE,
            )
            if context_role_intent_pattern.search(normalized_context):
                return True

    return False


def _looks_like_compact_person_keyword(keyword: Any) -> bool:
    normalized = re.sub(r"\s+", "", str(keyword or "")).strip()
    if len(normalized) < 2 or len(normalized) > 4:
        return False
    return bool(re.fullmatch(r"[가-힣]{2,4}", normalized))


def _compact_person_surname(keyword: Any) -> str:
    normalized = re.sub(r"\s+", "", str(keyword or "")).strip()
    if not _looks_like_compact_person_keyword(normalized):
        return ""
    return normalized[:1]


def _extract_person_name_from_keyword(keyword: Any) -> str:
    normalized = re.sub(r"\s+", " ", str(keyword or "")).strip()
    if not normalized:
        return ""
    first_token = str(normalized.split(" ", 1)[0] or "").strip()
    if _looks_like_compact_person_keyword(first_token):
        return first_token
    collapsed = re.sub(r"\s+", "", normalized)
    if _looks_like_compact_person_keyword(collapsed):
        return collapsed
    return ""


def _normalize_reduced_role_label(role_text: Any) -> str:
    normalized = re.sub(r"\s+", "", str(role_text or "")).strip()
    if not normalized:
        return ""
    if normalized.endswith("예비후보"):
        return "예비후보"
    if normalized.endswith("도지사") or normalized == "지사":
        return "지사"
    if normalized.endswith("국회의원") or normalized.endswith("의원"):
        return "의원"
    if normalized.endswith("시장"):
        return "시장"
    if normalized.endswith("위원장"):
        return "위원장"
    if normalized.endswith("대표"):
        return "대표"
    if normalized.endswith("장관"):
        return "장관"
    if normalized.endswith("후보"):
        return "후보"
    return ""


def _extract_geographic_role_label(role_text: Any) -> str:
    normalized = re.sub(r"\s+", "", str(role_text or "")).strip()
    if not normalized:
        return ""
    if re.fullmatch(r"[가-힣]{1,8}도지사", normalized):
        return normalized
    if re.fullmatch(r"[가-힣]{1,8}시장", normalized) and normalized != "시장":
        return normalized
    return ""


def _build_short_role_reference(keyword: Any, role_text: Any) -> str:
    surname = _compact_person_surname(_extract_person_name_from_keyword(keyword) or keyword)
    reduced_role = _normalize_reduced_role_label(role_text)
    if not surname or not reduced_role:
        return ""
    return f"{surname} {reduced_role}"


def _candidate_reference_labels(fact: Mapping[str, Any]) -> list[str]:
    label = _normalize_user_keyword(fact.get("explicitCandidateLabel") or "")
    if label == "예비후보":
        return ["예비후보", "후보"]
    if label == "후보":
        return ["후보"]
    return []


def _build_generic_role_reference(role_text: Any, *, allow_candidate_label: bool = False) -> str:
    reduced_role = _normalize_reduced_role_label(role_text)
    if not reduced_role:
        return "상대"
    generic_map = {
        "지사": "상대 지사",
        "시장": "상대 시장",
        "위원장": "상대 위원장",
        "대표": "상대 대표",
        "장관": "상대 장관",
    }
    if reduced_role in {"예비후보", "후보"}:
        return "상대 후보" if allow_candidate_label else "상대"
    return generic_map.get(reduced_role, "상대")


def _has_batchim(text: Any) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    last_char = normalized[-1]
    if not ("가" <= last_char <= "힣"):
        return False
    return (ord(last_char) - ord("가")) % 28 != 0


def _normalize_reduced_reference_particles(text: Any) -> str:
    base = str(text or "")
    if not base:
        return ""

    particle_pairs = {
        ("은", "는"): ("은", "는"),
        ("이", "가"): ("이", "가"),
        ("을", "를"): ("을", "를"),
        ("과", "와"): ("과", "와"),
    }
    role_pattern = r"(?:의원|지사|시장|위원장|대표|장관|예비후보|후보)"
    pattern = re.compile(
        rf"(?P<lemma>(?:[가-힣]{{1,4}}\s+)?{role_pattern})(?P<particle>은|는|이|가|을|를|과|와)"
    )

    def _replace(match: re.Match[str]) -> str:
        lemma = str(match.group("lemma") or "")
        particle = str(match.group("particle") or "")
        for pair in particle_pairs.values():
            if particle not in pair:
                continue
            selected = pair[0] if _has_batchim(lemma) else pair[1]
            return f"{lemma}{selected}"
        return match.group(0)

    return pattern.sub(_replace, base)


def _build_person_role_reduction_pattern(keyword: Any) -> Optional[re.Pattern[str]]:
    normalized_keyword = _normalize_user_keyword(keyword)
    if not normalized_keyword:
        return None
    return re.compile(
        PERSON_ROLE_REDUCTION_PATTERN_TEMPLATE.format(keyword=re.escape(normalized_keyword)),
    )


def _build_person_role_reduction_candidates(
    keyword: Any,
    role_text: Any,
    *,
    preserve_full_name: bool,
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
) -> list[str]:
    normalized_keyword = _normalize_user_keyword(keyword)
    person_name = _extract_person_name_from_keyword(normalized_keyword) or normalized_keyword
    reference_fact = get_person_reference_fact(role_keyword_policy, person_name)
    candidate_labels = _candidate_reference_labels(reference_fact)
    base_role_text = _normalize_user_keyword(reference_fact.get("sourceRole") or "") or str(role_text or "")
    generic_base_role_text = base_role_text or (candidate_labels[0] if candidate_labels else "")
    reduced_role = _normalize_reduced_role_label(base_role_text)
    geographic_role = _extract_geographic_role_label(base_role_text)
    surname = _compact_person_surname(person_name)

    candidates: list[str] = []

    def _append(candidate: str) -> None:
        cleaned = _normalize_user_keyword(candidate)
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    for candidate_label in candidate_labels:
        if preserve_full_name and person_name:
            _append(f"{person_name} {candidate_label}")
        if surname:
            _append(f"{surname} {candidate_label}")
    if preserve_full_name and person_name and reduced_role:
        _append(f"{person_name} {reduced_role}")
    if surname and reduced_role:
        _append(f"{surname} {reduced_role}")
    if surname and geographic_role:
        _append(f"{surname} {geographic_role}")
    _append(_build_generic_role_reference(generic_base_role_text, allow_candidate_label=bool(candidate_labels)))
    return candidates


def _build_keyword_replacement_pool(
    keyword: str,
    *,
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
) -> list[str]:
    normalized_keyword = _normalize_user_keyword(keyword)
    if not normalized_keyword:
        return ["이 흐름"]
    person_name = _extract_person_name_from_keyword(normalized_keyword) or (
        normalized_keyword if _looks_like_compact_person_keyword(normalized_keyword) else ""
    )
    reference_fact = get_person_reference_fact(role_keyword_policy, person_name)
    candidate_labels = _candidate_reference_labels(reference_fact)
    generic_base_role_text = _normalize_user_keyword(reference_fact.get("sourceRole") or "") or (
        candidate_labels[0] if candidate_labels else ""
    )
    short_reference = _build_short_role_reference(
        person_name or normalized_keyword,
        generic_base_role_text,
    )
    generic_reference = _build_generic_role_reference(
        generic_base_role_text,
        allow_candidate_label=bool(candidate_labels),
    )
    if _looks_like_compact_person_keyword(normalized_keyword):
        safe_person_references: list[str] = []
        if short_reference and short_reference != normalized_keyword:
            safe_person_references.append(short_reference)
        if generic_reference not in {"", "상대"} and generic_reference not in safe_person_references:
            safe_person_references.append(generic_reference)
        return safe_person_references
    if _is_role_keyword(normalized_keyword):
        safe_role_references: list[str] = []
        if short_reference and short_reference != normalized_keyword:
            safe_role_references.append(short_reference)
        if generic_reference not in {"", "상대"} and generic_reference not in safe_role_references:
            safe_role_references.append(generic_reference)
        return safe_role_references

    variants = build_keyword_variants(normalized_keyword)
    deduped: list[str] = []
    seen: set[str] = set()
    extras = []
    if short_reference and short_reference != normalized_keyword:
        extras.append(short_reference)
    if generic_reference != "상대" and generic_reference not in extras:
        extras.append(generic_reference)
    for item in [*extras, *variants]:
        normalized_item = _normalize_user_keyword(item)
        if not normalized_item or normalized_item == normalized_keyword or normalized_item in seen:
            continue
        seen.add(normalized_item)
        deduped.append(normalized_item)
    return deduped or ["이 흐름"]


def _protect_shadowed_keywords(
    text: str,
    shadowed_by: Optional[Sequence[str]] = None,
) -> tuple[str, Dict[str, str]]:
    protected = str(text or "")
    mapping: Dict[str, str] = {}
    for index, item in enumerate(
        sorted(
            {
                _normalize_user_keyword(keyword)
                for keyword in (shadowed_by or [])
                if _normalize_user_keyword(keyword)
            },
            key=len,
            reverse=True,
        )
    ):
        placeholder = f"__KWPROTECT_{index}__"
        protected, count = re.subn(re.escape(item), placeholder, protected)
        if count > 0:
            mapping[placeholder] = item
    return protected, mapping


def _restore_shadowed_keywords(text: str, mapping: Mapping[str, str]) -> str:
    restored = str(text or "")
    for placeholder, original in mapping.items():
        restored = restored.replace(str(placeholder), str(original))
    return restored


def _paragraph_contains_equivalent_sentence(paragraph_inner: str, sentence: str) -> bool:
    target = _normalize_sentence_for_compare(sentence)
    if not target:
        return False

    plain_paragraph = _strip_html(paragraph_inner)
    if not plain_paragraph:
        return False

    for match in re.finditer(r"[^.!?。]+[.!?。]?", plain_paragraph):
        existing = _normalize_sentence_for_compare(match.group(0))
        if existing and existing == target:
            return True
    return False


def _append_sentence_to_paragraph(paragraph_inner: str, sentence: str) -> str:
    base = str(paragraph_inner or "").rstrip()
    addition = str(sentence or "").strip()
    if not addition:
        return base
    if not base:
        return addition
    if _paragraph_contains_equivalent_sentence(base, addition):
        return base

    if not re.search(r"[.!?。]\s*$", base):
        base += "."
    return f"{base} {addition}"


def _count_keyword_reference_sentences_in_content(content: str) -> int:
    working = str(content or "")
    if not working:
        return 0

    count = 0
    plain_content = _strip_html(working)
    for match in re.finditer(r"[^.!?。]+[.!?。]?", plain_content):
        sentence = str(match.group(0) or "").strip()
        if sentence and _looks_like_keyword_reference_sentence(sentence):
            count += 1
    return count


def _should_allow_keyword_reference_fallback(
    content: str,
    keyword: str,
    user_keywords: Optional[Sequence[str]] = None,
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
) -> bool:
    normalized_keyword = _normalize_user_keyword(keyword)
    normalized_user_keywords = [
        _normalize_user_keyword(item)
        for item in (user_keywords or [])
        if _normalize_user_keyword(item)
    ]
    if not normalized_keyword or not normalized_user_keywords:
        return False
    if normalized_keyword != normalized_user_keywords[0]:
        return False
    if not _is_role_keyword(normalized_keyword):
        return False
    if should_block_role_keyword(role_keyword_policy, normalized_keyword):
        return False
    if _count_keyword_reference_sentences_in_content(content) >= 1:
        return False
    return True



def _is_keyword_reference_sentence(
    sentence: str,
    keyword: str,
    *,
    role_keyword_policy: Optional[Mapping[str, Any]] = None,
) -> bool:
    normalized_sentence = _normalize_sentence_for_compare(sentence)
    normalized_keyword = _normalize_user_keyword(keyword)
    if not normalized_sentence or not normalized_keyword or normalized_keyword not in normalized_sentence:
        return False

    template_candidates = {
        _normalize_sentence_for_compare(
            _build_role_keyword_reference_sentence(
                normalized_keyword,
                section_type,
                variant_index,
                role_keyword_policy=role_keyword_policy,
            )
        )
        for section_type in ("body", "conclusion")
        for variant_index in range(3)
    }
    template_candidates.add(
        _normalize_sentence_for_compare(f"온라인에서는 '{normalized_keyword}' 검색어도 함께 거론되고 있습니다.")
    )
    if normalized_sentence in template_candidates:
        return True

    return _looks_like_keyword_reference_sentence(normalized_sentence)

