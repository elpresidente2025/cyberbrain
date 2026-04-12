"""피처 엔진 통합 — 모든 결정론적 피처를 한 번에 추출."""

from __future__ import annotations

from ..models import RawFeatureProfile
from ..schemas import MIN_STATISTICAL_CHARS, CONJUNCTIONS
from .sentence import extract_sentence_features
from .lexical import extract_lexical_features
from .punctuation import extract_punctuation_features
from .korean import extract_korean_features


def extract_raw_features(text: str) -> RawFeatureProfile | None:
    """텍스트에서 모든 결정론적 피처를 추출한다.

    Returns None if text is too short for meaningful analysis.
    """
    clean = (text or "").strip()
    if len(clean) < MIN_STATISTICAL_CHARS:
        return None

    sentences = extract_sentence_features(clean)
    lexical = extract_lexical_features(clean)
    punctuation = extract_punctuation_features(clean, sentences.count)
    korean = extract_korean_features(clean)

    # 복잡도 점수 (기존 interpret.py 호환)
    n = max(sentences.count, 1)
    import re
    from ..schemas import CONJUNCTIONS as _cj
    conj_count = sum(len(re.findall(re.escape(c), clean)) for c in _cj)
    complexity_score = round((punctuation.comma + conj_count) / n, 1)
    if complexity_score < 1:
        level = "simple"
    elif complexity_score < 2.5:
        level = "medium"
    else:
        level = "complex"

    return RawFeatureProfile(
        sentences=sentences,
        lexical=lexical,
        punctuation=punctuation,
        korean=korean,
        complexity_score=complexity_score,
        complexity_level=level,
        char_count=len(clean),
    )
