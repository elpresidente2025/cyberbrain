"""Stylometry 재학습: 다이어리 코퍼스 구성 + Firestore 저장.

JS ``style-refresh.js`` 의 Python 포팅.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from firebase_admin import firestore

from .generation import build_generation_profile
from .guide import build_style_guide_prompt
from .interpret import extract_style_fingerprint
from .models import RawFeatureProfile
from .schemas import MAX_DIARY_ENTRIES, MIN_CORPUS_LENGTH

logger = logging.getLogger(__name__)


# ── 말미 반복 문구(슬로건 후보) 감지 ───────────────────────────

_ENTRY_SEPARATOR_RE = re.compile(r"\n-{3,}\n|\n={4,}\n|\[Facebook 입장문\]")

# 말미에서 추출할 최대 줄 수
_TAIL_LINES = 3


def _extract_tail(entry_text: str) -> list[str]:
    """엔트리 텍스트의 마지막 비어있지 않은 줄들을 추출한다."""
    lines = [
        line.strip() for line in entry_text.strip().splitlines()
        if line.strip()
    ]
    return lines[-_TAIL_LINES:] if lines else []


def detect_slogan_candidate(
    source_text: str,
    *,
    min_entries: int = 2,
) -> str | None:
    """코퍼스에서 2개 이상의 입장문 말미에 verbatim 반복되는 문구를 찾는다.

    발견되면 해당 문구를 반환, 없으면 None.
    """
    if not source_text:
        return None

    entries = _ENTRY_SEPARATOR_RE.split(source_text)
    entries = [e.strip() for e in entries if e.strip()]

    if len(entries) < min_entries:
        return None

    # 각 엔트리 말미 줄들을 수집
    tail_counter: Counter[str] = Counter()
    for entry in entries:
        tail_lines = _extract_tail(entry)
        # 같은 엔트리 내 중복은 1회로 카운트 (set)
        for line in set(tail_lines):
            tail_counter[line] += 1

    # min_entries 이상 반복되는 말미 문구 중 가장 빈도 높은 것
    candidates = [
        (phrase, count)
        for phrase, count in tail_counter.items()
        if count >= min_entries
    ]

    if not candidates:
        return None

    # 빈도 높은 순, 동률이면 긴 문구 우선 (짧은 인사말보다 슬로건이 길 가능성)
    candidates.sort(key=lambda x: (-x[1], -len(x[0])))
    return candidates[0][0]


# ── 헬퍼 ─────────────────────────────────────────────────────

def _format_entry_date(created_at: Any) -> str:
    if not created_at:
        return ""
    try:
        if hasattr(created_at, "isoformat"):
            return created_at.isoformat()[:10]
        return str(created_at)[:10]
    except Exception:
        return ""


def _build_bio_block(bio_data: dict[str, Any]) -> str:
    entries = bio_data.get("entries") if isinstance(bio_data.get("entries"), list) else []
    chunks: list[str] = []
    for entry in entries:
        content = str(entry.get("content") or "").strip() if isinstance(entry, dict) else ""
        if not content:
            continue
        entry_type = str(entry.get("type") or "content").strip().upper()
        title = str(entry.get("title") or "").strip()
        chunks.append(f"[{entry_type}]{f' {title}' if title else ''}\n{content}")

    if not chunks:
        return str(bio_data.get("content") or "").strip()
    return "\n\n".join(chunks)


def build_consolidated_bio_content(bio_data: dict[str, Any]) -> str:
    """admin-users 호환: bio entries → 단일 문자열."""
    entries = bio_data.get("entries") if isinstance(bio_data.get("entries"), list) else []
    parts: list[str] = []
    for entry in entries:
        content = str(entry.get("content") or "").strip() if isinstance(entry, dict) else ""
        if not content:
            continue
        entry_type = str(entry.get("type") or "content").strip().upper()
        title = str(entry.get("title") or "").strip()
        parts.append(f"\n[{entry_type}] {title}: {content}\n")

    consolidated = "".join(parts).strip()
    if not consolidated:
        consolidated = str(bio_data.get("content") or "").strip()
    return consolidated


# ── 코퍼스 구성 ──────────────────────────────────────────────

async def build_diary_augmented_corpus(
    uid: str,
    bio_data: dict[str, Any],
    *,
    db: Any | None = None,
) -> dict[str, Any]:
    """사용자별 stylometry 학습용 코퍼스 구성.

    다이어리 우선, 바이오 보조. JS ``buildDiaryAugmentedCorpus`` 동일 계약.
    Returns ``{ text, source, stats }``.
    """
    if db is None:
        db = firestore.client()

    stats = {"bioChars": 0, "diaryEntryCount": 0, "diaryChars": 0, "totalChars": 0}

    bio_block = _build_bio_block(bio_data)
    stats["bioChars"] = len(bio_block)

    diary_parts: list[str] = []
    try:
        diary_ref = (
            db.collection("bios")
            .document(uid)
            .collection("facebook_entries")
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .limit(MAX_DIARY_ENTRIES)
        )
        diary_docs = diary_ref.get()
        for doc in diary_docs:
            entry = doc.to_dict() or {}
            text = str(entry.get("text") or "").strip()
            if not text:
                continue
            date_str = _format_entry_date(entry.get("createdAt"))
            category = str(entry.get("category") or "").strip()
            header_parts = ["[Facebook 입장문]"]
            if date_str:
                header_parts.append(date_str)
            if category:
                header_parts.append(f"({category})")
            diary_parts.append(f"{' '.join(header_parts)}\n{text}")
            stats["diaryChars"] += len(text)
        stats["diaryEntryCount"] = len(diary_parts)
    except Exception as exc:
        logger.warning("[StyleRefresh] facebook_entries 조회 실패 (%s): %s", uid, exc)

    sections: list[str] = []
    if diary_parts:
        sections.append(f"[사용자 실제 입장문 모음 — 최신순]\n\n" + "\n\n---\n\n".join(diary_parts))
    if bio_block:
        sections.append(f"[사용자 바이오 — 보조 자료]\n\n{bio_block}")

    corpus_text = "\n\n====\n\n".join(sections)
    stats["totalChars"] = len(corpus_text)

    if diary_parts and bio_block:
        source = "diary-augmented"
    elif diary_parts:
        source = "diary-only"
    elif bio_block:
        source = "bio-only"
    else:
        source = "empty"

    return {"text": corpus_text, "source": source, "stats": stats}


# ── Firestore 갱신 ───────────────────────────────────────────

async def _record_refresh_error(uid: str, message: str, *, db: Any | None = None) -> None:
    try:
        if db is None:
            db = firestore.client()
        db.collection("bios").document(uid).set(
            {
                "styleRefreshError": {
                    "message": str(message or "unknown")[:500],
                    "at": firestore.SERVER_TIMESTAMP,
                },
            },
            merge=True,
        )
    except Exception as exc:
        logger.warning("[StyleRefresh] error 기록 실패 (%s): %s", uid, exc)


async def refresh_user_style_fingerprint(
    uid: str,
    *,
    corpus_text: str = "",
    source: str = "bio-only",
    corpus_stats: dict[str, Any] | None = None,
    user_meta: dict[str, str] | None = None,
    slogan: str = "",
    db: Any | None = None,
) -> dict[str, Any]:
    """코퍼스로 stylometry 재계산 → Firestore 갱신.

    JS ``refreshUserStyleFingerprint`` 동일 계약.
    Returns ``{ ok, version?, reason? }``.
    """
    if db is None:
        db = firestore.client()
    meta = user_meta or {}

    if not uid:
        return {"ok": False, "reason": "missing-uid"}
    if not corpus_text or len(corpus_text) < MIN_CORPUS_LENGTH:
        await _record_refresh_error(uid, f"corpus too short ({len(corpus_text)} chars)", db=db)
        return {"ok": False, "reason": "corpus-too-short"}

    try:
        fingerprint = await extract_style_fingerprint(
            corpus_text,
            user_name=str(meta.get("userName") or "").strip(),
            region=str(meta.get("region") or "").strip(),
        )

        if not fingerprint:
            await _record_refresh_error(uid, "extract_style_fingerprint returned None", db=db)
            return {"ok": False, "reason": "empty-result"}

        style_guide = build_style_guide_prompt(fingerprint, source_text=corpus_text)

        # rawFeatures → GenerationProfile 빌드
        raw_feat_dict = fingerprint.get("rawFeatures") or {}
        raw_feat = RawFeatureProfile.from_dict(raw_feat_dict) if raw_feat_dict else None
        gen_profile = build_generation_profile(
            fingerprint, raw_feat,
            source_text=corpus_text,
            slogan=slogan,
        )

        # ── 말미 반복 문구 감지 (슬로건 후보) ──────────────────
        detected = detect_slogan_candidate(corpus_text)
        detected_slogan_field: dict[str, Any] | Any = firestore.DELETE_FIELD
        if detected and detected.strip() != slogan.strip():
            # 현재 프로필 슬로건과 다른 새 슬로건 후보 발견
            detected_slogan_field = {
                "text": detected,
                "detectedAt": firestore.SERVER_TIMESTAMP,
            }
            logger.info(
                "[StyleRefresh] uid=%s 슬로건 후보 감지: %s", uid, detected,
            )

        bio_ref = db.collection("bios").document(uid)
        now = firestore.SERVER_TIMESTAMP

        bio_ref.set(
            {
                "styleFingerprint": fingerprint,
                "styleGuide": style_guide,
                "generationProfile": gen_profile.to_dict(),
                "styleFingerprintUpdatedAt": now,
                "styleGuideUpdatedAt": now,
                "styleFingerprintSource": source,
                "styleFingerprintVersion": firestore.Increment(1),
                "styleFingerprintCorpusStats": corpus_stats,
                "pendingStyleEntryCount": 0,
                "styleRefreshRequestedAt": firestore.DELETE_FIELD,
                "styleRefreshError": firestore.DELETE_FIELD,
                "detectedSlogan": detected_slogan_field,
                "lastAnalyzed": now,
            },
            merge=True,
        )

        # users/{uid}.styleGuide 미러
        user_ref = db.collection("users").document(uid)
        user_snap = user_ref.get()
        if user_snap.exists:
            user_ref.set(
                {
                    "styleGuide": style_guide or "",
                    "styleGuideUpdatedAt": now,
                },
                merge=True,
            )

        # version 읽기
        updated = bio_ref.get()
        version = int((updated.to_dict() or {}).get("styleFingerprintVersion") or 0)

        logger.info(
            "[StyleRefresh] uid=%s source=%s version=%d chars=%d",
            uid, source, version, len(corpus_text),
        )
        return {"ok": True, "version": version}

    except Exception as exc:
        logger.error("[StyleRefresh] uid=%s 실패: %s", uid, exc, exc_info=True)
        await _record_refresh_error(uid, str(exc), db=db)
        return {"ok": False, "reason": str(exc)}


# ── Firestore trigger에서 호출하는 진입점 ────────────────────

async def process_bio_style_update(
    uid: str,
    new_data: dict[str, Any],
    old_data: dict[str, Any] | None = None,
    *,
    db: Any | None = None,
) -> None:
    """``styleRefreshRequestedAt`` 변화를 감지하여 재학습을 수행한다.

    Node ``maybeRefreshStyleFromDiary`` 대체.
    """
    if db is None:
        db = firestore.client()

    new_requested = new_data.get("styleRefreshRequestedAt")
    old_requested = (old_data or {}).get("styleRefreshRequestedAt")

    if not new_requested:
        return
    if _timestamps_equal(new_requested, old_requested):
        return

    # 재귀 가드: 최근 60초 이내 갱신이면 스킵
    last_updated = new_data.get("styleFingerprintUpdatedAt")
    if last_updated and _seconds_since(last_updated) < 60:
        logger.info("[StyleRefresh] uid=%s 재귀 가드 — 최근 갱신 직후", uid)
        return

    try:
        db.collection("bios").document(uid).set(
            {"styleRefreshStartedAt": firestore.SERVER_TIMESTAMP},
            merge=True,
        )

        corpus = await build_diary_augmented_corpus(uid, new_data, db=db)
        if corpus["source"] == "empty" or not corpus["text"]:
            logger.warning("[StyleRefresh] uid=%s 코퍼스 비어 있음 — 스킵", uid)
            db.collection("bios").document(uid).set(
                {
                    "styleRefreshRequestedAt": firestore.DELETE_FIELD,
                    "styleRefreshError": {
                        "message": "empty-corpus",
                        "at": firestore.SERVER_TIMESTAMP,
                    },
                },
                merge=True,
            )
            return

        logger.info(
            "[StyleRefresh] uid=%s source=%s chars=%d",
            uid, corpus["source"], corpus["stats"]["totalChars"],
        )

        result = await refresh_user_style_fingerprint(
            uid,
            corpus_text=corpus["text"],
            source=corpus["source"],
            corpus_stats=corpus["stats"],
            user_meta={
                "userName": str(new_data.get("userName") or new_data.get("name") or "").strip(),
                "region": str(new_data.get("region") or "").strip(),
            },
            slogan=str(new_data.get("slogan") or "").strip(),
            db=db,
        )

        if not result["ok"]:
            logger.warning("[StyleRefresh] uid=%s 실패: %s", uid, result.get("reason"))
    except Exception as exc:
        logger.error("[StyleRefresh] uid=%s 처리 중 예외: %s", uid, exc, exc_info=True)
        try:
            db.collection("bios").document(uid).set(
                {
                    "styleRefreshError": {
                        "message": str(exc)[:500],
                        "at": firestore.SERVER_TIMESTAMP,
                    },
                },
                merge=True,
            )
        except Exception:
            pass


# ── timestamp 헬퍼 ───────────────────────────────────────────

def _timestamps_equal(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        a_ts = a.timestamp() if isinstance(a, datetime) else float(getattr(a, "seconds", 0))
        b_ts = b.timestamp() if isinstance(b, datetime) else float(getattr(b, "seconds", 0))
        return abs(a_ts - b_ts) < 0.001
    except Exception:
        return False


def _seconds_since(ts: Any) -> float:
    try:
        if isinstance(ts, datetime):
            dt = ts
        elif hasattr(ts, "seconds"):
            dt = datetime.fromtimestamp(ts.seconds, tz=timezone.utc)
        else:
            return float("inf")
        return (datetime.now(tz=timezone.utc) - dt).total_seconds()
    except Exception:
        return float("inf")
