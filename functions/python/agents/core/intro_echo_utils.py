"""서론-결론 문구 중복(에코) 탐지 공용 유틸."""

from __future__ import annotations

import re
from typing import Iterable, List


_TAG_RE = re.compile(r"<[^>]*>")
_SPACE_RE = re.compile(r"\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|\n+")
_TRIM_PUNCT_RE = re.compile(r"^[\s\"'“”‘’\-\.,!?…]+|[\s\"'“”‘’\-\.,!?…]+$")
_SIGNATURE_RE = re.compile(r"[^0-9A-Za-z가-힣]+")


def _to_plain(text: object) -> str:
    value = str(text or "")
    if not value:
        return ""
    value = _TAG_RE.sub(" ", value)
    value = _SPACE_RE.sub(" ", value).strip()
    return value


def _signature(text: str) -> str:
    if not text:
        return ""
    compact = _SIGNATURE_RE.sub("", text)
    return compact.lower()


def _clean_sentence(text: str) -> str:
    cleaned = _SPACE_RE.sub(" ", str(text or "")).strip()
    cleaned = _TRIM_PUNCT_RE.sub("", cleaned)
    return cleaned.strip()


def _split_sentences(text: str) -> List[str]:
    plain = _to_plain(text)
    if not plain:
        return []
    chunks = _SENTENCE_SPLIT_RE.split(plain)
    results: List[str] = []
    for chunk in chunks:
        sentence = _clean_sentence(chunk)
        if sentence:
            results.append(sentence)
    return results


def normalize_keywords(keywords: Iterable[object] | None) -> List[str]:
    """키워드 리스트를 중복 제거/공백 정리한 문자열 목록으로 반환."""
    normalized: List[str] = []
    seen: set[str] = set()
    for item in keywords or []:
        text = _clean_sentence(_to_plain(item))
        if not text:
            continue
        key = _signature(text)
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def _is_keyword_dominated(phrase: str, keyword_signatures: List[str]) -> bool:
    phrase_key = _signature(phrase)
    if not phrase_key:
        return True
    for keyword_key in keyword_signatures:
        if not keyword_key:
            continue
        if keyword_key in phrase_key or phrase_key in keyword_key:
            return True
    return False


def find_intro_conclusion_duplicates(
    intro_text: str,
    conclusion_text: str,
    *,
    user_keywords: Iterable[object] | None = None,
    min_phrase_len: int = 12,
) -> List[str]:
    """서론/결론 사이에서 동일 문장(또는 유사한 핵심 문구) 중복을 탐지한다."""
    intro_sentences = _split_sentences(intro_text)
    conclusion_sentences = _split_sentences(conclusion_text)
    if not intro_sentences or not conclusion_sentences:
        return []

    keyword_signatures = [_signature(item) for item in normalize_keywords(user_keywords)]
    intro_signature_map: dict[str, str] = {}
    for sentence in intro_sentences:
        sig = _signature(sentence)
        if len(sig) < max(4, min_phrase_len):
            continue
        intro_signature_map.setdefault(sig, sentence)

    duplicates: List[str] = []
    seen_phrase_keys: set[str] = set()
    for sentence in conclusion_sentences:
        sig = _signature(sentence)
        if len(sig) < max(4, min_phrase_len):
            continue
        if sig not in intro_signature_map:
            continue
        if _is_keyword_dominated(sentence, keyword_signatures):
            continue
        phrase_key = sig
        if phrase_key in seen_phrase_keys:
            continue
        seen_phrase_keys.add(phrase_key)
        duplicates.append(sentence)

    return duplicates


__all__ = [
    "find_intro_conclusion_duplicates",
    "normalize_keywords",
]

