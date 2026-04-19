"""Stylometry 데이터 모델 — dataclass 기반 타입 정의.

외부 패키지(pydantic) 없이 표준 라이브러리만 사용한다.
모든 모델은 .to_dict()로 Firestore 직렬화, .from_dict()로 역직렬화 가능.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# ── 결정론적 피처 (LLM 없음) ───────────────────────────────────

@dataclass
class SentenceFeatures:
    """문장 수준 통계."""
    count: int = 0
    avg_length: float = 0.0
    min_length: int = 0
    max_length: int = 0
    std_dev: float = 0.0
    cv: float = 0.0                     # coefficient of variation
    skewness: float = 0.0               # 길이 분포 비대칭도
    short_ratio: float = 0.0            # < 30자
    medium_ratio: float = 0.0           # 30-60자
    long_ratio: float = 0.0             # > 60자

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SentenceFeatures:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class LexicalFeatures:
    """어휘 수준 통계."""
    total_tokens: int = 0
    unique_tokens: int = 0
    ttr: float = 0.0                    # type-token ratio
    hapax_ratio: float = 0.0            # 1회 등장 어휘 비율
    avg_word_length: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LexicalFeatures:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PunctuationFeatures:
    """구두점 통계."""
    comma: int = 0
    period: int = 0
    question: int = 0
    exclamation: int = 0
    ellipsis: int = 0
    colon: int = 0
    semicolon: int = 0
    commas_per_sentence: float = 0.0
    entropy: float = 0.0               # 구두점 엔트로피

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PunctuationFeatures:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class KoreanFeatures:
    """한국어 특화 통계."""
    formal_ending_ratio: float = 0.0    # 격식체 비율
    informal_ending_ratio: float = 0.0  # 비격식체 비율
    ending_diversity: float = 0.0       # 종결 어미 다양성
    top_endings: list[str] = field(default_factory=list)
    function_word_ratio: float = 0.0    # 기능어 비율
    conjunction_density: float = 0.0    # 접속사 밀도
    emotion_directness: float = 0.0     # 감정 직접 명명 비율 (0=간접/show ~ 1=직접/tell)
    concrete_detail_ratio: float = 0.0  # 구체 디테일(숫자·고유명사·날짜) 포함 문장 비율

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> KoreanFeatures:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class RawFeatureProfile:
    """결정론적 피처 전체 — LLM 없이 코드만으로 계산."""
    sentences: SentenceFeatures = field(default_factory=SentenceFeatures)
    lexical: LexicalFeatures = field(default_factory=LexicalFeatures)
    punctuation: PunctuationFeatures = field(default_factory=PunctuationFeatures)
    korean: KoreanFeatures = field(default_factory=KoreanFeatures)
    complexity_score: float = 0.0
    complexity_level: str = "medium"    # simple | medium | complex
    char_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sentences": self.sentences.to_dict(),
            "lexical": self.lexical.to_dict(),
            "punctuation": self.punctuation.to_dict(),
            "korean": self.korean.to_dict(),
            "complexityScore": self.complexity_score,
            "complexityLevel": self.complexity_level,
            "charCount": self.char_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RawFeatureProfile:
        return cls(
            sentences=SentenceFeatures.from_dict(d.get("sentences", {})),
            lexical=LexicalFeatures.from_dict(d.get("lexical", {})),
            punctuation=PunctuationFeatures.from_dict(d.get("punctuation", {})),
            korean=KoreanFeatures.from_dict(d.get("korean", {})),
            complexity_score=d.get("complexityScore", 0.0),
            complexity_level=d.get("complexityLevel", "medium"),
            char_count=d.get("charCount", 0),
        )


# ── LLM 해석 결과 ─────────────────────────────────────────────

@dataclass
class InterpretationProfile:
    """Gemini가 피처를 해석한 결과 — 기존 fingerprint의 상위 구조."""
    characteristic_phrases: dict[str, list[str]] = field(default_factory=dict)
    sentence_patterns: dict[str, Any] = field(default_factory=dict)
    vocabulary_profile: dict[str, Any] = field(default_factory=dict)
    tone_profile: dict[str, float | str] = field(default_factory=dict)
    rhetorical_devices: dict[str, Any] = field(default_factory=dict)
    ai_alternatives: dict[str, str] = field(default_factory=dict)
    analysis_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """기존 Firestore fingerprint 형식 호환."""
        return {
            "characteristicPhrases": self.characteristic_phrases,
            "sentencePatterns": self.sentence_patterns,
            "vocabularyProfile": self.vocabulary_profile,
            "toneProfile": self.tone_profile,
            "rhetoricalDevices": self.rhetorical_devices,
            "aiAlternatives": self.ai_alternatives,
            "analysisMetadata": self.analysis_metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> InterpretationProfile:
        return cls(
            characteristic_phrases=d.get("characteristicPhrases", {}),
            sentence_patterns=d.get("sentencePatterns", {}),
            vocabulary_profile=d.get("vocabularyProfile", {}),
            tone_profile=d.get("toneProfile", {}),
            rhetorical_devices=d.get("rhetoricalDevices", {}),
            ai_alternatives=d.get("aiAlternatives", {}),
            analysis_metadata=d.get("analysisMetadata", {}),
        )


# ── 생성 제약조건 ──────────────────────────────────────────────

@dataclass
class GenerationProfile:
    """피처 + 해석을 종합한 원고 생성 제약조건."""
    target_sentence_length: tuple[int, int] = (30, 60)  # min, max
    target_cv: float = 0.3                               # 문장 길이 변동 목표
    formality: float = 0.7                               # 0~1
    emotionality: float = 0.3
    directness: float = 0.6
    preferred_endings: list[str] = field(default_factory=list)
    forbidden_patterns: list[str] = field(default_factory=list)
    signature_phrases: list[str] = field(default_factory=list)
    ai_alternatives: dict[str, str] = field(default_factory=dict)
    style_summary: str = ""
    # ── 서술 전략 슬롯 ────────────────────────────────────────
    emotion_directness: float = 0.5     # 0~1: 0=간접(show, don't tell) ~ 1=직접(tell)
    sentence_length_variance: float = 0.3  # CV 목표 (높을수록 짧은/긴 문장 낙차 큼)
    concrete_detail_ratio: float = 0.4  # 0~1: 구체 디테일 포함 문장 목표 비율

    def to_dict(self) -> dict[str, Any]:
        return {
            "targetSentenceLength": list(self.target_sentence_length),
            "targetCV": self.target_cv,
            "formality": self.formality,
            "emotionality": self.emotionality,
            "directness": self.directness,
            "preferredEndings": self.preferred_endings,
            "forbiddenPatterns": self.forbidden_patterns,
            "signaturePhrases": self.signature_phrases,
            "aiAlternatives": self.ai_alternatives,
            "styleSummary": self.style_summary,
            "emotionDirectness": self.emotion_directness,
            "sentenceLengthVariance": self.sentence_length_variance,
            "concreteDetailRatio": self.concrete_detail_ratio,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GenerationProfile:
        tsl = d.get("targetSentenceLength", [30, 60])
        return cls(
            target_sentence_length=tuple(tsl) if isinstance(tsl, (list, tuple)) else (30, 60),
            target_cv=d.get("targetCV", 0.3),
            formality=d.get("formality", 0.7),
            emotionality=d.get("emotionality", 0.3),
            directness=d.get("directness", 0.6),
            preferred_endings=d.get("preferredEndings", []),
            forbidden_patterns=d.get("forbiddenPatterns", []),
            signature_phrases=d.get("signaturePhrases", []),
            ai_alternatives=d.get("aiAlternatives", {}),
            style_summary=d.get("styleSummary", ""),
            emotion_directness=d.get("emotionDirectness", 0.5),
            sentence_length_variance=d.get("sentenceLengthVariance", 0.3),
            concrete_detail_ratio=d.get("concreteDetailRatio", 0.4),
        )


# ── 통합 결과 ──────────────────────────────────────────────────

@dataclass
class StylometryResult:
    """stylometry 전체 파이프라인 산출물."""
    raw_features: RawFeatureProfile = field(default_factory=RawFeatureProfile)
    interpretation: InterpretationProfile = field(default_factory=InterpretationProfile)
    generation: GenerationProfile = field(default_factory=GenerationProfile)
    style_guide: str = ""
    source: str = "bio-only"
    version: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rawFeatures": self.raw_features.to_dict(),
            "interpretation": self.interpretation.to_dict(),
            "generation": self.generation.to_dict(),
            "styleGuide": self.style_guide,
            "source": self.source,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StylometryResult:
        return cls(
            raw_features=RawFeatureProfile.from_dict(d.get("rawFeatures", {})),
            interpretation=InterpretationProfile.from_dict(d.get("interpretation", {})),
            generation=GenerationProfile.from_dict(d.get("generation", {})),
            style_guide=d.get("styleGuide", ""),
            source=d.get("source", "bio-only"),
            version=d.get("version", 0),
        )

    def get_fingerprint_dict(self) -> dict[str, Any]:
        """기존 Firestore styleFingerprint 형식 호환 — 하위호환."""
        fp = self.interpretation.to_dict()
        fp["rawFeatures"] = self.raw_features.to_dict()
        return fp
