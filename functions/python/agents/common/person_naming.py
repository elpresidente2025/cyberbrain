"""공유 이름/역할 정규화 helper.

pipeline.py에 분산돼 있던 인물명·역할 라벨 helper를 모아 `agents/common/` 레이어로 승격한다.
H2 소제목 수리 모듈(`h2_repair.py`), SubheadingAgent, pipeline.py 모두 이 모듈을 import한다.

원 출처:
    handlers/generate_posts_pkg/pipeline.py 의 `_normalize_person_name`,
    `_clean_full_name_candidate`, `_is_same_speaker_name`, `_canonical_role_label`,
    `_extract_keyword_person_role`.
"""

from __future__ import annotations

import re
from typing import Any, Tuple

from .role_keyword_policy import (
    extract_role_keyword_parts,
    normalize_role_label as normalize_role_label_common,
)

__all__ = [
    "ROLE_TOKEN_PRIORITY",
    "normalize_person_name",
    "clean_full_name_candidate",
    "is_same_speaker_name",
    "canonical_role_label",
    "extract_keyword_person_role",
]


ROLE_TOKEN_PRIORITY: Tuple[Tuple[str, str], ...] = (
    ("국회의원", "국회의원"),
    ("의원", "국회의원"),
    ("당대표", "당대표"),
    ("원내대표", "원내대표"),
    ("대표", "대표"),
    ("위원장", "위원장"),
    ("장관", "장관"),
    ("구청장", "구청장"),
    ("군수", "군수"),
    ("교육감", "교육감"),
)


def normalize_person_name(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip()


def clean_full_name_candidate(raw_name: Any) -> str:
    text = str(raw_name or "").strip()
    if not text:
        return ""
    text = re.sub(r"[^가-힣A-Za-z\s]", "", text).strip()
    compact = normalize_person_name(text)
    if len(compact) < 2 or len(compact) > 12:
        return ""
    return compact


def is_same_speaker_name(candidate: Any, full_name: Any) -> bool:
    cand = normalize_person_name(candidate)
    full = normalize_person_name(full_name)
    if not cand or not full:
        return False
    return cand == full or cand in full or full in cand


def canonical_role_label(role: Any) -> str:
    return normalize_role_label_common(role)


def extract_keyword_person_role(keyword: Any) -> Tuple[str, str]:
    parts = extract_role_keyword_parts(keyword)
    name = clean_full_name_candidate(parts.get("name"))
    role_label = canonical_role_label(parts.get("role") or parts.get("roleCanonical") or "")
    if not role_label:
        normalized = re.sub(r"\s+", " ", str(keyword or "")).strip()
        for token, mapped in ROLE_TOKEN_PRIORITY:
            if token in normalized:
                role_label = mapped
                break
    return name, role_label
