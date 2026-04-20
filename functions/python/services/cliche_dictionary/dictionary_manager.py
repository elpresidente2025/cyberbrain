"""상투어 대체어 사전 관리 모듈.

- 후보(cliche_alt_candidates) 집계 → 확정 사전(cliche_dictionary) 승격
- 퇴장 로직 (90일 미사용 시 비활성화)
- 확정 사전 로드 (프롬프트 주입용)
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 설정 ──
PROMOTION_THRESHOLD = 3    # 동일 (상투어, 대체어) 쌍이 이 횟수 이상이면 승격
MAX_ALTERNATIVES = 5       # 상투어당 대체어 최대 수
RETIREMENT_DAYS = 90       # 마지막 관측 후 이 기간 지나면 비활성화
CANDIDATE_PRUNE_DAYS = 90  # 이보다 오래된 후보는 삭제


def _cliche_hash(phrase: str) -> str:
    return hashlib.md5(phrase.encode("utf-8")).hexdigest()[:12]


def promote_candidates(db: Any) -> Dict[str, Any]:
    """cliche_alt_candidates 를 집계하여 cliche_dictionary 에 승격.

    Returns:
        {"promoted_pairs": int, "total_candidates": int}
    """
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP

    # 1. 모든 후보 읽기
    candidates = db.collection("cliche_alt_candidates").stream()
    pair_counts: Dict[tuple, int] = {}
    pair_sentences: Dict[tuple, str] = {}

    total = 0
    for doc in candidates:
        data = doc.to_dict() or {}
        cliche = data.get("cliche", "")
        alternative = data.get("alternative", "")
        if not cliche or not alternative:
            continue
        key = (cliche, alternative)
        pair_counts[key] = pair_counts.get(key, 0) + 1
        if key not in pair_sentences:
            pair_sentences[key] = data.get("source_sentence", "")
        total += 1

    # 2. 기존 사전 로드
    existing_dict: Dict[str, Dict[str, Any]] = {}
    for doc in db.collection("cliche_dictionary").stream():
        data = doc.to_dict() or {}
        cliche = data.get("cliche", "")
        if cliche:
            existing_dict[cliche] = data

    # 3. threshold 이상인 쌍을 승격
    promoted = 0
    updates: Dict[str, List[Dict[str, Any]]] = {}  # cliche → alternatives list

    for (cliche, alt), count in pair_counts.items():
        if count < PROMOTION_THRESHOLD:
            continue

        if cliche not in updates:
            # 기존 대체어 로드
            existing = existing_dict.get(cliche, {})
            updates[cliche] = list(existing.get("alternatives", []))

        alt_list = updates[cliche]

        # 이미 존재하는 대체어면 count 갱신
        found = False
        for item in alt_list:
            if item.get("expression") == alt:
                item["count"] = max(item.get("count", 0), count)
                item["last_seen"] = datetime.now(timezone.utc).isoformat()
                found = True
                break

        if not found:
            alt_list.append({
                "expression": alt,
                "count": count,
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat(),
            })
            promoted += 1

    # 4. 상위 MAX_ALTERNATIVES 개만 유지, Firestore 에 저장
    for cliche, alt_list in updates.items():
        alt_list.sort(key=lambda x: x.get("count", 0), reverse=True)
        alt_list = alt_list[:MAX_ALTERNATIVES]

        doc_id = _cliche_hash(cliche)
        db.collection("cliche_dictionary").document(doc_id).set({
            "cliche": cliche,
            "alternatives": alt_list,
            "updatedAt": SERVER_TIMESTAMP,
        })

    logger.info(
        "[dictionary_manager] Promoted %d new pairs from %d total candidates",
        promoted,
        total,
    )
    return {"promoted_pairs": promoted, "total_candidates": total}


def retire_stale_alternatives(db: Any) -> int:
    """RETIREMENT_DAYS 이상 신규 관측이 없는 대체어를 제거.

    Returns:
        제거된 대체어 수
    """
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP

    cutoff = datetime.now(timezone.utc) - timedelta(days=RETIREMENT_DAYS)
    cutoff_iso = cutoff.isoformat()

    removed = 0
    for doc in db.collection("cliche_dictionary").stream():
        data = doc.to_dict() or {}
        alternatives = data.get("alternatives", [])
        if not alternatives:
            continue

        filtered = [
            alt for alt in alternatives
            if alt.get("last_seen", "") >= cutoff_iso
        ]
        removed_count = len(alternatives) - len(filtered)
        if removed_count > 0:
            doc.reference.update({
                "alternatives": filtered,
                "updatedAt": SERVER_TIMESTAMP,
            })
            removed += removed_count

    logger.info("[dictionary_manager] Retired %d stale alternatives", removed)
    return removed


def prune_old_candidates(db: Any) -> int:
    """CANDIDATE_PRUNE_DAYS 이상 된 후보를 삭제.

    Returns:
        삭제된 후보 수
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=CANDIDATE_PRUNE_DAYS)

    query = (
        db.collection("cliche_alt_candidates")
        .where("createdAt", "<", cutoff)
    )

    deleted = 0
    batch = db.batch()
    batch_size = 0

    for doc in query.stream():
        batch.delete(doc.reference)
        batch_size += 1
        deleted += 1

        if batch_size >= 400:
            batch.commit()
            batch = db.batch()
            batch_size = 0

    if batch_size > 0:
        batch.commit()

    logger.info("[dictionary_manager] Pruned %d old candidates", deleted)
    return deleted


# ── 확정 사전 로드 (프롬프트 주입용) ──

_DICT_CACHE: Optional[Dict[str, List[str]]] = None
_DICT_CACHE_TIME: float = 0
_DICT_CACHE_TTL: float = 3600  # 1시간


def load_cliche_dictionary(db: Any) -> Dict[str, List[str]]:
    """확정 사전을 로드. {상투어: [대체어1, 대체어2, ...]}

    인스턴스당 1시간 캐시.
    """
    global _DICT_CACHE, _DICT_CACHE_TIME

    now = time.time()
    if _DICT_CACHE is not None and (now - _DICT_CACHE_TIME) < _DICT_CACHE_TTL:
        return _DICT_CACHE

    result: Dict[str, List[str]] = {}
    try:
        for doc in db.collection("cliche_dictionary").stream():
            data = doc.to_dict() or {}
            cliche = data.get("cliche", "")
            alternatives = data.get("alternatives", [])
            if cliche and alternatives:
                result[cliche] = [
                    alt["expression"]
                    for alt in alternatives
                    if alt.get("expression")
                ]
    except Exception as e:
        logger.warning("[dictionary_manager] Failed to load cliche dictionary: %s", e)
        if _DICT_CACHE is not None:
            return _DICT_CACHE
        return {}

    _DICT_CACHE = result
    _DICT_CACHE_TIME = now
    logger.info("[dictionary_manager] Loaded %d cliche dictionary entries", len(result))
    return result
