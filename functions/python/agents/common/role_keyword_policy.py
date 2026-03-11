from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

ROLE_SURFACE_CORE_TOKENS: tuple[str, ...] = (
    "국회의원",
    "의원",
    "대표",
    "당대표",
    "원내대표",
    "위원장",
    "장관",
    "후보",
    "구청장",
    "군수",
    "교육감",
)
ROLE_SURFACE_PATTERN = (
    r"(?:"
    r"[가-힣]{1,10}(?:특별|광역|자치)?(?:시장|도지사)"
    r"|구청장|군수|교육감|국회의원|의원|대표|당대표|원내대표|위원장|장관|후보"
    r")"
)
ROLE_KEYWORD_PATTERN = re.compile(
    rf"^(?P<name>[가-힣]{{2,8}})\s*(?P<role>{ROLE_SURFACE_PATTERN})$"
)
PERSON_ROLE_FACT_PATTERN = re.compile(
    rf"(?P<name>[가-힣]{{2,8}})\s*(?P<current>현\s*)?(?P<role>{ROLE_SURFACE_PATTERN})(?!\s*후보)",
    re.IGNORECASE,
)
ROLE_CONTEXT_PATTERN = re.compile(
    rf"(?P<role>{ROLE_SURFACE_PATTERN})\s*"
    r"(?:(?:선거|출마|출마설|후보|후보군|가상대결|양자대결|대결|적합도|하마평|거론|론|판세|경선))",
    re.IGNORECASE,
)
ROLE_CONTEXT_REVERSE_PATTERN = re.compile(
    r"(?:(?:선거|출마|출마설|후보|후보군|가상대결|양자대결|대결|적합도|하마평|거론|론|판세|경선)"
    rf"(?:의|에서|과|와)?\s*)(?P<role>{ROLE_SURFACE_PATTERN})",
    re.IGNORECASE,
)
ROLE_CONTEXT_CUE_PATTERN = re.compile(
    r"(?:선거|출마|출마설|후보|후보군|가상대결|양자대결|대결|적합도|하마평|거론|론|판세|경선)",
    re.IGNORECASE,
)
ROLE_INTENT_PATTERN = re.compile(
    r"^\s*(?:출마(?:설|론|가능성)?|거론(?:\s*이유|되나|되는)?|하마평|후보론|가능성|론|설|\?)",
    re.IGNORECASE,
)


def _normalize_spaces(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clean_name(name: Any) -> str:
    text = re.sub(r"[^가-힣A-Za-z\s]", "", str(name or "")).strip()
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 2 or len(compact) > 12:
        return ""
    return compact


def normalize_role_label(role: Any) -> str:
    text = re.sub(r"\s+", "", str(role or "")).strip()
    if not text:
        return ""
    if text.startswith("현") and len(text) > 1:
        text = text[1:]
    if text == "의원":
        return "국회의원"
    if text in {"대표", "당대표", "원내대표", "위원장", "장관", "후보", "구청장", "군수", "교육감"}:
        return text
    if text.endswith("시장") or text.endswith("도지사"):
        return text
    return text


def roles_equivalent(left: Any, right: Any) -> bool:
    normalized_left = normalize_role_label(left)
    normalized_right = normalize_role_label(right)
    if not normalized_left or not normalized_right:
        return False
    if normalized_left == normalized_right:
        return True
    if normalized_left.endswith("시장") and normalized_right == "시장":
        return True
    if normalized_right.endswith("시장") and normalized_left == "시장":
        return True
    if normalized_left.endswith("도지사") and normalized_right == "도지사":
        return True
    if normalized_right.endswith("도지사") and normalized_left == "도지사":
        return True
    return False


def extract_role_keyword_parts(keyword: Any) -> Dict[str, str]:
    normalized = _normalize_spaces(keyword)
    if not normalized:
        return {"name": "", "role": "", "roleCanonical": ""}
    match = ROLE_KEYWORD_PATTERN.fullmatch(normalized)
    if not match:
        return {"name": "", "role": "", "roleCanonical": ""}
    name = _clean_name(match.group("name"))
    role = _normalize_spaces(match.group("role"))
    return {
        "name": name,
        "role": role,
        "roleCanonical": normalize_role_label(role),
    }


def is_role_keyword(keyword: Any) -> bool:
    parts = extract_role_keyword_parts(keyword)
    return bool(parts.get("name") and parts.get("role"))


def extract_person_role_facts_from_text(text: Any) -> Dict[str, str]:
    source = _normalize_spaces(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not source:
        return {}

    votes: Dict[str, Dict[str, int]] = {}
    for match in PERSON_ROLE_FACT_PATTERN.finditer(source):
        name = _clean_name(match.group("name"))
        role = _normalize_spaces(f"{str(match.group('current') or '').strip()} {str(match.group('role') or '').strip()}")
        if not name or not role:
            continue
        role_votes = votes.setdefault(name, {})
        role_votes[role] = int(role_votes.get(role) or 0) + 1

    facts: Dict[str, str] = {}
    for name, role_votes in votes.items():
        selected_role = ""
        selected_score = -1
        for role, count in role_votes.items():
            canonical = normalize_role_label(role)
            score = int(count) * 10
            if role.startswith("현 "):
                score += 5
            if canonical == "국회의원":
                score += 1
            elif canonical.endswith("시장") or canonical.endswith("도지사"):
                score += 2
            elif canonical in {"대표", "당대표", "원내대표", "위원장", "장관"}:
                score += 1
            if score > selected_score:
                selected_role = role
                selected_score = score
        if selected_role:
            facts[name] = _normalize_spaces(selected_role)
    return facts


def extract_target_role_contexts(texts: Iterable[Any]) -> set[str]:
    roles: set[str] = set()
    for text in texts:
        source = _normalize_spaces(re.sub(r"<[^>]*>", " ", str(text or "")))
        if not source:
            continue
        for pattern in (ROLE_CONTEXT_PATTERN, ROLE_CONTEXT_REVERSE_PATTERN):
            for match in pattern.finditer(source):
                role = _normalize_spaces(match.group("role"))
                canonical = normalize_role_label(role)
                if canonical:
                    roles.add(canonical)
    return roles


def _split_context_units(text: Any) -> list[str]:
    source = _normalize_spaces(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not source:
        return []
    parts = [
        str(part or "").strip()
        for part in re.split(r"(?<=[.!?。])\s+|\n+", source)
        if str(part or "").strip()
    ]
    return parts or [source]


def _has_person_target_role_context(name: str, target_role: str, texts: Iterable[Any]) -> bool:
    normalized_name = _clean_name(name)
    normalized_target_role = normalize_role_label(target_role)
    if not normalized_name or not normalized_target_role:
        return False
    for text in texts or []:
        for unit in _split_context_units(text):
            if normalized_name not in unit:
                continue
            if not ROLE_CONTEXT_CUE_PATTERN.search(unit):
                continue
            unit_roles = set()
            for pattern in (ROLE_CONTEXT_PATTERN, ROLE_CONTEXT_REVERSE_PATTERN):
                for match in pattern.finditer(unit):
                    canonical = normalize_role_label(match.group("role"))
                    if canonical:
                        unit_roles.add(canonical)
            if normalized_target_role in unit_roles:
                return True
    return False


def build_role_keyword_policy(
    user_keywords: Iterable[Any],
    *,
    person_roles: Optional[Dict[str, str]] = None,
    source_texts: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    roles = person_roles or {}
    source_text_list = list(source_texts or [])
    source_role_contexts = extract_target_role_contexts(source_text_list)
    entries: Dict[str, Dict[str, Any]] = {}

    for raw_keyword in user_keywords or []:
        keyword = _normalize_spaces(raw_keyword)
        if not keyword:
            continue
        parts = extract_role_keyword_parts(keyword)
        if not parts.get("name") or not parts.get("role"):
            continue

        source_role = _normalize_spaces(roles.get(parts["name"]) or "")
        source_role_canonical = normalize_role_label(source_role)
        keyword_role_canonical = str(parts.get("roleCanonical") or "")
        target_role_supported = bool(
            keyword_role_canonical
            and keyword_role_canonical in source_role_contexts
            and _has_person_target_role_context(parts["name"], keyword_role_canonical, source_text_list)
        )
        mode = "exact"
        reason = ""

        if source_role_canonical and not roles_equivalent(source_role_canonical, keyword_role_canonical):
            if target_role_supported:
                mode = "intent_only"
                reason = "source_role_conflict_with_target_role_context"
            else:
                mode = "blocked"
                reason = "source_role_conflict_without_target_role_context"

        entries[keyword] = {
            "keyword": keyword,
            "name": parts["name"],
            "role": parts["role"],
            "roleCanonical": keyword_role_canonical,
            "sourceRole": source_role,
            "sourceRoleCanonical": source_role_canonical,
            "targetRoleSupported": target_role_supported,
            "mode": mode,
            "reason": reason,
        }

    return {
        "entries": entries,
        "sourceRoleContexts": sorted(source_role_contexts),
        "intentOnlyKeywords": sorted(
            keyword for keyword, entry in entries.items() if str(entry.get("mode") or "") == "intent_only"
        ),
        "blockedKeywords": sorted(
            keyword for keyword, entry in entries.items() if str(entry.get("mode") or "") == "blocked"
        ),
    }


def get_role_keyword_entry(policy: Any, keyword: Any) -> Dict[str, Any]:
    if not isinstance(policy, dict):
        return {}
    entries = policy.get("entries")
    if not isinstance(entries, dict):
        return {}
    normalized_keyword = _normalize_spaces(keyword)
    entry = entries.get(normalized_keyword)
    return entry if isinstance(entry, dict) else {}


def should_block_role_keyword(policy: Any, keyword: Any) -> bool:
    entry = get_role_keyword_entry(policy, keyword)
    return str(entry.get("mode") or "") == "blocked"


def should_render_role_keyword_as_intent(policy: Any, keyword: Any) -> bool:
    entry = get_role_keyword_entry(policy, keyword)
    return str(entry.get("mode") or "") == "intent_only"


def is_role_keyword_intent_surface(text: Any, start: int, end: int) -> bool:
    source = str(text or "")
    if not source or start < 0 or end <= start:
        return False
    after = source[end : min(len(source), end + 24)]
    return bool(ROLE_INTENT_PATTERN.match(after))


def build_role_keyword_intent_text(keyword: Any, *, context: str = "title", variant_index: int = 0) -> str:
    normalized_keyword = _normalize_spaces(keyword)
    if not normalized_keyword:
        return ""
    normalized_context = str(context or "").strip().lower()
    if normalized_context == "inline":
        templates = (
            f"{normalized_keyword} 출마론",
            f"{normalized_keyword} 후보론",
            f"{normalized_keyword} 거론",
        )
    elif normalized_context == "body":
        templates = (
            f"온라인에서는 {normalized_keyword} 출마 가능성도 함께 거론됩니다.",
            f"이 흐름 속에서 {normalized_keyword} 후보론도 함께 언급됩니다.",
            f"{normalized_keyword} 거론도 이어지고 있습니다.",
        )
    elif normalized_context == "conclusion":
        templates = (
            f"마지막까지 {normalized_keyword} 출마 가능성도 함께 거론됩니다.",
            f"끝까지 {normalized_keyword} 후보론도 이어집니다.",
            f"이 흐름에서 {normalized_keyword} 거론도 이어지고 있습니다.",
        )
    else:
        templates = (
            f"{normalized_keyword} 출마?",
            f"{normalized_keyword} 거론 이유",
            f"{normalized_keyword} 후보론?",
        )
    return templates[int(variant_index) % len(templates)]


__all__ = [
    "ROLE_KEYWORD_PATTERN",
    "ROLE_SURFACE_PATTERN",
    "extract_role_keyword_parts",
    "extract_person_role_facts_from_text",
    "extract_target_role_contexts",
    "build_role_keyword_policy",
    "get_role_keyword_entry",
    "should_block_role_keyword",
    "should_render_role_keyword_as_intent",
    "is_role_keyword",
    "is_role_keyword_intent_surface",
    "normalize_role_label",
    "roles_equivalent",
    "build_role_keyword_intent_text",
]
