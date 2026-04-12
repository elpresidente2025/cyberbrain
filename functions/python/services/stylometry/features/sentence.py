"""문장 수준 피처 추출."""

from __future__ import annotations

import math
import re

from ..models import SentenceFeatures

# 한국어 문장 종결 패턴 (마침표/물음표/느낌표 + 따옴표 허용)
_SENTENCE_SPLIT = re.compile(r'(?<=[.!?。])\s+|(?<=[.!?。])["\'」』）\)]*\s+')
_MIN_SENTENCE_LEN = 5


def _split_sentences(text: str) -> list[str]:
    """텍스트를 문장 단위로 분리. 최소 길이 미만은 제외."""
    raw = _SENTENCE_SPLIT.split(text.strip())
    return [s.strip() for s in raw if len(s.strip()) >= _MIN_SENTENCE_LEN]


def extract_sentence_features(text: str) -> SentenceFeatures:
    """문장 통계를 추출한다."""
    sentences = _split_sentences(text)
    n = len(sentences)
    if n < 2:
        lengths = [len(s) for s in sentences] if sentences else [0]
        return SentenceFeatures(
            count=n,
            avg_length=float(lengths[0]) if lengths else 0.0,
            min_length=lengths[0] if lengths else 0,
            max_length=lengths[0] if lengths else 0,
        )

    lengths = [len(s) for s in sentences]
    avg = sum(lengths) / n
    variance = sum((l - avg) ** 2 for l in lengths) / n
    std = math.sqrt(variance)
    cv = std / avg if avg > 0 else 0.0

    # skewness (Fisher-Pearson)
    if std > 0 and n >= 3:
        skew = sum(((l - avg) / std) ** 3 for l in lengths) / n
    else:
        skew = 0.0

    short = sum(1 for l in lengths if l < 30)
    medium = sum(1 for l in lengths if 30 <= l <= 60)
    long = sum(1 for l in lengths if l > 60)

    return SentenceFeatures(
        count=n,
        avg_length=round(avg, 1),
        min_length=min(lengths),
        max_length=max(lengths),
        std_dev=round(std, 1),
        cv=round(cv, 3),
        skewness=round(skew, 3),
        short_ratio=round(short / n, 3),
        medium_ratio=round(medium / n, 3),
        long_ratio=round(long / n, 3),
    )
