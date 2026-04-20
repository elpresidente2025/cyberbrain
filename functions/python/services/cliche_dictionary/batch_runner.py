"""상투어 대체어 사전 배치 갱신 Cloud Function 진입점.

3단계 실행:
  1. centroid 갱신 (TF-IDF 모델 재구축)
  2. 미처리 stanceText 에서 후보 추출
  3. 승격/퇴장/정리
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from firebase_functions import https_fn

logger = logging.getLogger(__name__)

_GCS_BUCKET = "ai-secretary-6e9c8.appspot.com"


def handle_refresh(req: https_fn.Request) -> https_fn.Response:
    """배치 갱신 핸들러.

    Cloud Scheduler 또는 관리자 수동 호출로 실행.
    query param ?phase=centroid|extract|promote 로 개별 단계 실행 가능.
    기본(phase 없음)은 전체 3단계 실행.
    """
    from firebase_admin import firestore

    db = firestore.client()
    phase = (req.args.get("phase") or "").strip().lower()
    results: dict[str, Any] = {}
    t0 = time.time()

    try:
        if not phase or phase == "centroid":
            from .centroid_builder import run_centroid_build

            logger.info("[batch_runner] Phase 1: centroid build")
            results["centroid"] = run_centroid_build(db, _GCS_BUCKET)

        if not phase or phase == "extract":
            from .candidate_extractor import extract_candidates_from_posts

            logger.info("[batch_runner] Phase 2: candidate extraction")
            results["extract"] = extract_candidates_from_posts(db, _GCS_BUCKET)

        if not phase or phase == "promote":
            from .dictionary_manager import (
                promote_candidates,
                prune_old_candidates,
                retire_stale_alternatives,
            )

            logger.info("[batch_runner] Phase 3: promotion + cleanup")
            results["promote"] = promote_candidates(db)
            results["retire"] = {"removed": retire_stale_alternatives(db)}
            results["prune"] = {"deleted": prune_old_candidates(db)}

        elapsed = round(time.time() - t0, 1)
        results["elapsed_seconds"] = elapsed
        logger.info("[batch_runner] Done in %.1fs: %s", elapsed, results)

        return https_fn.Response(
            json.dumps({"ok": True, "results": results}, ensure_ascii=False, default=str),
            status=200,
            content_type="application/json",
        )

    except Exception as e:
        logger.exception("[batch_runner] Failed: %s", e)
        return https_fn.Response(
            json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            status=500,
            content_type="application/json",
        )
