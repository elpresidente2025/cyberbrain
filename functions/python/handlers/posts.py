"""
Posts callable handlers migrated from Node.js.

This module provides:
- getUserPosts
- getPost
- updatePost
- deletePost
- checkUsageLimit
- indexPastPosts
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import google.generativeai as genai
from firebase_admin import firestore
from firebase_functions import https_fn
from google.api_core import exceptions as google_exceptions
from google.cloud.firestore_v1.vector import Vector

logger = logging.getLogger(__name__)

EMBEDDINGS_COLLECTION = "embeddings"
CHUNKS_SUBCOLLECTION = "chunks"
EMBEDDING_MODEL = "models/text-embedding-004"
EMBEDDING_TASK_TYPE = "retrieval_document"
EMBEDDING_BATCH_SIZE = 10
FIRESTORE_BATCH_SIZE = 400

_GENAI_CONFIGURED = False


class ApiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _get_callable_data(req: https_fn.CallableRequest) -> Dict[str, Any]:
    data = req.data
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return data if isinstance(data, dict) else {}


def _extract_uid(req: https_fn.CallableRequest) -> str:
    auth = req.auth
    uid = auth.uid if auth else None
    if not uid:
        raise ApiError("unauthenticated", "로그인이 필요합니다.")
    return str(uid)


def _to_https_error(error: ApiError) -> https_fn.HttpsError:
    valid_codes = {
        "cancelled",
        "unknown",
        "invalid-argument",
        "deadline-exceeded",
        "not-found",
        "already-exists",
        "permission-denied",
        "resource-exhausted",
        "failed-precondition",
        "aborted",
        "out-of-range",
        "unimplemented",
        "internal",
        "unavailable",
        "data-loss",
        "unauthenticated",
    }
    code = error.code if error.code in valid_codes else "internal"
    return https_fn.HttpsError(code, error.message)


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "to_datetime"):  # defensive for some timestamp wrappers
        value = value.to_datetime()
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _serialize_post(post_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    post = dict(data)
    post["id"] = post_id
    post["createdAt"] = _to_iso(data.get("createdAt"))
    post["updatedAt"] = _to_iso(data.get("updatedAt"))
    post["publishedAt"] = _to_iso(data.get("publishedAt"))
    return post


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]*>", "", text or "")


def _count_without_space(text: str) -> int:
    if not text:
        return 0
    return sum(1 for ch in text if not ch.isspace())


def _iter_batches(items: List[Any], batch_size: int) -> Iterable[List[Any]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def _configure_genai() -> None:
    global _GENAI_CONFIGURED
    if _GENAI_CONFIGURED:
        return
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ApiError("internal", "GEMINI_API_KEY가 설정되지 않았습니다.")
    genai.configure(api_key=api_key)
    _GENAI_CONFIGURED = True


def _coerce_embedding_vector(raw_item: Any) -> Optional[List[float]]:
    if raw_item is None:
        return None
    if isinstance(raw_item, (list, tuple)):
        return [float(v) for v in raw_item]
    if isinstance(raw_item, dict):
        if isinstance(raw_item.get("values"), (list, tuple)):
            return [float(v) for v in raw_item["values"]]
        if isinstance(raw_item.get("embedding"), (list, tuple)):
            return [float(v) for v in raw_item["embedding"]]
        return None
    values = getattr(raw_item, "values", None)
    if isinstance(values, (list, tuple)):
        return [float(v) for v in values]
    embedding = getattr(raw_item, "embedding", None)
    if isinstance(embedding, (list, tuple)):
        return [float(v) for v in embedding]
    return None


def _extract_embedding_list(raw_response: Any) -> List[List[float]]:
    if raw_response is None:
        return []

    container = None
    if isinstance(raw_response, dict):
        container = raw_response.get("embedding") or raw_response.get("embeddings")
    else:
        container = getattr(raw_response, "embedding", None) or getattr(raw_response, "embeddings", None)

    if container is None:
        return []

    # Single vector
    if isinstance(container, (list, tuple)) and container and isinstance(container[0], (int, float)):
        return [[float(v) for v in container]]

    if not isinstance(container, (list, tuple)):
        vector = _coerce_embedding_vector(container)
        return [vector] if vector else []

    vectors: List[List[float]] = []
    for item in container:
        vector = _coerce_embedding_vector(item)
        if vector:
            vectors.append(vector)
    return vectors


def _embed_batch(texts: List[str]) -> List[Dict[str, Any]]:
    try:
        raw = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=texts,
            task_type=EMBEDDING_TASK_TYPE,
        )
        vectors = _extract_embedding_list(raw)
        if len(vectors) == len(texts):
            return [{"success": True, "embedding": vectors[i]} for i in range(len(texts))]
    except Exception as exc:
        logger.warning("Batch embedding failed (fallback to single): %s", exc)

    # Fallback to per-text embedding for better compatibility.
    results: List[Dict[str, Any]] = []
    for text in texts:
        try:
            raw_single = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=text,
                task_type=EMBEDDING_TASK_TYPE,
            )
            vectors = _extract_embedding_list(raw_single)
            vector = vectors[0] if vectors else None
            if vector:
                results.append({"success": True, "embedding": vector})
            else:
                results.append({"success": False, "embedding": None, "error": "empty embedding"})
        except Exception as exc:
            results.append({"success": False, "embedding": None, "error": str(exc)})
    return results


def _batch_generate_embeddings(texts: List[str]) -> List[Dict[str, Any]]:
    _configure_genai()
    all_results: List[Dict[str, Any]] = []
    for batch in _iter_batches(texts, EMBEDDING_BATCH_SIZE):
        all_results.extend(_embed_batch(batch))
    return all_results


def _split_sentences(text: str) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s and s.strip()]
    return sentences or [text]


def _chunk_text(text: str, max_chars: int = 500, min_chars: int = 50, overlap: int = 50) -> List[str]:
    clean_text = (text or "").strip()
    if not clean_text:
        return []
    if len(clean_text) <= max_chars:
        return [clean_text]

    sentences = _split_sentences(clean_text)
    chunks: List[str] = []
    current = ""
    overlap_buffer = ""

    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if len(current) >= min_chars:
            chunks.append(current.strip())
            overlap_buffer = current[-overlap:] if overlap > 0 and len(current) > overlap else ""

        current = f"{overlap_buffer} {sentence}".strip() if overlap_buffer else sentence
        overlap_buffer = ""

    if current.strip():
        if len(current.strip()) >= min_chars:
            chunks.append(current.strip())
        elif chunks:
            chunks[-1] = f"{chunks[-1]} {current.strip()}".strip()
        else:
            chunks.append(current.strip())

    return chunks


def _run_callable(core_fn, req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        return core_fn(req)
    except ApiError as exc:
        raise _to_https_error(exc) from exc
    except https_fn.HttpsError:
        raise
    except Exception as exc:
        logger.exception("Unhandled posts handler error: %s", exc)
        raise https_fn.HttpsError("internal", "요청 처리 중 오류가 발생했습니다.") from exc


def _get_user_posts_core(req: https_fn.CallableRequest) -> Dict[str, Any]:
    uid = _extract_uid(req)
    db = firestore.client()

    posts_snapshot = (
        db.collection("posts")
        .where("userId", "==", uid)
        .order_by("createdAt", direction=firestore.Query.DESCENDING)
        .limit(50)
        .get()
    )

    posts: List[Dict[str, Any]] = []
    for doc in posts_snapshot:
        data = _safe_dict(doc.to_dict())
        if data.get("status") == "draft":
            continue
        posts.append(_serialize_post(doc.id, data))

    return {
        "success": True,
        "posts": posts,
        "data": {
            "posts": posts,
            "count": len(posts),
        },
    }


def _get_post_core(req: https_fn.CallableRequest) -> Dict[str, Any]:
    uid = _extract_uid(req)
    data = _get_callable_data(req)
    post_id = str(data.get("postId") or "").strip()
    if not post_id:
        raise ApiError("invalid-argument", "게시물 ID를 입력해 주세요.")

    db = firestore.client()
    post_doc = db.collection("posts").document(post_id).get()
    if not post_doc.exists:
        raise ApiError("not-found", "게시물을 찾을 수 없습니다.")

    post_data = _safe_dict(post_doc.to_dict())
    if str(post_data.get("userId") or "") != uid:
        raise ApiError("permission-denied", "게시물을 조회할 권한이 없습니다.")

    return {
        "success": True,
        "post": _serialize_post(post_doc.id, post_data),
    }


def _update_post_core(req: https_fn.CallableRequest) -> Dict[str, Any]:
    uid = _extract_uid(req)
    data = _get_callable_data(req)
    post_id = str(data.get("postId") or "").strip()
    updates = _safe_dict(data.get("updates"))

    if not post_id or not updates:
        raise ApiError("invalid-argument", "게시물 ID와 수정 내용을 입력해 주세요.")

    db = firestore.client()
    post_ref = db.collection("posts").document(post_id)
    post_doc = post_ref.get()
    if not post_doc.exists:
        raise ApiError("not-found", "게시물을 찾을 수 없습니다.")

    current = _safe_dict(post_doc.to_dict())
    if str(current.get("userId") or "") != uid:
        raise ApiError("permission-denied", "게시물을 수정할 권한이 없습니다.")

    allowed = {"title", "content", "category", "subCategory", "keywords", "status"}
    sanitized = {k: updates[k] for k in allowed if k in updates}
    if "content" in sanitized:
        sanitized["wordCount"] = _count_without_space(_strip_html(str(sanitized.get("content") or "")))
    sanitized["updatedAt"] = firestore.SERVER_TIMESTAMP

    post_ref.update(sanitized)
    return {"success": True, "message": "게시물이 성공적으로 수정되었습니다."}


def _delete_post_core(req: https_fn.CallableRequest) -> Dict[str, Any]:
    uid = _extract_uid(req)
    data = _get_callable_data(req)
    post_id = str(data.get("postId") or "").strip()
    if not post_id:
        raise ApiError("invalid-argument", "게시물 ID를 입력해 주세요.")

    db = firestore.client()
    post_ref = db.collection("posts").document(post_id)
    post_doc = post_ref.get()
    if not post_doc.exists:
        raise ApiError("not-found", "게시물을 찾을 수 없습니다.")

    post_data = _safe_dict(post_doc.to_dict())
    if str(post_data.get("userId") or "") != uid:
        raise ApiError("permission-denied", "게시물을 삭제할 권한이 없습니다.")

    post_ref.delete()
    return {"success": True, "message": "게시물이 성공적으로 삭제되었습니다."}


def _check_usage_limit_core(req: https_fn.CallableRequest) -> Dict[str, Any]:
    uid = _extract_uid(req)
    db = firestore.client()
    now = datetime.now(timezone.utc)
    this_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    try:
        snap = (
            db.collection("posts")
            .where("userId", "==", uid)
            .where("createdAt", ">=", this_month)
            .get()
        )
        used = len(snap)
        limit = 50
        return {
            "success": True,
            "postsGenerated": used,
            "monthlyLimit": limit,
            "canGenerate": used < limit,
            "remainingPosts": max(0, limit - used),
        }
    except google_exceptions.FailedPrecondition:
        return {
            "success": True,
            "postsGenerated": 0,
            "monthlyLimit": 50,
            "canGenerate": True,
            "remainingPosts": 50,
        }
    except Exception as exc:
        if "FAILED_PRECONDITION" in str(exc).upper():
            return {
                "success": True,
                "postsGenerated": 0,
                "monthlyLimit": 50,
                "canGenerate": True,
                "remainingPosts": 50,
            }
        raise ApiError("internal", "사용량을 확인하는 데 실패했습니다.") from exc


def _delete_old_post_chunks(chunks_ref) -> int:
    old_docs = list(chunks_ref.where("sourceType", "==", "post_content").stream())
    for docs_batch in _iter_batches(old_docs, FIRESTORE_BATCH_SIZE):
        batch = firestore.client().batch()
        for doc in docs_batch:
            batch.delete(doc.reference)
        batch.commit()
    return len(old_docs)


def _index_past_posts_core(req: https_fn.CallableRequest) -> Dict[str, Any]:
    uid = _extract_uid(req)
    db = firestore.client()

    posts_snapshot = db.collection("posts").where("userId", "==", uid).get()
    if not posts_snapshot:
        return {
            "success": True,
            "count": 0,
            "chunkCount": 0,
            "message": "인덱싱할 과거 원고가 없습니다.",
        }

    chunks: List[Dict[str, Any]] = []
    post_count = 0
    for post_doc in posts_snapshot:
        post = _safe_dict(post_doc.to_dict())
        post_count += 1
        raw_content = str(post.get("content") or "")
        if len(raw_content) < 50:
            continue

        plain_text = re.sub(r"<[^>]*>", " ", raw_content)
        plain_text = re.sub(r"\s+", " ", plain_text).strip()
        if len(plain_text) < 50:
            continue

        text_chunks = _chunk_text(plain_text, max_chars=500, min_chars=50, overlap=50)
        for position, chunk_text in enumerate(text_chunks):
            chunks.append(
                {
                    "text": chunk_text,
                    "sourceEntryId": post_doc.id,
                    "position": position,
                    "metadata": {
                        "sourceEntryId": post_doc.id,
                        "sourceType": "post_content",
                        "title": str(post.get("title") or ""),
                        "tags": post.get("keywords") if isinstance(post.get("keywords"), list) else [],
                        "weight": 1.0,
                        "charLength": len(chunk_text),
                        "totalChunks": len(text_chunks),
                    },
                }
            )

    if not chunks:
        return {
            "success": True,
            "count": post_count,
            "chunkCount": 0,
            "message": "유효한 원고 내용이 없습니다.",
        }

    chunks_ref = db.collection(EMBEDDINGS_COLLECTION).document(uid).collection(CHUNKS_SUBCOLLECTION)
    removed_count = _delete_old_post_chunks(chunks_ref)
    logger.info("Removed old post chunks: uid=%s count=%s", uid, removed_count)

    embedding_results = _batch_generate_embeddings([chunk["text"] for chunk in chunks])

    indexed_count = 0
    for chunk_batch in _iter_batches(list(enumerate(chunks)), FIRESTORE_BATCH_SIZE):
        batch = db.batch()
        write_count = 0
        for idx, chunk in chunk_batch:
            result = embedding_results[idx] if idx < len(embedding_results) else {}
            vector_values = result.get("embedding") if isinstance(result, dict) else None
            if not result.get("success") or not vector_values:
                continue

            doc_ref = chunks_ref.document()
            batch.set(
                doc_ref,
                {
                    "userId": uid,
                    "chunkText": chunk["text"],
                    "embedding": Vector(vector_values),
                    "sourceType": "post_content",
                    "sourceEntryId": chunk["sourceEntryId"],
                    "sourcePosition": chunk["position"],
                    "metadata": chunk["metadata"],
                    "createdAt": firestore.SERVER_TIMESTAMP,
                },
            )
            indexed_count += 1
            write_count += 1

        if write_count > 0:
            batch.commit()

    db.collection(EMBEDDINGS_COLLECTION).document(uid).set(
        {
            "lastPastPostsIndexedAt": firestore.SERVER_TIMESTAMP,
            "postChunkCount": indexed_count,
        },
        merge=True,
    )

    return {
        "success": True,
        "count": post_count,
        "chunkCount": indexed_count,
        "message": f"{post_count}개의 과거 원고를 성공적으로 인덱싱했습니다.",
    }


def handle_get_user_posts_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    return _run_callable(_get_user_posts_core, req)


def handle_get_post_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    return _run_callable(_get_post_core, req)


def handle_update_post_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    return _run_callable(_update_post_core, req)


def handle_delete_post_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    return _run_callable(_delete_post_core, req)


def handle_check_usage_limit_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    return _run_callable(_check_usage_limit_core, req)


def handle_index_past_posts_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    return _run_callable(_index_past_posts_core, req)

