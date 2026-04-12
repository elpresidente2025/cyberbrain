"""관리자 전용 — 문체(stylometry) 일괄 재학습 핸들러.

Node `admin-users.js:batchAnalyzeBioStyles`의 Python 이관.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from firebase_admin import firestore
from firebase_functions import https_fn

from services.authz import is_admin_user
from services.stylometry.refresh import (
    build_consolidated_bio_content,
    build_diary_augmented_corpus,
    refresh_user_style_fingerprint,
)
from services.stylometry.schemas import MIN_CORPUS_LENGTH

logger = logging.getLogger(__name__)


def _require_admin(req: https_fn.CallableRequest) -> str:
    """관리자 권한 확인. uid 반환."""
    auth = req.auth
    if not auth or not auth.uid:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="로그인이 필요합니다.",
        )
    uid = auth.uid
    db = firestore.client()
    user_snap = db.collection("users").document(uid).get()
    if not user_snap.exists:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="사용자 정보를 찾을 수 없습니다.",
        )
    if not is_admin_user(user_snap.to_dict()):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="관리자 권한이 필요합니다.",
        )
    return uid


async def _batch_analyze(data: dict[str, Any]) -> dict[str, Any]:
    """일괄 재학습 비동기 본체."""
    db = firestore.client()

    raw_limit = data.get("limit")
    try:
        limit = max(1, min(int(raw_limit), 20))
    except (TypeError, ValueError):
        limit = 10

    start_after = str(data.get("startAfter") or "").strip()

    raw_min_conf = data.get("minConfidence")
    try:
        min_confidence = max(0.0, min(float(raw_min_conf), 1.0))
    except (TypeError, ValueError):
        min_confidence = 0.7

    force = data.get("force") is True
    use_diary = data.get("useDiary") is True

    query = db.collection("bios").order_by("__name__").limit(limit)
    if start_after:
        query = query.start_after({"__name__": start_after})

    snapshot = query.get()
    docs = list(snapshot)

    if not docs:
        return {
            "success": True,
            "processedCount": 0,
            "successCount": 0,
            "skippedCount": 0,
            "failedCount": 0,
            "noContentCount": 0,
            "hasMore": False,
            "lastUid": "",
            "message": "처리할 bio 문서가 없습니다.",
        }

    success_count = 0
    skipped_count = 0
    failed_count = 0
    no_content_count = 0
    failures: list[dict[str, str]] = []

    for doc in docs:
        bio_data = doc.to_dict() or {}
        existing_confidence = float(
            (bio_data.get("styleFingerprint") or {})
            .get("analysisMetadata", {})
            .get("confidence", 0)
        )

        if not force and existing_confidence >= min_confidence:
            skipped_count += 1
            continue

        if use_diary:
            corpus = await build_diary_augmented_corpus(doc.id, bio_data, db=db)
            corpus_text = corpus["text"]
            corpus_source = corpus["source"]
            corpus_stats = corpus["stats"]
        else:
            corpus_text = build_consolidated_bio_content(bio_data)
            corpus_source = "bio-only"
            corpus_stats = {
                "bioChars": len(corpus_text),
                "diaryEntryCount": 0,
                "diaryChars": 0,
                "totalChars": len(corpus_text),
            }

        if not corpus_text or len(corpus_text) < MIN_CORPUS_LENGTH:
            no_content_count += 1
            continue

        result = await refresh_user_style_fingerprint(
            doc.id,
            corpus_text=corpus_text,
            source=corpus_source,
            corpus_stats=corpus_stats,
            user_meta={
                "userName": str(bio_data.get("userName") or bio_data.get("name") or "").strip(),
                "region": str(bio_data.get("region") or "").strip(),
            },
            db=db,
        )

        if result["ok"]:
            success_count += 1
        else:
            failed_count += 1
            failures.append({"uid": doc.id, "reason": result.get("reason", "unknown-error")})

    last_uid = docs[-1].id if docs else ""
    has_more = len(docs) == limit and bool(last_uid)

    return {
        "success": True,
        "processedCount": len(docs),
        "successCount": success_count,
        "skippedCount": skipped_count,
        "failedCount": failed_count,
        "noContentCount": no_content_count,
        "hasMore": has_more,
        "lastUid": last_uid,
        "failures": failures[:10],
        "minConfidence": min_confidence,
        "force": force,
        "useDiary": use_diary,
    }


def handle_batch_analyze_bio_styles(req: https_fn.CallableRequest) -> dict:
    """on_call 진입점."""
    _require_admin(req)

    data = req.data if isinstance(req.data, dict) else {}

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_batch_analyze(data))
    finally:
        loop.close()
