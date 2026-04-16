"""H2 소제목 계획 단계 (결정론적, 비-LLM).

SubheadingAgent의 Plan → Gen → Score → Repair 파이프라인에서 첫 단계.
각 섹션 본문에서 suggested_type / must_include_keyword / numerics / key_claim 등
결정론적으로 추출 가능한 정보를 뽑아 SectionPlan으로 제공한다.

재사용:
- `title_common.extract_numbers_from_content` — 숫자/단위 추출
- `h2_guide` 상수 — 길이 밴드
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterable, List, Optional, Sequence, TypedDict

from . import korean_morph
from .h2_guide import resolve_category_archetypes
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
    "extract_user_role",
    "localize_user_role",
    "distribute_keyword_assignments",
    "canonicalize_entity_surface",
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

# 행정 단위 접미사 (변이형 canonical stem 추출용).
# 길이 긴 접미사를 먼저 시도하도록 alternation 순서 유지.
_ENTITY_SUFFIX_RE = re.compile(
    r"(?:광역시|특별자치시|특별시|특별자치도|자치시|자치도|시|구|군|동|읍|면|도)$"
)

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
    # user 가 명시한 키워드. deterministic fallback 템플릿의 키워드 안전 검사에서 allowlist 로 사용.
    user_keywords: List[str]
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


# kiwi 형태소 분석 기반 명사 추출 헬퍼.
# _PROPER_NOUN_RE (묵은 정규식) 가 "약화시키는"→"약화시", "외에도"→"외에도" 같은
# 동사·조사 조각을 고유명사로 오인하는 문제를 해결하기 위해 kiwi 태그를 1차로 사용.
# kiwi 초기화 실패 시(Windows 한글 username 등) 호출부가 regex fallback 을 사용.
_KOREAN_MORPH_NOUN_TAGS = frozenset({"NNG", "NNP", "NNB"})

# 기존 _PROPER_NOUN_RE 경로로만 잡힐 때 오매칭되기 쉬운 stem 접두 목록.
# stem + (시/도/군/동/...) 형태의 false-positive 제거용.
_PROPER_NOUN_STOPSTEMS = frozenset(
    {
        "외에", "위에", "아래", "뒤에", "앞에", "이에", "그에",
        "하기", "되기", "이기", "보기", "가기", "오기", "있기", "없기",
        "받기", "쓰기", "듣기", "말기", "끝나",
        "약화", "강화", "활성", "변화", "발생", "증가", "감소",
        "성장", "악화", "완화",
    }
)


def _kiwi_extract_nouns(text: str) -> Optional[List[str]]:
    """NNG/NNP/NNB 태그 토큰의 form 을 순서대로 반환. Kiwi 불가 시 None."""
    tokens = korean_morph.tokenize(text)
    if tokens is None:
        return None
    return [
        tok.form
        for tok in tokens
        if tok.tag in _KOREAN_MORPH_NOUN_TAGS and len(tok.form) >= 2
    ]


def _kiwi_extract_proper_nouns(text: str) -> Optional[List[str]]:
    """NNP(고유명사) 태그만 반환. Kiwi 불가 시 None."""
    tokens = korean_morph.tokenize(text)
    if tokens is None:
        return None
    return [
        tok.form
        for tok in tokens
        if tok.tag == "NNP" and len(tok.form) >= 2
    ]


def _filter_regex_proper_nouns(matches: Iterable[str]) -> List[str]:
    """regex fallback 에서 stem 이 stop-list 에 걸리는 false-positive 제거."""
    out: List[str] = []
    for raw in matches or ():
        m = str(raw or "").strip()
        if len(m) < 2:
            continue
        # 접미사 한 글자를 떼어낸 stem 부분 검사
        stem = m[:-1]
        if stem in _PROPER_NOUN_STOPSTEMS:
            continue
        out.append(m)
    return out


def _extract_proper_nouns(text: str) -> List[str]:
    """kiwi 우선 → 실패 시 regex + stopstem 필터 fallback."""
    kiwi_result = _kiwi_extract_proper_nouns(text)
    if kiwi_result is not None:
        return kiwi_result
    return _filter_regex_proper_nouns(_PROPER_NOUN_RE.findall(str(text or "")))


def _extract_noun_candidates(text: str) -> List[str]:
    """kiwi 우선으로 본문 명사 후보를 뽑는다. 실패 시 기존 _tokenize 경로로 우회.

    candidate_keywords 풀을 깨끗한 명사만으로 채우기 위한 함수. 조사/동사 활용형
    같은 조각이 섞이지 않도록 kiwi 의 NNG/NNP/NNB 태그만 통과시킨다.
    """
    kiwi_result = _kiwi_extract_nouns(text)
    if kiwi_result is not None:
        return kiwi_result
    return [tok for tok in _tokenize(str(text or "")) if tok not in _STOPWORDS]


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


def _filter_by_body_presence(tokens: Iterable[str], body: str) -> List[str]:
    """body 에 실제 등장하는 토큰만 유지. 빈 문자열/None 은 제외.

    Why: H2 는 자기 밑에 딸린 본문을 "정답" 으로 간주한 질문·주장이어야 한다.
         body 에 없는 토큰이 candidate_keywords 풀로 흘러들어가면
         `distribute_keyword_assignments` 가 초과분 plan 을 "본문에 없는 대안"
         으로 재배치하고, LLM 프롬프트에 노출돼 섹션 본문과 동떨어진 H2 를
         유도한다.
    How to apply: user_keywords, entity_hints 를 candidate_keywords 풀에 넣기
         전에 이 필터를 통과시킨다. body 에서 직접 뽑은 noun candidates 는
         이미 body 소속이므로 재필터 불필요.
    """
    haystack = str(body or "")
    if not haystack:
        return []
    out: List[str] = []
    for tok in tokens or ():
        text = str(tok or "").strip()
        if not text:
            continue
        if text in haystack:
            out.append(text)
    return out


# ---------------------------------------------------------------------------
# Key claim / keyword / type 추출
# ---------------------------------------------------------------------------


_KEY_CLAIM_DECLARATIVE_TAIL_RE = re.compile(
    r"(?:이다|한다|된다|있다|없다|해야\s*한다|해야\s*합니다|"
    r"있습니다|없습니다|됩니다|합니다|입니다|"
    r"하겠습니다|했습니다|것입니다|것이다|ㄹ\s*것입니다)"
    r"\s*[.\"”’']*$"
)

_KEY_CLAIM_CLAIM_KEYWORDS: tuple = (
    "주장", "강조", "약속", "다짐", "제안", "추진", "관철", "실천",
    "기여", "확보", "개선", "촉진", "강화", "개편", "개혁", "지원",
    "감면", "확대", "통과", "발의", "대응", "해결", "마련", "구축",
    "도입", "완수", "실현", "집중", "전념", "앞장", "책임", "헌신",
)

_KEY_CLAIM_GREETING_MARKERS: tuple = (
    "존경하는", "사랑하는", "당원 여러분", "시민 여러분",
    "동지 여러분", "주민 여러분", "안녕하", "반갑", "인사드립",
)

_KEY_CLAIM_SELF_INTRO_RE = re.compile(
    r"(?:저는|저희는|제가)\s*[^.!?]{0,30}?"
    r"(?:입니다|출신입니다|소속입니다|의원입니다|시장입니다|후보입니다|"
    r"대표입니다|의원이며|의원으로서|시장으로서|후보로서|대표로서)"
)

_KEY_CLAIM_FILLER_PREFIXES: tuple = (
    "이를 위해", "이러한 ", "따라서", "그리고 ", "그러나 ",
    "또한 ", "한편 ", "더불어 ", "아울러 ", "그래서 ", "그러므로 ",
)


def _score_key_claim_sentence(
    sentence: str,
    *,
    index: int,
    total: int,
) -> int:
    """문장 하나에 대해 "섹션 주장 문장" 가능성 스코어를 계산한다.

    길이 밴드(15~80) 통과가 기본 조건. 탈락 시 매우 낮은 값(-10_000) 반환.
    """
    length = len(sentence)
    if length < _KEY_CLAIM_MIN_LEN or length > _KEY_CLAIM_MAX_LEN:
        return -10_000

    score = 0

    # 단정·선언 어미 (결론성 / 주장 성격)
    if _KEY_CLAIM_DECLARATIVE_TAIL_RE.search(sentence):
        score += 3

    # 주장/행동 키워드
    if any(kw in sentence for kw in _KEY_CLAIM_CLAIM_KEYWORDS):
        score += 2

    # 뒤쪽 위치 보너스 (결론부 선호)
    if total > 1 and index >= total // 2:
        score += 2

    # 인사말 / 호격 페널티
    if any(marker in sentence for marker in _KEY_CLAIM_GREETING_MARKERS):
        score -= 5

    # 자기소개 페널티 ("저는 ~ 입니다")
    if _KEY_CLAIM_SELF_INTRO_RE.search(sentence):
        score -= 4

    # 전환어/군더더기 시작 페널티
    if any(sentence.startswith(prefix) for prefix in _KEY_CLAIM_FILLER_PREFIXES):
        score -= 2

    # 첫 문장 약한 페널티 (인사·도입 확률 높음)
    if index == 0:
        score -= 1

    return score


def extract_key_claim(section_text: str, *, style: str = "aeo") -> str:
    """섹션 본문의 주장/결론 문장을 키 클레임으로 선택한다.

    Why: H2 는 섹션 본문을 정답으로 간주한 질문·주장이어야 한다. 기존 구현은
         "길이 밴드 통과하는 첫 문장" 을 뽑아 인사말·자기소개·도입부 문장이
         key_claim 으로 박혔고, 그 결과 H2 가 본문 답이 아닌 본문 첫 문장을
         포장하는 형태가 됐다.
    How to apply: 모든 문장에 (a) 단정 어미, (b) 주장/행동 키워드, (c) 후반부
         위치 보너스, (d) 인사말·자기소개·전환어 페널티를 합산한 스코어를
         매겨 최상위 선택. 동점이면 등장 순서대로 안정 정렬.

    Fallback: 모든 문장이 길이 밴드에서 탈락하면 가장 긴 문장을 80자로 절단해
    반환 (기존 동작 유지).
    """
    text = strip_html(section_text)
    if not text:
        return ""

    candidates = _split_sentences(text)
    if not candidates:
        return text[:_KEY_CLAIM_MAX_LEN].rstrip()

    total = len(candidates)
    best_sentence = ""
    best_score = -10_000
    for idx, sentence in enumerate(candidates):
        score = _score_key_claim_sentence(sentence, index=idx, total=total)
        if score > best_score:
            best_score = score
            best_sentence = sentence

    if best_sentence and best_score > -9_000:
        return best_sentence

    # 길이 밴드 통과 문장이 하나도 없으면 가장 긴 문장 절단
    longest = max(candidates, key=len)
    return longest[:_KEY_CLAIM_MAX_LEN].rstrip()


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


def canonicalize_entity_surface(value: Any) -> str:
    """지역/고유명사 변이형을 공통 stem 으로 정규화.

    예: "인천" / "인천시" / "인천광역시" → 모두 "인천".
        "계양구" → "계양". "경기도" → "경기".

    Why: 동일 entity 가 다른 행정단위 접미사로 표기되면 단순 문자열 매칭으로는
         별개 키워드로 보여 `distribute_keyword_assignments` / `enforce_keyword_diversity`
         의 cap 규제를 우회한다. canonical stem 으로 묶어야 변이형 반복 스탬핑을 막는다.
    How to apply: 카운팅/dedupe 키로만 사용. 실제 표시/제거 작업은 원본 표면형 기준.

    stem 이 2 글자 미만으로 줄면 원본 유지 (접미사 단독어 "시"/"도" 등 보호).
    """
    text = str(value or "").strip()
    if len(text) < 2:
        return text
    stem = _ENTITY_SUFFIX_RE.sub("", text).strip()
    if len(stem) < 2:
        return text
    return stem


def distribute_keyword_assignments(
    plans: List[SectionPlan],
) -> List[SectionPlan]:
    """동일 `must_include_keyword` 가 과반 이상의 section 에 배정된 경우 초과분을 재배치.

    cap = ceil(len(plans) * 0.5). 한 키워드가 cap 이상 들어가면 초과분의
    `must_include_keyword` 를 해당 plan 의 `candidate_keywords` 에서 대안을 찾아
    교체한다. 대안이 없으면 빈 문자열 (scoring 에서 KEYWORD_MISSING hard-fail 미적용).

    변이형 정규화: "인천" / "인천시" / "인천광역시" 는 canonical stem "인천" 으로
    동일 entity 취급해 카운팅. 표면형만 다른 반복 스탬핑을 막는다.
    """
    if len(plans) <= 2:
        return plans

    cap = math.ceil(len(plans) * 0.5)

    # canonical stem → section 인덱스 목록
    canonical_indices: dict[str, list[int]] = {}
    for i, plan in enumerate(plans):
        kw = str(plan.get("must_include_keyword") or "").strip()
        if not kw:
            continue
        canonical = canonicalize_entity_surface(kw)
        canonical_indices.setdefault(canonical, []).append(i)

    # 이미 배정된 canonical 카운트 (교체 시 갱신)
    assigned_counts: dict[str, int] = {c: len(v) for c, v in canonical_indices.items()}

    for canonical, indices in canonical_indices.items():
        if len(indices) <= cap:
            continue
        # 앞쪽 cap 개는 유지, 나머지는 대안으로 교체
        excess = indices[cap:]
        for idx in excess:
            plan = plans[idx]
            alt_candidates: list[tuple[str, str]] = []
            for raw_alt in plan.get("candidate_keywords") or []:
                alt_text = str(raw_alt or "").strip()
                if not alt_text:
                    continue
                alt_canonical = canonicalize_entity_surface(alt_text)
                if alt_canonical == canonical:
                    # 변이형(예: "인천시") 은 동일 entity 로 보고 대안에서 제외
                    continue
                alt_candidates.append((alt_text, alt_canonical))

            replacement = ""
            for alt_text, alt_canonical in alt_candidates:
                if assigned_counts.get(alt_canonical, 0) < cap:
                    replacement = alt_text
                    assigned_counts[alt_canonical] = assigned_counts.get(alt_canonical, 0) + 1
                    break
            plan["must_include_keyword"] = replacement
            assigned_counts[canonical] -= 1

    return plans


def pick_suggested_type(
    section_text: str,
    *,
    preferred_types: Sequence[str],
    style: str = "aeo",
) -> str:
    """섹션 본문 특징으로 아키타입을 추정한다. preferred_types 풀 안에서만 선택.

    Why: 6 아키타입(질문/목표/주장/이유/대조/사례) 중 섹션 본문 마커와 가장
    잘 맞는 하나를 고른다. 허용 풀이 비어 있으면 주장형을 기본값으로 반환.
    """
    text = strip_html(section_text)
    preferred = [str(t).strip() for t in (preferred_types or ()) if str(t).strip()]

    def pick(*candidates: str) -> Optional[str]:
        for candidate in candidates:
            if candidate in preferred:
                return candidate
        return None

    lowered = text.lower()

    # 질문/의문사 마커: 질문형 최우선
    if text.rstrip().endswith("?") or "어떻게" in text or "무엇" in text or "왜" in text:
        chosen = pick("질문형", "이유형")
        if chosen:
            return chosen

    # 대조 마커
    if any(marker in lowered for marker in _COMPARATIVE_MARKERS):
        chosen = pick("대조형", "주장형")
        if chosen:
            return chosen

    # 숫자/현장/실적 마커: 사례형
    if _NUMERIC_LEAD_RE.search(text) or any(
        marker in text for marker in ("현장", "실적", "성과", "사례", "통계", "데이터")
    ):
        chosen = pick("사례형", "주장형")
        if chosen:
            return chosen

    # 배경/이유 마커
    if any(marker in text for marker in ("배경", "이유", "까닭", "원인", "때문")):
        chosen = pick("이유형", "주장형")
        if chosen:
            return chosen

    # 약속/목표 마커 + 절차 마커는 목표형에 흡수
    if any(marker in text for marker in ("약속", "목표", "다짐", "하겠", "추진", "계획", "로드맵")) or any(
        marker in text for marker in _PROCEDURAL_MARKERS
    ):
        chosen = pick("목표형", "주장형")
        if chosen:
            return chosen

    # 단정 tail 또는 비판 마커: 주장형
    if _DECLARATIVE_TAIL_RE.search(text[-40:]) or any(
        marker in text for marker in _CRITICAL_MARKERS
    ):
        chosen = pick("주장형", "이유형")
        if chosen:
            return chosen

    return preferred[0] if preferred else "주장형"


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
    commemorative: bool = False,
    matchup: bool = False,
) -> SectionPlan:
    """섹션 한 개에 대한 SectionPlan 을 생성한다.

    commemorative/matchup 플래그는 카테고리 아키타입 풀을 오버라이드한다.
    style_config.preferred_types 가 명시적으로 지정돼 있으면 그것을 우선
    사용(레거시 호환). 그렇지 않으면 카테고리 → 아키타입 매핑으로 resolve.
    """
    raw_slice = str(section_text or "")[:_SECTION_TEXT_MAX_LEN]
    cleaned = strip_html(raw_slice)

    entity_hints = _dedupe_preserve_order(
        list(extra_entities or ()) + [full_name, full_region]
    )
    proper_nouns = _extract_proper_nouns(cleaned)
    entity_hints = _dedupe_preserve_order(entity_hints + proper_nouns)

    numerics_bundle = extract_numbers_from_content(cleaned) or {}
    numerics = list(numerics_bundle.get("numbers") or [])

    override_types = list(
        style_config.get("preferred_types") or style_config.get("preferredTypes") or []
    )
    commemorative_flag = commemorative or bool(style_config.get("commemorative"))
    matchup_flag = matchup or bool(style_config.get("matchup"))
    if override_types:
        preferred_types = override_types
    else:
        pool = resolve_category_archetypes(
            category, commemorative=commemorative_flag, matchup=matchup_flag
        )
        preferred_types = list(pool["primary"]) + list(pool["auxiliary"])

    style = str(style_config.get("style") or "aeo").strip().lower() or "aeo"

    suggested_type = pick_suggested_type(
        cleaned, preferred_types=preferred_types, style=style
    )

    # Body-presence filter: candidate_keywords 풀에는 섹션 본문에 실제 등장하는
    # 토큰만 담는다. user_keywords / entity_hints 가 이 섹션 본문과 무관하면
    # `distribute_keyword_assignments` 의 대안 후보에서 제외되고 LLM 프롬프트에도
    # 노출되지 않아 H2 가 섹션 본문을 답으로 간주하는 구조를 지킬 수 있다.
    candidate_keywords = _dedupe_preserve_order(
        _filter_by_body_presence(user_keywords or (), cleaned)
        + _filter_by_body_presence(
            (hint for hint in entity_hints if hint), cleaned
        )
        + _extract_noun_candidates(cleaned)
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
        user_keywords=[str(k).strip() for k in (user_keywords or ()) if str(k).strip()],
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
        dominant_type = "이유형"
    elif _DECLARATIVE_TAIL_RE.search(joined):
        dominant_type = "주장형"

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


def extract_user_role(profile: Optional[Any]) -> str:
    """사용자 본인 직책(single source of truth)을 profile 에서 뽑아낸다.

    Why: H2 에 사용자 본인 직책을 붙일 때 role_facts, 본문 맥락, descriptor
         pool 등 여러 소스가 섞이면 "국회의원"/"위원장" 같은 타인 역할이
         본인에게 스탬핑되는 사고가 난다. 직책의 SSOT 는 profile 에서
         사용자가 직접 설정한 값뿐이다. Firestore 스키마의 canonical
         필드는 `position` (국회의원/광역의원/기초의원/광역자치단체장/
         기초자치단체장) 이므로 그것을 최우선으로 읽고, 없으면 자유 입력
         필드로 fallback 한다. 단일 라벨이므로 token split 금지.
    """
    if not isinstance(profile, dict):
        return ""
    for key in ("position", "currentRole", "current_role", "publicRole", "identity", "tagline"):
        value = profile.get(key)
        if value is None:
            continue
        cleaned = re.sub(r"\s+", " ", str(value)).strip()
        if cleaned:
            return cleaned
    return ""


_METRO_SUFFIXES = ("특별자치도", "특별자치시", "광역시", "특별시", "도")
_WIDE_METRO_SHORTS = {"서울", "부산", "대구", "인천", "광주", "대전", "울산"}
_PROVINCE_SHORTS = {"경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남"}
_SPECIAL_PROVINCE_SHORTS = {"제주"}
_SPECIAL_CITY_SHORTS = {"세종"}


def _short_metro_name(metro: Any) -> str:
    text = re.sub(r"\s+", "", str(metro or "")).strip()
    if not text:
        return ""
    for suffix in _METRO_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


def _metro_kind(short: str) -> str:
    if short in _WIDE_METRO_SHORTS:
        return "wide_metro"
    if short in _PROVINCE_SHORTS:
        return "province"
    if short in _SPECIAL_PROVINCE_SHORTS:
        return "special_province"
    if short in _SPECIAL_CITY_SHORTS:
        return "special_city"
    return ""


def localize_user_role(
    role: Any,
    *,
    region_metro: Any = "",
    region_local: Any = "",
) -> str:
    """일반 계층 명(광역시장/기초의원 등)을 지역과 결합해 실제 호칭으로 변환.

    Why: 사용자가 "광역시장"/"기초의원" 같은 계층 분류만 profile 에 저장하는데
         이걸 그대로 H2 에 쓰면 어색하다. 지역(regionMetro/regionLocal)과
         조합해서 "서울시장"/"계양구의원" 같은 실제 호칭으로 바꿔 써야 한다.
    How to apply: SubheadingAgent 가 extract_user_role 결과를 이 함수에 통과
                  시켜 최종 user_role 로 사용한다. 이미 지역이 붙어 있거나
                  매칭 실패 시 원본을 그대로 반환(lossless fallback).

    규칙:
    - 광역자치단체장 + 광역시/특별자치시 → "{short}시장"
    - 광역자치단체장 + 도/특별자치도 → "{short}도지사"
    - 기초자치단체장 + 기초시 → "{local}장" (수원시 → 수원시장)
    - 기초자치단체장 + 군 → "{local}수" (양평군 → 양평군수)
    - 기초자치단체장 + 자치구 → "{local}청장" (계양구 → 계양구청장)
    - 광역의원 + 광역시/특별자치시 → "{short}시의원"
    - 광역의원 + 도/특별자치도 → "{short}도의원"
    - 기초의원 + 자치구/기초시/군 → "{local}의원"
    """
    raw = re.sub(r"\s+", " ", str(role or "")).strip()
    if not raw:
        return ""

    compact = re.sub(r"\s+", "", raw)
    short_metro = _short_metro_name(region_metro)
    kind = _metro_kind(short_metro)
    local = re.sub(r"\s+", "", str(region_local or "")).strip()

    # 이미 지역이 붙은 구체적 호칭이면 그대로 반환.
    if short_metro and short_metro in compact and compact != short_metro:
        return raw
    if local and local in compact and compact != local:
        return raw

    if compact in ("광역자치단체장", "광역단체장", "광역시장", "특별시장", "도지사"):
        if kind in ("wide_metro", "special_city"):
            return f"{short_metro}시장"
        if kind in ("province", "special_province"):
            return f"{short_metro}도지사"

    if compact in ("기초자치단체장", "기초단체장", "시장", "군수", "구청장") and local:
        if local.endswith("시"):
            return f"{local}장"
        if local.endswith("군"):
            return f"{local}수"
        if local.endswith("구"):
            return f"{local}청장"

    if compact in ("광역의원", "시도의원"):
        if kind in ("wide_metro", "special_city"):
            return f"{short_metro}시의원"
        if kind in ("province", "special_province"):
            return f"{short_metro}도의원"

    if compact == "시의원":
        if local.endswith("시"):
            return f"{local}의원"
        if kind in ("wide_metro", "special_city"):
            return f"{short_metro}시의원"

    if compact == "도의원":
        if kind in ("province", "special_province"):
            return f"{short_metro}도의원"

    if compact == "기초의원" and local:
        if local.endswith(("구", "시", "군")):
            return f"{local}의원"

    if compact == "구의원" and local.endswith("구"):
        return f"{local}의원"
    if compact == "군의원" and local.endswith("군"):
        return f"{local}의원"

    return raw


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
