"""validation ?? ?? ??."""

from __future__ import annotations

import re

def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", text or "")).strip()

__all__ = ["_strip_html"]
