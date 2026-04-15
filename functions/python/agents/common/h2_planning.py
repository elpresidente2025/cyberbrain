"""H2 소제목 계획 단계 (결정론적, 비-LLM).

SubheadingAgent의 Plan → Gen → Score → Repair 파이프라인에서 첫 단계.
각 섹션 본문에서 suggested_type / must_include_keyword / numerics / key_claim 등
결정론적으로 추출 가능한 정보를 뽑아 SectionPlan으로 제공한다.

재사용:
- `title_common.extract_numbers_from_content` — 숫자/단위 추출
- `h2_guide` 상수 — 길이 밴드
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional, Sequence, TypedDict

from .title_common import extract_numbers_from_content

__all__ = [
    "SectionPlan",
    "StanceBrief",
    "extract_section_plan",
    "extract_stance_claims",
    "pick_suggested_type",
    "pick_must_include_keyword",
    "extract_key_claim",
    "strip_html",
    "classify_section_intent",
    "detect_answer_type",
    "build_target_keyword_canonical",
    "build_descriptor_pool",
    "assign_h2_entity_slots",
    "AEO_INTENT_KINDS",
    "AEO_ANSWER_TYPES",
]


# ---------------------------------------------------------------------------
# 상수 / 정규식
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.!?。])\s+|(?<=다)\s+(?=[가-힣A-Z])")
# TUNABLE: 신규 의존성 없이 경량 토크나이저 — 2글자 이상 한글/영문/숫자 토큰
_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_PROPER_NOUN_RE = re.compile(r"[가-힣]{2,4}(?:시|구|군|동|읍|면|도|광역시|특별시)")
_NUMERIC_LEAD_RE = re.compile(r"\d")

_PROCEDURAL_MARKERS = ("단계", "절차", "방법", "순서", "신청", "접수", "가이드")
_COMPARATIVE_MARKERS = ("vs", "대비", "비교", "차이", "기존 ")
_DECLARATIVE_TAIL_RE = re.compile(r"(?:이다|아니다|한다|해야|없다|있다|된다|이다\.|다\.)$")
_CRITICAL_MARKERS = ("거부", "회피", "남용", "파괴", "왜곡", "무너", "실패")

_KEY_CLAIM_MIN_LEN = 15
_KEY_CLAIM_MAX_LEN = 80
_SECTION_TEXT_MAX_LEN = 400

_STOPWORDS = frozenset(
    {
        "그리고",
        "그러나",
        "하지만",
        "또한",
        "이것",
        "그것",
        "저것",
        "위해",
        "통해",
        "대한",
        "관련",
        "있는",
        "없는",
        "하는",
        "됩니다",
        "합니다",
    }
)


# ---------------------------------------------------------------------------
# TypedDict
# ---------------------------------------------------------------------------


class SectionPlan(TypedDict, total=False):
    index: int
    section_text: str
    suggested_type: str
    must_include_keyword: str
    candidate_keywords: List[str]
    numerics: List[str]
    entity_hints: List[str]
    key_claim: str
    # AEO 확장 필드
    query_intent: str
    answer_type: str
    target_keyword_canonical: str
    assigned_entity_surface: str


class StanceBrief(TypedDict, total=False):
    top_claims: List[str]
    key_entities: List[str]
    dominant_type: str


# ---------------------------------------------------------------------------
# 보조 함수
# ---------------------------------------------------------------------------


def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", _HTML_TAG_RE.sub(" ", str(text or ""))).strip()


_TRAILING_PUNCT_RE = re.compile(r"[\.!?。\s]+$")


def _trim_punct(text: str) -> str:
    return _TRAILING_PUNCT_RE.sub("", str(text or "")).strip()


def _split_sentences(text: str) -> List[str]:
    raw = _SENTENCE_SPLIT_RE.split(str(text or ""))
    return [_trim_punct(segment) for segment in raw if segment and segment.strip()]


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(str(text or ""))


def _dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    seen: set = set()
    result: List[str] = []
    for item in items:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


# ---------------------------------------------------------------------------
# Key claim / keyword / type 추출
# ---------------------------------------------------------------------------


def extract_key_claim(section_text: str, *, style: str = "aeo") -> str:
    """섹션 본문의 첫 유의미 문장을 키 클레임으로 선택한다.

    길이 밴드(15~80자)를 만족하는 첫 문장 → 만족하는 문장이 없으면 가장 긴
    문장을 80자로 절단.
    """
    text = strip_html(section_text)
    if not text:
        return ""

    candidates = _split_sentences(text)
    for sentence in candidates:
        length = len(sentence)
        if _KEY_CLAIM_MIN_LEN <= length <= _KEY_CLAIM_MAX_LEN:
            return sentence

    if candidates:
        longest = max(candidates, key=len)
        return longest[:_KEY_CLAIM_MAX_LEN].rstrip()

    return text[:_KEY_CLAIM_MAX_LEN].rstrip()


def pick_must_include_keyword(
    section_text: str,
    *,
    user_keywords: Sequence[str],
    entity_hints: Sequence[str],
) -> str:
    """섹션에 강제로 포함해야 할 핵심 키워드를 결정론적으로 고른다.

    우선순위:
    1. 섹션 본문에 실제로 등장하는 user_keywords 중 첫 항목
    2. 섹션에 등장하는 entity_hints 중 첫 항목
    3. 본문의 가장 빈번한 2글자 이상 토큰(스톱워드 제외)
    """
    haystack = strip_html(section_text)
    if not haystack:
        if user_keywords:
            return str(user_keywords[0]).strip()
        if entity_hints:
            return str(entity_hints[0]).strip()
        return ""

    for kw in user_keywords or ():
        candidate = str(kw or "").strip()
        if candidate and candidate in haystack:
            return candidate

    for hint in entity_hints or ():
        candidate = str(hint or "").strip()
        if candidate and candidate in haystack:
            return candidate

    tokens = [tok for tok in _tokenize(haystack) if tok not in _STOPWORDS]
    if not tokens:
        if user_keywords:
            return str(user_keywords[0]).strip()
        if entity_hints:
            return str(entity_hints[0]).strip()
        return ""

    counts: dict = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1
    # 빈도 동률 시 먼저 등장한 토큰 우선
    ordered = sorted(counts.items(), key=lambda item: (-item[1], tokens.index(item[0])))
    return ordered[0][0]


def pick_suggested_type(
    section_text: str,
    *,
    preferred_types: Sequence[str],
    style: str = "aeo",
) -> str:
    """섹션 본문 특징으로 type을 추정한다. preferred_types 내에서만 선택."""
    text = strip_html(section_text)
    preferred = [str(t).strip() for t in (preferred_types or ()) if str(t).strip()]

    def pick(*candidates: str) -> Optional[str]:
        for candidate in candidates:
            if candidate in preferred:
                return candidate
        return None

    if style == "assertive":
        if any(marker in text for marker in _CRITICAL_MARKERS):
            chosen = pick("비판형", "단정형", "명사형", "주장형")
            if chosen:
                return chosen
        if _DECLARATIVE_TAIL_RE.search(text[-40:]):
            chosen = pick("단정형", "주장형", "명사형")
            if chosen:
                return chosen
        return pick("단정형", "주장형", "명사형") or (preferred[0] if preferred else "단정형")

    # AEO 스타일
    if _NUMERIC_LEAD_RE.search(text):
        chosen = pick("데이터형", "명사형", "절차형")
        if chosen:
            return chosen
    if any(marker in text for marker in _PROCEDURAL_MARKERS):
        chosen = pick("절차형", "명사형", "데이터형")
        if chosen:
            return chosen
    if any(marker in text for marker in _COMPARATIVE_MARKERS):
        chosen = pick("비교형", "명사형")
        if chosen:
            return chosen
    if text.rstrip().endswith("?") or "어떻게" in text or "무엇" in text:
        chosen = pick("질문형", "명사형")
        if chosen:
            return chosen

    return preferred[0] if preferred else "명사형"


# ---------------------------------------------------------------------------
# Section plan / stance brief
# ---------------------------------------------------------------------------


def extract_section_plan(
    section_text: str,
    *,
    index: int,
    category: str,
    style_config: dict,
    user_keywords: Sequence[str],
    full_name: str = "",
    full_region: str = "",
    extra_entities: Optional[Sequence[str]] = None,
) -> SectionPlan:
    """섹션 한 개에 대한 SectionPlan 을 생성한다."""
    raw_slice = str(section_text or "")[:_SECTION_TEXT_MAX_LEN]
    cleaned = strip_html(raw_slice)

    entity_hints = _dedupe_preserve_order(
        list(extra_entities or ()) + [full_name, full_region]
    )
    proper_nouns = _PROPER_NOUN_RE.findall(cleaned)
    entity_hints = _dedupe_preserve_order(entity_hints + proper_nouns)

    numerics_bundle = extract_numbers_from_content(cleaned) or {}
    numerics = list(numerics_bundle.get("numbers") or [])

    preferred_types = list(style_config.get("preferred_types") or style_config.get("preferredTypes") or [])
    style = str(style_config.get("style") or "aeo").strip().lower() or "aeo"

    suggested_type = pick_suggested_type(
        cleaned, preferred_types=preferred_types, style=style
    )

    candidate_keywords = _dedupe_preserve_order(
        list(user_keywords or ())
        + [hint for hint in entity_hints if hint]
        + [tok for tok in _tokenize(cleaned) if tok not in _STOPWORDS]
    )[:10]

    must_include = pick_must_include_keyword(
        cleaned,
        user_keywords=user_keywords or (),
        entity_hints=entity_hints,
    )
    if not must_include and candidate_keywords:
        must_include = candidate_keywords[0]

    key_claim = extract_key_claim(cleaned, style=style)

    return SectionPlan(
        index=int(index),
        section_text=cleaned,
        suggested_type=suggested_type,
        must_include_keyword=must_include,
        candidate_keywords=candidate_keywords,
        numerics=numerics,
        entity_hints=entity_hints,
        key_claim=key_claim,
    )


def extract_stance_claims(stance_text: str) -> StanceBrief:
    """입장문에서 상위 주장 문장과 주요 엔티티를 추출한다.

    기사 단위로 1회만 호출 — 섹션마다 재호출하지 않는다.
    """
    text = strip_html(stance_text)
    if not text:
        return StanceBrief(top_claims=[], key_entities=[], dominant_type="")

    sentences = _split_sentences(text)
    meaningful = [
        s for s in sentences if _KEY_CLAIM_MIN_LEN <= len(s) <= _KEY_CLAIM_MAX_LEN
    ]
    if not meaningful and sentences:
        meaningful = [s[:_KEY_CLAIM_MAX_LEN].rstrip() for s in sentences[:3]]

    top_claims = _dedupe_preserve_order(meaningful)[:3]

    entities = _dedupe_preserve_order(_PROPER_NOUN_RE.findall(text))[:8]

    dominant_type = ""
    joined = " ".join(top_claims)
    if any(marker in joined for marker in _CRITICAL_MARKERS):
        dominant_type = "비판형"
    elif _DECLARATIVE_TAIL_RE.search(joined):
        dominant_type = "단정형"

    return StanceBrief(
        top_claims=top_claims,
        key_entities=entities,
        dominant_type=dominant_type,
    )


# ---------------------------------------------------------------------------
# AEO 확장: intent 분류 · answer type · descriptor pool · 엔티티 슬롯 배정
# ---------------------------------------------------------------------------

AEO_INTENT_KINDS = ("info", "nav", "cmp", "tx")
AEO_ANSWER_TYPES = ("question-form", "declarative-fact", "declarative-list")

_INTENT_CMP_MARKERS = (
    "vs",
    "대비",
    "차이",
    "비교",
    "대결",
    "양자",
    "가상대결",
    "맞대결",
    "쟁점",
)
_INTENT_CMP_NUMERIC_RE = re.compile(r"\d{1,3}(?:\.\d)?\s?%[^a-zA-Z0-9%]{0,8}\d{1,3}(?:\.\d)?\s?%")
_INTENT_TX_MARKERS = (
    "신청",
    "접수",
    "절차",
    "단계",
    "방법",
    "가이드",
    "지원금",
    "신청서",
    "자격",
    "심사",
)
_INTENT_NAV_MARKERS = (
    "이력",
    "출마",
    "프로필",
    "소개",
    "약력",
    "성과",
    "공약",
    "활동",
    "경력",
)

_ANSWER_LIST_MARKERS = (
    "첫째",
    "둘째",
    "셋째",
    "넷째",
    "다섯째",
    "하나,",
    "둘,",
    "셋,",
)
_ANSWER_LIST_NUMERIC_RE = re.compile(r"(?:^|[^\d])(?:[1-9]|1[0-9])[\)\.]\s")
_ANSWER_LIST_COUNT_RE = re.compile(r"(?:3|4|5|6|7|8|9|10)\s?(?:대|가지|단계|축|원칙|영역)")
_ANSWER_FACT_TAIL_RE = re.compile(r"(?:입니다|이다|합니다|한다|됩니다|된다|했습니다|했다)\s*[\.]")


def classify_section_intent(section_text: str) -> str:
    """섹션 본문의 패턴으로 query intent 를 결정론 분류한다.

    반환값: "cmp" | "tx" | "nav" | "info" — 매칭 실패 시 "info" 기본값.
    """
    text = strip_html(section_text)
    if not text:
        return "info"

    if _INTENT_CMP_NUMERIC_RE.search(text):
        return "cmp"
    if any(marker in text for marker in _INTENT_CMP_MARKERS):
        return "cmp"
    if any(marker in text for marker in _INTENT_TX_MARKERS):
        return "tx"
    if any(marker in text for marker in _INTENT_NAV_MARKERS):
        return "nav"
    return "info"


def detect_answer_type(section_text: str) -> str:
    """섹션 본문이 지향하는 답변 형태를 분류한다.

    반환값: "declarative-list" | "declarative-fact" | "question-form"
    - 리스트/열거 패턴이면 list
    - 단정형 문장 비율이 높으면 fact
    - 그 외(기본) question-form — LLM 에 질문형 H2 를 요구
    """
    text = strip_html(section_text)
    if not text:
        return "question-form"

    if any(marker in text for marker in _ANSWER_LIST_MARKERS):
        return "declarative-list"
    if _ANSWER_LIST_NUMERIC_RE.search(text) or _ANSWER_LIST_COUNT_RE.search(text):
        return "declarative-list"

    sentences = _split_sentences(text)
    if len(sentences) >= 3:
        fact_hits = sum(
            1 for sentence in sentences if _ANSWER_FACT_TAIL_RE.search(sentence + ".")
        )
        if fact_hits / len(sentences) >= 0.7:
            return "declarative-fact"

    return "question-form"


def build_target_keyword_canonical(
    *,
    preferred_keyword: str = "",
    full_name: str = "",
    user_keywords: Optional[Sequence[str]] = None,
) -> str:
    """전역 타깃 canonical 키워드를 결정한다 (H2 세트 전체가 공유)."""
    candidates = [
        str(preferred_keyword or "").strip(),
        str(full_name or "").strip(),
    ]
    for kw in user_keywords or ():
        candidates.append(str(kw or "").strip())
    for candidate in candidates:
        if candidate:
            return candidate
    return ""


def _split_role_label_tokens(value: Any) -> List[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    parts = [
        token.strip()
        for token in re.split(r"[·•,/]+", raw)
        if token and token.strip()
    ]
    return parts or [raw]


def build_descriptor_pool(
    *,
    full_name: str = "",
    full_region: str = "",
    role_facts: Optional[Any] = None,
    profile: Optional[Any] = None,
    max_items: int = 6,
) -> List[str]:
    """H2 엔티티 슬롯 배정에 사용할 descriptor 후보 리스트를 생성한다.

    우선순위:
    1. profile.currentRole / profile.identity / profile.tagline
    2. role_facts 내 본인(full_name) 에 매핑된 역할 라벨
    3. full_region 기반 "지역 + 청년 정치인" 류 positioning
    4. role_facts 값 중 일반 정치 role 키워드

    descriptor 는 본문에서 이미 선언된 것만 사용하는 것이 이상적이지만,
    이 함수는 후보 풀 생성만 담당. 최종 검증은 h2_scoring 에서 수행.
    """
    pool: List[str] = []
    name_clean = str(full_name or "").strip()
    region_clean = str(full_region or "").strip()

    if isinstance(profile, dict):
        for key in ("currentRole", "current_role", "identity", "tagline", "publicRole"):
            value = profile.get(key)
            pool.extend(_split_role_label_tokens(value))

    if isinstance(role_facts, dict) and name_clean:
        own_role = role_facts.get(name_clean)
        pool.extend(_split_role_label_tokens(own_role))

    if region_clean:
        short_region = region_clean.split()[-1] if region_clean else ""
        if short_region:
            pool.append(f"{short_region} 청년 정치인")
            pool.append(f"{short_region} 정책 실무자")

    # Why: role_facts 는 소스 텍스트에서 추출된 다인물 역할 맵이다.
    #      본인 역할은 위에서 이미 추가했으므로, 여기서 values() 전체를 다시
    #      순회하면 타인의 역할(예: "국회의원", "위원장")이 본인 descriptor
    #      pool 에 섞여 들어가 H2 에 엉뚱한 직책이 스탬핑된다. 본인 외 역할은
    #      descriptor 로 절대 쓰지 않는다.

    cleaned: List[str] = []
    seen: set = set()
    for item in pool:
        key = str(item or "").strip()
        if not key or key == name_clean or key in seen:
            continue
        if len(key) < 2 or len(key) > 20:
            continue
        seen.add(key)
        cleaned.append(key)
        if len(cleaned) >= max_items:
            break
    return cleaned


def assign_h2_entity_slots(
    section_count: int,
    *,
    full_name: str,
    descriptor_pool: Sequence[str],
    anchor_max_ratio: float = 0.5,
) -> List[str]:
    """H2 섹션별로 노출할 엔티티 surface 를 미리 배정한다.

    정책:
    - 1번째 섹션은 앵커(full_name) 고정 — 글 시작부에 본명 1회 확보
    - 2번째 이후는 descriptor_pool 을 순환 배정
    - N≥5 인 경우에만 중반에 second anchor 1회 허용 (anchor_max_ratio 한도 내)
    - descriptor_pool 이 비면 나머지 슬롯은 full_name 로 fallback (경고 대상)
    """
    count = max(int(section_count or 0), 0)
    if count == 0:
        return []
    name_clean = str(full_name or "").strip()
    pool = [str(item).strip() for item in (descriptor_pool or ()) if str(item).strip()]

    if not name_clean:
        if not pool:
            return [""] * count
        return [pool[idx % len(pool)] for idx in range(count)]

    anchor_cap = max(1, int(count * anchor_max_ratio))
    result: List[str] = [""] * count

    result[0] = name_clean
    used_anchors = 1

    descriptor_cursor = 0
    for idx in range(1, count):
        if pool:
            result[idx] = pool[descriptor_cursor % len(pool)]
            descriptor_cursor += 1
        else:
            result[idx] = name_clean
            used_anchors += 1

    if used_anchors < anchor_cap and count >= 5 and pool:
        mid_idx = count // 2
        if result[mid_idx] != name_clean:
            result[mid_idx] = name_clean
            used_anchors += 1

    return result
