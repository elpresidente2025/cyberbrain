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
    r"|[가-힣]{1,10}(?:구청장|군수|시의원|도의원|구의원|군의원)"
    r"|광역의원|기초의원|시의원|도의원|구의원|군의원"
    r"|구청장|군수|교육감|국회의원|의원|대표|당대표|원내대표|위원장|장관|후보"
    r")"
)
# ROLE_SURFACE_PATTERN 의 candidate-role 전용 확장판. 단독 "시장|도지사" 도
# 매치해 "아무개 시장후보" 같은 표현을 잡는다. ROLE_SURFACE_PATTERN 에 바로
# "시장|도지사" 를 추가하면 PERSON_ROLE_FACT_PATTERN 등에서 "재래 시장에서"
# 같은 문구가 person fact 로 잡혀 person_roles 가 오염되므로, 후보 라벨이
# 반드시 뒤따르는 candidate-role 매칭에서만 이 확장판을 사용한다.
ROLE_SURFACE_PATTERN_CANDIDATE = (
    r"(?:"
    r"[가-힣]{1,10}(?:특별|광역|자치)?(?:시장|도지사)"
    r"|[가-힣]{1,10}(?:구청장|군수|시의원|도의원|구의원|군의원)"
    r"|광역의원|기초의원|시의원|도의원|구의원|군의원"
    r"|구청장|군수|교육감|국회의원|의원|대표|당대표|원내대표|위원장|장관|후보"
    r"|시장|도지사"
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
TITLE_INTENT_ANCHOR_SUFFIXES: tuple[str, ...] = (
    "출마론",
    "거론",
    "출마 가능성",
    "거론 속",
    "구도",
)
METRO_REGION_PREFIXES: tuple[str, ...] = (
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "세종",
)
ALLIED_CONTEXT_PATTERN = re.compile(
    r"(?:함께|같이|동행|지원|필승|힘을\s*모아|발로\s*뛰|손잡고|원팀)",
    re.IGNORECASE,
)
DIRECT_COMPETITION_CONTEXT_PATTERN = re.compile(
    r"(?:맞대결|가상대결|양자대결|대결|경쟁|상대|vs|VS|접전|판세|적합도|여론조사)",
    re.IGNORECASE,
)
CANDIDATE_LABEL_PATTERN = r"(?:예비후보|후보(?!군|론|설))"
PERSON_TARGET_CANDIDATE_PATTERN = re.compile(
    rf"(?P<name>[가-힣]{{2,8}})\s*(?P<target>{ROLE_SURFACE_PATTERN_CANDIDATE})\s*(?P<label>{CANDIDATE_LABEL_PATTERN})",
    re.IGNORECASE,
)
TARGET_CANDIDATE_PERSON_PATTERN = re.compile(
    rf"(?P<target>{ROLE_SURFACE_PATTERN_CANDIDATE})\s*(?P<label>{CANDIDATE_LABEL_PATTERN})\s*(?P<name>[가-힣]{{2,8}})(?:은|는|이|가|도|의)?",
    re.IGNORECASE,
)
PERSON_CANDIDATE_PATTERN = re.compile(
    rf"(?P<name>[가-힣]{{2,8}})\s*(?P<label>{CANDIDATE_LABEL_PATTERN})",
    re.IGNORECASE,
)
CANDIDATE_PERSON_PATTERN = re.compile(
    rf"(?P<label>{CANDIDATE_LABEL_PATTERN})\s*(?P<name>[가-힣]{{2,8}})(?:은|는|이|가|도|의)?",
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


def _clean_name_token(token: Any) -> str:
    compact = _clean_name(token)
    if len(compact) >= 3 and compact[-1] in {"은", "는", "이", "가", "도", "의", "를", "을", "와", "과"}:
        trimmed = compact[:-1]
        if 2 <= len(trimmed) <= 12:
            return trimmed
    return compact


def _normalize_candidate_label(label: Any) -> str:
    normalized = re.sub(r"[^가-힣A-Za-z]", "", _normalize_spaces(label))
    if len(normalized) >= 3 and normalized[-1] in {"은", "는", "이", "가", "도", "의", "를", "을", "와", "과"}:
        normalized = normalized[:-1]
    if normalized == "예비후보":
        return "예비후보"
    if normalized == "후보":
        return "후보"
    return ""


def _normalize_role_surface_token(token: Any) -> str:
    normalized = _normalize_spaces(token)
    if not normalized:
        return ""
    canonical = normalize_role_label(normalized)
    if not canonical:
        return ""
    if canonical == "후보":
        return ""
    if canonical in {
        "국회의원",
        "광역의원",
        "기초의원",
        "시의원",
        "도의원",
        "구의원",
        "군의원",
        "대표",
        "당대표",
        "원내대표",
        "위원장",
        "장관",
        "구청장",
        "군수",
        "교육감",
    }:
        return canonical
    if canonical.endswith("시장") or canonical.endswith("도지사"):
        return canonical
    if canonical.endswith("구청장") or canonical.endswith("군수"):
        return canonical
    return ""


def normalize_role_label(role: Any) -> str:
    text = re.sub(r"\s+", "", str(role or "")).strip()
    if not text:
        return ""
    if text.startswith("현") and len(text) > 1:
        text = text[1:]
    if text == "의원":
        return "국회의원"
    if text in {
        "대표",
        "당대표",
        "원내대표",
        "위원장",
        "장관",
        "후보",
        "구청장",
        "군수",
        "교육감",
        "광역의원",
        "기초의원",
        "시의원",
        "도의원",
        "구의원",
        "군의원",
    }:
        return text
    if (
        text.endswith("시장")
        or text.endswith("도지사")
        or text.endswith("구청장")
        or text.endswith("군수")
        or text.endswith("시의원")
        or text.endswith("도의원")
        or text.endswith("구의원")
        or text.endswith("군의원")
    ):
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
    if normalized_left.endswith("구청장") and normalized_right == "구청장":
        return True
    if normalized_right.endswith("구청장") and normalized_left == "구청장":
        return True
    if normalized_left.endswith("군수") and normalized_right == "군수":
        return True
    if normalized_right.endswith("군수") and normalized_left == "군수":
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


def _normalize_region_token(value: Any) -> str:
    text = re.sub(r"[^가-힣A-Za-z0-9]", "", str(value or "")).strip()
    if not text:
        return ""
    suffixes = (
        "특별자치시",
        "특별자치도",
        "특별시",
        "광역시",
        "자치시",
        "자치도",
        "시",
        "도",
        "구",
        "군",
    )
    for suffix in suffixes:
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


def _office_level_from_role(role: Any, *, profile_region_metro: str = "") -> str:
    normalized = normalize_role_label(role)
    compact = re.sub(r"\s+", "", normalized)
    if not compact:
        return ""
    if compact in {"국회의원"}:
        return "national_assembly"
    if compact in {"광역의원", "도의원"}:
        return "metropolitan_assembly"
    if compact == "시의원":
        metro_hint = _normalize_region_token(profile_region_metro)
        return "metropolitan_assembly" if metro_hint in METRO_REGION_PREFIXES else "basic_assembly"
    if compact in {"기초의원", "구의원", "군의원"}:
        return "basic_assembly"
    if compact in {"대표", "당대표", "원내대표", "위원장"}:
        return "party_role"
    if compact in {"장관"}:
        return "government_role"
    if compact == "교육감":
        return "education_head"
    if compact.endswith("도지사"):
        return "metropolitan_head"
    if compact.endswith("구청장") or compact.endswith("군수"):
        return "basic_municipal_head"
    if compact.endswith("시장"):
        prefix = compact[: -len("시장")]
        if _normalize_region_token(prefix) in METRO_REGION_PREFIXES:
            return "metropolitan_head"
        return "basic_municipal_head"
    return ""


def _role_region_hint(role: Any) -> Dict[str, str]:
    compact = re.sub(r"\s+", "", normalize_role_label(role))
    if not compact:
        return {"metro": "", "local": ""}
    if compact.endswith("구청장"):
        return {"metro": "", "local": _normalize_region_token(compact[: -len("구청장")])}
    if compact.endswith("군수"):
        return {"metro": "", "local": _normalize_region_token(compact[: -len("군수")])}
    if compact.endswith("시장"):
        prefix = _normalize_region_token(compact[: -len("시장")])
        if prefix in METRO_REGION_PREFIXES:
            return {"metro": prefix, "local": ""}
        return {"metro": "", "local": prefix}
    if compact.endswith("도지사"):
        return {"metro": _normalize_region_token(compact[: -len("도지사")]), "local": ""}
    return {"metro": "", "local": ""}


def _profile_region_hints(profile: Optional[Dict[str, Any]]) -> Dict[str, set[str]]:
    profile_dict = profile if isinstance(profile, dict) else {}
    metro_values = {
        _normalize_region_token(profile_dict.get("regionMetro")),
        _normalize_region_token(profile_dict.get("metroRegion")),
        _normalize_region_token(profile_dict.get("region")),
    }
    local_values = {
        _normalize_region_token(profile_dict.get("regionLocal")),
        _normalize_region_token(profile_dict.get("regionDistrict")),
        _normalize_region_token(profile_dict.get("electoralDistrict")),
    }
    return {
        "metro": {item for item in metro_values if item},
        "local": {item for item in local_values if item},
    }


def _profile_position(profile: Optional[Dict[str, Any]]) -> str:
    profile_dict = profile if isinstance(profile, dict) else {}
    target = profile_dict.get("targetElection") if isinstance(profile_dict.get("targetElection"), dict) else {}
    for key in ("position", "office", "role"):
        value = str(target.get(key) or "").strip()
        if value:
            return value
    for key in ("position", "currentPosition", "office", "role"):
        value = str(profile_dict.get(key) or "").strip()
        if value:
            return value
    return ""


def _role_matches_profile_region(role: Any, profile: Optional[Dict[str, Any]]) -> bool:
    role_region = _role_region_hint(role)
    profile_regions = _profile_region_hints(profile)
    role_metro = str(role_region.get("metro") or "")
    role_local = str(role_region.get("local") or "")
    if role_local and role_local in profile_regions.get("local", set()):
        return True
    if role_metro and role_metro in profile_regions.get("metro", set()):
        return True
    return False


def _units_containing_person(name: str, texts: Iterable[Any]) -> list[str]:
    normalized_name = _clean_name(name)
    if not normalized_name:
        return []
    units: list[str] = []
    for text in texts or []:
        for unit in _split_context_units(text):
            if normalized_name in unit:
                units.append(unit)
    return units


def _has_allied_person_context(name: str, texts: Iterable[Any]) -> bool:
    return any(ALLIED_CONTEXT_PATTERN.search(unit) for unit in _units_containing_person(name, texts))


def _has_direct_competition_person_context(name: str, texts: Iterable[Any]) -> bool:
    return any(DIRECT_COMPETITION_CONTEXT_PATTERN.search(unit) for unit in _units_containing_person(name, texts))


def classify_role_keyword_speaker_relation(
    *,
    keyword: Any = "",
    name: Any = "",
    role: Any = "",
    speaker_profile: Optional[Dict[str, Any]] = None,
    source_texts: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """사용자 프로필과 역할형 키워드의 관계를 분류한다.

    이 함수는 제목의 경쟁자 intent 활성화 여부를 정하기 위한 일반 규칙이다.
    같은 지역의 다른 선거 단위 후보나 당 지도부를 직접 경쟁자로 오판하지
    않도록, 화자 직책/지역과 원문 문맥을 함께 본다.
    """
    profile = speaker_profile if isinstance(speaker_profile, dict) else {}
    source_text_list = list(source_texts or [])
    parts = extract_role_keyword_parts(keyword)
    person_name = _clean_name(name or parts.get("name") or "")
    role_text = str(role or parts.get("role") or keyword or "").strip()

    speaker_role = _profile_position(profile)
    speaker_level = _office_level_from_role(
        speaker_role,
        profile_region_metro=str(profile.get("regionMetro") or ""),
    )
    target_level = _office_level_from_role(
        role_text,
        profile_region_metro=str(profile.get("regionMetro") or ""),
    )
    same_region = _role_matches_profile_region(role_text, profile)
    allied_context = _has_allied_person_context(person_name, source_text_list) if person_name else False
    direct_context = _has_direct_competition_person_context(person_name, source_text_list) if person_name else False

    relation = "unknown"
    allow_competitor_intent = True
    if not speaker_level or not target_level:
        relation = "unknown"
    elif target_level == "party_role":
        relation = "party_allied_figure"
        allow_competitor_intent = False
    elif speaker_level != target_level:
        if allied_context and same_region:
            relation = "same_region_allied_candidate"
        elif allied_context:
            relation = "allied_figure"
        elif same_region:
            relation = "same_region_other_office"
        else:
            relation = "different_office"
        allow_competitor_intent = False
    elif direct_context:
        relation = "direct_competitor"
    else:
        relation = "same_office_unknown"

    return {
        "relation": relation,
        "allowCompetitorIntent": allow_competitor_intent,
        "speakerRole": speaker_role,
        "speakerOfficeLevel": speaker_level,
        "targetRole": role_text,
        "targetOfficeLevel": target_level,
        "sameRegion": same_region,
        "alliedContext": allied_context,
        "directCompetitionContext": direct_context,
    }


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


def build_person_reference_facts(
    *,
    person_roles: Optional[Dict[str, str]] = None,
    source_texts: Optional[Iterable[Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    source_text_list = list(source_texts or [])
    role_facts: Dict[str, str] = {}
    for name, role in (person_roles or {}).items():
        cleaned_name = _clean_name(name)
        normalized_role = _normalize_spaces(role)
        if cleaned_name and normalized_role and cleaned_name not in role_facts:
            role_facts[cleaned_name] = normalized_role

    if not role_facts:
        for text in source_text_list:
            for name, role in extract_person_role_facts_from_text(text).items():
                if name not in role_facts:
                    role_facts[name] = role

    candidate_votes: Dict[str, Dict[tuple[str, str], int]] = {}
    candidate_patterns = (
        PERSON_TARGET_CANDIDATE_PATTERN,
        TARGET_CANDIDATE_PERSON_PATTERN,
        PERSON_CANDIDATE_PATTERN,
        CANDIDATE_PERSON_PATTERN,
    )
    for text in source_text_list:
        source = _normalize_spaces(re.sub(r"<[^>]*>", " ", str(text or "")))
        if not source:
            continue
        for pattern in candidate_patterns:
            for match in pattern.finditer(source):
                name = _clean_name(match.group("name"))
                label = _normalize_candidate_label(match.group("label"))
                target_role = normalize_role_label(match.groupdict().get("target") or "")
                if not name or not label or _normalize_role_surface_token(name) or _normalize_candidate_label(name):
                    continue
                person_votes = candidate_votes.setdefault(name, {})
                vote_key = (label, target_role)
                person_votes[vote_key] = int(person_votes.get(vote_key) or 0) + 1
        tokens = [token for token in source.split(" ") if token]
        for index, token in enumerate(tokens):
            role_token = _normalize_role_surface_token(token)
            label_token = _normalize_candidate_label(token)
            next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
            next_next_token = tokens[index + 2] if index + 2 < len(tokens) else ""

            if role_token and _normalize_candidate_label(next_token):
                name = _clean_name_token(next_next_token)
                if name and not _normalize_role_surface_token(name) and not _normalize_candidate_label(name):
                    label = _normalize_candidate_label(next_token)
                    person_votes = candidate_votes.setdefault(name, {})
                    vote_key = (label, role_token)
                    person_votes[vote_key] = int(person_votes.get(vote_key) or 0) + 1

            if label_token:
                name = _clean_name_token(next_token)
                if name and not _normalize_role_surface_token(name) and not _normalize_candidate_label(name):
                    person_votes = candidate_votes.setdefault(name, {})
                    vote_key = (label_token, "")
                    person_votes[vote_key] = int(person_votes.get(vote_key) or 0) + 1
                continue
            if role_token:
                continue

            name_token = _clean_name_token(token)
            if not name_token or _normalize_role_surface_token(name_token) or _normalize_candidate_label(name_token):
                continue
            if _normalize_role_surface_token(next_token) and _normalize_candidate_label(next_next_token):
                person_votes = candidate_votes.setdefault(name_token, {})
                vote_key = (_normalize_candidate_label(next_next_token), _normalize_role_surface_token(next_token))
                person_votes[vote_key] = int(person_votes.get(vote_key) or 0) + 1

    facts: Dict[str, Dict[str, Any]] = {}
    names = set(role_facts.keys()) | set(candidate_votes.keys())
    for name in sorted(names):
        source_role = _normalize_spaces(role_facts.get(name) or "")
        source_role_canonical = normalize_role_label(source_role)
        selected_label = ""
        selected_target_role = ""
        selected_score = -1
        for (label, target_role), count in (candidate_votes.get(name) or {}).items():
            score = int(count) * 10
            if label == "예비후보":
                score += 3
            elif label == "후보":
                score += 2
            if target_role:
                score += 2
                if target_role.endswith("시장") or target_role.endswith("도지사"):
                    score += 1
            if score > selected_score:
                selected_label = label
                selected_target_role = target_role
                selected_score = score

        facts[name] = {
            "name": name,
            "sourceRole": source_role,
            "sourceRoleCanonical": source_role_canonical,
            "explicitCandidateLabel": selected_label,
            "explicitCandidateRole": selected_target_role,
            "explicitCandidateRoleCanonical": normalize_role_label(selected_target_role),
            "candidateRegistered": bool(selected_label),
        }
    return facts


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
    speaker_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    roles = person_roles or {}
    source_text_list = list(source_texts or [])
    person_reference_facts = build_person_reference_facts(
        person_roles=roles,
        source_texts=source_text_list,
    )
    source_role_contexts = extract_target_role_contexts(source_text_list)
    entries: Dict[str, Dict[str, Any]] = {}

    for raw_keyword in user_keywords or []:
        keyword = _normalize_spaces(raw_keyword)
        if not keyword:
            continue
        parts = extract_role_keyword_parts(keyword)
        if not parts.get("name") or not parts.get("role"):
            continue

        source_fact = person_reference_facts.get(parts["name"]) or {}
        source_role = _normalize_spaces(source_fact.get("sourceRole") or "")
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

        speaker_relation = classify_role_keyword_speaker_relation(
            keyword=keyword,
            name=parts.get("name"),
            role=parts.get("role"),
            speaker_profile=speaker_profile,
            source_texts=source_text_list,
        )
        allow_competitor_intent = bool(speaker_relation.get("allowCompetitorIntent", True))
        if not allow_competitor_intent and mode == "intent_only":
            mode = "exact"
            reason = "profile_not_direct_competitor"

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
            "speakerRelation": speaker_relation,
            "allowCompetitorIntent": allow_competitor_intent,
            "allowTitleIntentAnchor": bool(
                mode == "blocked"
                and parts.get("name")
                and parts.get("role")
                and allow_competitor_intent
            ),
        }

    # ── personRelations ──
    # 사용자 키워드 루프(entries) 와 별도로, source_texts 에 등장한 모든
    # 인물(personReferenceFacts) 에 대해 ally classification 을 돌린다.
    # dd923cf 가 추가한 부정 차단(profile_not_competitor) 의 짝꿍 — 화자와
    # 같은 팀의 다른 직책 후보(러닝메이트) 를 LLM 에게 명시 안내한다.
    # allowCompetitorIntent == False 인 인물만 모은다 (직접 경쟁자/미상 제외).
    speaker_full_name_raw = ""
    if isinstance(speaker_profile, dict):
        speaker_full_name_raw = str(
            speaker_profile.get("name") or speaker_profile.get("displayName") or ""
        )
    speaker_full_name = _clean_name(speaker_full_name_raw)
    covered_names = set()
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        cleaned = _clean_name(entry.get("name"))
        if cleaned:
            covered_names.add(cleaned)

    person_relations: Dict[str, Dict[str, Any]] = {}
    for raw_name, fact in person_reference_facts.items():
        name = _clean_name(raw_name)
        if not name or not isinstance(fact, dict):
            continue
        if speaker_full_name and name == speaker_full_name:
            continue
        if name in covered_names:
            continue
        role_for_relation = (
            _normalize_spaces(fact.get("explicitCandidateRole"))
            or _normalize_spaces(fact.get("sourceRole"))
        )
        if not role_for_relation:
            continue
        relation_info = classify_role_keyword_speaker_relation(
            keyword="",
            name=name,
            role=role_for_relation,
            speaker_profile=speaker_profile,
            source_texts=source_text_list,
        )
        if bool(relation_info.get("allowCompetitorIntent", True)):
            continue
        candidate_label = _normalize_spaces(fact.get("explicitCandidateLabel"))
        person_relations[name] = {
            "name": name,
            "role": role_for_relation,
            "candidateLabel": candidate_label,
            "relation": str(relation_info.get("relation") or ""),
            "speakerOfficeLevel": str(relation_info.get("speakerOfficeLevel") or ""),
            "targetOfficeLevel": str(relation_info.get("targetOfficeLevel") or ""),
            "sameRegion": bool(relation_info.get("sameRegion")),
            "alliedContext": bool(relation_info.get("alliedContext")),
            "allowCompetitorIntent": False,
        }

    return {
        "entries": entries,
        "personReferenceFacts": person_reference_facts,
        "personRelations": person_relations,
        "allyPeople": sorted(person_relations.keys()),
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


def get_person_reference_fact(policy: Any, name: Any) -> Dict[str, Any]:
    if not isinstance(policy, dict):
        return {}
    reference_facts = policy.get("personReferenceFacts")
    if not isinstance(reference_facts, dict):
        return {}
    normalized_name = _clean_name(name)
    fact = reference_facts.get(normalized_name)
    return fact if isinstance(fact, dict) else {}


def get_person_relation(policy: Any, name: Any) -> Dict[str, Any]:
    """personRelations 에서 이름으로 ally 관계 정보를 조회한다.

    person_relations 는 build_role_keyword_policy 가 source_texts 의
    인물들에 대해 ally classification 을 돌린 결과로, 사용자 키워드 루프에는
    들어오지 않은 인물(러닝메이트 등)을 LLM 에 명시 안내할 때 사용한다.
    """
    if not isinstance(policy, dict):
        return {}
    relations = policy.get("personRelations")
    if not isinstance(relations, dict):
        return {}
    normalized_name = _clean_name(name)
    relation = relations.get(normalized_name)
    return relation if isinstance(relation, dict) else {}


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
        return templates[int(variant_index) % len(templates)]
    elif normalized_context == "body":
        return ""
    elif normalized_context == "conclusion":
        templates = (
            f"마지막까지 {normalized_keyword} 출마 가능성도 함께 언급됩니다.",
            f"끝까지 {normalized_keyword} 후보론도 함께 거론됩니다.",
            f"이 흐름에서 {normalized_keyword} 출마론도 이어집니다.",
        )
        return templates[int(variant_index) % len(templates)]
    else:
        templates = (
            f"{normalized_keyword} 출마?",
            f"{normalized_keyword} 거론 이유",
            f"{normalized_keyword} 후보론?",
        )
    return templates[int(variant_index) % len(templates)]


def build_role_keyword_intent_anchor_text(keyword: Any, *, variant_index: int = 0) -> str:
    normalized_keyword = _normalize_spaces(keyword)
    if not normalized_keyword:
        return ""
    suffix = TITLE_INTENT_ANCHOR_SUFFIXES[int(variant_index) % len(TITLE_INTENT_ANCHOR_SUFFIXES)]
    return f"{normalized_keyword} {suffix}"


def extract_role_keyword_intent_anchor_suffix(title: Any, keyword: Any) -> str:
    source = _normalize_spaces(title)
    normalized_keyword = _normalize_spaces(keyword)
    if not source or not normalized_keyword or normalized_keyword not in source:
        return ""
    start_index = source.find(normalized_keyword)
    tail = source[start_index + len(normalized_keyword) :].lstrip(" ,:;!?")
    for suffix in sorted(TITLE_INTENT_ANCHOR_SUFFIXES, key=len, reverse=True):
        if tail.startswith(suffix):
            return suffix
    return ""


def order_role_keyword_intent_anchor_candidates(
    keyword: Any,
    recent_titles: Iterable[Any] | None = None,
    *,
    limit_recent: int = 5,
) -> list[str]:
    normalized_keyword = _normalize_spaces(keyword)
    if not normalized_keyword:
        return []

    recent_items = list(recent_titles or [])[:limit_recent]
    used_suffixes: list[str] = []
    seen_suffixes: set[str] = set()
    for raw_title in recent_items:
        suffix = extract_role_keyword_intent_anchor_suffix(raw_title, normalized_keyword)
        if not suffix or suffix in seen_suffixes:
            continue
        seen_suffixes.add(suffix)
        used_suffixes.append(suffix)

    ordered_suffixes = [
        *[suffix for suffix in TITLE_INTENT_ANCHOR_SUFFIXES if suffix not in seen_suffixes],
        *used_suffixes,
    ]
    return [f"{normalized_keyword} {suffix}" for suffix in ordered_suffixes]


__all__ = [
    "ROLE_KEYWORD_PATTERN",
    "ROLE_SURFACE_PATTERN",
    "TITLE_INTENT_ANCHOR_SUFFIXES",
    "extract_role_keyword_parts",
    "extract_person_role_facts_from_text",
    "extract_target_role_contexts",
    "build_person_reference_facts",
    "build_role_keyword_policy",
    "classify_role_keyword_speaker_relation",
    "get_role_keyword_entry",
    "get_person_reference_fact",
    "get_person_relation",
    "should_block_role_keyword",
    "should_render_role_keyword_as_intent",
    "is_role_keyword",
    "is_role_keyword_intent_surface",
    "normalize_role_label",
    "roles_equivalent",
    "build_role_keyword_intent_text",
    "build_role_keyword_intent_anchor_text",
    "extract_role_keyword_intent_anchor_suffix",
    "order_role_keyword_intent_anchor_candidates",
]
