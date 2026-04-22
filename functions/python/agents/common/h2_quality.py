"""Lightweight H2 quality helpers shared by generation and validation."""

from __future__ import annotations

import re
from typing import Any, Dict

from . import korean_morph


def normalize_h2_surface(text: str) -> str:
    plain = re.sub(r"<[^>]*>", " ", str(text or ""))
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain


def compact_h2_surface(text: str) -> str:
    plain = normalize_h2_surface(text)
    return re.sub(r"[\s,.;:·!?\"'“”‘’()\[\]{}<>]+", "", plain)


def is_h2_prefix_fragment(text: str) -> bool:
    """Detect headings whose leading source word was cut off.

    Example: "형 {policy_name}, ..." where the intended anchor was
    "{region_type} {policy_name}".
    """
    plain = normalize_h2_surface(text)
    if not plain:
        return False
    if re.match(r"^(?:형|식|용|성)\s+", plain):
        return True
    compact = compact_h2_surface(plain)
    if compact.startswith("형") and not compact.startswith(("형평", "형식", "형태", "형사", "형성", "형편")):
        return True
    if compact.startswith("식") and not compact.startswith(("식품", "식당", "식물", "식민", "식별")):
        return True
    if compact.startswith("용") and not compact.startswith(("용역", "용도", "용산", "용인", "용기")):
        return True
    if compact.startswith("성") and not compact.startswith(("성남", "성장", "성과", "성공", "성숙")):
        return True
    return False


def h2_semantic_family_key(text: str) -> str:
    """Return a key for generic H2 templates that must not repeat.

    This intentionally targets low-information template families, not topic
    nouns. Two sections can both mention the same policy, but they should not
    both be titled as the same generic institutionalization promise.
    """
    compact = compact_h2_surface(text)
    if not compact:
        return ""

    if "주목" in compact and ("가능성" in compact or "이유" in compact):
        return "possibility_focus"

    if any(token in compact for token in ("제도기반", "제도적기반", "법적근거", "법적기반")):
        return "institutional_basis"

    if "조례" in compact and any(
        token in compact
        for token in ("뒷받침", "제정", "개정", "마련", "추진", "세우", "확립")
    ):
        return "institutional_basis"

    if any(token in compact for token in ("실행계획", "실행방안", "추진계획")):
        return "execution_plan"

    return ""


_DEICTIC_ROOTS = frozenset({"이", "그", "저", "이것", "그것", "저것"})
_CONTEXT_LOCATION_ROOTS = frozenset({"앞", "위", "상기"})
_PUNCT_TAGS = frozenset({"SF", "SP", "SS", "SW", "SO", "SE"})


def _first_sentence(text: str) -> str:
    plain = normalize_h2_surface(text)
    if not plain:
        return ""
    match = re.match(r"[^.!?。]+[.!?。]?", plain)
    return normalize_h2_surface(match.group(0) if match else plain)


def _first_eojeol_surface(sentence: str) -> str:
    match = re.match(r"\S+", str(sentence or "").strip())
    return match.group(0) if match else ""


def _fallback_dependent_opening(sentence: str) -> Dict[str, Any]:
    """Regex fallback used only when Kiwi is unavailable."""
    surface = _first_eojeol_surface(sentence)
    if not surface:
        return {"detected": False}
    compact = compact_h2_surface(surface)
    if re.match(r"^(?:이|그|저)(?:는|것|러한|런|와|를|로|에|에서|대로)", compact):
        return {
            "detected": True,
            "reason": "deictic_reference_opening",
            "surface": surface,
            "mode": "regex_fallback",
        }
    if re.match(r"^(?:또한|아울러|나아가|더불어|한편)$", compact):
        return {
            "detected": True,
            "reason": "connective_adverb_opening",
            "surface": surface,
            "mode": "regex_fallback",
        }
    if re.match(r"^(?:앞서|위에서|상기)", compact):
        return {
            "detected": True,
            "reason": "contextual_reference_opening",
            "surface": surface,
            "mode": "regex_fallback",
        }
    return {"detected": False}


def detect_dependent_section_opening(text: str) -> Dict[str, Any]:
    """Detect whether a section-opening sentence depends on previous context.

    The primary path is Kiwi-based: we inspect the first eojeol's morphology
    rather than maintaining a long banned-surface list. Regex is retained only
    as a safety fallback for environments where Kiwi cannot initialize.
    """
    sentence = _first_sentence(text)
    if not sentence:
        return {"detected": False}

    surface = _first_eojeol_surface(sentence)
    if not surface:
        return {"detected": False}

    tokens = korean_morph.tokenize(sentence)
    if tokens is None:
        return _fallback_dependent_opening(sentence)

    surface_len = len(surface)
    first_eojeol_tokens = [
        tok
        for tok in tokens
        if getattr(tok, "start", 999999) < surface_len
        and getattr(tok, "tag", "") not in _PUNCT_TAGS
    ]
    if not first_eojeol_tokens:
        return {"detected": False}

    first = first_eojeol_tokens[0]
    first_form = str(getattr(first, "form", "") or "")
    first_tag = str(getattr(first, "tag", "") or "")
    tag_sequence = [str(getattr(tok, "tag", "") or "") for tok in first_eojeol_tokens]
    forms = [str(getattr(tok, "form", "") or "") for tok in first_eojeol_tokens]

    if first_tag in {"MAJ"}:
        return {
            "detected": True,
            "reason": "connective_adverb_opening",
            "surface": surface,
            "mode": "kiwi",
            "tags": tag_sequence,
        }

    if first_tag == "MAG" and not any(tag.startswith("NN") or tag == "NP" for tag in tag_sequence):
        return {
            "detected": True,
            "reason": "connective_adverb_opening",
            "surface": surface,
            "mode": "kiwi",
            "tags": tag_sequence,
        }

    if first_form in _DEICTIC_ROOTS and first_tag in {"NP", "MM"}:
        reason = "deictic_reference_opening"
        if any(tag.startswith("J") for tag in tag_sequence[1:]):
            reason = "contextual_reference_opening"
        return {
            "detected": True,
            "reason": reason,
            "surface": surface,
            "mode": "kiwi",
            "tags": tag_sequence,
        }

    if first_form in _CONTEXT_LOCATION_ROOTS and any(tag == "JKB" for tag in tag_sequence[1:]):
        return {
            "detected": True,
            "reason": "contextual_reference_opening",
            "surface": surface,
            "mode": "kiwi",
            "tags": tag_sequence,
        }

    if forms[:2] and forms[0] in _DEICTIC_ROOTS and any(tag.startswith("J") for tag in tag_sequence[1:]):
        return {
            "detected": True,
            "reason": "contextual_reference_opening",
            "surface": surface,
            "mode": "kiwi",
            "tags": tag_sequence,
        }

    return {"detected": False}
