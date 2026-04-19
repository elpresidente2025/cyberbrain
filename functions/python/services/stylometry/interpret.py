"""Gemini 기반 문체 해석 + 통계 분석 + fingerprint 조립.

JS `stylometry.js:extractStyleFingerprint` + `analyzeTextStatistics` 포팅.
단일 public 함수 `extract_style_fingerprint` 가 전체 파이프라인을 수행한다.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agents.common.gemini_client import generate_json_async

from .features import extract_raw_features
from .fingerprint import validate_style_fingerprint
from .models import RawFeatureProfile
from .schemas import (
    CONJUNCTIONS,
    LEGACY_REQUIRED_KEYS,
    MAX_INTERPRET_TEXT_CHARS,
    MIN_ANALYZABLE_CHARS,
    MIN_STATISTICAL_CHARS,
)

logger = logging.getLogger(__name__)


# ── 통계 분석 (LLM 없이) ────────────────────────────────────

def analyze_text_statistics(text: str) -> dict[str, Any] | None:
    """JS ``analyzeTextStatistics`` 과 동일한 shape 반환."""
    clean = (text or "").strip()
    if len(clean) < MIN_STATISTICAL_CHARS:
        return None

    sentences = [s.strip() for s in re.split(r"[.!?]+", clean) if len(s.strip()) > 5]
    if len(sentences) < 3:
        return None

    lengths = [len(s) for s in sentences]
    avg = round(sum(lengths) / len(lengths))
    mn, mx = min(lengths), max(lengths)
    variance = sum((l - avg) ** 2 for l in lengths) / len(lengths)
    std_dev = round(variance ** 0.5)

    comma = clean.count(",")
    period = clean.count(".")
    question = clean.count("?")
    exclamation = clean.count("!")
    colon = clean.count(":")
    semicolon = clean.count(";")
    ellipsis = clean.count("...") + clean.count("…")

    commas_per_sentence = round(comma / len(sentences), 1) if sentences else 0

    conj_count = sum(len(re.findall(re.escape(c), clean)) for c in CONJUNCTIONS)
    complexity_score = round((comma + conj_count) / len(sentences), 1)
    if complexity_score < 1:
        level = "simple"
    elif complexity_score < 2.5:
        level = "medium"
    else:
        level = "complex"

    short = sum(1 for l in lengths if l < 30)
    medium = sum(1 for l in lengths if 30 <= l <= 60)
    long = sum(1 for l in lengths if l > 60)
    n = len(sentences)

    return {
        "sentenceCount": n,
        "sentenceLength": {
            "avg": avg,
            "min": mn,
            "max": mx,
            "stdDev": std_dev,
            "distribution": {
                "short": round(short / n * 100),
                "medium": round(medium / n * 100),
                "long": round(long / n * 100),
            },
        },
        "punctuation": {
            "comma": comma,
            "period": period,
            "question": question,
            "exclamation": exclamation,
            "colon": colon,
            "semicolon": semicolon,
            "ellipsis": ellipsis,
            "commasPerSentence": commas_per_sentence,
            "totalPunctuation": comma + period + question + exclamation + colon + semicolon + ellipsis,
        },
        "complexity": {
            "score": complexity_score,
            "level": level,
            "conjunctionsCount": conj_count,
        },
        "summary": (
            f"문장 평균 {avg}자({mn}~{mx}자), "
            f"콤마 {commas_per_sentence}회/문장, "
            f"복잡도 {level}"
        ),
    }


# ── Gemini 프롬프트 (JS 원본과 동일) ────────────────────────

def _format_feature_context(features: RawFeatureProfile | None) -> str:
    """rawFeatures를 Gemini 프롬프트에 주입할 참고 블록으로 포맷."""
    if features is None:
        return ""
    s = features.sentences
    lx = features.lexical
    p = features.punctuation
    k = features.korean
    return f"""
[정량 분석 결과 — 아래 수치를 해석의 근거로 활용하세요]
- 문장 수: {s.count}개, 평균 길이: {s.avg_length}자 (표준편차 {s.std_dev}, CV {s.cv})
- 문장 길이 분포: 짧음({s.short_ratio:.0%}) / 보통({s.medium_ratio:.0%}) / 긴({s.long_ratio:.0%})
- 어휘 다양성: TTR {lx.ttr:.3f}, 단일 출현 어휘 비율 {lx.hapax_ratio:.3f}
- 구두점 엔트로피: {p.entropy:.2f} (높을수록 다양한 구두점 사용)
- 문장당 쉼표: {p.commas_per_sentence}회, 물음표 {p.question}개, 말줄임 {p.ellipsis}개
- 격식체 비율: {k.formal_ending_ratio:.0%}, 비격식체 비율: {k.informal_ending_ratio:.0%}
- 종결 어미 다양성: {k.ending_diversity:.2f}, 상위 어미: {', '.join(k.top_endings[:5]) or '정보 없음'}
- 접속사 밀도: 문장당 {k.conjunction_density:.1f}회
- 감정 직접 명명 비율: {k.emotion_directness:.0%} (높을수록 감정을 직접 이름 붙임)
- 구체 디테일 포함 문장: {k.concrete_detail_ratio:.0%} (숫자·날짜·지명·법령명 등)
- 복잡도: {features.complexity_level} ({features.complexity_score}점)
"""


def _build_extract_prompt(
    bio_content: str,
    *,
    user_name: str = "",
    region: str = "",
    features: RawFeatureProfile | None = None,
) -> str:
    source = bio_content[:MAX_INTERPRET_TEXT_CHARS]
    feature_block = _format_feature_context(features)
    return f"""당신은 정치 텍스트 전문 언어학자입니다. 다음 정치인의 자기소개 텍스트를 stylometry(문체 분석) 관점에서 분석하여 고유한 "Style Fingerprint"를 추출하세요.

[분석 대상 텍스트]
\"\"\"
{source}
\"\"\"

{f"[참고] 작성자: {user_name}" if user_name else ""}
{f"[참고] 지역: {region}" if region else ""}
{feature_block}
다음 JSON 형식으로 정확히 응답하세요. 텍스트에서 실제로 발견되는 패턴만 추출하세요.

{{
  "characteristicPhrases": {{
    "greetings": ["인사 표현 1-3개, 없으면 빈 배열"],
    "transitions": ["전환 표현 2-5개"],
    "conclusions": ["마무리 표현 1-3개"],
    "emphatics": ["강조 표현 2-5개"],
    "signatures": ["복수 텍스트에서 반복 관찰되는 구조적 패턴 1-5개 (은유 체계, 문장 구조 습관, 구성 방식 등). 1회만 등장한 인상적 표현은 시그니처가 아님. 매 글 고정 반복되는 브랜딩 슬로건도 제외"]
  }},

  "sentencePatterns": {{
    "avgLength": 평균_문장_길이_숫자,
    "preferredStarters": ["선호하는 문장 시작어 3-5개"],
    "clauseComplexity": "simple 또는 medium 또는 complex",
    "listingStyle": "numbered 또는 bullet 또는 prose",
    "endingPatterns": ["자주 쓰는 문장 종결 패턴 2-4개"]
  }},

  "vocabularyProfile": {{
    "frequentWords": ["고빈도 명사/동사 5-10개"],
    "preferredVerbs": ["선호 동사 3-5개"],
    "preferredAdjectives": ["선호 형용사 2-4개"],
    "technicalLevel": "accessible 또는 moderate 또는 technical",
    "localTerms": ["지역 관련 용어 (있으면)"]
  }},

  "toneProfile": {{
    "formality": 0.0-1.0 사이 숫자 (0:친근 ~ 1:격식),
    "emotionality": 0.0-1.0 사이 숫자 (0:논리적 ~ 1:감성적),
    "directness": 0.0-1.0 사이 숫자 (0:완곡 ~ 1:직설),
    "optimism": 0.0-1.0 사이 숫자 (0:비판적 ~ 1:희망적),
    "emotionDirectness": 0.0-1.0 사이 숫자 (0:감정을 상황묘사로 간접 전달(show) ~ 1:감정을 직접 명명(tell). 예: "누구 엄마가 안 보이는 날"=0.1, "안타깝게도 환자가 사망했습니다"=0.9),
    "toneDescription": "전체적인 어조를 한 문장으로 설명"
  }},

  "rhetoricalDevices": {{
    "usesRepetition": true 또는 false,
    "usesRhetoricalQuestions": true 또는 false,
    "usesMetaphors": true 또는 false,
    "usesEnumeration": true 또는 false,
    "examplePatterns": ["실제 사용된 수사적 패턴 2-5개"]
  }},

  "aiAlternatives": {{
    "instead_of_평범한_이웃": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_함께_힘을_모아": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_더_나은_내일": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_밝은_미래": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_획기적인": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_혁신적인": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_체계적인": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_종합적인": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_지속적인": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_극대화": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_도모": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_기여": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_도약": "이 사람이 실제로 쓸 대체 표현"
  }},

  "analysisMetadata": {{
    "confidence": 0.0-1.0 사이 숫자 (분석 신뢰도),
    "dominantStyle": "이 사람의 문체를 한 마디로 정의",
    "uniqueFeatures": ["다른 정치인과 구별되는 독특한 특징 2-3개"]
  }}
}}

분석 지침:
1. 텍스트에서 실제로 발견되는 패턴만 추출하세요. 추측하지 마세요.
2. 배열이 비어있어도 괜찮습니다. 억지로 채우지 마세요.
3. 수치는 텍스트 분석을 기반으로 정확하게 계산하세요.
4. aiAlternatives는 AI 상투어를 이 사람의 실제 어휘로 대체할 표현입니다. 텍스트에서 이 사람이 실제로 사용한 형용사·동사·명사를 찾아 매핑하세요. 텍스트에 근거가 없으면 빈 문자열로 두세요.
5. JSON만 반환하세요. 다른 설명은 하지 마세요."""


# ── 공개 API ─────────────────────────────────────────────────

async def extract_style_fingerprint(
    bio_content: str,
    *,
    user_name: str = "",
    region: str = "",
) -> dict[str, Any] | None:
    """Bio/코퍼스 텍스트에서 Style Fingerprint를 추출한다.

    Returns validated fingerprint dict, or ``None`` if text is too short.
    JS ``extractStyleFingerprint`` 과 동일한 계약.
    """
    text = (bio_content or "").strip()
    if len(text) < MIN_ANALYZABLE_CHARS:
        logger.warning("텍스트가 너무 짧아 stylometry 분석 불가 (최소 %d자, 현재 %d자)", MIN_ANALYZABLE_CHARS, len(text))
        return None

    # 결정론적 피처 (LLM 없음)
    raw_features: RawFeatureProfile | None = extract_raw_features(text)
    text_stats = analyze_text_statistics(text)

    prompt = _build_extract_prompt(
        text, user_name=user_name, region=region, features=raw_features,
    )

    logger.info("[Stylometry] 분석 시작 (텍스트 길이: %d자)", len(text))

    raw = await generate_json_async(
        prompt,
        temperature=0.2,
        required_keys=list(LEGACY_REQUIRED_KEYS),
        max_output_tokens=4096,
    )

    validated = validate_style_fingerprint(raw, len(text), text_stats, source_text=text)

    # 결정론적 피처를 fingerprint에 첨부
    if raw_features is not None:
        validated["rawFeatures"] = raw_features.to_dict()

    logger.info("[Stylometry] 분석 완료 (신뢰도: %.2f)", validated["analysisMetadata"]["confidence"])
    return validated
