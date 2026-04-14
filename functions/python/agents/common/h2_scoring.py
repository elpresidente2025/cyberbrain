"""H2 소제목 점수화 — 플랜 기반 rubric 게이트.

SubheadingAgent의 Plan → Gen → Score → Repair 파이프라인에서 세 번째 단계.
생성된 헤딩이 rulebook 기준을 얼마나 충족하는지 가중 점수로 환산하고,
임계값(H2_MIN_PASSING_SCORE) 기준으로 통과/실패를 판정한다.

순수 함수만 — I/O 없음, LLM 호출 없음, 전역 상태 없음.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, TypedDict

from .h2_guide import (
    H2_MAX_LENGTH,
    H2_MIN_LENGTH,
    _H2_CONSECUTIVE_DUPLICATE_TOKEN_RE,
    _H2_DUPLICATED_PARTICLE_RE,
    has_incomplete_h2_ending,
    normalize_h2_style,
)
from .h2_planning import SectionPlan

__all__ = [
    "H2Score",
    "H2_MIN_PASSING_SCORE",
    "H2_HARD_FAIL_ISSUES",
    "H2_BANNED_PATTERNS_AEO",
    "H2_BANNED_PATTERNS_ASSERTIVE",
    "score_h2",
]


# TUNABLE: 통과 임계값 — 프로덕션 로그에서 h2Trace.first_score 분포를 보고 조정
H2_MIN_PASSING_SCORE = 0.65

# 구조적 위반 — 점수 총합과 무관하게 passed=False 로 강제한다.
H2_HARD_FAIL_ISSUES = frozenset(
    {
        "EMPTY_HEADING",
        "KEYWORD_MISSING",
        "INCOMPLETE_ENDING",
        "QUESTION_FORM_IN_ASSERTIVE",
        "DUPLICATE_PARTICLE_OR_TOKEN",
    }
)

_WEIGHTS = {
    "length": 0.20,
    "keyword": 0.20,
    "type": 0.15,
    "banned": 0.15,
    "ending": 0.15,
    "assertive_gate": 0.10,
    "duplicate": 0.05,
}


# ---------------------------------------------------------------------------
# Banned pattern 테이블 (h2_guide.py 152-160, 185 규칙의 측정 가능한 형태)
# ---------------------------------------------------------------------------

H2_BANNED_PATTERNS_AEO: List[tuple] = [
    ("추상표현", re.compile(r"(노력|열정|마음가짐|최선|열심히)")),
    ("모호지시어", re.compile(r"(이것|그것|저것|관련\s?내용|관련\s?이야기)")),
    ("과장표현", re.compile(r"(최고의?|혁명적|놀라운|엄청난|대박)")),
    ("서술어포함", re.compile(r"(에\s?대한\s?설명|을\s?알려드립니다|에\s?관한\s?모든)")),
    ("1인칭", re.compile(r"(저는|제가|나는|내가)")),
    ("후보약속형", re.compile(r"반드시\s?해내겠")),
]

H2_BANNED_PATTERNS_ASSERTIVE: List[tuple] = [
    ("질문형어미", re.compile(r"(인가요|일까요|할까요|할까|인가\?)$")),
    ("완곡유도", re.compile(r"(생각해\s?봅시다|함께\s?보시죠|같이\s?살펴봐요)")),
    ("내용없는추상", re.compile(r"^(정책|입장|논평|소개|안내|이야기)$")),
]


_QUESTION_TAIL_RE = re.compile(r"(\?|나요$|까요$|할까$|는가$|는지$)")
_DATA_PRESENCE_RE = re.compile(r"\d")
_PROCEDURAL_RE = re.compile(r"(단계|절차|방법|순서|가이드)")
_COMPARATIVE_RE = re.compile(r"(vs|대비|차이|비교)")
_DECLARATIVE_TAIL_RE = re.compile(r"(이다|아니다|한다|해야|없다|된다)$")
_CRITICAL_RE = re.compile(r"(거부|회피|남용|파괴|왜곡|무너|실패|한계)")


# ---------------------------------------------------------------------------
# TypedDict
# ---------------------------------------------------------------------------


class H2Score(TypedDict, total=False):
    heading: str
    score: float
    passed: bool
    issues: List[str]
    category_tags: List[str]
    breakdown: Dict[str, Dict[str, float]]


# ---------------------------------------------------------------------------
# 축별 스코어
# ---------------------------------------------------------------------------


def _length_band_score(heading: str) -> float:
    length = len(heading)
    if 15 <= length <= 22:
        return 1.0
    if 12 <= length <= 14 or 23 <= length <= 25:
        return 0.7
    if 10 <= length <= 11 or 26 <= length <= 27:
        return 0.3
    return 0.0


def _keyword_first_third_score(heading: str, keyword: str) -> float:
    keyword = str(keyword or "").strip()
    heading = str(heading or "")
    if not keyword or not heading:
        return 0.0
    first_third_len = max(len(keyword), len(heading) // 3 + 1)
    head_slice = heading[:first_third_len]
    if keyword in head_slice:
        return 1.0
    if keyword in heading:
        return 0.5
    return 0.0


def _type_match_score(heading: str, suggested_type: str, preferred_types: List[str]) -> float:
    heading = str(heading or "")
    suggested_type = str(suggested_type or "")

    def match_type(type_name: str) -> bool:
        if not type_name:
            return False
        if type_name == "질문형":
            return bool(_QUESTION_TAIL_RE.search(heading) or heading.rstrip().endswith("?"))
        if type_name == "데이터형":
            return bool(_DATA_PRESENCE_RE.search(heading))
        if type_name == "절차형":
            return bool(_PROCEDURAL_RE.search(heading))
        if type_name == "비교형":
            return bool(_COMPARATIVE_RE.search(heading))
        if type_name in ("단정형", "주장형"):
            return bool(_DECLARATIVE_TAIL_RE.search(heading.rstrip()))
        if type_name == "비판형":
            return bool(_CRITICAL_RE.search(heading))
        if type_name == "명사형":
            return not bool(_QUESTION_TAIL_RE.search(heading))
        return False

    if match_type(suggested_type):
        return 1.0
    for alt in preferred_types or ():
        if alt == suggested_type:
            continue
        if match_type(alt):
            return 0.5
    return 0.0


def _banned_pattern_hits(heading: str, style: str) -> List[str]:
    table = H2_BANNED_PATTERNS_ASSERTIVE if style == "assertive" else H2_BANNED_PATTERNS_AEO
    hits: List[str] = []
    for label, pattern in table:
        if pattern.search(heading):
            hits.append(label)
    return hits


def _banned_pattern_score(hit_count: int) -> float:
    return max(0.0, 1.0 - 0.4 * hit_count)


def _assertive_question_gate_score(heading: str, style: str) -> tuple:
    """assertive 스타일에서만 질문형을 금지한다. AEO는 중립 1.0."""
    if style != "assertive":
        return (1.0, False)
    if heading.rstrip().endswith("?") or _QUESTION_TAIL_RE.search(heading):
        return (0.0, True)
    return (1.0, False)


def _duplicate_score(heading: str) -> tuple:
    """sanitize_h2_text 이후 잔존하는 중복 검사 — defense in depth."""
    if _H2_DUPLICATED_PARTICLE_RE.search(heading) or _H2_CONSECUTIVE_DUPLICATE_TOKEN_RE.search(heading):
        return (0.0, True)
    return (1.0, False)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def score_h2(
    heading: str,
    plan: SectionPlan,
    *,
    style: str = "aeo",
    preferred_types: Optional[List[str]] = None,
    passing_threshold: Optional[float] = None,
) -> H2Score:
    """주어진 heading 을 plan 과 대조해 rubric 점수를 반환한다."""
    normalized_style = normalize_h2_style(style)
    heading_text = str(heading or "").strip()
    threshold = (
        float(passing_threshold) if passing_threshold is not None else H2_MIN_PASSING_SCORE
    )
    issues: List[str] = []
    breakdown: Dict[str, Dict[str, float]] = {}

    if not heading_text:
        return H2Score(
            heading="",
            score=0.0,
            passed=False,
            issues=["EMPTY_HEADING"],
            category_tags=[normalized_style],
            breakdown={},
        )

    length_raw = _length_band_score(heading_text)
    length_weighted = length_raw * _WEIGHTS["length"]
    if length_raw < 1.0:
        if len(heading_text) < H2_MIN_LENGTH:
            issues.append("LENGTH_TOO_SHORT")
        elif len(heading_text) > H2_MAX_LENGTH:
            issues.append("LENGTH_TOO_LONG")
        else:
            issues.append("LENGTH_OUT_OF_BAND")
    breakdown["length"] = {"raw": length_raw, "weighted": length_weighted, "chars": float(len(heading_text))}

    keyword = str(plan.get("must_include_keyword") or "").strip()
    keyword_raw = _keyword_first_third_score(heading_text, keyword)
    keyword_weighted = keyword_raw * _WEIGHTS["keyword"]
    if keyword_raw < 1.0:
        if keyword_raw == 0.0:
            issues.append("KEYWORD_MISSING")
        else:
            issues.append("KEYWORD_NOT_IN_FIRST_THIRD")
    breakdown["keyword"] = {"raw": keyword_raw, "weighted": keyword_weighted}

    suggested_type = str(plan.get("suggested_type") or "")
    resolved_preferred = preferred_types or []
    type_raw = _type_match_score(heading_text, suggested_type, resolved_preferred)
    type_weighted = type_raw * _WEIGHTS["type"]
    if type_raw < 1.0:
        issues.append("TYPE_MISMATCH")
    breakdown["type"] = {"raw": type_raw, "weighted": type_weighted}

    banned_hits = _banned_pattern_hits(heading_text, normalized_style)
    banned_raw = _banned_pattern_score(len(banned_hits))
    banned_weighted = banned_raw * _WEIGHTS["banned"]
    for label in banned_hits:
        issues.append(f"BANNED_PATTERN:{label}")
    breakdown["banned"] = {"raw": banned_raw, "weighted": banned_weighted, "hits": float(len(banned_hits))}

    if has_incomplete_h2_ending(heading_text):
        ending_raw = 0.0
        issues.append("INCOMPLETE_ENDING")
    else:
        ending_raw = 1.0
    ending_weighted = ending_raw * _WEIGHTS["ending"]
    breakdown["ending"] = {"raw": ending_raw, "weighted": ending_weighted}

    assertive_raw, assertive_fail = _assertive_question_gate_score(heading_text, normalized_style)
    assertive_weighted = assertive_raw * _WEIGHTS["assertive_gate"]
    if assertive_fail:
        issues.append("QUESTION_FORM_IN_ASSERTIVE")
    breakdown["assertive_gate"] = {"raw": assertive_raw, "weighted": assertive_weighted}

    dup_raw, dup_fail = _duplicate_score(heading_text)
    dup_weighted = dup_raw * _WEIGHTS["duplicate"]
    if dup_fail:
        issues.append("DUPLICATE_PARTICLE_OR_TOKEN")
    breakdown["duplicate"] = {"raw": dup_raw, "weighted": dup_weighted}

    total = round(
        length_weighted
        + keyword_weighted
        + type_weighted
        + banned_weighted
        + ending_weighted
        + assertive_weighted
        + dup_weighted,
        4,
    )

    category_tags = [normalized_style]
    if suggested_type:
        category_tags.append(suggested_type)

    hard_fail = any(
        (issue.split(":", 1)[0] if isinstance(issue, str) else "")
        in H2_HARD_FAIL_ISSUES
        for issue in issues
    )
    passed = (total >= threshold) and not hard_fail

    return H2Score(
        heading=heading_text,
        score=total,
        passed=passed,
        issues=issues,
        category_tags=category_tags,
        breakdown=breakdown,
    )
