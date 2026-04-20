"""상투어 마스터 카탈로그.

프로젝트 전역에 흩어진 상투어 리스트를 하나의 dict 로 통합한다.
각 상투어에 카테고리 태그를 붙여 centroid 구축 · 승격 로직에서 활용.

소스:
  - agents/common/natural_tone.py      BLACKLIST_PATTERNS
  - agents/common/korean_morph.py      _CLICHE_PROSPECT_PHRASES 등
  - agents/core/prompt_guards.py       static_forbidden
  - services/stylometry/schemas.py     DEFAULT_AI_ALTERNATIVES keys
"""

from __future__ import annotations

from typing import Dict


def build_cliche_catalog() -> Dict[str, str]:
    """중복 제거된 {상투어: 카테고리} dict 를 반환한다.

    import 를 함수 안에서 수행해 모듈 로드 순서 문제를 방지한다.
    """
    catalog: Dict[str, str] = {}

    # ── 1. natural_tone.BLACKLIST_PATTERNS ──
    from agents.common.natural_tone import BLACKLIST_PATTERNS

    for category, phrases in BLACKLIST_PATTERNS.items():
        for phrase in phrases:
            p = str(phrase).strip()
            if p and p not in catalog:
                catalog[p] = f"natural_tone:{category}"

    # ── 2. korean_morph 상수 ──
    from agents.common.korean_morph import (
        _AI_ADJ_MM_FORMS,
        _CLICHE_PROSPECT_PHRASES,
        _HYPERBOLE_NOUNS,
        _NEGATIVE_PARALLEL_PHRASES,
        _TRANSLATIONESE_PHRASES,
        _VAGUE_SOURCE_NOUNS,
        _VERBOSE_PARTICLE_PHRASES,
    )

    _MORPH_SOURCES = {
        "morph:ai_adjective": _AI_ADJ_MM_FORMS,
        "morph:cliche_prospect": _CLICHE_PROSPECT_PHRASES,
        "morph:hyperbole": _HYPERBOLE_NOUNS,
        "morph:negative_parallel": _NEGATIVE_PARALLEL_PHRASES,
        "morph:translationese": _TRANSLATIONESE_PHRASES,
        "morph:vague_source": _VAGUE_SOURCE_NOUNS,
        "morph:verbose_particle": _VERBOSE_PARTICLE_PHRASES,
    }
    for category, phrases in _MORPH_SOURCES.items():
        for phrase in phrases:
            p = str(phrase).strip()
            if p and p not in catalog:
                catalog[p] = category

    # ── 3. prompt_guards.static_forbidden ──
    # static_forbidden 은 모듈 레벨 변수가 아니라 함수 내 로컬이므로
    # 여기서 직접 정의한다 (원본과 동기화 유지 필요).
    _STATIC_FORBIDDEN = [
        "진정성", "울림", "획기적으로", "명실상부한", "주목할 만한",
        "혁신적이고 체계적인", "도모하", "기하겠", "제고하",
        "인사이트", "임팩트", "시너지",
        "라고 할 수 있습니다", "것은 사실입니다",
        "풍부한 경험을 바탕으로", "궁극적인 목표",
        "새로운 역사를 써 내려", "열정과 헌신",
        "더 나은 미래", "더 나은 내일", "더 나은 방향",
        "단순한 구호", "단순한 구호에 그치지 않고", "단순한 숫자",
        "저의 이러한 진정성", "마음을 움직이고",
        "강력한 힘이 됩니다", "공감과 희망을 줍니다",
        "우선순위를 명확히 하고", "일정을 현실적으로 맞추겠습니다",
        "오늘 이 자리에서", "소홀히 하지 않았습니다",
    ]
    for phrase in _STATIC_FORBIDDEN:
        p = phrase.strip()
        if p and p not in catalog:
            catalog[p] = "prompt_guards:static_forbidden"

    # ── 4. stylometry schemas DEFAULT_AI_ALTERNATIVES keys ──
    from services.stylometry.schemas import DEFAULT_AI_ALTERNATIVES

    for raw_key in DEFAULT_AI_ALTERNATIVES:
        # "instead_of_혁신적인" → "혁신적인"
        cleaned = str(raw_key).replace("instead_of_", "").replace("_", " ").strip()
        if cleaned and cleaned not in catalog:
            catalog[cleaned] = "stylometry:ai_alternative"

    return catalog


# 모듈 로드 시 캐시 (Cold Start 1회만 빌드)
_CATALOG_CACHE: Dict[str, str] | None = None


def get_cliche_catalog() -> Dict[str, str]:
    """캐시된 카탈로그 반환."""
    global _CATALOG_CACHE
    if _CATALOG_CACHE is None:
        _CATALOG_CACHE = build_cliche_catalog()
    return _CATALOG_CACHE
