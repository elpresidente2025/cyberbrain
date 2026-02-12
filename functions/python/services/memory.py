"""
Memory Systems - 사용자별 장기 메모리 관리.

Node.js `services/memory/index.js`의 Python 포팅 버전이다.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from firebase_admin import firestore

logger = logging.getLogger(__name__)


def get_default_memory() -> Dict[str, Any]:
    return {
        "preferences": {
            "favoriteKeywords": [],
            "preferredLength": "medium",
            "preferredTone": None,
            "avoidKeywords": [],
        },
        "patterns": {
            "commonPhrases": [],
            "effectiveOpenings": [],
            "effectiveClosings": [],
        },
        "feedback": {
            "liked": [],
            "disliked": [],
        },
        "stats": {
            "totalGenerated": 0,
            "totalSelected": 0,
            "selectionRate": 0,
            "categoryBreakdown": {},
        },
    }


def _update_keyword_frequency(existing: List[Any], new_keywords: List[str]) -> List[Dict[str, Any]]:
    keyword_map: Dict[str, int] = {}

    for item in existing or []:
        if isinstance(item, dict):
            keyword = str(item.get("keyword", "")).strip()
            count = int(item.get("count", 1))
        else:
            keyword = str(item).strip()
            count = 1
        if keyword:
            keyword_map[keyword] = max(1, keyword_map.get(keyword, 0) + count)

    for keyword in new_keywords or []:
        normalized = str(keyword).strip()
        if normalized:
            keyword_map[normalized] = keyword_map.get(normalized, 0) + 1

    ranked = [{"keyword": k, "count": c} for k, c in keyword_map.items()]
    ranked.sort(key=lambda item: item["count"], reverse=True)
    return ranked[:20]


def _update_pattern_list(existing: List[str], new_pattern: str | None, max_count: int) -> List[str]:
    if not new_pattern:
        return list(existing or [])
    filtered = [item for item in (existing or []) if item != new_pattern]
    filtered.insert(0, new_pattern)
    return filtered[:max_count]


def _extract_effective_patterns(content: str) -> Dict[str, str | None]:
    if not content:
        return {"opening": None, "closing": None}
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", content) if len(s.strip()) > 10]
    opening = sentences[0][:100] if sentences else None
    closing = sentences[-1][:100] if len(sentences) > 1 else None
    return {"opening": opening, "closing": closing}


def get_user_memory(uid: str) -> Dict[str, Any]:
    if not uid:
        return get_default_memory()

    db = firestore.client()
    try:
        memory_doc = db.collection("users").document(uid).collection("memory").document("preferences").get()
        if not memory_doc.exists:
            return get_default_memory()
        return memory_doc.to_dict() or get_default_memory()
    except Exception as exc:
        logger.warning("[Memory] 메모리 조회 실패: %s", exc)
        return get_default_memory()


def save_best_post(uid: str, post_data: Dict[str, Any]) -> None:
    if not uid or not post_data:
        return

    db = firestore.client()
    category = str(post_data.get("category") or "")
    content = str(post_data.get("content") or "")
    title = str(post_data.get("title") or "")
    topic = str(post_data.get("topic") or "")
    keywords = post_data.get("keywords") if isinstance(post_data.get("keywords"), list) else []
    quality_score = post_data.get("qualityScore")

    best_posts_ref = db.collection("users").document(uid).collection("best_posts")

    try:
        query = (
            best_posts_ref.where("category", "==", category).order_by("savedAt", direction=firestore.Query.DESCENDING).limit(3)
        )
        existing_docs = list(query.stream())
    except Exception:
        # 인덱스 이슈 등 예외 시 카테고리 필터를 느슨하게 fallback
        existing_docs = []
        try:
            fallback_query = best_posts_ref.order_by("savedAt", direction=firestore.Query.DESCENDING).limit(10)
            existing_docs = [doc for doc in fallback_query.stream() if (doc.to_dict() or {}).get("category") == category][:3]
        except Exception as exc:
            logger.warning("[Memory] 베스트 포스트 기존 조회 실패: %s", exc)

    if len(existing_docs) >= 3:
        oldest_doc = existing_docs[-1]
        try:
            oldest_doc.reference.delete()
        except Exception as exc:
            logger.warning("[Memory] 베스트 포스트 정리 실패: %s", exc)

    try:
        best_posts_ref.add(
            {
                "category": category,
                "topic": topic,
                "title": title,
                "contentPreview": content[:300],
                "contentLength": len(content),
                "keywords": keywords[:10],
                "qualityScore": quality_score,
                "savedAt": firestore.SERVER_TIMESTAMP,
            }
        )
    except Exception as exc:
        logger.warning("[Memory] 베스트 포스트 저장 실패: %s", exc)


def update_memory_on_selection(uid: str, post_data: Dict[str, Any]) -> None:
    if not uid or not post_data:
        return

    db = firestore.client()
    category = str(post_data.get("category") or "")
    content = str(post_data.get("content") or "")
    title = str(post_data.get("title") or "")
    keywords = post_data.get("keywords")
    quality_score = post_data.get("qualityScore")

    if not isinstance(keywords, list):
        keywords = []

    memory_ref = db.collection("users").document(uid).collection("memory").document("preferences")

    @firestore.transactional
    def _update_in_txn(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        memory = snapshot.to_dict() if snapshot.exists else get_default_memory()

        stats = memory.setdefault("stats", {})
        stats["totalSelected"] = int(stats.get("totalSelected", 0)) + 1
        total_generated = int(stats.get("totalGenerated", 0))
        stats["selectionRate"] = (stats["totalSelected"] / total_generated) if total_generated > 0 else 0

        patterns = memory.setdefault("patterns", {})
        extracted = _extract_effective_patterns(content)
        patterns["effectiveOpenings"] = _update_pattern_list(
            patterns.get("effectiveOpenings", []), extracted.get("opening"), 5
        )
        patterns["effectiveClosings"] = _update_pattern_list(
            patterns.get("effectiveClosings", []), extracted.get("closing"), 5
        )

        preferences = memory.setdefault("preferences", {})
        preferences["favoriteKeywords"] = _update_keyword_frequency(
            preferences.get("favoriteKeywords", []),
            keywords,
        )

        memory["updatedAt"] = firestore.SERVER_TIMESTAMP
        transaction.set(ref, memory, merge=True)

    try:
        transaction = db.transaction()
        _update_in_txn(transaction, memory_ref)
        logger.info("[Memory] 선택 메모리 업데이트 완료: uid=%s category=%s", uid, category)
    except Exception as exc:
        logger.warning("[Memory] 선택 메모리 업데이트 실패: %s", exc)
        return

    quality_ok = quality_score is None
    if quality_score is not None:
        try:
            quality_ok = float(quality_score) >= 7.0
        except Exception:
            quality_ok = False

    if quality_ok:
        save_best_post(
            uid,
            {
                "category": category,
                "content": content,
                "title": title,
                "topic": str(post_data.get("topic") or ""),
                "keywords": keywords,
                "qualityScore": quality_score,
            },
        )
