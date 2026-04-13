"""Stylometry 패키지 — 문체 분석/재학습 통합 모듈.

Public API:
    extract_style_fingerprint   — Gemini 기반 fingerprint 추출
    validate_style_fingerprint  — fingerprint 정규화/검증
    build_style_guide_prompt    — fingerprint → 프롬프트 텍스트
    analyze_text_statistics     — LLM 없는 통계 분석 (legacy 호환)
    extract_raw_features        — 결정론적 피처 엔진 (고도화)
    build_diary_augmented_corpus— 다이어리+바이오 코퍼스 구성
    refresh_user_style_fingerprint — 코퍼스 → Firestore 갱신
    process_bio_style_update    — Firestore trigger 진입점
    build_consolidated_bio_content — bio entries → 단일 텍스트
"""

from __future__ import annotations

from .features import extract_raw_features
from .fingerprint import validate_style_fingerprint
from .generation import build_generation_profile
from .guide import build_style_guide_prompt
from .interpret import analyze_text_statistics, extract_style_fingerprint
from .models import (
    GenerationProfile,
    InterpretationProfile,
    KoreanFeatures,
    LexicalFeatures,
    PunctuationFeatures,
    RawFeatureProfile,
    SentenceFeatures,
    StylometryResult,
)
from .refresh import (
    MAX_DIARY_ENTRIES,
    MIN_CORPUS_LENGTH,
    build_consolidated_bio_content,
    build_diary_augmented_corpus,
    process_bio_style_update,
    refresh_user_style_fingerprint,
)
from .schemas import MIN_ANALYZABLE_CHARS

__all__ = [
    # 상수
    "MIN_ANALYZABLE_CHARS",
    "MAX_DIARY_ENTRIES",
    "MIN_CORPUS_LENGTH",
    # 데이터 모델
    "SentenceFeatures",
    "LexicalFeatures",
    "PunctuationFeatures",
    "KoreanFeatures",
    "RawFeatureProfile",
    "InterpretationProfile",
    "GenerationProfile",
    "StylometryResult",
    # 피처 엔진
    "extract_raw_features",
    "analyze_text_statistics",
    "build_generation_profile",
    # Gemini 파이프라인
    "extract_style_fingerprint",
    "validate_style_fingerprint",
    "build_style_guide_prompt",
    # 코퍼스 + Firestore
    "build_consolidated_bio_content",
    "build_diary_augmented_corpus",
    "refresh_user_style_fingerprint",
    "process_bio_style_update",
]
