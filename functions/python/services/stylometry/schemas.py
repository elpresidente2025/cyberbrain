"""Stylometry 패키지 공유 상수 및 스키마 정의."""

from __future__ import annotations

# ── 분석 임계치 ──────────────────────────────────────────────
MIN_ANALYZABLE_CHARS = 100          # extractStyleFingerprint 최소 입력
MIN_STATISTICAL_CHARS = 50          # analyzeTextStatistics 최소 입력
MIN_SENTENCE_COUNT = 3
MAX_INTERPRET_TEXT_CHARS = 6_000    # Gemini 프롬프트에 넘길 최대 원문 길이

# ── refresh 상수 ─────────────────────────────────────────────
MAX_DIARY_ENTRIES = 30
MIN_CORPUS_LENGTH = 100

# ── extractStyleFingerprint Gemini 응답 필수 키 ──────────────
LEGACY_REQUIRED_KEYS = (
    "characteristicPhrases",
    "sentencePatterns",
    "vocabularyProfile",
    "toneProfile",
    "rhetoricalDevices",
    "aiAlternatives",
    "analysisMetadata",
)

# ── AI 상투어 기본 대체 표현 ─────────────────────────────────
DEFAULT_AI_ALTERNATIVES: dict[str, str] = {
    "instead_of_평범한_이웃": "주민 여러분",
    "instead_of_함께_힘을_모아": "함께 만들어가겠습니다",
    "instead_of_더_나은_내일": "실질적인 변화",
    "instead_of_밝은_미래": "구체적인 성과",
}

# ── 한국어 접속사 (복잡도 측정용) ────────────────────────────
CONJUNCTIONS = (
    "그리고", "그러나", "하지만", "또한", "그래서",
    "따라서", "그러므로", "왜냐하면",
)

# ── 한국어 격식 종결 어미 ───────────────────────────────────��
FORMAL_ENDINGS = (
    "합니다", "습니다", "입니다", "습니까",
    "겠습니다", "드리겠습니다",
)

# ── 한국어 기능어 (조사/어미 빈도 분석용) ───────────────────���
KOREAN_FUNCTION_WORDS = (
    "은", "는", "이", "가", "을", "를",
    "에", "에서", "로", "으로", "와", "과",
    "의", "도", "만", "까지", "부터",
)
