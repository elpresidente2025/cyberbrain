"""한국어 특화 피처 — 종결 어미, 기능어 밀도, 서술 전략."""

from __future__ import annotations

import re
from collections import Counter

from agents.common import korean_morph

from ..models import KoreanFeatures
from ..schemas import CONJUNCTIONS, FORMAL_ENDINGS, KOREAN_FUNCTION_WORDS

# 문장 종결 부분에서 어미 추출용 (마지막 2~6글자)
_ENDING_RE = re.compile(r"([가-힣]{2,6})[.!?。！？\s]*$")

# ── 감정 직접 명명 패턴 (emotionDirectness) ──────────────────
# 감정을 직접 이름 붙이는 표현 — "안타깝다", "감사하다" 등
# 이 비율이 높으면 tell, 낮으면 show
_EMOTION_DIRECT_RE = re.compile(
    r"(?:안타깝|감사하|감사드리|기쁘|기쁜|슬프|슬픈|행복하|행복한|두렵|두려운"
    r"|걱정되|걱정스러운|화가\s*나|분노하|뿌듯하|뿌듯한|가슴\s*아프"
    r"|마음이?\s*(?:무겁|아프|따뜻|뜨거)|감동적|유감스럽|다행히|안타깝게도"
    r"|감사하게도|유감스럽게도|기쁘게도|놀랍게도|부끄럽|자랑스럽|서럽"
    r"|서러운|절망적|희망적|참담하|통탄하|한탄하|괴롭)"
)

# ── 구체 디테일 마커 (concreteDetailRatio) ──────────────────
# 숫자·날짜·고유명사·단위 등 구체적 사실이 포함된 문장 비율
_CONCRETE_DETAIL_RE = re.compile(
    r"\d+"                               # 숫자 (년도, 금액, 비율 등)
    r"|(?:\d{1,2}월\s*\d{1,2}일)"       # 날짜
    r"|(?:\d{4}년)"                      # 연도
    r"|(?:\d+[%％])"                     # 퍼센트
    r"|(?:\d+(?:억|만|천|백)\s*원)"      # 금액
    r"|(?:\d+(?:명|건|개|곳|호|동|층))"  # 수량+단위
    r"|(?:[가-힣]{1,8}(?:법|조례|법률안|시행령))"  # 법령명
    r"|(?:[가-힣]{1,6}(?:구|동|면|읍|리|역|로|길)\b)"  # 지명
)

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
_TRAILING_SKIP_TAGS = frozenset({"SF", "SP", "SS", "SW", "SO", "SE"})
_FUNCTION_WORD_TAGS = frozenset({
    "JKS", "JKO", "JKB", "JKG", "JKC", "JKV", "JKQ", "JX", "JC",
    "EP", "EF", "EC", "ETM", "ETN",
    "XSN", "XSV", "XSA",
})


def _split_sentences(text: str) -> list[str]:
    sentences = korean_morph.split_sentences(text)
    if sentences is not None:
        return [sentence.strip() for sentence in sentences if len(sentence.strip()) >= 5]
    return [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT.split(text.strip())
        if len(sentence.strip()) >= 5
    ]


def _last_content_token(tokens: list) -> object | None:
    for tok in reversed(tokens):
        if tok.tag in _TRAILING_SKIP_TAGS:
            continue
        return tok
    return None


def extract_korean_features(text: str) -> KoreanFeatures:
    """한국어 특화 통계를 추출한다."""
    sentences = _split_sentences(text)
    n = len(sentences)
    if n == 0:
        return KoreanFeatures()

    # 종결 어미 분석
    endings: list[str] = []
    formal_count = 0
    informal_count = 0

    for sent in sentences:
        sentence_tokens = korean_morph.tokenize(sent)
        if sentence_tokens:
            last_token = _last_content_token(sentence_tokens)
            if last_token is not None and last_token.form:
                endings.append(str(last_token.form))
        else:
            m = _ENDING_RE.search(sent)
            if m:
                endings.append(m.group(1))

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
    morph_tokens = korean_morph.tokenize(text)
    if morph_tokens:
        content_tokens = [tok for tok in morph_tokens if tok.tag not in _TRAILING_SKIP_TAGS]
        total_tokens = len(content_tokens)
        if total_tokens > 0:
            func_count = sum(1 for tok in content_tokens if tok.tag in _FUNCTION_WORD_TAGS)
            function_word_ratio = func_count / total_tokens
        else:
            function_word_ratio = 0.0
        conj_count = sum(
            1 for tok in content_tokens
            if tok.form in CONJUNCTIONS
        )
    else:
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
        conj_count = sum(len(re.findall(re.escape(c), text)) for c in CONJUNCTIONS)

    # 접속사 밀도
    conjunction_density = conj_count / n if n > 0 else 0.0

    # ── 감정 직접 명명 비율 ──────────────────────────────────
    emotion_direct_count = sum(
        1 for sent in sentences if _EMOTION_DIRECT_RE.search(sent)
    )
    emotion_directness = emotion_direct_count / n

    # ── 구체 디테일 비율 ──────────────────────────────────────
    concrete_count = sum(
        1 for sent in sentences if _CONCRETE_DETAIL_RE.search(sent)
    )
    concrete_detail_ratio = concrete_count / n

    return KoreanFeatures(
        formal_ending_ratio=round(formal_ratio, 3),
        informal_ending_ratio=round(informal_ratio, 3),
        ending_diversity=round(ending_diversity, 3),
        top_endings=top_endings,
        function_word_ratio=round(function_word_ratio, 4),
        conjunction_density=round(conjunction_density, 3),
        emotion_directness=round(emotion_directness, 3),
        concrete_detail_ratio=round(concrete_detail_ratio, 3),
    )
