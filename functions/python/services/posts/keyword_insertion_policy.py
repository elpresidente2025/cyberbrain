from __future__ import annotations

import re
from typing import Sequence

# Shared policy contract used by both:
# 1) KeywordInjectorAgent prompt instructions
# 2) validation.enforce_keyword_requirements post-repair guards

# Event-only tokens are kept as a subset for backward compatibility.
EVENT_CONTEXT_TOKENS: tuple[str, ...] = (
    "출판기념회",
    "출판 행사",
    "행사",
    "일정",
    "현장",
    "만남",
    "참석",
    "초대",
    "개최",
    "행사장",
    "장소",
)

# General, domain-agnostic location/action context tokens.
LOCATION_CONTEXT_TOKENS: tuple[str, ...] = (
    *EVENT_CONTEXT_TOKENS,
    "설명회",
    "간담회",
    "토론회",
    "브리핑",
    "점검",
    "방문",
    "협의",
    "논의",
    "발표",
    "추진",
    "시행",
    "개선",
    "지원",
    "전환",
    "구축",
    "주민",
    "시민",
    "지역",
    "거점",
)

UNSAFE_LOCATION_CONTEXT_TOKENS: tuple[str, ...] = (
    "학과",
    "졸업",
    "경력",
    "이사",
    "전무",
    "ceo",
    "경제성장률",
    "성장률",
    "국비",
    "예산",
    "정부",
    "정책 과제",
)

UNSAFE_LOCATION_ATTACH_TOKENS: tuple[str, ...] = (
    "과제",
    "정책",
    "문제",
    "비전",
    "리더십",
    "경력",
    "학과",
    "졸업",
    "산업",
    "경제",
    "성장률",
    "국비",
    "연구",
    "기업",
)

SENTENCE_FOCUS_TOKENS: tuple[str, ...] = (
    "출판기념회",
    "행사",
    "일정",
    "참여",
    "현장",
    "소통",
    "대화",
    "문제",
    "과제",
    "정책",
    "의제",
    "설명",
    "점검",
    "방문",
    "논의",
)

TERMINAL_MARKERS: tuple[str, ...] = (
    "감사합니다",
    "감사드립니다",
    "고맙습니다",
    "이상입니다",
)

GREETING_MARKERS: tuple[str, ...] = (
    "존경하는",
    "안녕하십니까",
)

LOCATION_PREFIX_STOPWORDS: tuple[str, ...] = (
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "세종",
    "수도권",
    "서면",
)


def normalize_plain(text: str) -> str:
    plain = re.sub(r"<[^>]*>", " ", str(text or ""))
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain


def _contains_any(normalized_text: str, tokens: Sequence[str]) -> bool:
    lowered = str(normalized_text or "").lower()
    if not lowered:
        return False
    return any(str(token).lower() in lowered for token in tokens if str(token).strip())


def _extract_keyword_hint_tokens(keyword: str) -> list[str]:
    normalized = normalize_plain(keyword)
    chunks = re.split(r"[ \t\r\n,./|:;(){}\[\]<>\"'“”‘’《》『』]+", normalized)
    tokens = [chunk.strip() for chunk in chunks if len(chunk.strip()) >= 2]
    return [token for token in tokens if token not in LOCATION_PREFIX_STOPWORDS]


def is_location_context_text(text: str, keyword: str = "") -> bool:
    normalized = normalize_plain(text)
    if not normalized:
        return False

    if _contains_any(normalized, LOCATION_CONTEXT_TOKENS):
        return True

    # Keyword-aware fallback:
    # if keyword hint appears and there is at least one action/location verb,
    # allow contextual insertion even when explicit event tokens are missing.
    hint_tokens = _extract_keyword_hint_tokens(keyword)
    if hint_tokens:
        hint_hits = sum(1 for token in hint_tokens if token and token in normalized)
        if hint_hits >= 2:
            return True
        if hint_hits >= 1 and _contains_any(
            normalized,
            ("현장", "장소", "지역", "방문", "논의", "설명", "참석", "개최", "진행", "점검", "추진"),
        ):
            return True

    return False


# Backward-compatible name (legacy callers).
def is_event_context_text(text: str, keyword: str = "") -> bool:
    return is_location_context_text(text, keyword=keyword)


def is_unsafe_location_context(text: str) -> bool:
    return _contains_any(normalize_plain(text), UNSAFE_LOCATION_CONTEXT_TOKENS)


def is_terminal_sentence(text: str) -> bool:
    return _contains_any(normalize_plain(text), TERMINAL_MARKERS)


def is_greeting_sentence(text: str) -> bool:
    normalized = normalize_plain(text)
    return _contains_any(normalized, GREETING_MARKERS)


def build_keyword_injection_policy_lines() -> list[str]:
    return [
        "append보다 문맥 내 치환(replace)을 우선한다.",
        "위치 키워드는 주제·행동 문맥 문장에만 삽입한다.",
        "경력·학력·숫자 보고 문장은 위치 키워드 삽입 대상으로 쓰지 않는다.",
        "인사말·맺음말(감사합니다 등) 문장은 수정하지 않는다.",
        "사실관계와 논리 순서는 바꾸지 않는다.",
    ]

