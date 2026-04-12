"""한국어 특화 피처 — 종결 어미, 기능어 밀도."""

from __future__ import annotations

import re
from collections import Counter

from ..models import KoreanFeatures
from ..schemas import CONJUNCTIONS, FORMAL_ENDINGS, KOREAN_FUNCTION_WORDS

# 문장 종결 부분에서 어미 추출용 (마지막 2~6글자)
_ENDING_RE = re.compile(r"([가-힣]{2,6})[.!?。！？\s]*$")

# 격식 종결 어미 패턴
_FORMAL_PATTERN = re.compile(
    r"(?:" + "|".join(re.escape(e) for e in FORMAL_ENDINGS) + r")[.!?。！？\s]*$"
)

# 비격식 종결 어미 패턴
_INFORMAL_ENDINGS = (
    "해요", "에요", "이에요", "거에요", "네요",
    "죠", "잖아요", "나요", "할게요", "할까요",
    "해", "야", "지", "어", "아",
)
_INFORMAL_PATTERN = re.compile(
    r"(?:" + "|".join(re.escape(e) for e in _INFORMAL_ENDINGS) + r")[.!?。！？\s]*$"
)

_SENTENCE_SPLIT = re.compile(r'(?<=[.!?。])\s+')


def extract_korean_features(text: str) -> KoreanFeatures:
    """한국어 특화 통계를 추출한다."""
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if len(s.strip()) >= 5]
    n = len(sentences)
    if n == 0:
        return KoreanFeatures()

    # 종결 어미 분석
    endings: list[str] = []
    formal_count = 0
    informal_count = 0

    for sent in sentences:
        m = _ENDING_RE.search(sent)
        if m:
            ending = m.group(1)
            endings.append(ending)

        if _FORMAL_PATTERN.search(sent):
            formal_count += 1
        elif _INFORMAL_PATTERN.search(sent):
            informal_count += 1

    formal_ratio = formal_count / n
    informal_ratio = informal_count / n

    # 종결 어미 다양성 (unique / total)
    ending_freq = Counter(endings)
    ending_diversity = len(ending_freq) / len(endings) if endings else 0.0
    top_endings = [e for e, _ in ending_freq.most_common(5)]

    # 기능어 비율
    tokens = re.findall(r"[가-힣]+", text)
    total_tokens = len(tokens)
    if total_tokens > 0:
        func_count = sum(
            1 for t in tokens
            if any(t.endswith(fw) for fw in KOREAN_FUNCTION_WORDS)
        )
        function_word_ratio = func_count / total_tokens
    else:
        function_word_ratio = 0.0

    # 접속사 밀도
    conj_count = sum(len(re.findall(re.escape(c), text)) for c in CONJUNCTIONS)
    conjunction_density = conj_count / n if n > 0 else 0.0

    return KoreanFeatures(
        formal_ending_ratio=round(formal_ratio, 3),
        informal_ending_ratio=round(informal_ratio, 3),
        ending_diversity=round(ending_diversity, 3),
        top_endings=top_endings,
        function_word_ratio=round(function_word_ratio, 4),
        conjunction_density=round(conjunction_density, 3),
    )
