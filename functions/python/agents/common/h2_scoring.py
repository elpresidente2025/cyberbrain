"""H2 소제목 점수화 — 플랜 기반 rubric 게이트.

SubheadingAgent의 Plan → Gen → Score → Repair 파이프라인에서 세 번째 단계.
생성된 헤딩이 rulebook 기준을 얼마나 충족하는지 가중 점수로 환산하고,
임계값(H2_MIN_PASSING_SCORE) 기준으로 통과/실패를 판정한다.

순수 함수만 — I/O 없음, LLM 호출 없음, 전역 상태 없음.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, TypedDict

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

_INTERNAL_PROMPT_LEAK_RE = re.compile(
    r"원문\s*(?:약속|대로|에서\s*약속|범위|기준|바탕으로\s*약속)"
    r"|검색어\s*(?:반영|삽입|횟수)"
    r"|생성\s*시간"
    r"|카테고리\s*:"
    r"|프롬프트|지시사항",
    re.IGNORECASE,
)

# forbidden_numeric_anchors 중 heading에 등장한 숫자 반환.
# lookbehind (?<![\d.]) : 56.8억 안의 8억 오탐 방지 (PR 2-A 연동).
def _forbidden_numeric_anchor_hits(heading_text: str, forbidden: Sequence[str]) -> List[str]:
    hits: List[str] = []
    for num in forbidden or ():
        n = str(num or "").strip()
        if not n:
            continue
        if re.search(rf"(?<![\d.]){re.escape(n)}(?![\d.A-Za-z])", heading_text):
            hits.append(n)
    return hits

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
    "detect_sibling_prefix_overlap",
    "detect_register_mismatch",
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
        # heading 이 6개 AEO 아키타입 (질문형/목표형/주장형/이유형/대조형/
        # 사례형) 중 어디에도 매치되지 않음 = 약속(promise) 이 아니라
        # 단순 토픽 설명에 그친 경우. 예: "정책 방향 제시", "지난 4년간 조성".
        # suggested_type 과 어긋나기(= TYPE_MISMATCH) 보다 한 단계 더 나쁜 상태.
        "ARCHETYPE_MISMATCH",
        # 세트 내 2개 이상의 H2 가 동일 첫 어절로 시작 — 복붙 느낌.
        # AEO advisory 에서 hard-fail 로 격상: repair 를 강제한다.
        "H2_SIBLING_PREFIX_OVERLAP",
        # 인물명·지역명을 제외하면 구체적 고유명사/숫자가 전무한 상투적 H2.
        "H2_GENERIC_CONTENT",
        # 같은 글 안에서 "제도 기반을 세우겠습니다" 류 저정보 템플릿이 반복됨.
        "H2_GENERIC_FAMILY_REPEAT",
        # "형 햇빛연금"처럼 앞 토큰이 잘린 소제목.
        "H2_TEXT_FRAGMENT",
        # "실행 계획을 세우겠습니다", "제도 기반을 세우겠습니다"처럼
        # 본문 고유 실행수단을 하나도 담지 않은 저정보 H2.
        "H2_LOW_INFORMATION_TEMPLATE",
        # "원문 약속대로", "검색어 반영 횟수" 등 시스템 내부어가 H2에 노출됨.
        "H2_INTERNAL_PROMPT_LEAK",
        # plan의 forbidden_numeric_anchors(삭감·폐지 맥락 숫자)가 H2에 등장.
        "H2_COUNTEREXAMPLE_NUMERIC_ANCHOR",
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
        "H2_QUESTION_ARCHETYPE_EXCESS",  # 세트 내 질문형 H2 초과
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

_LOW_INFORMATION_HEADING_PATTERNS: List[tuple[str, re.Pattern[str]]] = [
    ("execution_plan", re.compile(r"(?:실행\s*계획|실행\s*방안|추진\s*계획|계획을\s*세우)")),
    ("institutional_basis", re.compile(r"(?:제도\s*기반|제도적\s*기반|제도로\s*뒷받침|조례로\s*뒷받침|근거를\s*마련)")),
    ("financial_concern", re.compile(r"(?:재정\s*우려|예산\s*우려|재원\s*우려|어떻게\s*넘)")),
    ("generic_issue", re.compile(r"(?:핵심\s*쟁점|필요한\s*이유|기존\s*정책과\s*차이|회복의\s*출발점)")),
]


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


def _low_information_heading_family(heading: str) -> str:
    text = re.sub(r"\s+", " ", str(heading or "")).strip()
    if not text:
        return ""
    for family, pattern in _LOW_INFORMATION_HEADING_PATTERNS:
        if pattern.search(text):
            return family
    return ""


def _matches_specific_anchor(heading: str, plan: SectionPlan) -> bool:
    text = str(heading or "")
    if not text:
        return False
    anchors = [
        str(anchor or "").strip()
        for anchor in (plan.get("specific_anchors") or [])
        if str(anchor or "").strip()
    ]
    for anchor in anchors:
        if anchor and anchor in text:
            return True
    return False


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
    if 15 <= length <= 28:
        return 1.0
    if 12 <= length <= 14 or 29 <= length <= H2_MAX_LENGTH:
        return 0.7
    if 10 <= length <= 11:
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

    if _INTERNAL_PROMPT_LEAK_RE.search(heading_text):
        issues.append("H2_INTERNAL_PROMPT_LEAK")

    forbidden_nums = list(plan.get("forbidden_numeric_anchors") or [])
    if forbidden_nums and _forbidden_numeric_anchor_hits(heading_text, forbidden_nums):
        issues.append("H2_COUNTEREXAMPLE_NUMERIC_ANCHOR")

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

    # AEO 아키타입 미매치 — TYPE_MISMATCH 보다 한 단계 강한 게이트.
    # Why: "정책 방향 제시", "~ 조성" 같이 어떤 약속 성격(질문/주장/목표/
    # 이유/대조/사례) 도 갖지 못한 heading 은 본문 미리보기/제목 뒤풀이일 뿐
    # H2 로서의 promise 기능이 없다. hard-fail 로 격상해 repair 를 강제한다.
    detected_archetype = detect_h2_archetype(heading_text)
    if not detected_archetype:
        issues.append("ARCHETYPE_MISMATCH")
    breakdown["archetype"] = {"detected": detected_archetype or ""}

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

    low_info_family = _low_information_heading_family(heading_text)
    if low_info_family:
        anchor_matched = _matches_specific_anchor(heading_text, plan)
        breakdown["specific_anchor"] = {
            "matched": 1.0 if anchor_matched else 0.0,
            "family": low_info_family,
        }
        if not anchor_matched:
            issues.append(f"H2_LOW_INFORMATION_TEMPLATE:{low_info_family}")

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


_COMMA_SPLIT_RE = re.compile(r"[가-힣]+\s*,\s*[가-힣]")


def _is_comma_split_form(heading: str) -> bool:
    """쉼표로 두 구를 끊어 잇는 H2 형태인지 ("X, Y인가요" 등)."""
    return bool(_COMMA_SPLIT_RE.search(str(heading or "")))


def detect_sibling_prefix_overlap(headings: List[str]) -> List[tuple]:
    """인접 H2 간 첫 어절 중복을 탐지한다.

    "인천, …" 이 연속 2개 이상이면 독자에게 복붙 느낌을 준다.
    """
    cleaned = [str(h or "").strip() for h in headings or []]
    cleaned = [h for h in cleaned if h]
    if len(cleaned) < 2:
        return []

    first_counts: Dict[str, int] = {}
    for heading in cleaned:
        tokens = re.findall(r"[가-힣A-Za-z0-9]+", heading)
        if tokens:
            first_counts[tokens[0]] = first_counts.get(tokens[0], 0) + 1

    return [(tok, cnt) for tok, cnt in first_counts.items() if cnt >= 2]


_POLITE_TAIL_RE = re.compile(
    r"(인가요|일까요|할까요|는가요|나요|인지요|ㄹ까요|인가요)\s*\??$"
)
_PLAIN_TAIL_RE = re.compile(
    r"(인가|일까|할까|는가|되나|하나|을까|ㄹ까)\s*\??$"
)


def _detect_h2_register(heading: str) -> str:
    """H2 종결어미의 register 를 판정: 'polite', 'plain', '' (판정불가)."""
    text = str(heading or "").strip().rstrip("?")
    if not text:
        return ""
    if _POLITE_TAIL_RE.search(text + "?"):
        return "polite"
    if _PLAIN_TAIL_RE.search(text + "?"):
        return "plain"
    return ""


def detect_register_mismatch(headings: List[str]) -> bool:
    """H2 세트 내 경어체/평서체 혼재 여부를 반환한다."""
    registers = set()
    for h in headings or []:
        r = _detect_h2_register(h)
        if r:
            registers.add(r)
    return len(registers) >= 2


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


# 상투어 사전 — NNG 밀도 체크에 사용. 개별 단어 존재로 감점하지 않고
# NNG 중 상투어 비율(밀도)이 높을 때만 H2_GENERIC_CONTENT 를 발화한다.
_H2_CLICHE_NNG = frozenset({
    # 관찰된 H2에서 추출
    "미래", "혁신", "포용", "도약", "비전", "헌신", "거점",
    "발전", "성공", "활성화", "연결", "시대", "길",
    # patina ko-content (과도한 중요성 / 과제와 전망)
    "전환점", "이정표", "지평", "패러다임", "토대", "전망", "과제",
    # patina ko-language (AI 특유 어휘)
    "촉진", "극대화", "도모",
    # patina ko-filler (막연한 긍정)
    "여정",
})


def _has_concrete_content(heading: str, full_name: str, full_region: str) -> bool:
    """H2에 인물명·지역명을 제외한 구체적 토큰(고유명사·숫자)이 있는지 판정.

    kiwi 사용 가능 시 NNP/SN 태그 기반, 불가 시 regex fallback.
    상투어 밀도 체크: NNG 중 상투어 비율이 높고 구체 토큰이 부족하면 실패.
    """
    text = str(heading or "").strip()
    if not text:
        return False

    # full_name, full_region에서 제외할 토큰 수집
    exclude = set()
    for src in (full_name, full_region):
        for tok in re.findall(r"[가-힣A-Za-z0-9]{2,}", str(src or "")):
            exclude.add(tok)

    kiwi = korean_morph.get_kiwi()
    if kiwi is not None:
        tokens = kiwi.tokenize(text)
        concrete = [
            t for t in tokens
            if t.tag in ("NNP", "SN", "NR") and t.form not in exclude
        ]
        if len(concrete) == 0:
            return False

        # 상투어 밀도 체크: NNG 중 상투어 비율이 60% 이상이고
        # 구체 토큰이 1개 이하이면 실패
        nng_tokens = [t for t in tokens if t.tag == "NNG" and t.form not in exclude]
        if nng_tokens:
            cliche_count = sum(1 for t in nng_tokens if t.form in _H2_CLICHE_NNG)
            density = cliche_count / len(nng_tokens)
            if density >= 0.6 and len(concrete) <= 1:
                return False

        return True

    # regex fallback: 숫자 존재 여부로 간이 판정
    digits = re.findall(r"\d+", text)
    if digits:
        return True
    # 한글 토큰에서 name/region 제외 후 2음절 이상 고유명사 추정 불가 → False
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
    article_title: str = "",
    full_region: str = "",
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
    all_headings_for_overlap = sibling_list + [text]
    overlaps = detect_sibling_suffix_overlap(all_headings_for_overlap)
    if len(overlaps) >= _SIBLING_SUFFIX_OVERLAP_THRESHOLD:
        issues.append("H2_SIBLING_SUFFIX_OVERLAP")
        uniqueness_score = 0.4
    elif overlaps:
        uniqueness_score = 0.7
    else:
        uniqueness_score = 1.0

    prefix_overlaps = detect_sibling_prefix_overlap(all_headings_for_overlap)
    if prefix_overlaps:
        issues.append("H2_SIBLING_PREFIX_OVERLAP")
        uniqueness_score = min(uniqueness_score, 0.5)

    if detect_register_mismatch(all_headings_for_overlap):
        issues.append("H2_REGISTER_MISMATCH")
        uniqueness_score = min(uniqueness_score, 0.5)

    # 서술형(사전형 종결) 빈도 제한: 글당 최대 1회
    if detect_h2_archetype(text) == "서술형":
        narrative_count = sum(
            1 for h in all_headings_for_overlap
            if detect_h2_archetype(h) == "서술형"
        )
        if narrative_count > 1:
            issues.append("H2_NARRATIVE_OVERUSE")
            uniqueness_score = min(uniqueness_score, 0.5)

    # 쉼표 분리형 빈도 제한: 세트 내 최대 2개
    if _is_comma_split_form(text):
        comma_count = sum(
            1 for h in all_headings_for_overlap
            if _is_comma_split_form(h)
        )
        if comma_count > 2:
            issues.append("H2_COMMA_FORM_EXCESS")
            uniqueness_score = min(uniqueness_score, 0.5)

    # 질문형 빈도 제한: 세트 내 최대 N개 (서술형·쉼표형 cap과 동일 패턴)
    if detect_h2_archetype(text) == "질문형":
        # siblings에 현재 heading이 포함된 경우 중복 계산 방지 — dedupe 후 count
        _seen: set = set()
        _deduped: List[str] = []
        for _h in all_headings_for_overlap:
            if _h not in _seen:
                _seen.add(_h)
                _deduped.append(_h)
        question_count = sum(
            1 for h in _deduped
            if detect_h2_archetype(h) == "질문형"
        )
        question_cap = 1 if section_count <= 3 else 2
        if question_count > question_cap:
            issues.append("H2_QUESTION_ARCHETYPE_EXCESS")
            uniqueness_score = min(uniqueness_score, 0.6)

    # H2-title 유사도 체크: 제목 복사 H2 차단
    title_clean = str(article_title or "").strip()
    if title_clean:
        h_toks = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", text))
        t_toks = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", title_clean))
        if h_toks and t_toks:
            jaccard = len(h_toks & t_toks) / len(h_toks | t_toks)
            if jaccard >= 0.7:
                issues.append("H2_TITLE_ECHO")
                uniqueness_score = min(uniqueness_score, 0.3)

    keyword_surfaces = [
        str(item or "").strip()
        for item in ([target_keyword_canonical] + list(user_keywords or []))
        if str(item or "").strip()
    ]
    keyword_concrete = any(
        keyword
        and keyword != name_clean
        and len(keyword) >= 2
        and keyword in text
        for keyword in keyword_surfaces
    )

    # 구체성 체크: 인물명·지역명·사용자 정책 키워드를 제외하고 구체 토큰이 전무하면 상투적 H2.
    # 사용자 지정 정책명은 NNP/SN이 아니어도 해당 글의 구체 주제이므로 구체성 신호로 인정한다.
    if not keyword_concrete and not _has_concrete_content(text, name_clean, str(full_region or "")):
        issues.append("H2_GENERIC_CONTENT")
        uniqueness_score = min(uniqueness_score, 0.3)

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
