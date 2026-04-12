"""어휘 수준 피처 추출 — TTR, hapax ratio."""

from __future__ import annotations

import re
from collections import Counter

from ..models import LexicalFeatures

# 한국어+영문 토큰화 (공백 기반, 조사 미분리 — 간이 토크나이저)
_TOKEN_RE = re.compile(r"[가-힣a-zA-Z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def extract_lexical_features(text: str) -> LexicalFeatures:
    """어휘 통계를 추출한다."""
    tokens = _tokenize(text)
    n = len(tokens)
    if n == 0:
        return LexicalFeatures()

    freq = Counter(tokens)
    unique = len(freq)
    hapax = sum(1 for v in freq.values() if v == 1)
    avg_word_len = sum(len(t) for t in tokens) / n

    return LexicalFeatures(
        total_tokens=n,
        unique_tokens=unique,
        ttr=round(unique / n, 4) if n > 0 else 0.0,
        hapax_ratio=round(hapax / unique, 4) if unique > 0 else 0.0,
        avg_word_length=round(avg_word_len, 2),
    )
