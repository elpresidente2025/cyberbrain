from __future__ import annotations

import re
from typing import Any


HASHTAG_TOKEN_RE = re.compile(r"(?<!\w)#[0-9A-Za-z가-힣_]+")


def normalize_stance_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def looks_like_hashtag_bullet_line(value: Any) -> bool:
    normalized = normalize_stance_text(value)
    if not normalized:
        return False

    stripped = normalized.lstrip("*-• ").strip()
    if not stripped:
        return False

    hashtag_tokens = HASHTAG_TOKEN_RE.findall(stripped)
    if not hashtag_tokens:
        return False

    # 해시태그로 시작하는 목록형 라인은 본문 강제 문구가 아니라 메모/목록으로 본다.
    if stripped.startswith("#"):
        return True

    # 해시태그만 나열된 조각도 동일하게 제외한다.
    without_tags = HASHTAG_TOKEN_RE.sub(" ", stripped)
    compact = re.sub(r"[\s,;/|()\[\]{}·]+", "", without_tags)
    return not compact


__all__ = [
    "looks_like_hashtag_bullet_line",
    "normalize_stance_text",
]
