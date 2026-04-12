"""구두점 피처 추출 — 엔트로피 포함."""

from __future__ import annotations

import math

from ..models import PunctuationFeatures


def extract_punctuation_features(text: str, sentence_count: int) -> PunctuationFeatures:
    """구두점 통계 + Shannon 엔트로피를 계산한다."""
    comma = text.count(",") + text.count("，")
    period = text.count(".") + text.count("。")
    question = text.count("?") + text.count("？")
    exclamation = text.count("!") + text.count("！")
    ellipsis = text.count("...") + text.count("…")
    colon = text.count(":") + text.count("：")
    semicolon = text.count(";") + text.count("；")

    counts = [comma, period, question, exclamation, ellipsis, colon, semicolon]
    total = sum(counts)

    # Shannon entropy
    if total > 0:
        probs = [c / total for c in counts if c > 0]
        entropy = -sum(p * math.log2(p) for p in probs)
    else:
        entropy = 0.0

    n = max(sentence_count, 1)
    return PunctuationFeatures(
        comma=comma,
        period=period,
        question=question,
        exclamation=exclamation,
        ellipsis=ellipsis,
        colon=colon,
        semicolon=semicolon,
        commas_per_sentence=round(comma / n, 2),
        entropy=round(entropy, 4),
    )
