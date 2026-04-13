"""배경지시문에서 필수 키워드를 추출하는 유틸리티.

토큰 단위로 분절한 뒤 접미사 패턴을 fullmatch 방식으로 검사한다.
복합명사 내부에서 접미사가 일부만 매칭되는 greedy/backtrack 오탐
(예: "대한민국임시정부" → "대한민국임시", "독립운동" → "독립운"+"동")을
구조적으로 차단한다.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Tuple

# ---------- 분절/정제 ----------

_HANGUL_START = "\uac00"
_HANGUL_END = "\ud7a3"

_TOKEN_SPLIT_RE = re.compile(
    r"[\s,.!?;:·\-–—/()\[\]{}「」『』《》〈〉\"'“”‘’]+"
)

# 길이가 긴 조사부터 검사해야 탐욕 매칭을 피할 수 있음
_TRAILING_PARTICLES: Tuple[str, ...] = (
    "이라는", "이라고", "으로서", "으로써",
    "라는", "으로", "에서", "부터", "까지",
    "에게", "한테", "께서", "라도", "이나",
    "라고", "이란",
    "은", "는", "이", "가", "을", "를",
    "의", "와", "과", "도", "만", "로",
    "에", "며", "고",
)


def _is_hangul(ch: str) -> bool:
    return _HANGUL_START <= ch <= _HANGUL_END


def _all_hangul(s: str) -> bool:
    return bool(s) and all(_is_hangul(ch) for ch in s)


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    return [tok for tok in _TOKEN_SPLIT_RE.split(text) if tok]


def _strip_trailing_particle(token: str) -> str:
    if not token:
        return token
    for particle in _TRAILING_PARTICLES:
        if len(token) > len(particle) + 1 and token.endswith(particle):
            return token[: -len(particle)]
    return token


# ---------- 접미사 그룹 ----------

_ORG_SUFFIXES: Tuple[str, ...] = (
    "위원회", "협의회", "연합회",
    "도당", "시당", "구당",
    "재단", "협회", "연합",
)
_EVENT_SUFFIXES: Tuple[str, ...] = (
    "토론회", "간담회", "설명회", "워크숍",
    "세미나", "대회", "행사", "회의",
    "집회", "축제", "포럼",
)
_PLACE_SUFFIXES: Tuple[str, ...] = (
    "특별자치시", "특별자치도",
    "특별시", "광역시",
    "자치시", "자치도",
    "도", "시", "군", "구", "읍", "면", "동",
)
_POLICY_SUFFIXES: Tuple[str, ...] = (
    "조례", "정책", "사업", "계획", "방안", "제도", "법",
)
_ROLE_SUFFIXES: Tuple[str, ...] = (
    "경기도당위원장",
    "국회의원",
    "위원장", "부위원장",
    "도지사", "시장", "군수", "구청장",
    "교육감", "장관", "총리", "대통령",
    "의원", "지사",
)

_ALL_SUFFIX_GROUPS: Tuple[Tuple[str, ...], ...] = (
    _ORG_SUFFIXES,
    _EVENT_SUFFIXES,
    _PLACE_SUFFIXES,
    _POLICY_SUFFIXES,
)

# 단독 접미사 토큰("시", "도", "법" 등)은 키워드로 삼지 않는다
_SUFFIX_STOPWORDS: set[str] = set()
for _grp in _ALL_SUFFIX_GROUPS + (_ROLE_SUFFIXES,):
    _SUFFIX_STOPWORDS.update(_grp)

# 접미사로 오해되기 쉬운 알려진 복합명사 (구조적 차단)
_COMPOUND_STOPWORDS: set[str] = {
    "독립운동",
    "임시정부",
    "대한민국임시정부",
}


def _match_suffix_whole(
    stem: str,
    suffixes: Sequence[str],
    min_head: int = 2,
) -> bool:
    """stem이 접미사 중 하나로 끝나면서 접두부가 최소 길이 이상 한글인지 검사."""
    for suffix in suffixes:
        if stem == suffix:
            continue
        if not stem.endswith(suffix):
            continue
        head = stem[: -len(suffix)]
        if len(head) < min_head:
            continue
        if not _all_hangul(head):
            continue
        return True
    return False


# ---------- 공개 API ----------

def _normalize_instructions(instructions: str | Sequence[str] | None) -> str:
    if not instructions:
        return ""
    if isinstance(instructions, str):
        return instructions
    if isinstance(instructions, Iterable):
        return " ".join(str(item) for item in instructions if item)
    return str(instructions)


def extract_keywords_from_instructions(
    instructions: str | Sequence[str] | None,
) -> List[str]:
    """배경정보에서 검색/검증에 필요한 키워드를 추출한다.

    Args:
        instructions: 문자열 또는 문자열 배열.

    Returns:
        중복 제거된 키워드 리스트.
    """
    text = _normalize_instructions(instructions)
    if not text:
        return []

    keywords: list[str] = []

    # 1) 숫자 + 단위 — 단어 내부 출현이 정상이므로 findall 유지
    keywords.extend(re.findall(r"[0-9]+여?[명개회건차월일년원]", text))

    # 6) 연도 — 동일
    keywords.extend(re.findall(r"20[0-9]{2}년", text))

    tokens = _tokenize(text)
    stems = [_strip_trailing_particle(tok) for tok in tokens]

    # 2) 인명 + 직책 (인접 토큰 쌍으로 검사)
    for idx in range(len(stems) - 1):
        name = stems[idx]
        role = stems[idx + 1]
        if not (2 <= len(name) <= 4 and _all_hangul(name)):
            continue
        if role in _ROLE_SUFFIXES:
            keywords.append(f"{name} {role}")
            keywords.append(name)

    # 3~5, 7) 토큰 단위 접미사 매칭
    for stem in stems:
        if not stem or len(stem) < 3:
            continue
        if not _all_hangul(stem):
            continue
        if stem in _SUFFIX_STOPWORDS or stem in _COMPOUND_STOPWORDS:
            continue

        matched = False
        for suffixes in _ALL_SUFFIX_GROUPS:
            if _match_suffix_whole(stem, suffixes):
                keywords.append(stem)
                matched = True
                break
        if matched:
            continue

        # 복합 직책이 단독 토큰으로 나타난 경우 (예: "국회의원", "경기도당위원장")
        if stem in _ROLE_SUFFIXES and len(stem) >= 4:
            keywords.append(stem)
            continue

        # 직책이 접미사로 합쳐진 복합어 (예: "부산시장", "경기도당위원장")
        for role in _ROLE_SUFFIXES:
            if stem == role:
                break
            if stem.endswith(role) and _all_hangul(stem[: -len(role)]):
                keywords.append(stem)
                break

    # 순서 보존 중복 제거 + 스톱워드 필터
    seen: set[str] = set()
    deduped: list[str] = []
    for keyword in keywords:
        if keyword in seen:
            continue
        if keyword in _COMPOUND_STOPWORDS:
            continue
        seen.add(keyword)
        deduped.append(keyword)
    return deduped


# JS 호환 별칭
extractKeywordsFromInstructions = extract_keywords_from_instructions


__all__ = [
    "extract_keywords_from_instructions",
    "extractKeywordsFromInstructions",
]
