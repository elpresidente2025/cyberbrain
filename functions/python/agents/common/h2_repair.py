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

import re
from typing import Any, Dict, List, Sequence

from .person_naming import extract_keyword_person_role
from .role_keyword_policy import ROLE_KEYWORD_PATTERN

__all__ = [
    "H2_TAG_PATTERN",
    "build_keyword_intent_h2",
    "ensure_keyword_first_slot",
    "ensure_user_keyword_first_slot",
    "repair_awkward_phrases",
    "repair_branding_phrases",
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
