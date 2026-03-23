"""?? ??? role-keyword ?? ??."""

import re
from typing import Any, Dict, List, Optional

from .role_keyword_policy import (
    build_role_keyword_intent_anchor_text,
    extract_role_keyword_parts,
    is_role_keyword_intent_surface,
    order_role_keyword_intent_anchor_candidates,
)
from .title_common import (
    COMPETITOR_INTENT_TAIL_FORBIDDEN_TOKENS,
    TITLE_LENGTH_HARD_MAX,
    TITLE_LENGTH_HARD_MIN,
    are_keywords_similar,
    _collect_recent_title_values,
    _contains_competitor_tail_forbidden_token,
    _find_title_first_person_expression,
    _split_title_anchor_and_tail,
    normalize_title_surface,
)

def _resolve_competitor_intent_title_keyword(params: Optional[Dict[str, Any]]) -> str:
    params_dict = params if isinstance(params, dict) else {}
    explicit_keyword = str(params_dict.get("competitorIntentKeyword") or "").strip()
    if explicit_keyword:
        return explicit_keyword

    role_keyword_policy = params_dict.get("roleKeywordPolicy") if isinstance(params_dict.get("roleKeywordPolicy"), dict) else {}
    entries = role_keyword_policy.get("entries") if isinstance(role_keyword_policy.get("entries"), dict) else {}
    user_keywords = params_dict.get("userKeywords") if isinstance(params_dict.get("userKeywords"), list) else []

    for raw_keyword in user_keywords:
        keyword = str(raw_keyword or "").strip()
        if not keyword:
            continue
        entry = entries.get(keyword) if isinstance(entries, dict) else {}
        mode = str((entry or {}).get("mode") or "").strip().lower()
        allow_title_intent_anchor = bool((entry or {}).get("allowTitleIntentAnchor"))
        if mode == "intent_only" or (mode == "blocked" and allow_title_intent_anchor):
            return keyword

    fallback_candidates: List[str] = []
    full_name = re.sub(r"\s+", "", str(params_dict.get("fullName") or "")).strip()
    source_pool = " ".join(
        str(params_dict.get(key) or "")
        for key in ("topic", "contentPreview", "stanceText", "backgroundText")
        if str(params_dict.get(key) or "").strip()
    )
    for raw_keyword in user_keywords:
        keyword = str(raw_keyword or "").strip()
        parts = extract_role_keyword_parts(keyword)
        name = re.sub(r"\s+", "", str(parts.get("name") or "")).strip()
        if not keyword or not name or not str(parts.get("role") or "").strip():
            continue
        if full_name and name == full_name:
            continue
        fallback_candidates.append(keyword)

    if fallback_candidates:
        fallback_candidates.sort(
            key=lambda item: (
                1 if str(item or "").strip() and str(item or "").strip() in source_pool else 0,
                len(str(item or "").strip()),
            ),
            reverse=True,
        )
        return str(fallback_candidates[0] or "").strip()

    return ""

def _has_competitor_intent_anchor_surface(title: str, intent_keyword: str) -> bool:
    normalized_title = normalize_title_surface(title) or str(title or "").strip()
    normalized_keyword = str(intent_keyword or "").strip()
    if not normalized_title or not normalized_keyword or normalized_keyword not in normalized_title:
        return False
    keyword_start = normalized_title.find(normalized_keyword)
    keyword_end = keyword_start + len(normalized_keyword)
    return is_role_keyword_intent_surface(normalized_title, keyword_start, keyword_end)

def _assess_competitor_intent_title_structure(title: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    intent_keyword = _resolve_competitor_intent_title_keyword(params)
    if not intent_keyword:
        return {"passed": True, "keyword": "", "anchor": "", "tail": "", "reason": ""}

    normalized_title = normalize_title_surface(title) or str(title or "").strip()
    if not normalized_title:
        return {"passed": True, "keyword": intent_keyword, "anchor": "", "tail": "", "reason": ""}

    split_title = _split_title_anchor_and_tail(normalized_title, primary_keyword=intent_keyword)
    anchor = re.sub(r"\s+", " ", str(split_title.get("anchor") or "")).strip()
    tail = re.sub(r"\s+", " ", str(split_title.get("tail") or "")).strip()
    has_comma_structure = "," in normalized_title and bool(anchor) and bool(tail)
    has_anchor_surface = _has_competitor_intent_anchor_surface(normalized_title, intent_keyword)

    if has_comma_structure and has_anchor_surface and intent_keyword in anchor:
        return {"passed": True, "keyword": intent_keyword, "anchor": anchor, "tail": tail, "reason": ""}

    bare_name_list = False
    full_name = str((params or {}).get("fullName") or "").strip()
    if "," in normalized_title:
        bare_left, bare_right = [part.strip() for part in normalized_title.split(",", 1)]
        if bare_left and bare_right and not has_anchor_surface:
            if full_name and bare_right.startswith(full_name):
                bare_name_list = True
            elif re.fullmatch(r"[가-힣]{2,8}", bare_left):
                bare_name_list = True

    reason = (
        "경쟁자 intent 제목은 인명을 쉼표로 나열하지 말고 "
        f'"{build_role_keyword_intent_anchor_text(intent_keyword, variant_index=0)}"처럼 '
        "[경쟁자 출마/거론 표현], [본문 핵심 논지] 구조를 유지하세요."
        if bare_name_list else
        "경쟁자 intent 제목은 앞절 검색 앵커를 유지해야 합니다. "
        f'"{build_role_keyword_intent_anchor_text(intent_keyword, variant_index=0)}"처럼 '
        "[경쟁자 출마/거론 표현], [본문 핵심 논지] 구조로 작성하세요."
    )
    return {
        "passed": False,
        "keyword": intent_keyword,
        "anchor": anchor,
        "tail": tail,
        "reason": reason,
    }

def _is_low_signal_competitor_tail(tail: str) -> bool:
    normalized_tail = re.sub(r"\s+", " ", str(tail or "")).strip()
    if not normalized_tail or len(normalized_tail) < 8:
        return True
    if _find_title_first_person_expression(normalized_tail):
        return True
    if _contains_competitor_tail_forbidden_token(normalized_tail):
        return True
    if re.search(r"\d{1,2}(?:\.\d)?\s*%\s*대\s*\d{1,2}(?:\.\d)?\s*%", normalized_tail):
        return False
    if re.search(r"\d{1,2}(?:\.\d)?\s*%", normalized_tail) and any(
        token in normalized_tail for token in ("앞선", "앞서는", "우세", "리드", "격차", "배경", "이유")
    ):
        return False
    if re.search(r"^(?:왜|어떻게)\b", normalized_tail):
        return True
    if any(token in normalized_tail for token in ("흔들리", "밀리", "역전", "뒤집")):
        return True

    generic_tail = re.sub(r"[0-9]+(?:\.[0-9]+)?%?", "", normalized_tail)
    generic_tail = re.sub(r"[^\w가-힣\s]", " ", generic_tail)
    generic_tail = re.sub(r"([가-힣A-Za-z0-9]+)의\b", r"\1", generic_tail)
    generic_tail = re.sub(r"([가-힣A-Za-z0-9]+)(?:와|과|은|는|이|가|을|를)\b", r"\1", generic_tail)
    generic_tail = re.sub(r"\s+", " ", generic_tail).strip()
    generic_tokens = {
        "이재성",
        "주진우",
        "가상대결",
        "양자대결",
        "대결",
        "접전",
        "경쟁력",
        "가능성",
        "드러난",
        "확인된",
        "앞선",
        "앞서",
        "이유",
        "왜",
        "구도",
        "출마",
        "출마론",
        "거론",
        "여론조사",
        "도시",
        "부산",
        "부산시",
        "지역",
        "대한민국",
        "미래",
        "변화",
        "혁신",
        "배경",
    }
    tokens = [token for token in generic_tail.split() if token]
    if not tokens:
        return True
    if all(token in generic_tokens for token in tokens):
        return True

    signal_tokens = (
        "공약",
        "정책",
        "해법",
        "현안",
        "산업",
        "일자리",
        "교통",
        "복지",
        "교육",
        "실행력",
        "역량",
        "차별점",
        "온도차",
        "현장",
        "경험",
        "ai",
        "AI",
    )
    if any(token in normalized_tail for token in signal_tokens):
        return False

    return all(token in generic_tokens for token in tokens)

def _assess_competitor_intent_title_tail(title: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    structure_validation = _assess_competitor_intent_title_structure(title, params)
    if not structure_validation.get("passed", True):
        return {
            "passed": False,
            "keyword": str(structure_validation.get("keyword") or ""),
            "tail": str(structure_validation.get("tail") or ""),
            "forbiddenTokens": [],
            "reason": str(structure_validation.get("reason") or ""),
        }

    intent_keyword = _resolve_competitor_intent_title_keyword(params)
    if not intent_keyword:
        return {"passed": True, "keyword": "", "tail": "", "forbiddenTokens": [], "reason": ""}
    normalized_title = normalize_title_surface(title) or str(title or "").strip()
    if intent_keyword not in normalized_title:
        return {"passed": True, "keyword": intent_keyword, "tail": "", "forbiddenTokens": [], "reason": ""}

    split_title = _split_title_anchor_and_tail(title, primary_keyword=intent_keyword)
    tail = re.sub(r"\s+", " ", str(split_title.get("tail") or "")).strip()
    if not tail:
        return {"passed": True, "keyword": intent_keyword, "tail": "", "forbiddenTokens": [], "reason": ""}

    if _is_low_signal_competitor_tail(tail):
        return {
            "passed": False,
            "keyword": intent_keyword,
            "tail": tail,
            "forbiddenTokens": [],
            "reason": (
                "경쟁자 intent 제목의 쉼표 뒤가 "
                f'"{tail}"처럼 범용 문구에 머물렀습니다. '
                "본문 쟁점이나 차별점으로 다시 쓰세요."
            ),
        }

    forbidden_tokens = [
        token
        for token in COMPETITOR_INTENT_TAIL_FORBIDDEN_TOKENS
        if token in tail
    ]
    if not forbidden_tokens:
        return {"passed": True, "keyword": intent_keyword, "tail": tail, "forbiddenTokens": [], "reason": ""}

    return {
        "passed": False,
        "keyword": intent_keyword,
        "tail": tail,
        "forbiddenTokens": forbidden_tokens,
        "reason": (
            "경쟁자 intent 제목의 쉼표 뒤에는 "
            + ", ".join(forbidden_tokens)
            + " 같은 조사 상투구를 쓰지 말고 본문 논지를 반영하세요."
        ),
    }

def _repair_competitor_intent_title_tail(title: str, params: Optional[Dict[str, Any]]) -> str:
    validation = _assess_competitor_intent_title_tail(title, params)
    if validation.get("passed", True):
        return ""
    structure_validation = _assess_competitor_intent_title_structure(title, params)

    intent_keyword = str(validation.get("keyword") or "").strip()
    if not intent_keyword:
        return ""

    normalized_title = normalize_title_surface(title) or str(title or "").strip()
    split_title = _split_title_anchor_and_tail(normalized_title, primary_keyword=intent_keyword)
    anchor = str(split_title.get("anchor") or "").strip()
    keyword_start = normalized_title.find(intent_keyword)
    keyword_end = keyword_start + len(intent_keyword) if keyword_start >= 0 else -1
    if (
        not structure_validation.get("passed", True)
        or keyword_start < 0
        or not is_role_keyword_intent_surface(normalized_title, keyword_start, keyword_end)
    ):
        recent_titles = _collect_recent_title_values(params)
        anchor = (
            order_role_keyword_intent_anchor_candidates(intent_keyword, recent_titles) or [
                build_role_keyword_intent_anchor_text(intent_keyword, variant_index=0)
            ]
        )[0]
    if not anchor:
        return ""

    for candidate_tail in _build_argument_tail_candidates(str(validation.get("tail") or ""), params):
        if _is_low_signal_competitor_tail(candidate_tail) or _contains_competitor_tail_forbidden_token(candidate_tail):
            continue
        repaired_title = normalize_title_surface(f"{anchor}, {candidate_tail}") or f"{anchor}, {candidate_tail}"
        if repaired_title and repaired_title != normalized_title:
            return repaired_title
    return ""

def _assess_title_first_person_usage(title: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    matched = _find_title_first_person_expression(title)
    if not matched:
        return {"passed": True, "matched": "", "reason": "", "repairedTitle": ""}

    repaired_title = ""
    if _resolve_competitor_intent_title_keyword(params):
        repaired_title = _repair_competitor_intent_title_tail(title, params)

    return {
        "passed": False,
        "matched": matched,
        "reason": (
            f'메인 제목에는 1인칭 표현("{matched}")을 쓰지 말고 '
            "화자 이름·정책명·수치 중심의 기사형 제목으로 다시 작성하세요."
        ),
        "repairedTitle": repaired_title,
    }

def _extract_argument_title_cues(params: Optional[Dict[str, Any]], *, limit: int = 4) -> List[str]:
    params_dict = params if isinstance(params, dict) else {}
    cues: List[str] = []
    seen: set[str] = set()

    def _append(value: str) -> None:
        normalized = re.sub(r"\s+", " ", str(value or "")).strip(" ,.:;!?")
        compact = re.sub(r"\s+", "", normalized)
        if (
            not normalized
            or compact in seen
            or len(compact) < 2
            or normalized in {"이재성", "주진우", "부산시장", "가상대결", "양자대결", "접전", "경쟁력", "가능성"}
            or _contains_competitor_tail_forbidden_token(normalized)
        ):
            return
        seen.add(compact)
        cues.append(normalized)

    for raw_keyword in params_dict.get("keywords") or []:
        keyword = str(raw_keyword or "").strip()
        if any(token in keyword for token in ("가상대결", "양자대결", "접전", "경쟁력", "가능성", "비전")):
            continue
        if any(token in keyword for token in ("공약", "정책", "해법", "현안", "산업", "일자리", "교통", "복지", "교육", "역량")):
            _append(keyword)

    source_text = " ".join(
        str(params_dict.get(key) or "")
        for key in ("stanceText", "contentPreview", "backgroundText")
        if str(params_dict.get(key) or "").strip()
    )
    normalized_source = re.sub(r"<[^>]*>", " ", source_text)
    normalized_source = re.sub(r"\s+", " ", normalized_source).strip()
    patterns = (
        r"(현장\s*\d{1,3}년)",
        r"(\d{1,3}년\s*(?:현장|경험))",
        r"([A-Za-z]{1,6}\s*AI\s*(?:공약|정책|전략|해법))",
        r"([가-힣A-Za-z0-9]{1,12}\s*(?:공약|정책|해법|현안|산업|일자리|교통|복지|교육|실행력|역량|개혁|전환))",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, normalized_source):
            _append(str(match.group(1) or ""))
            if len(cues) >= limit:
                return cues[:limit]
    return cues[:limit]

def _extract_local_issue_title_cues(params: Optional[Dict[str, Any]], *, limit: int = 3) -> List[str]:
    params_dict = params if isinstance(params, dict) else {}
    source_text = " ".join(
        str(params_dict.get(key) or "")
        for key in ("topic", "stanceText", "contentPreview", "backgroundText")
        if str(params_dict.get(key) or "").strip()
    )
    normalized_source = re.sub(r"<[^>]*>", " ", source_text)
    normalized_source = re.sub(r"\s+", " ", normalized_source).strip()
    if not normalized_source:
        return []

    issues: List[str] = []
    seen: set[str] = set()

    def _append(value: str) -> None:
        normalized = re.sub(r"\s+", " ", str(value or "")).strip(" ,.:;!?")
        compact = re.sub(r"\s+", "", normalized)
        if (
            not normalized
            or compact in seen
            or len(compact) < 4
            or _contains_competitor_tail_forbidden_token(normalized)
        ):
            return
        seen.add(compact)
        issues.append(normalized)

    patterns = (
        r"(제조업\s*위기)",
        r"(청년\s*이탈)",
        r"(북항\s*재개발)",
        r"([가-힣A-Za-z0-9]{2,12}\s*(?:위기|이탈|침체|난|부담|공백|정체|부진|재개발))",
        r"([가-힣A-Za-z0-9]{2,12}\s*(?:산업|일자리|교통|복지|교육)\s*(?:문제|현안))",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, normalized_source):
            _append(str(match.group(1) or ""))
            if len(issues) >= limit:
                return issues[:limit]
    return issues[:limit]

def _strip_leading_subject_name(text: str, subject_name: str) -> str:
    normalized_text = re.sub(r"\s+", " ", str(text or "")).strip()
    normalized_subject = re.sub(r"\s+", "", str(subject_name or "")).strip()
    if not normalized_text or not normalized_subject:
        return normalized_text
    stripped = re.sub(
        rf"^{re.escape(normalized_subject)}(?:의|이|가|은|는)?\s*",
        "",
        normalized_text,
        count=1,
    ).strip()
    return stripped or normalized_text

def _build_argument_tail_candidates(base_tail: str, params: Optional[Dict[str, Any]]) -> List[str]:
    full_name = str((params or {}).get("fullName") or "").strip()
    candidates: List[str] = []
    seen: set[str] = set()

    def _append(value: str) -> None:
        normalized = re.sub(r"\s+", " ", str(value or "")).strip(" ,.:;!?")
        if not normalized or normalized in seen or _contains_competitor_tail_forbidden_token(normalized):
            return
        seen.add(normalized)
        candidates.append(normalized)

    normalized_tail = re.sub(r"\s+", " ", str(base_tail or "")).strip()
    tail_is_low_signal = _is_low_signal_competitor_tail(normalized_tail) if normalized_tail else True
    if normalized_tail and not tail_is_low_signal:
        _append(normalized_tail)

    bundle = (params or {}).get("pollFocusBundle") if isinstance((params or {}).get("pollFocusBundle"), dict) else {}
    primary_pair = bundle.get("primaryPair") if isinstance(bundle.get("primaryPair"), dict) else {}
    speaker = str(primary_pair.get("speaker") or "").strip()
    speaker_percent = str(primary_pair.get("speakerPercent") or primary_pair.get("speakerScore") or "").strip()
    opponent_percent = str(primary_pair.get("opponentPercent") or primary_pair.get("opponentScore") or "").strip()
    if not speaker_percent:
        source_pool = " ".join(
            str((params or {}).get(key) or "")
            for key in ("contentPreview", "stanceText", "backgroundText")
        )
        pair_match = re.search(
            r"([0-9]{1,2}(?:\.[0-9])?)\s*%\s*대\s*([0-9]{1,2}(?:\.[0-9])?)\s*%",
            source_pool,
        )
        if pair_match:
            speaker_percent = f"{pair_match.group(1)}%"
            opponent_percent = f"{pair_match.group(2)}%"
        percent_matches = re.findall(r"([0-9]{1,2}(?:\.[0-9])?)\s*%", source_pool)
        if percent_matches:
            speaker_percent = f"{percent_matches[0]}%"
            if len(percent_matches) > 1:
                opponent_percent = f"{percent_matches[1]}%"
    subject_name = speaker or full_name
    has_matchup_numeric_cue = bool(speaker_percent)
    if subject_name and speaker_percent:
        _append(f"{subject_name} {speaker_percent} 앞선 배경")
        _append(f"{subject_name}이 {speaker_percent}로 앞서는 이유")
    has_reason_question_tail = bool(re.search(r"(왜|이유)", normalized_tail))
    has_advantage_context = bool(
        re.search(
            r"(앞서|앞선|우세|리드|근소하게 앞|우위를|우위를 점|격차)",
            " ".join(
                str((params or {}).get(key) or "")
                for key in ("topic", "contentPreview", "stanceText", "backgroundText")
            ),
        )
    )
    if subject_name and (has_matchup_numeric_cue or has_reason_question_tail or has_advantage_context):
        _append(f"{subject_name}이 앞서는 이유")
        if opponent_percent:
            _append(f"{subject_name}과의 지지율 격차")

    for cue in _extract_argument_title_cues(params):
        cue_core = _strip_leading_subject_name(cue, full_name)
        if re.search(r"(?:현장\s*\d{1,3}년|\d{1,3}년\s*(?:현장|경험))", cue):
            if full_name:
                _append(f"{full_name}이 내세우는 {cue_core}")
            _append(f"{cue}에서 갈린다")
            continue
        if cue_core.endswith("정책"):
            if full_name:
                _append(f"{full_name}과의 정책 온도차는")
                _append(f"{full_name} {cue_core}과 무엇이 다른가")
            _append(f"{cue_core} 차별점은")
            continue
        if full_name:
            _append(f"{full_name} {cue_core}과 무엇이 다른가")
            _append(f"{full_name}이 내세운 {cue_core}")
        _append(f"{cue_core} 차별점은")

    for issue in _extract_local_issue_title_cues(params):
        _append(f"{issue} 해법")
        _append(f"{issue} 대안")

    if normalized_tail and not tail_is_low_signal:
        _append(normalized_tail)
    return candidates

def _compose_repaired_title_surface(base_title: str, start: int, end: int, replacement: str) -> str:
    prefix = str(base_title[:start] or "").rstrip(" ,·:;!?")
    suffix = re.sub(r"^[\s,·:;!?]+", "", str(base_title[end:] or ""))
    anchor_like_replacement = bool(re.search(r"(?:출마론|거론|출마 가능성|거론 속|구도)$", str(replacement or "").strip()))
    if anchor_like_replacement and suffix:
        candidate_surface = (
            f"{prefix} {replacement}, {suffix}".strip()
            if prefix else
            f"{replacement}, {suffix}".strip()
        )
        return normalize_title_surface(candidate_surface) or candidate_surface
    parts = [part for part in (prefix, str(replacement or "").strip(), suffix) if str(part or "").strip()]
    candidate_surface = " ".join(parts).strip()
    return normalize_title_surface(candidate_surface) or candidate_surface

def _iter_role_policy_title_repair_candidates(
    title: str,
    role_keyword_policy: Optional[Dict[str, Any]],
    recent_titles: Optional[List[str]] = None,
) -> List[str]:
    normalized_title = normalize_title_surface(title)
    entries = role_keyword_policy.get("entries") if isinstance(role_keyword_policy, dict) else {}
    if not normalized_title or not isinstance(entries, dict) or not entries:
        return []

    candidates: List[str] = []
    seen_candidates: set[str] = set()

    for keyword, raw_entry in entries.items():
        entry = raw_entry if isinstance(raw_entry, dict) else {}
        normalized_keyword = str(keyword or "").strip()
        if not normalized_keyword or normalized_keyword not in normalized_title:
            continue

        start_index = normalized_title.find(normalized_keyword)
        end_index = start_index + len(normalized_keyword)
        mode = str(entry.get("mode") or "").strip().lower()

        replacements: List[str] = []
        if mode == "intent_only" and not is_role_keyword_intent_surface(
            normalized_title,
            start_index,
            end_index,
        ):
            replacements = order_role_keyword_intent_anchor_candidates(
                normalized_keyword,
                recent_titles or [],
            ) or [
                build_role_keyword_intent_anchor_text(normalized_keyword, variant_index=0),
            ]
        elif mode == "blocked":
            if bool(entry.get("allowTitleIntentAnchor")) and not is_role_keyword_intent_surface(
                normalized_title,
                start_index,
                end_index,
            ):
                replacements = order_role_keyword_intent_anchor_candidates(
                    normalized_keyword,
                    recent_titles or [],
                ) or [
                    build_role_keyword_intent_anchor_text(normalized_keyword, variant_index=0),
                ]
            elif not bool(entry.get("allowTitleIntentAnchor")):
                source_role = str(entry.get("sourceRole") or "").strip()
                person_name = str(entry.get("name") or "").strip()
                if source_role and person_name:
                    replacements = [f"{person_name} {source_role}", person_name]
                elif person_name:
                    replacements = [person_name]

        for replacement in replacements:
            repaired_candidate = _compose_repaired_title_surface(
                normalized_title,
                start_index,
                end_index,
                replacement,
            )
            if (
                not repaired_candidate
                or repaired_candidate == normalized_title
                or repaired_candidate in seen_candidates
            ):
                continue
            if not (TITLE_LENGTH_HARD_MIN <= len(repaired_candidate) <= TITLE_LENGTH_HARD_MAX):
                continue
            seen_candidates.add(repaired_candidate)
            candidates.append(repaired_candidate)

    return candidates

def _repair_title_for_role_keyword_policy(
    title: str,
    role_keyword_policy: Optional[Dict[str, Any]],
    user_keywords: Optional[List[str]] = None,
    recent_titles: Optional[List[str]] = None,
) -> str:
    filtered_keywords = [str(item or "").strip() for item in (user_keywords or []) if str(item or "").strip()]
    for repaired_candidate in _iter_role_policy_title_repair_candidates(
        title,
        role_keyword_policy,
        recent_titles=recent_titles,
    ):
        role_gate = _validate_role_keyword_title_policy(repaired_candidate, role_keyword_policy or {})
        if not role_gate.get("passed"):
            continue
        keyword_gate = _validate_user_keyword_title_requirements(repaired_candidate, filtered_keywords)
        severity = str(keyword_gate.get("severity") or "").strip().lower()
        if keyword_gate.get("passed") or severity == "soft":
            return repaired_candidate
    return ""

_ROLE_KEYWORD_TOKENS = (
    '부산시장',
    '시장',
    '국회의원',
    '의원',
    '후보',
)

def _is_role_keyword_token(token: str) -> bool:
    normalized = str(token or '').strip()
    if not normalized:
        return False
    return any(role_token == normalized for role_token in _ROLE_KEYWORD_TOKENS)

def _repair_title_for_missing_keywords(
    title: str,
    keyword_gate: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """2순위 키워드 고유 어절을 1순위 키워드를 보존하면서 제목에 삽입한다.

    전략: primary_kw 직후에 괄호 또는 중간점으로 missing word를 추가.
    예: "부산 영광도서, ..." → "부산 영광도서(서면), ..."
    """
    missing_type = keyword_gate.get('missingType', '')
    primary_kw = str(keyword_gate.get('primaryKw') or '')
    missing_words = keyword_gate.get('uniqueWords') or []

    if not primary_kw or primary_kw not in title:
        return None

    if missing_type == 'secondary_unique' and missing_words:
        secondary_kw = str(keyword_gate.get('secondaryKw') or '').strip()
        normalized_missing_roles = [word for word in missing_words if _is_role_keyword_token(word)]
        has_primary_role = bool(
            re.search(
                rf"{re.escape(primary_kw)}\s*(?:현\s*)?(?:부산시장|국회의원|의원|시장)(?:\s*후보)?",
                title,
            )
        )
        # 호칭 충돌(예: "주진우 국회의원" + 2순위 "주진우 부산시장")은
        # 제목 전체를 덮어쓰지 말고 intent 앵커(prefix)만 교체한다.
        if secondary_kw and normalized_missing_roles and has_primary_role:
            recent_titles = _collect_recent_title_values(params)
            split_title = _split_title_anchor_and_tail(title, primary_keyword=primary_kw)
            tail_candidates = _build_argument_tail_candidates(
                str(split_title.get("tail") or ""),
                params,
            )
            anchor_candidates = order_role_keyword_intent_anchor_candidates(
                secondary_kw,
                recent_titles,
            ) or [build_role_keyword_intent_anchor_text(secondary_kw, variant_index=0)]

            candidate_surfaces: List[str] = []
            if tail_candidates:
                for anchor in anchor_candidates:
                    for tail_candidate in tail_candidates[:3]:
                        candidate_surfaces.append(f"{anchor}, {tail_candidate}")
            else:
                candidate_surfaces.extend(anchor_candidates)

            for candidate in candidate_surfaces:
                normalized_candidate = normalize_title_surface(candidate) or candidate
                if TITLE_LENGTH_HARD_MIN <= len(normalized_candidate) <= TITLE_LENGTH_HARD_MAX:
                    return normalized_candidate

        # 고유 어절만 삽입: "부산 영광도서" → "부산 영광도서(서면)"
        suffix = '·'.join(missing_words)
        repaired = title.replace(primary_kw, f"{primary_kw}({suffix})", 1)
    elif missing_type == 'secondary_full':
        secondary_kw = str(keyword_gate.get('secondaryKw') or '')
        if not secondary_kw:
            return None
        # 전체 2순위 키워드 삽입: primary_kw 뒤에 추가
        repaired = title.replace(primary_kw, f"{primary_kw}·{secondary_kw}", 1)
    else:
        return None

    if len(repaired) > TITLE_LENGTH_HARD_MAX:
        return None
    if len(repaired) < TITLE_LENGTH_HARD_MIN:
        return None

    return repaired

def _validate_role_keyword_title_policy(title: str, role_keyword_policy: Dict[str, Any]) -> Dict[str, Any]:
    cleaned_title = str(title or "").strip()
    if not cleaned_title:
        return {"passed": True}
    entries = role_keyword_policy.get("entries") if isinstance(role_keyword_policy, dict) else {}
    if not isinstance(entries, dict) or not entries:
        return {"passed": True}

    for keyword, raw_entry in entries.items():
        entry = raw_entry if isinstance(raw_entry, dict) else {}
        normalized_keyword = str(keyword or "").strip()
        if not normalized_keyword or normalized_keyword not in cleaned_title:
            continue
        mode = str(entry.get("mode") or "").strip()
        start_index = cleaned_title.find(normalized_keyword)
        end_index = start_index + len(normalized_keyword)
        if mode == "blocked":
            if bool(entry.get("allowTitleIntentAnchor")) and is_role_keyword_intent_surface(cleaned_title, start_index, end_index):
                continue
            source_role = str(entry.get("sourceRole") or "").strip() or "입력 근거"
            return {
                "passed": False,
                "reason": (
                    f'"{normalized_keyword}"는 입력 근거의 현재 직함("{source_role}")과 충돌합니다. '
                    f'제목에서는 "{build_role_keyword_intent_anchor_text(normalized_keyword, variant_index=0)}"처럼 '
                    "출마/거론 의도를 붙인 검색 앵커로만 사용하세요."
                    if bool(entry.get("allowTitleIntentAnchor")) else
                    f'"{normalized_keyword}"는 입력 근거의 현재 직함("{source_role}")과 충돌해 제목에 사용할 수 없습니다.'
                ),
            }
        if mode == "intent_only" and not is_role_keyword_intent_surface(cleaned_title, start_index, end_index):
            return {
                "passed": False,
                "reason": (
                    f'"{normalized_keyword}"는 완성된 호칭처럼 쓰지 말고 '
                    f'"{build_role_keyword_intent_anchor_text(normalized_keyword, variant_index=0)}"처럼 '
                    "출마/거론 의도를 붙여 제목에 사용하세요."
                ),
            }
    return {"passed": True}

def _validate_user_keyword_title_requirements(title: str, user_keywords: List[str]) -> Dict[str, Any]:
    """사용자 지정 검색어의 제목 반영 여부를 강제 검증한다."""
    cleaned_title = str(title or '').strip()
    normalized_user_keywords = [str(item or '').strip() for item in (user_keywords or []) if str(item or '').strip()]
    if not normalized_user_keywords:
        return {'passed': True}

    primary_kw = normalized_user_keywords[0]
    if primary_kw not in cleaned_title:
        return {
            'passed': False,
            'reason': f'1순위 검색어 "{primary_kw}"가 제목에 없습니다.',
        }

    if len(normalized_user_keywords) < 2:
        return {'passed': True}

    secondary_kw = normalized_user_keywords[1]
    if not secondary_kw or secondary_kw == primary_kw:
        return {'passed': True}

    similar = are_keywords_similar(primary_kw, secondary_kw)
    if similar:
        kw2_words = [w for w in secondary_kw.split() if len(w) >= 2]
        kw1_words = set(primary_kw.split())
        unique_words = [w for w in kw2_words if w not in kw1_words]
        if unique_words and not any(word in cleaned_title for word in unique_words):
            return {
                'passed': False,
                'severity': 'soft',
                'missingType': 'secondary_unique',
                'primaryKw': primary_kw,
                'secondaryKw': secondary_kw,
                'uniqueWords': unique_words,
                'reason': (
                    f'2순위 검색어 "{secondary_kw}"의 고유 어절({", ".join(unique_words)})이 제목에 없습니다.'
                ),
            }
        return {'passed': True}

    if secondary_kw not in cleaned_title:
        return {
            'passed': False,
            'missingType': 'secondary_full',
            'primaryKw': primary_kw,
            'secondaryKw': secondary_kw,
            'uniqueWords': [],
            'reason': f'2순위 검색어 "{secondary_kw}"가 제목에 없습니다.',
        }

    return {'passed': True}
