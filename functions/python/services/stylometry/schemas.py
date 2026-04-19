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

# ── AI 상투어 기본 대체 표현 (patina 패턴 기반) ──────────────
# stylometry LLM이 사용자 텍스트에서 실제 대체어를 추출해 덮어씀.
# 여기는 fallback 기본값.
DEFAULT_AI_ALTERNATIVES: dict[str, str] = {
    # 기존
    "instead_of_평범한_이웃": "주민 여러분",
    "instead_of_함께_힘을_모아": "함께 만들어가겠습니다",
    "instead_of_더_나은_내일": "실질적인 변화",
    "instead_of_밝은_미래": "구체적인 성과",
    # patina #1 과도한 중요성
    "instead_of_획기적인": "눈에 띄는",
    "instead_of_전환점": "계기",
    # patina #7 AI 특유 어휘
    "instead_of_혁신적인": "실질적인",
    "instead_of_다양한": "여러",
    "instead_of_활발한": "잦은",
    # patina #8 ~적 접미사
    "instead_of_체계적인": "구체적인",
    "instead_of_종합적인": "전반적인",
    "instead_of_지속적인": "꾸준한",
    "instead_of_효과적인": "알맞은",
    # patina #18 과도한 한자어
    "instead_of_극대화": "확대",
    "instead_of_도모": "추진",
    "instead_of_촉진": "앞당기기",
    "instead_of_수립": "마련",
    "instead_of_창출": "만들기",
    # patina #6 과제와 전망 / #24 막연한 긍정
    "instead_of_기여": "도움",
    "instead_of_도약": "변화",
}

# ── patina 대상 어휘 (userNativeWords 화이트리스트 판별용) ────
# 사용자 입력 텍스트에 이 단어가 있으면 교정 제외 대상으로 등록.
PATINA_TARGET_WORDS: frozenset[str] = frozenset({
    # patina #1 과도한 중요성
    "핵심적", "획기적", "전환점", "지평",
    # patina #7 AI 특유 어휘
    "혁신적", "다양한", "활발한", "주목할",
    # patina #8 ~적 접미사 (빈도 높은 것만)
    "체계적", "종합적", "지속적", "효과적",
    # patina #18 과도한 한자어
    "극대화", "도모", "촉진", "수립", "창출",
    # patina #6/#24 과제와 전망 / 막연한 긍정
    "기여", "도약", "밝은 전망", "밝은 미래",
})

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
