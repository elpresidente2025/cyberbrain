"""
RAG 색인 핸들러.

- index_bio_to_rag     : 사용자 bioEntries → LightRAG (기존 Cloud Function)
- batch_index_bios     : 관리자 전용 일괄 색인
- index_facebook_entries : 페이스북 다이어리 엔트리 수동 재색인
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from firebase_admin import firestore
from firebase_functions import https_fn

logger = logging.getLogger(__name__)

_RAG_BUCKET = "ai-secretary-6e9c8.appspot.com"
_REINDEX_COOLDOWN = timedelta(minutes=5)


def _json_response(payload: Dict[str, Any], status: int = 200) -> https_fn.Response:
    return https_fn.Response(
        json.dumps(payload, ensure_ascii=False),
        status=status,
        mimetype="application/json",
    )


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except Exception:
            pass
        asyncio.set_event_loop(None)


# ---------------------------------------------------------------------------
# handle_index_bio
# ---------------------------------------------------------------------------

def handle_index_bio(req: https_fn.Request) -> https_fn.Response:
    """사용자 bioEntries를 LightRAG 지식 그래프에 색인한다."""
    if req.method == "OPTIONS":
        return https_fn.Response("", status=204)

    data = req.get_json(silent=True) or {}
    uid = str(data.get("uid") or "").strip()
    if not uid:
        return _json_response({"error": "uid가 필요합니다."}, 400)

    try:
        from rag_manager import LightRAGManager

        db = firestore.client()
        bio_doc = db.collection("bios").document(uid).get()
        bio_data = bio_doc.to_dict() or {}
        entries = bio_data.get("bioEntries") or []

        if not entries:
            return _json_response({"error": "색인할 bioEntries가 없습니다."}, 404)

        async def _index():
            manager = LightRAGManager(bucket_name=_RAG_BUCKET, uid=uid)
            doc = await manager.index_entries(entries)
            return doc

        doc_text = _run_async(_index())
        char_count = len(doc_text or "")

        # 키워드 별칭 추출
        try:
            from rag_manager import extract_keyword_aliases
            aliases = _run_async(extract_keyword_aliases(doc_text or ""))
            if aliases:
                bio_ref = db.collection("bios").document(uid)
                bio_ref.set({"keywordAliases": aliases}, merge=True)
                logger.info("[AliasExtract] %d개 별칭 저장 — uid=%s", len(aliases), uid)
        except Exception as alias_exc:
            logger.warning("[AliasExtract] 별칭 추출 실패(무시) — uid=%s: %s", uid, alias_exc)

        logger.info("[RAGIndex] bio 색인 완료 — uid=%s chars=%d", uid, char_count)
        return _json_response({"success": True, "uid": uid, "chars": char_count})

    except Exception as exc:
        logger.exception("[RAGIndex] bio 색인 실패 — uid=%s: %s", uid, exc)
        return _json_response({"error": str(exc)}, 500)


# ---------------------------------------------------------------------------
# handle_batch_index_bios
# ---------------------------------------------------------------------------

def handle_batch_index_bios(req: https_fn.Request) -> https_fn.Response:
    """관리자 전용 — 전체(또는 지정) 사용자 bioEntries를 일괄 색인한다."""
    if req.method == "OPTIONS":
        return https_fn.Response("", status=204)

    data = req.get_json(silent=True) or {}
    target_uids: list[str] = data.get("uids") or []

    db = firestore.client()
    if not target_uids:
        docs = db.collection("bios").stream()
        target_uids = [doc.id for doc in docs]

    results: list[Dict[str, Any]] = []
    for uid in target_uids:
        try:
            from rag_manager import LightRAGManager

            bio_doc = db.collection("bios").document(uid).get()
            entries = (bio_doc.to_dict() or {}).get("bioEntries") or []
            if not entries:
                results.append({"uid": uid, "status": "skipped", "reason": "no entries"})
                continue

            async def _index(u=uid, e=entries):
                manager = LightRAGManager(bucket_name=_RAG_BUCKET, uid=u)
                return await manager.index_entries(e)

            _run_async(_index())
            results.append({"uid": uid, "status": "ok"})
            logger.info("[BatchIndex] 완료 — uid=%s", uid)
        except Exception as exc:
            logger.warning("[BatchIndex] 실패 — uid=%s: %s", uid, exc)
            results.append({"uid": uid, "status": "error", "error": str(exc)})

    return _json_response({"results": results})


# ---------------------------------------------------------------------------
# handle_index_facebook_entries  (수동 트리거)
# ---------------------------------------------------------------------------

def handle_index_facebook_entries(req: https_fn.Request) -> https_fn.Response:
    """페이스북 다이어리 엔트리를 LightRAG에 수동으로 재색인한다."""
    if req.method == "OPTIONS":
        return https_fn.Response("", status=204)

    data = req.get_json(silent=True) or {}
    uid = str(data.get("uid") or "").strip()
    force = bool(data.get("force", False))  # 쿨다운 무시 여부
    if not uid:
        return _json_response({"error": "uid가 필요합니다."}, 400)

    try:
        db = firestore.client()
        bio_ref = db.collection("bios").document(uid)

        # 쿨다운 체크 (force=True면 스킵)
        if not force:
            snapshot = bio_ref.get(field_paths=["facebookEntryIndexedAt"])
            last_indexed = (snapshot.to_dict() or {}).get("facebookEntryIndexedAt")
            if last_indexed is not None:
                last_dt = last_indexed if isinstance(last_indexed, datetime) else None
                if last_dt:
                    elapsed = datetime.now(timezone.utc) - last_dt.replace(tzinfo=timezone.utc)
                    if elapsed < _REINDEX_COOLDOWN:
                        remaining = int((_REINDEX_COOLDOWN - elapsed).total_seconds())
                        return _json_response(
                            {"skipped": True, "reason": f"쿨다운 중 ({remaining}초 남음)"}
                        )

        docs = bio_ref.collection("facebook_entries").order_by("createdAt").get()
        entries = [doc.to_dict() for doc in docs if doc.to_dict()]
        if not entries:
            return _json_response({"error": "색인할 facebook_entries가 없습니다."}, 404)

        from rag_manager import LightRAGManager, _facebook_entries_to_document, upload_graph_to_gcs

        document = _facebook_entries_to_document(entries)
        if not document.strip():
            return _json_response({"error": "변환된 문서가 비어 있습니다."}, 422)

        async def _index():
            manager = LightRAGManager(bucket_name=_RAG_BUCKET, uid=uid)
            await manager.initialize(mode="write")
            await manager.rag.ainsert(document)
            upload_graph_to_gcs(_RAG_BUCKET, uid)

        _run_async(_index())

        # 키워드 별칭 추출
        try:
            from rag_manager import extract_keyword_aliases
            aliases = _run_async(extract_keyword_aliases(document))
            if aliases:
                bio_ref.set({"keywordAliases": aliases}, merge=True)
                logger.info("[AliasExtract] %d개 별칭 저장 — uid=%s", len(aliases), uid)
        except Exception as exc:
            logger.warning("[AliasExtract] 별칭 추출 실패(무시) — uid=%s: %s", uid, exc)

        bio_ref.set(
            {
                "pendingFacebookEntryCount": 0,
                "facebookEntryIndexedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

        logger.info("[FacebookDiary] 수동 재색인 완료 — uid=%s entries=%d", uid, len(entries))
        return _json_response({"success": True, "uid": uid, "entries": len(entries)})

    except Exception as exc:
        logger.exception("[FacebookDiary] 수동 재색인 실패 — uid=%s: %s", uid, exc)
        return _json_response({"error": str(exc)}, 500)
