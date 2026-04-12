"""Style Fingerprint 유효성 검사 및 정규화.

JS `stylometry.js:validateStyleFingerprint` 1:1 포팅.
LLM 해석 결과 + 통계값을 합쳐 정규화된 fingerprint 객체를 반환한다.
"""

from __future__ import annotations

from typing import Any

from .schemas import DEFAULT_AI_ALTERNATIVES


# ── 헬퍼 ─────────────────────────────────────────────────────

def _ensure_array(value: Any, max_length: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()][:max_length]


def _clamp(value: Any, min_val: float, max_val: float) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return (min_val + max_val) / 2
    return max(min_val, min(max_val, n))


def _ensure_enum(value: Any, allowed: tuple[str, ...], default: str) -> str:
    v = str(value or "").strip()
    return v if v in allowed else default


# ── 메인 검증 ────────────────────────────��───────────────────

def validate_style_fingerprint(
    fingerprint: dict[str, Any],
    source_length: int,
    text_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """LLM 해석 + 통계값을 합쳐 정규화된 fingerprint를 반환한다.

    JS ``validateStyleFingerprint`` 과 동일한 top-level shape.
    """
    stats = text_stats or {}
    sl = stats.get("sentenceLength") or {}
    punc = stats.get("punctuation") or {}
    comp = stats.get("complexity") or {}

    actual_avg = sl.get("avg") or (fingerprint.get("sentencePatterns") or {}).get("avgLength") or 45
    actual_complexity = comp.get("level") or (fingerprint.get("sentencePatterns") or {}).get("clauseComplexity") or "medium"

    fp = fingerprint  # alias

    validated: dict[str, Any] = {
        "characteristicPhrases": {
            "greetings": _ensure_array((fp.get("characteristicPhrases") or {}).get("greetings"), 3),
            "transitions": _ensure_array((fp.get("characteristicPhrases") or {}).get("transitions"), 5),
            "conclusions": _ensure_array((fp.get("characteristicPhrases") or {}).get("conclusions"), 3),
            "emphatics": _ensure_array((fp.get("characteristicPhrases") or {}).get("emphatics"), 5),
            "signatures": _ensure_array((fp.get("characteristicPhrases") or {}).get("signatures"), 5),
        },
        "sentencePatterns": {
            "avgLength": round(_clamp(actual_avg, 15, 100)),
            "minLength": int(sl.get("min") or 10),
            "maxLength": int(sl.get("max") or 100),
            "lengthRange": f"{sl['min']}~{sl['max']}자" if sl.get("min") is not None else None,
            "distribution": sl.get("distribution"),
            "preferredStarters": _ensure_array((fp.get("sentencePatterns") or {}).get("preferredStarters"), 5),
            "clauseComplexity": _ensure_enum(actual_complexity, ("simple", "medium", "complex"), "medium"),
            "listingStyle": _ensure_enum(
                (fp.get("sentencePatterns") or {}).get("listingStyle"),
                ("numbered", "bullet", "prose"),
                "prose",
            ),
            "endingPatterns": _ensure_array((fp.get("sentencePatterns") or {}).get("endingPatterns"), 4),
        },
        "punctuationProfile": (
            {
                "commasPerSentence": punc.get("commasPerSentence", 0),
                "totalCommas": punc.get("comma", 0),
                "questionMarks": punc.get("question", 0),
                "exclamationMarks": punc.get("exclamation", 0),
                "commaGuidance": (
                    "콤마 적게 사용 (문장당 1회 미만)"
                    if punc.get("commasPerSentence", 0) < 1
                    else "콤마 보통 사용 (문장당 1-2회)"
                    if punc.get("commasPerSentence", 0) < 2
                    else "콤마 자주 사용 (문장당 2회 이상)"
                ),
            }
            if stats
            else None
        ),
        "vocabularyProfile": {
            "frequentWords": _ensure_array((fp.get("vocabularyProfile") or {}).get("frequentWords"), 10),
            "preferredVerbs": _ensure_array((fp.get("vocabularyProfile") or {}).get("preferredVerbs"), 5),
            "preferredAdjectives": _ensure_array((fp.get("vocabularyProfile") or {}).get("preferredAdjectives"), 4),
            "technicalLevel": _ensure_enum(
                (fp.get("vocabularyProfile") or {}).get("technicalLevel"),
                ("accessible", "moderate", "technical"),
                "accessible",
            ),
            "localTerms": _ensure_array((fp.get("vocabularyProfile") or {}).get("localTerms"), 10),
        },
        "toneProfile": {
            "formality": _clamp((fp.get("toneProfile") or {}).get("formality", 0.5), 0, 1),
            "emotionality": _clamp((fp.get("toneProfile") or {}).get("emotionality", 0.5), 0, 1),
            "directness": _clamp((fp.get("toneProfile") or {}).get("directness", 0.5), 0, 1),
            "optimism": _clamp((fp.get("toneProfile") or {}).get("optimism", 0.5), 0, 1),
            "toneDescription": str((fp.get("toneProfile") or {}).get("toneDescription") or "중립적인 어조").strip(),
        },
        "rhetoricalDevices": {
            "usesRepetition": bool((fp.get("rhetoricalDevices") or {}).get("usesRepetition")),
            "usesRhetoricalQuestions": bool((fp.get("rhetoricalDevices") or {}).get("usesRhetoricalQuestions")),
            "usesMetaphors": bool((fp.get("rhetoricalDevices") or {}).get("usesMetaphors")),
            "usesEnumeration": bool((fp.get("rhetoricalDevices") or {}).get("usesEnumeration")),
            "examplePatterns": _ensure_array((fp.get("rhetoricalDevices") or {}).get("examplePatterns"), 5),
        },
        "aiAlternatives": {
            key: str((fp.get("aiAlternatives") or {}).get(key) or default).strip()
            for key, default in DEFAULT_AI_ALTERNATIVES.items()
        },
        "analysisMetadata": {
            "confidence": _clamp((fp.get("analysisMetadata") or {}).get("confidence", 0.7), 0, 1),
            "dominantStyle": str((fp.get("analysisMetadata") or {}).get("dominantStyle") or "표준적인 정치 문체").strip(),
            "uniqueFeatures": _ensure_array((fp.get("analysisMetadata") or {}).get("uniqueFeatures"), 3),
            "sourceLength": int(source_length or 0),
            "version": "3.0-python",
            "hasStatistics": bool(stats),
        },
        "textStatistics": stats or None,
    }

    # 신뢰도 보정: 텍스트 길이
    conf = validated["analysisMetadata"]["confidence"]
    if source_length < 200:
        conf = min(conf, 0.6)
    elif source_length < 500:
        conf = min(conf, 0.75)
    if stats:
        conf = min(conf + 0.1, 1.0)
    validated["analysisMetadata"]["confidence"] = round(conf, 3)

    return validated
