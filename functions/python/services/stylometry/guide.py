"""Style Guide 프롬프트 생성.

실제 구현은 ``services.posts.personalization._build_style_guide_prompt`` 에 있다.
이 모듈은 stylometry 패키지의 공개 진입점 역할만 한다.
"""

from __future__ import annotations

from typing import Any

from services.posts.personalization import _build_style_guide_prompt


def build_style_guide_prompt(
    fingerprint: dict[str, Any],
    *,
    compact: bool = False,
    source_text: str = "",
) -> str:
    """Style Fingerprint → 프롬프트 주입용 텍스트.

    JS ``buildStyleGuidePrompt(fingerprint, options)`` 과 동일한 계약.
    """
    return _build_style_guide_prompt(fingerprint, compact=compact, source_text=source_text)
