"""H2 소제목 점수화 — 플랜 기반 rubric 게이트.

SubheadingAgent의 Plan → Gen → Score → Repair 파이프라인에서 세 번째 단계.
생성된 헤딩이 rulebook 기준을 얼마나 충족하는지 가중 점수로 환산하고,
임계값(H2_MIN_PASSING_SCORE) 기준으로 통과/실패를 판정한다.

순수 함수만 — I/O 없음, LLM 호출 없음, 전역 상태 없음.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, TypedDict

from . import korean_morph
from .h2_guide import (
    H2_ARCHETYPE_NAMES,
    H2_MAX_LENGTH,
    H2_MIN_LENGTH,
    _H2_CONSECUTIVE_DUPLICATE_TOKEN_RE,
    _H2_DUPLICATED_PARTICLE_RE,
    detect_h2_archetype,
    has_incomplete_h2_ending,
    is_h2_archetype,
    normalize_h2_style,
)
from .h2_planning import SectionPlan

__all__ = [
    "H2Score",
    "H2_AEO_ADVISORIES",
    "H2_MIN_PASSING_SCORE",
    "H2_HARD_FAIL_ISSUES",
    "H2_BANNED_PATTERNS_AEO",
    "H2_BANNED_PATTERNS_ASSERTIVE",
    "H2_EMOTION_STRUCTURE_PATTERNS",
    "score_h2",
    "score_h2_aeo",
    "detect_emotion_appeal",
    "count_entity_distribution",
    "compute_anchor_cap",
    "detect_sibling_suffix_overlap",
]


def compute_anchor_cap(section_count: int) -> int:
    """H2 세트 내 fullName 앵커 허용 횟수.

    Why: memory feedback — H2 세트에서 fullName은 1~2회 앵커 (키워드 스탬핑 금지).
    제목이 이미 fullName을 포함하는 경우가 대부분이라 H2는 더 적게 허용해야 체감상
    '반복 스탬핑' 을 피한다. 섹션이 많을수록 한 번 더 허용.
    """
    try:
        count = int(section_count or 0)
    except (TypeError, ValueError):
        count = 0
    if count <= 4:
        return 1
    return 2


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
        "H2_EMOTION_APPEAL",
        # plan 의 suggested_type 이 "질문형" 인데 실제 heading 이
        # 의문 종결어미/의문부호를 갖추지 못한 경우. plan archetype 과
        # 실제 output 이 어긋나면 LLM repair 결과가 쓰레기여도 점수만
        # 합격하는 것을 막기 위해 hard-fail 로 격상한다.
        "H2_QUESTION_FORM_REQUIRED",
        # H2 가 자기 아래 섹션 본문을 답으로 삼지 않음.
        # "H2 = 본문이 정답인 질문/주장" 원칙을 깨고 본문에 없는 키워드·
        # 날조 약어·다른 주제를 H2 로 올린 경우 hard-fail.
        "BODY_ALIGNMENT_LOW",
    }
)

# AEO 어드바이저리 — 점수에는 반영되지만 passed 결정에는 개입하지 않는다.
# PR 6 이후 prod 데이터 확인 후 일부를 hard-fail 로 격상할 수 있다.
H2_AEO_ADVISORIES = frozenset(
    {
        "H2_NO_SUBJECT_ENTITY",
        "H2_NO_QUESTION_FORM",
        "H2_SHORT_LENGTH",
        "H2_LONG_LENGTH",
        "H2_ENTITY_ANCHOR_MISSING",
        "H2_ENTITY_ANCHOR_EXCESS",
        "H2_KEYWORD_STAMP_WARNING",
        "H2_USER_KEYWORD_STAMP",
        "H2_SIBLING_SUFFIX_OVERLAP",
        "H2_BODY_ECHO_FIRST_SENTENCE",
        "H2_QA_PAIRING_FAIL",
        "H2_CANONICAL_FORM_MISMATCH",
    }
)

_WEIGHTS = {
    "length": 0.17,
    "keyword": 0.17,
    "type": 0.13,
    "banned": 0.13,
    "ending": 0.13,
    "assertive_gate": 0.09,
    "body_alignment": 0.14,
    "duplicate": 0.04,
}


# H2 content token 추출용 — 조사/어미/불용어 배제한 2+ 글자 내용어
_H2_ALIGNMENT_TOKEN_RE = re.compile(r"[가-힣A-Za-z]{2,}")
_H2_ALIGNMENT_STOPWORDS = frozenset(
    {
        "하는", "되는", "이다", "있다", "없다", "있는", "없는",
        "대한", "관련", "위한", "통해", "통한", "위해", "대해",
        "지금", "이번", "우리", "여러분", "모든", "다른", "새로운",
        "오늘", "지난", "앞으로", "지속", "그리고", "하지만",
        "그러나", "또한", "한편", "다시", "계속",
    }
)

# H2 가 본문 답이 아닐 때 hard-fail 로 격상하는 coverage 임계
_BODY_ALIGNMENT_HARD_FAIL = 0.34
# 부분 감점만 주는 soft 임계 (이 사이는 비례 스코어)
_BODY_ALIGNMENT_FULL_PASS = 0.67


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


def _h2_content_tokens(text: str) -> List[str]:
    """H2 / 본문 alignment 비교용 content token 을 추출한다.

    kiwi 가 사용 가능하면 NNG/NNP/NNB 명사만 남긴다 (어근 수준 매칭).
    실패 시 정규식 fallback — 2+ 글자 한글/영문 토큰에서 불용어 제거.
    """
    plain = str(text or "").strip()
    if not plain:
        return []
    kiwi_nouns = korean_morph.extract_nouns(plain)
    if kiwi_nouns is not None:
        return [tok for tok in kiwi_nouns if len(tok) >= 2 and tok not in _H2_ALIGNMENT_STOPWORDS]
    return [
        tok for tok in _H2_ALIGNMENT_TOKEN_RE.findall(plain)
        if tok not in _H2_ALIGNMENT_STOPWORDS
    ]


def _body_alignment_coverage(heading: str, section_text: str) -> float:
    """H2 content token 중 섹션 본문에 substring 으로 등장하는 비율.

    Why: "H2 는 그 아래 본문을 정답으로 간주한 질문/주장" 원칙 — H2 의
         내용어(명사)가 본문에 실제로 근거를 두고 있어야 한다. 본문에 없는
         키워드·날조 약어·다른 주제를 H2 에 꽂으면 coverage 가 낮게 나온다.
    How to apply: 반환값은 0.0~1.0. 본문 또는 heading token 이 없으면 1.0
         (체크 생략). score_h2 는 이 값을 기반으로 BODY_ALIGNMENT_LOW 판정.

    매칭은 substring 기준(부분 일치) — "인천광역시" 가 본문 "인천광역시의원"
    안에 있으면 매칭으로 친다. kiwi 경로에서는 명사 form 기준이라 노이즈가
    적어 substring 매칭이 안전.
    """
    heading_tokens = _h2_content_tokens(heading)
    if not heading_tokens:
        return 1.0
    body = str(section_text or "").strip()
    if not body:
        return 1.0
    # 중복 토큰 제거 (같은 단어가 H2 에서 2번 나와도 1 counting)
    unique_tokens = list(dict.fromkeys(heading_tokens))
    matched = sum(1 for tok in unique_tokens if tok in body)
    return matched / len(unique_tokens)


def _body_alignment_score(coverage: float) -> float:
    """coverage → raw score(0.0~1.0) 변환.

    >= _BODY_ALIGNMENT_FULL_PASS (0.67) : 1.0 만점
    <= _BODY_ALIGNMENT_HARD_FAIL (0.34) : 0.0 바닥
    그 사이: 선형 보간
    """
    if coverage >= _BODY_ALIGNMENT_FULL_PASS:
        return 1.0
    if coverage <= _BODY_ALIGNMENT_HARD_FAIL:
        return 0.0
    span = _BODY_ALIGNMENT_FULL_PASS - _BODY_ALIGNMENT_HARD_FAIL
    return round((coverage - _BODY_ALIGNMENT_HARD_FAIL) / span, 4)


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


def _archetype_match_score(
    heading: str,
    primary_archetypes: List[str],
    auxiliary_archetypes: List[str],
) -> float:
    """아키타입 기반 type 점수.

    Why: "소제목이 약속, 본문이 이행" AEO 구조에서 소제목은 6 아키타입
    (질문/목표/주장/이유/대조/사례) 중 허용 풀 안에 들어야 한다. 기본 풀(primary)
    에 해당하면 1.0, 보조 풀(auxiliary)이면 0.5, 둘 다 밖이면 0.0.
    """
    text = str(heading or "")
    if not text:
        return 0.0

    primary = [str(a).strip() for a in (primary_archetypes or ()) if str(a).strip()]
    auxiliary = [str(a).strip() for a in (auxiliary_archetypes or ()) if str(a).strip()]

    for archetype in primary:
        if is_h2_archetype(text, archetype):
            return 1.0
    for archetype in auxiliary:
        if is_h2_archetype(text, archetype):
            return 0.5
    return 0.0


def _type_match_score(heading: str, suggested_type: str, preferred_types: List[str]) -> float:
    """레거시 시그니처 shim — preferred_types 를 primary 아키타입 풀로 간주한다.

    suggested_type 은 plan 이 제안한 archetype 이름 (h2_planning.pick_suggested_type
    가 생성). primary 매치 1.0, 다른 preferred 매치 0.5 로 유지한다.
    """
    text = str(heading or "")
    suggested = str(suggested_type or "").strip()
    preferred = [str(a).strip() for a in (preferred_types or ()) if str(a).strip()]

    if suggested and is_h2_archetype(text, suggested):
        return 1.0
    for archetype in preferred:
        if archetype == suggested:
            continue
        if is_h2_archetype(text, archetype):
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

    # plan 이 "질문형" archetype 을 배정했는데 실제 heading 이 질문 형태가 아니면
    # hard-fail. 점수만 합격해서 의문형 공백을 그대로 두는 것을 차단한다.
    if suggested_type == "질문형" and not _has_question_form(heading_text):
        issues.append("H2_QUESTION_FORM_REQUIRED")

    dup_raw, dup_fail = _duplicate_score(heading_text)
    dup_weighted = dup_raw * _WEIGHTS["duplicate"]
    if dup_fail:
        issues.append("DUPLICATE_PARTICLE_OR_TOKEN")
    breakdown["duplicate"] = {"raw": dup_raw, "weighted": dup_weighted}

    # H2 가 본문을 정답으로 삼고 있는가 — content token coverage 기반
    section_text = str(plan.get("section_text") or "")
    alignment_coverage = _body_alignment_coverage(heading_text, section_text)
    alignment_raw = _body_alignment_score(alignment_coverage)
    alignment_weighted = alignment_raw * _WEIGHTS["body_alignment"]
    if alignment_coverage < _BODY_ALIGNMENT_HARD_FAIL:
        issues.append("BODY_ALIGNMENT_LOW")
    elif alignment_coverage < _BODY_ALIGNMENT_FULL_PASS:
        issues.append("BODY_ALIGNMENT_PARTIAL")
    breakdown["body_alignment"] = {
        "raw": alignment_raw,
        "weighted": alignment_weighted,
        "coverage": round(alignment_coverage, 4),
    }

    total = round(
        length_weighted
        + keyword_weighted
        + type_weighted
        + banned_weighted
        + ending_weighted
        + assertive_weighted
        + alignment_weighted
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


# ---------------------------------------------------------------------------
# AEO 확장: 감정 호소형 탐지 · 엔티티 분포 · 인접 H2 꼬리 중복 · AEO 점수
# ---------------------------------------------------------------------------

# 감정 호소형 / 수사형 문장 구조. 어휘가 아니라 **구조** 매칭이 핵심.
H2_EMOTION_STRUCTURE_PATTERNS: List[tuple] = [
    # "~이 없었다면 ~다" (반어형 수사)
    ("reverse_counterfactual", re.compile(r".+(?:이|가)\s*없었다면\s+.+")),
    # "함께 더 ~", "함께 ~ 가자/갑시다"
    ("together_call", re.compile(r"^함께\s+")),
    ("together_march", re.compile(r"함께\s+.{1,12}(?:가자|갑시다|나아가)")),
    # "~을 위한 길"
    ("path_for", re.compile(r".+(?:을|를)\s*위한\s*(?:길|여정|약속)$")),
    # "지금 이 순간", "바로 지금"
    ("now_appeal", re.compile(r"^(?:지금\s*이\s*순간|바로\s*지금|오늘부터)")),
    # 명사 단독 호소형: "변화는 ~다", "미래는 ~다"
    ("abstract_noun_declaration", re.compile(r"^(?:변화|미래|희망|내일)는\s+.+")),
    # "믿습니다 / 약속드립니다" 단독 종결
    ("pledge_solo", re.compile(r"(?:약속드립니다|믿습니다|다짐합니다)$")),
]

_QUESTION_FORM_HINTS = ("어떻게", "무엇", "왜", "누가", "언제", "어디서", "무슨", "어떤")
_SIBLING_SUFFIX_OVERLAP_THRESHOLD = 1  # 1쌍만 중복돼도 어드바이저리 트리거


def detect_emotion_appeal(heading: str) -> Optional[str]:
    """감정 호소형 / 수사형 구조 패턴을 탐지한다.

    매칭되면 패턴 라벨, 아니면 None. 이 결과는 hard-fail 판정에 쓰인다
    (정치·자기PR 카테고리 기본). 매칭 로직은 정규식 리스트 기반으로 유지.
    """
    text = str(heading or "").strip()
    if not text:
        return None
    for label, pattern in H2_EMOTION_STRUCTURE_PATTERNS:
        if pattern.search(text):
            return label
    return None


def count_entity_distribution(
    headings: List[str],
    *,
    full_name: str,
    descriptor_pool: Optional[List[str]] = None,
) -> Dict[str, int]:
    """H2 세트 전체에서 본명·descriptor 등장 분포를 센다.

    반환: `{"full_name": N, "descriptor": M, "neither": K}`.
    anchor 비율 판정·키워드 스탬핑 경고에 쓰인다.
    """
    name_clean = str(full_name or "").strip()
    pool = [str(item).strip() for item in (descriptor_pool or []) if str(item).strip()]
    distribution = {"full_name": 0, "descriptor": 0, "neither": 0}
    for heading in headings or []:
        text = str(heading or "")
        if name_clean and name_clean in text:
            distribution["full_name"] += 1
            continue
        matched = False
        for descriptor in pool:
            if descriptor and descriptor in text:
                distribution["descriptor"] += 1
                matched = True
                break
        if not matched:
            distribution["neither"] += 1
    return distribution


def detect_sibling_suffix_overlap(headings: List[str]) -> List[tuple]:
    """인접 H2 간 마지막 어절 / penultimate 토큰 중복을 탐지한다.

    두 축을 본다:
    1) 마지막 두 어절 bigram (완전 중복)
    2) 마지막 어절 + penultimate 어절 각각의 개별 등장 회수
       — 2회 이상이면 "테마 토큰 스탬핑" 신호

    반환: (토큰 또는 bigram, 회수) 리스트. 2쌍 이상이면
    `H2_SIBLING_SUFFIX_OVERLAP` 어드바이저리 트리거.
    """
    cleaned = [str(heading or "").strip() for heading in headings or []]
    cleaned = [h for h in cleaned if h]
    if len(cleaned) < 2:
        return []

    def last_two_tokens(text: str) -> tuple:
        tokens = re.findall(r"[가-힣A-Za-z0-9]+", text)
        if len(tokens) < 2:
            return tuple(tokens)
        return tuple(tokens[-2:])

    suffix_counts: Dict[tuple, int] = {}
    last_single_counts: Dict[str, int] = {}
    penultimate_counts: Dict[str, int] = {}
    for heading in cleaned:
        tail = last_two_tokens(heading)
        if len(tail) == 2:
            suffix_counts[tail] = suffix_counts.get(tail, 0) + 1
            penultimate_counts[tail[0]] = penultimate_counts.get(tail[0], 0) + 1
        if tail:
            last_single_counts[tail[-1]] = last_single_counts.get(tail[-1], 0) + 1

    overlaps: List[tuple] = []
    seen_tokens: set = set()
    for pair, count in suffix_counts.items():
        if count >= 2:
            label = " ".join(pair)
            overlaps.append((label, count))
            seen_tokens.update(pair)
    for token, count in last_single_counts.items():
        if count >= 2 and token not in seen_tokens:
            overlaps.append((token, count))
            seen_tokens.add(token)
    for token, count in penultimate_counts.items():
        if count >= 2 and token not in seen_tokens:
            overlaps.append((token, count))
            seen_tokens.add(token)
    return overlaps


def _has_question_form(heading: str) -> bool:
    text = str(heading or "").strip()
    if not text:
        return False
    # Kiwi 형태소 분석: 종결어미 EF 가 의문형 whitelist 에 속하거나 의문 부사+EC.
    # 실패 시 None 반환 → regex fallback.
    kiwi_verdict = korean_morph.is_question_form(text)
    if kiwi_verdict is True:
        return True
    if text.rstrip().endswith("?"):
        return True
    if _QUESTION_TAIL_RE.search(text):
        return True
    if any(hint in text for hint in _QUESTION_FORM_HINTS):
        return True
    return False


def _has_numeric_answer_marker(heading: str) -> bool:
    text = str(heading or "")
    if re.search(r"\d+\s?(?:대|가지|단계|축|원칙)", text):
        return True
    return False


def _body_first_sentence_tokens(body_first_sentence: str) -> set:
    cleaned = str(body_first_sentence or "").strip()
    if not cleaned:
        return set()
    tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", cleaned)
    return set(tokens)


def score_h2_aeo(
    heading: str,
    *,
    siblings: Optional[List[str]] = None,
    full_name: str = "",
    descriptor_pool: Optional[List[str]] = None,
    body_first_sentence: str = "",
    target_keyword_canonical: str = "",
    section_index: int = 0,
    section_count: int = 0,
    user_keywords: Optional[List[str]] = None,
) -> Dict[str, object]:
    """단일 H2 에 AEO 관점의 soft score + 어드바이저리 이슈를 반환한다.

    이 함수는 hard-fail 을 결정하지 않는다(`detect_emotion_appeal` 은 별도).
    호출자가 점수를 기존 `score_h2` 결과에 병합하고 어드바이저리 리스트를
    `h2Trace` 에 기록하면 된다.
    """
    text = str(heading or "").strip()
    issues: List[str] = []
    breakdown: Dict[str, float] = {}

    if not text:
        return {
            "score": 0.0,
            "issues": ["EMPTY_HEADING"],
            "breakdown": {},
        }

    length_chars = len(text)
    if length_chars < 20:
        length_score = 0.4
        issues.append("H2_SHORT_LENGTH")
    elif 20 <= length_chars <= 40:
        length_score = 1.0
    elif 41 <= length_chars <= 48:
        length_score = 0.7
    else:
        length_score = 0.3
        issues.append("H2_LONG_LENGTH")
    breakdown["length"] = length_score

    has_question = _has_question_form(text)
    has_numeric = _has_numeric_answer_marker(text)
    if has_question:
        answer_score = 1.0
    elif has_numeric:
        answer_score = 0.85
    else:
        answer_score = 0.3
        issues.append("H2_NO_QUESTION_FORM")
    breakdown["answer_form"] = answer_score

    pool = [str(item).strip() for item in (descriptor_pool or []) if str(item).strip()]
    name_clean = str(full_name or "").strip()
    contains_name = bool(name_clean and name_clean in text)
    contains_descriptor = any(descriptor in text for descriptor in pool)
    if contains_name or contains_descriptor:
        entity_score = 1.0
    else:
        entity_score = 0.2
        issues.append("H2_NO_SUBJECT_ENTITY")
    breakdown["entity"] = entity_score

    canonical = str(target_keyword_canonical or "").strip()
    if canonical and canonical not in text and name_clean and name_clean not in text:
        if not contains_descriptor:
            issues.append("H2_CANONICAL_FORM_MISMATCH")

    sibling_list = [str(item or "").strip() for item in (siblings or []) if str(item).strip()]
    overlaps = detect_sibling_suffix_overlap(sibling_list + [text])
    if len(overlaps) >= _SIBLING_SUFFIX_OVERLAP_THRESHOLD:
        issues.append("H2_SIBLING_SUFFIX_OVERLAP")
        uniqueness_score = 0.4
    elif overlaps:
        uniqueness_score = 0.7
    else:
        uniqueness_score = 1.0
    breakdown["uniqueness"] = uniqueness_score

    body_tokens = _body_first_sentence_tokens(body_first_sentence)
    h2_tokens = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", text))
    qa_score = 1.0
    if body_tokens and h2_tokens:
        overlap_ratio = len(h2_tokens & body_tokens) / max(len(h2_tokens), 1)
        if overlap_ratio >= 0.8:
            issues.append("H2_BODY_ECHO_FIRST_SENTENCE")
            qa_score = 0.4
        elif overlap_ratio == 0:
            issues.append("H2_QA_PAIRING_FAIL")
            qa_score = 0.3
    breakdown["qa_pairing"] = qa_score

    entity_distribution_score = 1.0
    if section_count and sibling_list is not None:
        all_headings = sibling_list + [text]
        if len(all_headings) == section_count:
            distribution = count_entity_distribution(
                all_headings, full_name=name_clean, descriptor_pool=pool
            )
            anchor_count = distribution["full_name"]
            anchor_cap = compute_anchor_cap(section_count)
            if anchor_count == 0 and name_clean:
                issues.append("H2_ENTITY_ANCHOR_MISSING")
                entity_distribution_score = 0.4
            elif anchor_count > anchor_cap:
                issues.append("H2_KEYWORD_STAMP_WARNING")
                entity_distribution_score = 0.4
            # user_keyword 반복 스탬핑 감지
            kw_cap = max(1, math.ceil(section_count * 0.5))
            for kw in (user_keywords or []):
                kw_clean = str(kw or "").strip()
                if not kw_clean:
                    continue
                kw_count = sum(1 for h in all_headings if kw_clean in h)
                if kw_count > kw_cap:
                    issues.append("H2_USER_KEYWORD_STAMP")
                    entity_distribution_score = min(entity_distribution_score, 0.4)
                    break
    breakdown["entity_distribution"] = entity_distribution_score

    weights = {
        "length": 0.15,
        "answer_form": 0.25,
        "entity": 0.20,
        "uniqueness": 0.15,
        "qa_pairing": 0.15,
        "entity_distribution": 0.10,
    }
    total = round(
        sum(breakdown[key] * weight for key, weight in weights.items()),
        4,
    )

    return {
        "score": total,
        "issues": issues,
        "breakdown": breakdown,
        "section_index": section_index,
    }
