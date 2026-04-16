"""H2 소제목 결정론 수리 모듈.

pipeline.py의 인라인 소제목 수리 로직을 `agents/common/` 레이어로 이관.
LLM 호출 없이 Python 결정론만으로 다음 수리를 제공한다:

- 키워드 주입 (`ensure_keyword_first_slot`, `ensure_user_keyword_first_slot`,
  `build_keyword_intent_h2`)
- 어색한 H2 표현 정규화 (`repair_awkward_phrases`)
- 브랜딩/인지도 문구 재작성 (`repair_branding_phrases`)

향후 PR에서 generic surface 수리, 3인칭 변환, entity consistency 수리 등을
이 모듈에 추가한다.

SubheadingAgent·pipeline.py 모두 이 모듈을 import한다.
pipeline.py는 기존 `_build_keyword_intent_h2` / `_ensure_*_subheading_once` /
`_repair_*_h2_phrases_once` 시그니처를 delegation shim으로 유지한다.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Sequence

from .h2_planning import canonicalize_entity_surface
from .person_naming import (
    canonical_role_label,
    clean_full_name_candidate,
    extract_keyword_person_role,
    normalize_person_name,
)
from .role_keyword_policy import ROLE_KEYWORD_PATTERN

__all__ = [
    "H2_TAG_PATTERN",
    "build_keyword_intent_h2",
    "ensure_keyword_first_slot",
    "ensure_user_keyword_first_slot",
    "enforce_anchor_cap",
    "enforce_keyword_diversity",
    "enforce_user_role_lock",
    "repair_awkward_phrases",
    "repair_branding_phrases",
    "repair_generic_surface",
    "third_personize_subheading",
    "build_subheading_role_surface",
    "pick_matchup_counterpart_name",
    "pick_primary_person_name",
    "pick_scored_primary_person_name",
    "score_subheading_body_names",
    "is_subheading_subject_noise_sentence",
    "repair_malformed_matchup_heading",
    "repair_speaker_role_mismatch_matchup_heading",
    "repair_entity_consistency",
]


H2_TAG_PATTERN = re.compile(r"<h2\b[^>]*>([\s\S]*?)</h2\s*>", re.IGNORECASE)

_HTML_TAG_RE = re.compile(r"<[^>]*>")


def _normalize_inline_whitespace(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _plain_heading(inner: Any) -> str:
    return _normalize_inline_whitespace(_HTML_TAG_RE.sub(" ", str(inner or "")))


def build_keyword_intent_h2(keyword: Any) -> str:
    normalized = _normalize_inline_whitespace(keyword)
    if not normalized:
        return ""

    if ROLE_KEYWORD_PATTERN.fullmatch(normalized):
        quoted_candidate = f"'{normalized}' 검색어가 거론되는 이유"
        if 10 <= len(quoted_candidate) <= 25:
            return quoted_candidate

    candidates = (
        f"{normalized} 왜 거론되나?",
        f"{normalized} 경쟁력은?",
        f"{normalized} 쟁점은?",
    )
    for candidate in candidates:
        if 10 <= len(candidate) <= 25:
            return candidate

    fallback = f"{normalized} 쟁점"
    if len(fallback) > 25:
        trimmed = normalized[: max(8, 25 - len(" 쟁점"))].rstrip(" ,.:;!?")
        fallback = f"{trimmed} 쟁점"
    if len(fallback) < 10:
        fallback = (fallback + " 분석")[:25]
    return fallback


def ensure_keyword_first_slot(content: Any, keyword: Any) -> Dict[str, Any]:
    base = str(content or "")
    target_keyword = str(keyword or "").strip()
    if not base or not target_keyword:
        return {"content": base, "edited": False}

    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    if not h2_matches:
        return {"content": base, "edited": False}

    for match in h2_matches:
        heading = _plain_heading(match.group(1))
        if target_keyword in heading:
            return {"content": base, "edited": False}

    replacement = build_keyword_intent_h2(target_keyword)
    if not replacement:
        return {"content": base, "edited": False}

    person_name, _role = extract_keyword_person_role(target_keyword)
    target_index = 0
    if person_name:
        for idx, match in enumerate(h2_matches):
            heading = _plain_heading(match.group(1))
            if person_name in heading:
                target_index = idx
                break

    target_match = h2_matches[target_index]
    updated = base[: target_match.start(1)] + replacement + base[target_match.end(1) :]
    return {
        "content": updated,
        "edited": updated != base,
        "keyword": target_keyword,
        "headingBefore": str(target_match.group(1) or "").strip(),
        "headingAfter": replacement,
    }


def ensure_user_keyword_first_slot(
    content: Any,
    user_keywords: Sequence[Any],
    *,
    preferred_keyword: Any = "",
) -> Dict[str, Any]:
    base = str(content or "")
    normalized_keywords: List[str] = [
        str(item or "").strip() for item in (user_keywords or []) if str(item or "").strip()
    ]
    if not base or not normalized_keywords:
        return {"content": base, "edited": False}

    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    if not h2_matches:
        return {"content": base, "edited": False}

    for match in h2_matches:
        heading = _plain_heading(match.group(1))
        if any(keyword in heading for keyword in normalized_keywords):
            return {"content": base, "edited": False}

    preferred = str(preferred_keyword or "").strip()
    if preferred and preferred in normalized_keywords:
        target_keyword = preferred
    else:
        target_keyword = normalized_keywords[0]

    target_person_name, target_role = extract_keyword_person_role(target_keyword)
    if target_person_name or target_role or ROLE_KEYWORD_PATTERN.fullmatch(target_keyword):
        return {"content": base, "edited": False}

    return ensure_keyword_first_slot(base, target_keyword)


# ---------------------------------------------------------------------------
# Anchor cap enforcement — H2 세트 내 fullName 반복 스탬핑 방지
# ---------------------------------------------------------------------------

_LEADING_PARTICLE_RE = re.compile(
    r"^(?:을|를|은|는|이|가|과|와|의|에|도|만|로|으로|에서|에게|까지|부터)\s"
)


def _is_valid_stripped_heading(text: str) -> bool:
    stripped = str(text or "").strip()
    if len(stripped) < 8 or len(stripped) > 40:
        return False
    if _LEADING_PARTICLE_RE.match(stripped):
        return False
    return True


def _strip_name_from_heading(heading: str, name: str) -> str:
    """H2 앞/뒤에 붙은 fullName 앵커를 조용히 제거한다.

    다음 패턴만 처리 (의미 손실 없이 descriptor 만 남기는 경우):
    - `{name}, rest` → `rest`
    - `{name}· rest` → `rest`
    - `{name} rest` (공백 구분) → `rest`  — 단 rest 길이·조사 검증 통과 시만
    - `rest, {name}` → `rest`
    - `rest {name}` 끝 → `rest`  — 검증 통과 시만
    """
    text = str(heading or "").strip()
    escaped = re.escape(name)

    prefix = re.match(rf"^{escaped}\s*[,·]\s*(.+)$", text)
    if prefix:
        candidate = prefix.group(1).strip()
        if _is_valid_stripped_heading(candidate):
            return candidate

    suffix = re.match(rf"^(.+?)\s*[,·]\s*{escaped}\s*$", text)
    if suffix:
        candidate = suffix.group(1).strip()
        if _is_valid_stripped_heading(candidate):
            return candidate

    plain_prefix = re.match(rf"^{escaped}\s+(.+)$", text)
    if plain_prefix:
        candidate = plain_prefix.group(1).strip()
        if _is_valid_stripped_heading(candidate):
            return candidate

    plain_suffix = re.match(rf"^(.+?)\s+{escaped}\s*$", text)
    if plain_suffix:
        candidate = plain_suffix.group(1).strip()
        if _is_valid_stripped_heading(candidate):
            return candidate

    return ""


def enforce_anchor_cap(
    headings: Sequence[Any],
    *,
    full_name: Any,
    cap: int = 1,
) -> Dict[str, Any]:
    """H2 세트에서 fullName 앵커 횟수를 `cap` 이하로 낮춘다.

    Why: memory feedback_h2_entity_stamping — fullName은 1~2회 앵커, 나머지는
    descriptor 혼합. 제목이 이미 fullName을 포함하므로 H2 반복은 스탬핑처럼 느껴진다.
    How to apply: 스코어/프롬프트만으로 막지 못하고 최종 H2에 fullName이 cap보다
    많이 남은 경우, 앞/뒤 prefix 형태의 앵커를 조용히 제거해 descriptor만 남긴다.

    - 첫 `cap` 개의 fullName 포함 H2 는 유지 (앵커 역할).
    - 나머지는 `_strip_name_from_heading` 으로 전처리. 제거 결과가 유효하지
      않으면 원본 유지 (lossless — 이상하게 자르지 않는다).
    """
    name = str(full_name or "").strip()
    result: List[str] = [str(h or "") for h in (headings or [])]

    if not name or not result:
        return {"headings": result, "edited": False, "actions": []}

    try:
        cap_value = max(0, int(cap))
    except (TypeError, ValueError):
        cap_value = 1

    indices_with_name = [i for i, h in enumerate(result) if name in h]
    if len(indices_with_name) <= cap_value:
        return {"headings": result, "edited": False, "actions": []}

    actions: List[Dict[str, Any]] = []
    to_strip = indices_with_name[cap_value:]
    for idx in to_strip:
        original = result[idx]
        candidate = _strip_name_from_heading(original, name)
        if candidate and candidate != original.strip():
            result[idx] = candidate
            actions.append({"index": idx, "before": original, "after": candidate})

    return {
        "headings": result,
        "edited": bool(actions),
        "actions": actions,
    }


# ---------------------------------------------------------------------------
# Keyword diversity — H2 세트 내 동일 user_keyword 반복 방지
# ---------------------------------------------------------------------------

# 키워드 뒤에 올 수 있는 한국어 조사 (스트립 시 함께 제거)
_KEYWORD_TRAILING_PARTICLE_RE = re.compile(
    r"(?:은|는|이|가|을|를|의|에|에서|으로|과|와|도|만),?\s*"
)


def _strip_keyword_from_heading(heading: str, keyword: str) -> str:
    """H2 에서 keyword + 후행 조사/쉼표를 제거해 남은 부분을 반환.

    `_strip_name_from_heading` 과 비슷하지만 keyword 는 이름보다 길 수 있어
    prefix/suffix 위치만 시도한다.
    """
    text = str(heading or "").strip()
    escaped = re.escape(keyword)

    # prefix: "계양 테크노밸리, 앵커 기업 유치에 청신호" → "앵커 기업 유치에 청신호"
    prefix = re.match(
        rf"^{escaped}\s*(?:은|는|이|가|을|를|의|에|에서|으로|과|와|도|만)?\s*[,·]?\s*(.+)$",
        text,
    )
    if prefix:
        candidate = prefix.group(1).strip()
        if _is_valid_stripped_heading(candidate):
            return candidate

    # suffix: "앵커 기업, 계양 테크노밸리" → "앵커 기업"
    suffix = re.match(rf"^(.+?)\s*[,·]\s*{escaped}\s*$", text)
    if suffix:
        candidate = suffix.group(1).strip()
        if _is_valid_stripped_heading(candidate):
            return candidate

    return ""


def enforce_keyword_diversity(
    headings: Sequence[Any],
    *,
    user_keywords: Sequence[str],
    entity_hints: Sequence[str] = (),
    cap_ratio: float = 0.5,
) -> Dict[str, Any]:
    """H2 세트에서 동일 user_keyword / entity 가 과반 이상 반복되면 초과분을 스트립한다.

    Args:
        headings: H2 리스트.
        user_keywords: 사용자 지정 키워드 (반복 스탬핑 금지 대상).
        entity_hints: 자동 추출된 entity (지역명/고유명사 등) - 변이형 포함 카운팅.
            예: "인천", "인천시", "인천광역시" 는 canonical stem "인천" 으로 묶어
            과반 규제를 적용. 표면형만 바꿔 cap 을 회피하는 걸 막는다.
        cap_ratio: 최대 허용 비율 (기본 0.5 = 과반).

    앞쪽 cap 개는 유지, 나머지는 `_strip_keyword_from_heading` 으로 매칭된 표면형을
    제거한다. 제거 결과가 유효하지 않으면 원본 유지 (lossless).
    """
    result: List[str] = [str(h or "") for h in (headings or [])]
    if len(result) <= 2:
        return {"headings": result, "edited": False, "actions": []}

    cap = max(1, math.ceil(len(result) * cap_ratio))
    actions: List[Dict[str, Any]] = []

    # 중복 제거된 표면형 목록 작성 — user_keywords 우선, entity_hints 뒤에 append
    seen_surfaces: set = set()
    regulated_surfaces: List[str] = []
    for source in (user_keywords or (), entity_hints or ()):
        for item in source:
            surface = str(item or "").strip()
            if not surface or surface in seen_surfaces:
                continue
            seen_surfaces.add(surface)
            regulated_surfaces.append(surface)

    if not regulated_surfaces:
        return {"headings": result, "edited": False, "actions": []}

    # canonical stem 으로 그룹화 — 변이형("인천시"/"인천광역시") 을 묶어 카운트
    canonical_groups: Dict[str, List[str]] = {}
    for surface in regulated_surfaces:
        canonical = canonicalize_entity_surface(surface)
        canonical_groups.setdefault(canonical, []).append(surface)

    for canonical, surfaces in canonical_groups.items():
        # 긴 표면형을 먼저 매칭해야 "샘플광역시" 가 "샘플" 로 짧게 끊기지 않는다
        sorted_surfaces = sorted(surfaces, key=len, reverse=True)
        # 각 heading 에서 이 canonical 그룹의 표면형 중 하나라도 매치되는 인덱스 수집
        matched: List[tuple[int, str]] = []
        for idx, heading in enumerate(result):
            matched_surface = next((s for s in sorted_surfaces if s in heading), "")
            if matched_surface:
                matched.append((idx, matched_surface))
        if len(matched) <= cap:
            continue
        for idx, surface in matched[cap:]:
            original = result[idx]
            candidate = _strip_keyword_from_heading(original, surface)
            if candidate and candidate != original.strip():
                result[idx] = candidate
                actions.append({
                    "index": idx,
                    "keyword": surface,
                    "canonical": canonical,
                    "before": original,
                    "after": candidate,
                })

    return {
        "headings": result,
        "edited": bool(actions),
        "actions": actions,
    }


_USER_ROLE_TOKENS = (
    "국회의원",
    "원내대표",
    "부대표",
    "시의원",
    "구의원",
    "도의원",
    "광역시장",
    "구청장",
    "군수",
    "동장",
    "도지사",
    "지사",
    "시장",
    "부위원장",
    "위원장",
    "차관",
    "장관",
    "예비후보",
    "후보",
    "대표",
    "의원",
)
_USER_ROLE_RE = re.compile(
    "(" + "|".join(re.escape(token) for token in sorted(_USER_ROLE_TOKENS, key=len, reverse=True)) + ")"
)


def _user_role_tokens_compatible(detected: str, allowed: str) -> bool:
    det = str(detected or "").strip()
    allow = str(allowed or "").strip()
    if not det or not allow:
        return False
    if det in allow or allow in det:
        return True
    return False


def _strip_conflicting_role_around_name(
    text: str,
    *,
    full_name: str,
    allowed_role: str,
) -> tuple[str, list[str]]:
    """heading 안에서 full_name 바로 앞/뒤에 붙은 role token 중 allowed_role 과
    비호환인 것만 제거한다. 타인 언급에는 손대지 않는다.
    """
    base = str(text or "")
    name = str(full_name or "").strip()
    allowed = str(allowed_role or "").strip()
    if not base or not name or not allowed:
        return base, []

    removed: list[str] = []
    escaped_name = re.escape(name)
    role_alt = "|".join(
        re.escape(token) for token in sorted(_USER_ROLE_TOKENS, key=len, reverse=True)
    )

    forward_re = re.compile(rf"{escaped_name}(\s*[,·、]?\s*)({role_alt})")

    def _forward_sub(match: re.Match) -> str:
        detected = match.group(2)
        if _user_role_tokens_compatible(detected, allowed):
            return match.group(0)
        removed.append(detected)
        return name

    repaired = forward_re.sub(_forward_sub, base)

    reverse_re = re.compile(rf"({role_alt})(\s+){escaped_name}")

    def _reverse_sub(match: re.Match) -> str:
        detected = match.group(1)
        if _user_role_tokens_compatible(detected, allowed):
            return match.group(0)
        removed.append(detected)
        return name

    repaired = reverse_re.sub(_reverse_sub, repaired)
    return repaired, removed


def enforce_user_role_lock(
    headings: Sequence[Any],
    *,
    full_name: Any,
    allowed_role: Any,
) -> Dict[str, Any]:
    """사용자 본인 옆에 붙은 role token 이 profile 직책과 호환되지 않으면 제거.

    Why: H2 프롬프트·LLM 가 본문 맥락에 휩쓸려 본인({full_name}) 에게 "국회의원"/
         "위원장" 같은 타인 역할을 스탬핑하는 사고를 차단한다. profile 의 직책
         (extract_user_role 로 뽑은 단일 값) 이 SSOT 이며, 그와 호환되지 않는
         토큰은 본인 앵커 주변에서 조용히 strip 한다.
    How to apply: SubheadingAgent 재구성 직전 Phase 6.5 에서 enforce_anchor_cap
                  바로 다음에 호출. 타인 언급(예: "이재명 국회의원") 에는 손대지
                  않는다 — 반드시 full_name 과 인접한 토큰만 대상.
    """
    name = str(full_name or "").strip()
    allowed = str(allowed_role or "").strip()
    result: List[str] = [str(h or "") for h in (headings or [])]

    if not name or not allowed or not result:
        return {"headings": result, "edited": False, "actions": []}

    actions: List[Dict[str, Any]] = []
    for idx, heading in enumerate(result):
        repaired, removed = _strip_conflicting_role_around_name(
            heading,
            full_name=name,
            allowed_role=allowed,
        )
        if not removed:
            continue
        cleaned = re.sub(r"\s{2,}", " ", repaired)
        cleaned = re.sub(r"\s+([,.])", r"\1", cleaned).strip()
        if cleaned and cleaned != heading.strip() and len(cleaned) >= 6:
            result[idx] = cleaned
            actions.append(
                {
                    "index": idx,
                    "before": heading,
                    "after": cleaned,
                    "removed": removed,
                }
            )

    return {"headings": result, "edited": bool(actions), "actions": actions}


_AWKWARD_PLEDGE_RE = re.compile(r"필요성을\s+말씀드립니다$")
_AWKWARD_PROGRESSIVE_RE = re.compile(r"알려지고$")
_AWKWARD_TRUNCATED_VISION_RE = re.compile(r":\s*실질적인\s+변화를\s+비$")


def repair_awkward_phrases(content: Any) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    actions: List[str] = []

    for match in reversed(list(H2_TAG_PATTERN.finditer(base))):
        inner = str(match.group(1) or "")
        plain = _plain_heading(inner)
        if not plain:
            continue

        updated = plain
        local_actions: List[str] = []

        if _AWKWARD_PLEDGE_RE.search(updated):
            updated = _AWKWARD_PLEDGE_RE.sub("말씀드립니다", updated)
            local_actions.append("awkward_h2_pledge_neutralization")
        if _AWKWARD_PROGRESSIVE_RE.search(updated):
            updated = _AWKWARD_PROGRESSIVE_RE.sub("알려지고 있습니다", updated)
            local_actions.append("awkward_h2_incomplete_progressive")
        if _AWKWARD_TRUNCATED_VISION_RE.search(updated):
            updated = _AWKWARD_TRUNCATED_VISION_RE.sub(
                ": 실질적인 변화를 위한 비전",
                updated,
            )
            local_actions.append("awkward_h2_truncated_vision")

        if updated == plain:
            continue

        repaired = repaired[: match.start(1)] + updated + repaired[match.end(1) :]
        actions.extend(local_actions)

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


_BRANDING_CONTEST_TOKENS = ("양자대결", "가상대결", "대결", "접전", "승부", "오차 범위", "지지율")
_BRANDING_RECOGNITION_RE = re.compile(
    r"^(?P<name>[가-힣]{2,8})\s*,?\s*(?:(?P<region>[가-힣]{2,8})\s*)?시민(?:여러분)?에게\s*"
    r"(?:조금씩\s*)?(?:더\s*)?확실히\s*알려지(?:고|며)(?:\s*있습니다)?(?:.*)?$"
)
_BRANDING_ECONOMY_RE = re.compile(
    r"^(?P<region>[가-힣]{2,8})\s*경제는\s*(?P<name>[가-힣]{2,8})(?:입니다)?(?:\s*[:：,，-]\s*.*)?$"
)


def repair_branding_phrases(content: Any) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    actions: List[str] = []

    for match in reversed(list(H2_TAG_PATTERN.finditer(base))):
        inner = str(match.group(1) or "")
        plain = _plain_heading(inner)
        if not plain or "%" in plain or any(token in plain for token in _BRANDING_CONTEST_TOKENS):
            continue

        updated = plain
        local_actions: List[str] = []

        recognition_match = _BRANDING_RECOGNITION_RE.fullmatch(updated)
        if recognition_match:
            name = str(recognition_match.group("name") or "").strip()
            region = str(recognition_match.group("region") or "").strip()
            audience = f"{region} 시민 접점 확대" if region else "시민 접점 확대"
            updated = f"{name} 인지도 상승, {audience}"
            local_actions.append("branding_h2_recognition_rewrite")
        else:
            economy_match = _BRANDING_ECONOMY_RE.fullmatch(updated)
            if economy_match:
                region = str(economy_match.group("region") or "").strip()
                name = str(economy_match.group("name") or "").strip()
                if name.endswith("입니다") and len(name) > 3:
                    name = name[:-3]
                updated = f"{region} 경제 재도약, {name}의 정책 비전"
                local_actions.append("branding_h2_economy_rewrite")

        if updated == plain:
            continue

        repaired = repaired[: match.start(1)] + updated + repaired[match.end(1) :]
        actions.extend(local_actions)

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


# ---------------------------------------------------------------------------
# Entity consistency / 3인칭화 / generic surface 수리
# ---------------------------------------------------------------------------


_PARAGRAPH_TAG_PATTERN = re.compile(r"<p\b[^>]*>([\s\S]*?)</p\s*>", re.IGNORECASE)
_SENTENCE_LIKE_UNIT_PATTERN = re.compile(r"(?:\d+\.\d+|[^.!?。])+(?:[.!?。](?!\d)|$)")

_SUBHEADING_SUBJECT_NOISE_MARKERS: tuple = (
    "조사개요",
    "조사기관",
    "조사기간",
    "조사대상",
    "표본수",
    "표본오차",
    "응답률",
    "중앙선거여론조사심의위원회",
)
_SUBHEADING_LOW_SIGNAL_MARKERS: tuple = (
    "검색어",
    "키워드",
    "표현",
    "문구",
    "가상대결",
    "양자대결",
    "대결",
    "경쟁",
    "비교",
    "행보",
    "거론",
    "언급",
    "주목",
    "후보군",
    "지지율",
)
_SUBHEADING_FIRST_PERSON_SIGNAL_PATTERN = re.compile(
    r"(저는|제가|저의|저만의|제\s*(?:비전|해법|대안|정책|생각|진심|메시지)|말씀드리|설명드리|준비했습니다|제시하겠습니다)",
    re.IGNORECASE,
)
_SUBHEADING_FIRST_PERSON_TOPIC_NOUNS: tuple = (
    "비전", "해법", "대안", "정책", "생각", "진심", "메시지", "방향", "약속",
    "역할", "경쟁력", "가능성", "해결책", "행보", "구상", "계획", "승부수",
    "도전", "실천", "미래", "꿈", "과제", "원칙", "제안", "목표", "다짐",
    "소신", "철학", "이유", "해답", "로드맵", "리더십", "변화", "선택",
    "전략", "강점", "질문", "답", "설명", "주장", "진단", "기회",
)
_SUBHEADING_FIRST_PERSON_TOPIC_NOUN_FRAGMENT = "|".join(
    re.escape(item) for item in _SUBHEADING_FIRST_PERSON_TOPIC_NOUNS
)
_SUBHEADING_FIRST_PERSON_POSSESSIVE_PATTERN = re.compile(
    rf"(?:(?<=^)|(?<=[\s\(\[\{{\"'“”‘’,:/\-]))(?:제|내)"
    rf"(?=\s*(?:{_SUBHEADING_FIRST_PERSON_TOPIC_NOUN_FRAGMENT})"
    rf"(?:은|는|이|가|을|를|의|과|와|도)?(?:$|[\s?!.,]))",
    re.IGNORECASE,
)
_SUBHEADING_NUMERIC_TOKEN_PATTERN = re.compile(
    r"\d{1,4}(?:[.,]\d+)?(?:%p|%|명|일|월|년|회|건|개)?",
    re.IGNORECASE,
)
_SUBHEADING_SIGNAL_SENTENCE_LIMIT = 6
_SUBHEADING_SIGNAL_PARAGRAPH_LIMIT = 3

_CONSECUTIVE_HEADING_TOKEN_RE = re.compile(
    r"(?<![0-9A-Za-z가-힣])(?P<token>[0-9A-Za-z가-힣]{2,})(?:\s+(?P=token))+(?![0-9A-Za-z가-힣])",
    re.IGNORECASE,
)
_MISSING_OBJECT_PARTICLE_HEADING_RE = re.compile(
    r"(?P<head>[0-9A-Za-z가-힣]{2,16})\s+위한\s+(?P<tail>[0-9A-Za-z가-힣]{2,24})",
    re.IGNORECASE,
)
_LOW_SIGNAL_MATCHUP_HEADING_PREFIX_RE = re.compile(
    r"^(?P<prefix>상대\s+후보|상대\s+주자|상대)\s*[,，]\s*(?P<tail>.+(?:구도|쟁점|대결|경쟁).*)$",
    re.IGNORECASE,
)

_MATCHUP_TOKENS: tuple = ("양자대결", "가상대결", "대결", "접전", "승부", "오차 범위")
_ROLE_TRAILING_TOKENS: tuple = (
    "국회의원",
    "의원",
    "시장",
    "지사",
    "도지사",
    "대표",
    "위원장",
    "장관",
    "후보",
    "예비후보",
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _split_sentence_like_units(text: Any) -> List[str]:
    normalized = _normalize_inline_whitespace(text)
    if not normalized:
        return []
    parts = [
        str(match.group(0) or "").strip()
        for match in _SENTENCE_LIKE_UNIT_PATTERN.finditer(normalized)
        if str(match.group(0) or "").strip()
    ]
    return parts or [normalized]


def pick_matchup_counterpart_name(
    section_html: Any,
    *,
    speaker_name: Any,
    known_names: Sequence[Any],
) -> str:
    plain = re.sub(r"<[^>]*>", " ", str(section_html or ""))
    plain = _normalize_inline_whitespace(plain)
    normalized_speaker = normalize_person_name(speaker_name)
    if not plain or not normalized_speaker:
        return ""
    if normalized_speaker not in normalize_person_name(plain):
        return ""
    if not any(token in plain for token in ("양자대결", "가상대결", "대결", "접전", "승부")):
        return ""

    best_name = ""
    best_score = 0
    for name in known_names or []:
        normalized_name = normalize_person_name(name)
        if not normalized_name or normalized_name == normalized_speaker:
            continue
        score = plain.count(normalized_name)
        trailing_alt = "|".join(_ROLE_TRAILING_TOKENS)
        if re.search(
            rf"{re.escape(normalized_name)}\s+(?:현\s*)?(?:전\s*)?(?:{trailing_alt})",
            plain,
            re.IGNORECASE,
        ):
            score += 2
        if score > best_score:
            best_name = normalized_name
            best_score = score
    return best_name if best_score > 0 else ""


def pick_primary_person_name(text: Any, known_names: Sequence[Any]) -> str:
    plain = re.sub(r"<[^>]*>", " ", str(text or ""))
    plain = _normalize_inline_whitespace(plain)
    if not plain or not known_names:
        return ""

    best_name = ""
    best_score = 0
    for name in known_names:
        normalized = normalize_person_name(name)
        if len(normalized) < 2:
            continue
        score = plain.count(normalized)
        if score > best_score:
            best_name = normalized
            best_score = score
    return best_name if best_score > 0 else ""


def is_subheading_subject_noise_sentence(
    sentence: Any,
    *,
    known_names: Sequence[Any],
    preferred_names: Sequence[Any],
) -> bool:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(sentence or "")))
    if not plain:
        return True

    if any(marker in plain for marker in _SUBHEADING_SUBJECT_NOISE_MARKERS):
        return True

    if (
        any(marker in plain for marker in ("검색어", "키워드", "표현", "문구"))
        and any(verb in plain for verb in ("거론", "언급", "주목"))
    ):
        return True

    preferred_set = {
        normalize_person_name(item)
        for item in preferred_names or ()
        if len(normalize_person_name(item)) >= 2
    }
    mentioned_non_preferred = any(
        normalized_name
        and normalized_name not in preferred_set
        and normalized_name in plain
        for normalized_name in (normalize_person_name(item) for item in (known_names or ()))
    )
    if mentioned_non_preferred and any(marker in plain for marker in _SUBHEADING_LOW_SIGNAL_MARKERS):
        return True

    numeric_tokens = _SUBHEADING_NUMERIC_TOKEN_PATTERN.findall(plain)
    if len(numeric_tokens) >= 2 and ("여론조사" in plain or "조사" in plain):
        return True
    return False


def score_subheading_body_names(
    section_html: Any,
    *,
    known_names: Sequence[Any],
    preferred_names: Sequence[Any],
) -> Dict[str, Any]:
    paragraph_matches = list(_PARAGRAPH_TAG_PATTERN.finditer(str(section_html or "")))
    if not paragraph_matches:
        return {"scores": {}, "filteredText": "", "firstPersonSignal": False}

    filtered_sentences: List[str] = []
    first_person_signal = False
    for paragraph_match in paragraph_matches[:_SUBHEADING_SIGNAL_PARAGRAPH_LIMIT]:
        paragraph_plain = _normalize_inline_whitespace(
            re.sub(r"<[^>]*>", " ", str(paragraph_match.group(1) or ""))
        )
        if not paragraph_plain:
            continue

        for sentence in _split_sentence_like_units(paragraph_plain):
            if _SUBHEADING_FIRST_PERSON_SIGNAL_PATTERN.search(sentence):
                first_person_signal = True
            if is_subheading_subject_noise_sentence(
                sentence,
                known_names=known_names,
                preferred_names=preferred_names,
            ):
                continue
            filtered_sentences.append(sentence)
            if len(filtered_sentences) >= _SUBHEADING_SIGNAL_SENTENCE_LIMIT:
                break
        if len(filtered_sentences) >= _SUBHEADING_SIGNAL_SENTENCE_LIMIT:
            break

    filtered_text = " ".join(filtered_sentences).strip()
    scores: Dict[str, int] = {}
    for name in known_names or ():
        normalized_name = normalize_person_name(name)
        if len(normalized_name) < 2:
            continue
        score = filtered_text.count(normalized_name) * 3
        if score > 0:
            scores[normalized_name] = score

    if first_person_signal:
        for preferred in preferred_names or ():
            normalized_preferred = normalize_person_name(preferred)
            if len(normalized_preferred) < 2:
                continue
            scores[normalized_preferred] = int(scores.get(normalized_preferred) or 0) + 2

    return {
        "scores": scores,
        "filteredText": filtered_text,
        "firstPersonSignal": first_person_signal,
    }


def pick_scored_primary_person_name(
    scores: Dict[str, Any],
    *,
    preferred_names: Sequence[Any],
) -> str:
    if not scores:
        return ""

    preferred_set = {
        normalize_person_name(item)
        for item in preferred_names or ()
        if len(normalize_person_name(item)) >= 2
    }
    best_name = ""
    best_score = 0
    for name, score in scores.items():
        normalized_name = normalize_person_name(name)
        score_value = int(score or 0)
        if score_value <= 0 or len(normalized_name) < 2:
            continue
        if score_value > best_score:
            best_name = normalized_name
            best_score = score_value
            continue
        if score_value == best_score and normalized_name in preferred_set and best_name not in preferred_set:
            best_name = normalized_name
    return best_name if best_score > 0 else ""


def third_personize_subheading(
    heading_inner: Any,
    *,
    speaker_name: Any,
) -> tuple:
    normalized_speaker = clean_full_name_candidate(speaker_name)
    if not heading_inner or not normalized_speaker:
        return heading_inner, False

    updated = str(heading_inner)
    changed = False
    direct_replacements = (
        (re.compile(r"(?<![가-힣])저만의", re.IGNORECASE), f"{normalized_speaker}만의"),
        (re.compile(r"(?<![가-힣])저의", re.IGNORECASE), f"{normalized_speaker}의"),
        (re.compile(r"(?<![가-힣])제가", re.IGNORECASE), f"{normalized_speaker}이"),
        (re.compile(r"(?<![가-힣])저는", re.IGNORECASE), f"{normalized_speaker}은"),
        (re.compile(r"(?<![가-힣])나의", re.IGNORECASE), f"{normalized_speaker}의"),
        (re.compile(r"(?<![가-힣])내가", re.IGNORECASE), f"{normalized_speaker}이"),
        (re.compile(r"(?<![가-힣])나는", re.IGNORECASE), f"{normalized_speaker}은"),
    )
    for pattern, replacement in direct_replacements:
        updated, count = pattern.subn(replacement, updated)
        if count > 0:
            changed = True

    updated, possessive_count = _SUBHEADING_FIRST_PERSON_POSSESSIVE_PATTERN.subn(
        f"{normalized_speaker}의",
        updated,
    )
    if possessive_count > 0:
        changed = True

    awkward_possessive_pattern = re.compile(
        rf"(?<![가-힣]){re.escape(normalized_speaker)}이\s+"
        r"((?:[가-힣]{2,8}\s+)?(?:비전|해법|대안|정책|생각|진심|메시지|방향|해결책|경쟁력|가능성|역할))은\?",
        re.IGNORECASE,
    )
    updated, awkward_count = awkward_possessive_pattern.subn(
        rf"{normalized_speaker}의 \1은?",
        updated,
    )
    if awkward_count > 0:
        changed = True

    return updated, changed


def build_subheading_role_surface(
    name: Any,
    role_facts: Any = None,
) -> str:
    normalized_name = normalize_person_name(name)
    if not normalized_name:
        return ""
    raw_role = str(_safe_dict(role_facts).get(normalized_name) or "").strip()
    role_label = canonical_role_label(raw_role)
    if role_label == "국회의원":
        return f"{normalized_name} 의원"
    if raw_role.endswith("시장") and role_label not in {"국회의원", "의원"}:
        return f"{normalized_name} 시장"
    if raw_role.endswith("지사") and role_label not in {"국회의원", "의원"}:
        return f"{normalized_name} 지사"
    if role_label in {"시장", "지사", "대표", "위원장", "장관", "예비후보", "후보"}:
        return f"{normalized_name} {role_label}"
    return normalized_name


def _pick_object_particle_surface(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return "을"
    last_char = normalized[-1]
    code = ord(last_char)
    if 0xAC00 <= code <= 0xD7A3:
        has_batchim = (code - 0xAC00) % 28 != 0
        return "을" if has_batchim else "를"
    return "을"


def _ends_with_object_particle_surface(text: str) -> bool:
    normalized = str(text or "").strip()
    if len(normalized) < 2:
        return False
    last_char = normalized[-1]
    if last_char not in {"을", "를"}:
        return False
    stem = normalized[:-1].strip()
    if not stem:
        return False
    return _pick_object_particle_surface(stem) == last_char


def repair_generic_surface(heading_inner: Any) -> tuple:
    heading_plain = _plain_heading(heading_inner)
    if not heading_plain:
        return heading_inner, []

    updated = str(heading_inner)
    replacements: List[Dict[str, str]] = []

    prefix_repaired, prefix_count = _LOW_SIGNAL_MATCHUP_HEADING_PREFIX_RE.subn(
        lambda match: str(match.group("tail") or "").strip(),
        updated,
        count=1,
    )
    if prefix_count > 0 and prefix_repaired != updated:
        replacements.append(
            {
                "from": heading_plain,
                "to": _plain_heading(prefix_repaired),
                "type": "drop_low_signal_matchup_prefix",
            }
        )
        updated = prefix_repaired
        heading_plain = _plain_heading(updated)

    deduped, dedupe_count = _CONSECUTIVE_HEADING_TOKEN_RE.subn(
        lambda match: str(match.group("token") or "").strip(),
        updated,
    )
    if dedupe_count > 0 and deduped != updated:
        replacements.append(
            {
                "from": heading_plain,
                "to": _plain_heading(deduped),
                "type": "duplicate_heading_token",
            }
        )
        updated = deduped
        heading_plain = _plain_heading(updated)

    repaired_heading, particle_count = _MISSING_OBJECT_PARTICLE_HEADING_RE.subn(
        lambda match: (
            str(match.group(0) or "")
            if _ends_with_object_particle_surface(str(match.group("head") or "").strip())
            else (
                f"{str(match.group('head') or '').strip()}"
                f"{_pick_object_particle_surface(str(match.group('head') or '').strip())} "
                f"위한 {str(match.group('tail') or '').strip()}"
            )
        ),
        updated,
        count=1,
    )
    if particle_count > 0 and repaired_heading != updated:
        replacements.append(
            {
                "from": heading_plain,
                "to": _plain_heading(repaired_heading),
                "type": "heading_missing_object_particle",
            }
        )
        updated = repaired_heading

    return updated, replacements


def repair_malformed_matchup_heading(
    heading_inner: Any,
    *,
    speaker_name: Any,
    known_names: Sequence[Any],
    role_facts: Any = None,
) -> tuple:
    heading_plain = _plain_heading(heading_inner)
    normalized_speaker = normalize_person_name(speaker_name)
    if not heading_plain or not normalized_speaker:
        return heading_inner, None
    if not any(token in heading_plain for token in _MATCHUP_TOKENS):
        return heading_inner, None

    normalized_known = [
        normalize_person_name(item)
        for item in (known_names or [])
        if normalize_person_name(item) and normalize_person_name(item) != normalized_speaker
    ]
    for other_name in normalized_known:
        role_surface = build_subheading_role_surface(other_name, role_facts=role_facts) or other_name
        patterns = (
            re.compile(
                rf"{re.escape(other_name)}\s+(?:현|전)\s+{re.escape(normalized_speaker)}의\s+"
                rf"(?P<tail>(?:양자대결|가상대결|대결|접전|승부|오차 범위)[^<]*)",
                re.IGNORECASE,
            ),
            re.compile(
                rf"{re.escape(other_name)}\s+(?:현|전)\s+{re.escape(normalized_speaker)}\s+"
                rf"(?P<tail>(?:양자대결|가상대결|대결|접전|승부|오차 범위)[^<]*)",
                re.IGNORECASE,
            ),
        )
        for pattern in patterns:
            updated, count = pattern.subn(
                lambda match: f"{role_surface}과의 {str(match.group('tail') or '').strip()}",
                str(heading_inner),
                count=1,
            )
            if count > 0 and updated != heading_inner:
                return updated, {
                    "from": heading_plain,
                    "to": _plain_heading(updated),
                    "type": "malformed_matchup_heading",
                }
    return heading_inner, None


def repair_speaker_role_mismatch_matchup_heading(
    heading_inner: Any,
    *,
    speaker_name: Any,
    body_name: Any,
    role_facts: Any = None,
) -> tuple:
    heading_plain = _plain_heading(heading_inner)
    normalized_speaker = normalize_person_name(speaker_name)
    normalized_body = normalize_person_name(body_name)
    if not heading_plain or not normalized_speaker or not normalized_body:
        return heading_inner, None
    if normalized_speaker == normalized_body:
        return heading_inner, None
    if not any(token in heading_plain for token in _MATCHUP_TOKENS):
        return heading_inner, None

    role_surface = build_subheading_role_surface(normalized_body, role_facts=role_facts) or normalized_body
    trailing_alt = "|".join(_ROLE_TRAILING_TOKENS)
    pattern = re.compile(
        rf"{re.escape(normalized_speaker)}\s+(?:현\s*)?(?:전\s*)?(?:{trailing_alt})"
        rf"(?P<tail>\s*(?:과의|와의)?\s*(?:양자대결|가상대결|대결|접전|승부|오차 범위)[^<]*)",
        re.IGNORECASE,
    )
    updated, count = pattern.subn(
        lambda match: f"{role_surface}{str(match.group('tail') or '')}",
        str(heading_inner),
        count=1,
    )
    if count > 0 and updated != heading_inner:
        return updated, {
            "from": heading_plain,
            "to": _plain_heading(updated),
            "type": "speaker_role_mismatch_matchup_heading",
        }
    return heading_inner, None


def repair_entity_consistency(
    content: Any,
    known_names: Sequence[Any],
    *,
    preferred_names: Sequence[Any] = (),
    role_facts: Any = None,
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip() or not known_names:
        return {"content": base, "edited": False, "replacements": []}

    normalized_preferred = [
        normalize_person_name(item)
        for item in (preferred_names or [])
        if len(normalize_person_name(item)) >= 2
    ]
    preferred_name_set = set(normalized_preferred)
    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    if not h2_matches:
        return {"content": base, "edited": False, "replacements": []}

    replacements: List[Dict[str, Any]] = []
    repaired = base
    speaker_name = normalized_preferred[0] if normalized_preferred else ""

    for idx in range(len(h2_matches) - 1, -1, -1):
        match = h2_matches[idx]
        heading_inner = str(match.group(1) or "")
        heading_plain = _plain_heading(heading_inner)
        if not heading_plain:
            continue

        generic_heading_inner, generic_replacements = repair_generic_surface(heading_inner)
        if generic_replacements:
            repaired = repaired[: match.start(1)] + generic_heading_inner + repaired[match.end(1):]
            replacements.extend(generic_replacements)
            heading_inner = generic_heading_inner
            heading_plain = _plain_heading(heading_inner)

        updated_heading_inner, renamed_first_person = third_personize_subheading(
            heading_inner,
            speaker_name=speaker_name,
        )
        if renamed_first_person:
            repaired = repaired[: match.start(1)] + updated_heading_inner + repaired[match.end(1):]
            replacements.append(
                {
                    "from": "first_person_pronoun",
                    "to": speaker_name,
                    "headingBefore": heading_plain,
                    "headingAfter": _plain_heading(updated_heading_inner),
                }
            )
            heading_inner = updated_heading_inner
            heading_plain = _plain_heading(heading_inner)
        if re.search(r"(검색어|키워드|표현|문구)", heading_plain):
            continue

        integrity_heading_inner, malformed_replacement = repair_malformed_matchup_heading(
            heading_inner,
            speaker_name=speaker_name,
            known_names=known_names,
            role_facts=role_facts,
        )
        if malformed_replacement:
            repaired = repaired[: match.start(1)] + integrity_heading_inner + repaired[match.end(1):]
            replacements.append(malformed_replacement)
            heading_inner = integrity_heading_inner
            heading_plain = _plain_heading(heading_inner)

        section_start = match.end()
        section_end = h2_matches[idx + 1].start() if idx < len(h2_matches) - 1 else len(repaired)
        section_html = repaired[section_start:section_end]
        matchup_counterpart_name = pick_matchup_counterpart_name(
            section_html,
            speaker_name=speaker_name,
            known_names=list(known_names),
        )
        heading_name = pick_primary_person_name(heading_plain, list(known_names))
        subject_signal = score_subheading_body_names(
            section_html,
            known_names=known_names,
            preferred_names=normalized_preferred,
        )
        body_scores = subject_signal.get("scores") if isinstance(subject_signal, dict) else {}
        if not isinstance(body_scores, dict):
            body_scores = {}
        body_name = pick_scored_primary_person_name(
            {
                normalize_person_name(name): int(score or 0)
                for name, score in body_scores.items()
                if len(normalize_person_name(name)) >= 2
            },
            preferred_names=normalized_preferred,
        )
        if matchup_counterpart_name:
            body_name = matchup_counterpart_name
        mismatch_heading_inner, mismatch_replacement = repair_speaker_role_mismatch_matchup_heading(
            heading_inner,
            speaker_name=speaker_name,
            body_name=body_name,
            role_facts=role_facts,
        )
        if mismatch_replacement:
            repaired = repaired[: match.start(1)] + mismatch_heading_inner + repaired[match.end(1):]
            replacements.append(mismatch_replacement)
            continue
        if not heading_name or not body_name or heading_name == body_name:
            continue
        if heading_name in preferred_name_set and body_name not in preferred_name_set:
            continue
        # 방어 가드: 화자(speaker_name, 즉 본인 full_name)는 H2 에서 절대로
        # 다른 이름으로 치환되지 않는다. preferred_names 가 상위 호출자에서
        # 오염되더라도 화자 이름만은 지킨다 (Bug 1 재발 방지).
        if speaker_name and heading_name == speaker_name:
            continue
        body_name_score = int(body_scores.get(body_name) or 0)
        heading_name_score = int(body_scores.get(heading_name) or 0)
        if body_name_score <= heading_name_score:
            continue

        updated_heading_inner, changed = re.subn(
            re.escape(heading_name),
            body_name,
            heading_inner,
            count=1,
        )
        if changed <= 0:
            continue

        repaired = repaired[: match.start(1)] + updated_heading_inner + repaired[match.end(1):]
        replacements.append(
            {
                "from": heading_name,
                "to": body_name,
                "headingBefore": heading_plain,
                "headingAfter": _plain_heading(updated_heading_inner),
            }
        )

    return {
        "content": repaired,
        "edited": repaired != base,
        "replacements": replacements,
    }
