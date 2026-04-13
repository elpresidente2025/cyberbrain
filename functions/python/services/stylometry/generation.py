"""GenerationProfile 빌더 — 해석 + 피처 → 생성 제약조건.

fingerprint(Gemini 해석)와 rawFeatures(결정론적 통계)를 종합하여
원고 생성 시 사용할 구체적 제약조건을 산출한다.
"""

from __future__ import annotations

import logging
from typing import Any

from .models import GenerationProfile, RawFeatureProfile

logger = logging.getLogger(__name__)


def build_generation_profile(
    fingerprint: dict[str, Any],
    raw_features: RawFeatureProfile | None = None,
) -> GenerationProfile:
    """fingerprint + rawFeatures → GenerationProfile.

    fingerprint가 None이거나 비어 있으면 기본값 반환.
    """
    if not fingerprint:
        return GenerationProfile()

    tone = fingerprint.get("toneProfile") or {}
    sentences = fingerprint.get("sentencePatterns") or {}
    vocab = fingerprint.get("vocabularyProfile") or {}
    phrases = fingerprint.get("characteristicPhrases") or {}
    rhetoric = fingerprint.get("rhetoricalDevices") or {}
    ai_alts = fingerprint.get("aiAlternatives") or {}
    meta = fingerprint.get("analysisMetadata") or {}

    # ── 문장 길이 목표 ─────────────────────────────────────────
    avg_len = sentences.get("avgLength", 45)
    if raw_features and raw_features.sentences.count >= 3:
        # 결정론적 피처가 있으면 실측치 우선
        avg_len = raw_features.sentences.avg_length

    # 목표 범위: 평균 ± 40%
    margin = max(10, int(avg_len * 0.4))
    target_min = max(15, int(avg_len - margin))
    target_max = int(avg_len + margin)

    # ── 문장 길이 변동 목표 (CV) ───────────────────────────────
    target_cv = 0.3  # 기본
    if raw_features and raw_features.sentences.cv > 0:
        target_cv = round(raw_features.sentences.cv, 2)

    # ── 톤 수치 ────────────────────────────────────────────────
    formality = _clamp(tone.get("formality", 0.7))
    emotionality = _clamp(tone.get("emotionality", 0.3))
    directness = _clamp(tone.get("directness", 0.6))

    # 한국어 피처로 보정: 격식체 비율이 높으면 formality 상향
    if raw_features and raw_features.korean.formal_ending_ratio > 0.7:
        formality = max(formality, 0.8)
    elif raw_features and raw_features.korean.informal_ending_ratio > 0.5:
        formality = min(formality, 0.4)

    # ── 선호 종결 어미 ─────────────────────────────────────────
    preferred_endings: list[str] = []
    gemini_endings = sentences.get("endingPatterns") or []
    if isinstance(gemini_endings, list):
        preferred_endings.extend(gemini_endings)
    # 결정론적 피처에서 보충
    if raw_features and raw_features.korean.top_endings:
        for e in raw_features.korean.top_endings:
            if e not in preferred_endings:
                preferred_endings.append(e)
    preferred_endings = preferred_endings[:8]

    # ── 금지 패턴 ──────────────────────────────────────────────
    forbidden: list[str] = []
    # 구두점 엔트로피가 낮으면 다양한 구두점 사용을 권장하되 금지는 안 함
    # 물음표가 0이면 수사 의문문 지양
    if raw_features and raw_features.punctuation.question == 0:
        if not (rhetoric.get("usesRhetoricalQuestions") is True):
            forbidden.append("수사적 의문문")
    # 말줄임표가 0이면 지양
    if raw_features and raw_features.punctuation.ellipsis == 0:
        forbidden.append("말줄임표(...)")

    # ── 시그니처 표현 ──────────────────────────────────────────
    signatures: list[str] = []
    for key in ("signatures", "emphatics", "conclusions"):
        items = phrases.get(key) or []
        if isinstance(items, list):
            signatures.extend(items)
    signatures = signatures[:10]

    # ── 스타일 요약 ────────────────────────────────────────────
    style_summary = meta.get("dominantStyle", "")
    unique_features = meta.get("uniqueFeatures") or []
    if unique_features and isinstance(unique_features, list):
        style_summary += " / " + ", ".join(unique_features[:3])

    return GenerationProfile(
        target_sentence_length=(target_min, target_max),
        target_cv=target_cv,
        formality=formality,
        emotionality=emotionality,
        directness=directness,
        preferred_endings=preferred_endings,
        forbidden_patterns=forbidden,
        signature_phrases=signatures,
        ai_alternatives=ai_alts if isinstance(ai_alts, dict) else {},
        style_summary=style_summary.strip(" /"),
    )


def _clamp(value: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return 0.5
