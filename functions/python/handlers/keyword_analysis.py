"""
Keyword analysis handlers migrated from `functions/handlers/keyword-analysis.js`.

This module provides:
- requestKeywordAnalysis
- keywordAnalysisWorker
- getKeywordAnalysisResult
- getKeywordAnalysisHistory
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from firebase_admin import firestore
from firebase_functions import https_fn
from google.cloud import tasks_v2

from services.keyword_analysis import gemini_expander, keyword_scorer, scraper, trends_analyzer

logger = logging.getLogger(__name__)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _get_callable_data(req: https_fn.CallableRequest) -> Dict[str, Any]:
    data = req.data
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    return _safe_dict(data)


def _json_response(payload: Dict[str, Any], status: int = 200) -> https_fn.Response:
    return https_fn.Response(
        json.dumps(payload, ensure_ascii=False),
        status=status,
        mimetype="application/json",
    )


def _extract_auth_uid(req: https_fn.CallableRequest) -> str:
    auth_ctx = req.auth
    uid = auth_ctx.uid if auth_ctx else None
    if not uid:
        raise https_fn.HttpsError("unauthenticated", "인증이 필요합니다.")
    return str(uid)


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "to_datetime"):
        value = value.to_datetime()
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _create_cloud_task(task_id: str, payload: Dict[str, Any]) -> bool:
    try:
        client = tasks_v2.CloudTasksClient()

        project = os.environ.get("GCLOUD_PROJECT", "ai-secretary-6e9c8")
        location = "asia-northeast3"
        queue = "keyword-analysis-queue"
        parent = client.queue_path(project, location, queue)

        url = f"https://{location}-{project}.cloudfunctions.net/keywordAnalysisWorker"
        task_payload = {"taskId": task_id, **payload}
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": url,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(task_payload, ensure_ascii=False).encode("utf-8"),
            }
        }

        response = client.create_task(parent=parent, task=task)
        logger.info("Cloud Task created: %s", getattr(response, "name", "unknown"))
        return True
    except Exception as exc:
        logger.warning("Cloud Task create failed: %s", exc)
        return False


def _process_keyword_analysis_directly(task_id: str, district: str, topic: str, user_id: str) -> None:
    def _runner() -> None:
        try:
            _execute_keyword_analysis(
                {
                    "taskId": task_id,
                    "district": district,
                    "topic": topic,
                    "userId": user_id,
                }
            )
        except Exception:
            _update_task_status(task_id, "failed", {"error": "direct execution failed"})

    threading.Thread(target=_runner, daemon=True).start()


def _update_task_status(task_id: str, status: str, additional_data: Optional[Dict[str, Any]] = None) -> None:
    try:
        payload = {"status": status, "updatedAt": firestore.SERVER_TIMESTAMP}
        if isinstance(additional_data, dict):
            payload.update(additional_data)
        firestore.client().collection("keyword_tasks").document(task_id).update(payload)
    except Exception as exc:
        logger.warning("Task status update failed: taskId=%s status=%s error=%s", task_id, status, exc)


def _check_cache(cache_key: str) -> Optional[Dict[str, Any]]:
    try:
        doc = firestore.client().collection("keyword_cache").document(cache_key).get()
        if not doc.exists:
            return None

        data = _safe_dict(doc.to_dict())
        timestamp = data.get("timestamp")
        if hasattr(timestamp, "to_datetime"):
            timestamp = timestamp.to_datetime()
        if not isinstance(timestamp, datetime):
            return None

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)
        if age > timedelta(hours=12):
            return None
        return data
    except Exception as exc:
        logger.warning("Cache check failed: key=%s error=%s", cache_key, exc)
        return None


def _save_to_cache(cache_key: str, data: Dict[str, Any]) -> None:
    try:
        firestore.client().collection("keyword_cache").document(cache_key).set(
            {
                **_safe_dict(data),
                "timestamp": firestore.SERVER_TIMESTAMP,
                "cachedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
    except Exception as exc:
        logger.warning("Cache save failed: key=%s error=%s", cache_key, exc)


def _check_keyword_cache(keyword: str) -> Optional[Dict[str, Any]]:
    try:
        doc = firestore.client().collection("keyword_analysis_cache").document(keyword).get()
        if not doc.exists:
            return None

        data = _safe_dict(doc.to_dict())
        timestamp = data.get("timestamp")
        if hasattr(timestamp, "to_datetime"):
            timestamp = timestamp.to_datetime()
        if not isinstance(timestamp, datetime):
            return None

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)
        if age > timedelta(hours=24):
            return None
        return _safe_dict(data.get("analysis"))
    except Exception as exc:
        logger.warning("Keyword cache check failed: keyword=%s error=%s", keyword, exc)
        return None


def _cache_keyword_analysis(keyword: str, analysis: Dict[str, Any]) -> None:
    try:
        firestore.client().collection("keyword_analysis_cache").document(keyword).set(
            {
                "analysis": _safe_dict(analysis),
                "timestamp": firestore.SERVER_TIMESTAMP,
                "cachedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
    except Exception as exc:
        logger.warning("Keyword cache save failed: keyword=%s error=%s", keyword, exc)


def _sleep(ms: int) -> None:
    time.sleep(max(ms, 0) / 1000.0)


def _execute_keyword_analysis(params: Dict[str, Any]) -> None:
    task_id = str(params.get("taskId") or "")
    district = str(params.get("district") or "")
    topic = str(params.get("topic") or "")
    user_id = str(params.get("userId") or "")
    db = firestore.client()

    try:
        _update_task_status(task_id, "processing", {"progress": 10})

        cache_key = hashlib.sha256(f"{district}_{topic}".encode("utf-8")).hexdigest()
        cached_result = _check_cache(cache_key)
        if cached_result:
            _update_task_status(
                task_id,
                "completed",
                {
                    "keywords": _safe_list(cached_result.get("keywords")),
                    "fromCache": True,
                    "progress": 100,
                },
            )
            return

        _update_task_status(task_id, "processing", {"progress": 20, "stage": "기본 키워드 수집 중..."})
        base_keywords = scraper.get_naver_suggestions(topic)

        _update_task_status(task_id, "processing", {"progress": 30, "stage": "AI 키워드 확장 중..."})
        expanded_keywords = gemini_expander.expand_and_validate_keywords(
            {
                "district": district,
                "topic": topic,
                "baseKeywords": base_keywords,
                "targetCount": 30,
            }
        )

        _update_task_status(task_id, "processing", {"progress": 40, "stage": "키워드 분석 중..."})
        analyzed_keywords: List[Dict[str, Any]] = []

        for index, keyword in enumerate(expanded_keywords):
            keyword_cache = _check_keyword_cache(keyword)
            if keyword_cache:
                analyzed_keywords.append(keyword_cache)
                continue

            serp_data = scraper.analyze_naver_serp(keyword)
            result_count = scraper.get_search_result_count(keyword)

            trend_data = trends_analyzer.get_cached_trend_score(db, keyword)
            if not trend_data:
                trend_data = trends_analyzer.get_trend_score(keyword)
                trends_analyzer.cache_trend_score(db, keyword, trend_data)
                _sleep(1000)

            analysis = keyword_scorer.analyze_keyword(
                {
                    "keyword": keyword,
                    "serpData": serp_data,
                    "resultCount": result_count,
                    "trendScore": trend_data.get("trendScore", 5),
                    "district": district,
                    "topic": topic,
                }
            )
            analyzed_keywords.append(analysis)
            _cache_keyword_analysis(keyword, analysis)

            progress = 40
            if len(expanded_keywords) > 0:
                progress = 40 + math.floor(((index + 1) / len(expanded_keywords)) * 40)
            _update_task_status(
                task_id,
                "processing",
                {
                    "progress": progress,
                    "stage": f"키워드 분석 중... ({index + 1}/{len(expanded_keywords)})",
                },
            )

        _update_task_status(task_id, "processing", {"progress": 90, "stage": "최종 정리 중..."})
        analyzed_keywords.sort(key=lambda item: float(item.get("finalScore") or 0), reverse=True)
        top20_keywords = analyzed_keywords[:20]

        _save_to_cache(cache_key, {"keywords": top20_keywords})
        _update_task_status(
            task_id,
            "completed",
            {
                "keywords": top20_keywords,
                "totalAnalyzed": len(analyzed_keywords),
                "fromCache": False,
                "progress": 100,
                "completedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        )
    except Exception as exc:
        _update_task_status(
            task_id,
            "failed",
            {
                "error": str(exc),
                "errorStack": traceback.format_exc(),
            },
        )
        raise


def handle_request_keyword_analysis_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        uid = _extract_auth_uid(req)
    except Exception:
        raise https_fn.HttpsError("unauthenticated", "인증이 필요합니다.")

    data = _get_callable_data(req)
    district = str(data.get("district") or "").strip()
    topic = str(data.get("topic") or "").strip()
    if not district or not topic:
        raise https_fn.HttpsError("invalid-argument", "지역구와 주제는 필수입니다.")

    try:
        task_ref = firestore.client().collection("keyword_tasks").document()
        task_ref.set(
            {
                "userId": uid,
                "district": district,
                "topic": topic,
                "status": "pending",
                "progress": 0,
                "createdAt": firestore.SERVER_TIMESTAMP,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
        )
        task_id = task_ref.id

        task_created = _create_cloud_task(task_id, {"district": district, "topic": topic, "userId": uid})
        if not task_created:
            _process_keyword_analysis_directly(task_id, district, topic, uid)

        return {
            "success": True,
            "taskId": task_id,
            "status": "processing",
            "message": "키워드 분석이 시작되었습니다. 잠시 후 결과를 확인하세요.",
        }
    except Exception as exc:
        logger.exception("requestKeywordAnalysis failed: %s", exc)
        raise https_fn.HttpsError("internal", f"분석 요청 실패: {exc}") from exc


def handle_keyword_analysis_worker(req: https_fn.Request) -> https_fn.Response:
    if req.method != "POST":
        return https_fn.Response("Method Not Allowed", status=405)

    try:
        payload = req.get_json(silent=True) or {}
        payload = _safe_dict(payload)
        task_id = str(payload.get("taskId") or "").strip()
        district = str(payload.get("district") or "").strip()
        topic = str(payload.get("topic") or "").strip()
        user_id = str(payload.get("userId") or "").strip()

        _execute_keyword_analysis(
            {
                "taskId": task_id,
                "district": district,
                "topic": topic,
                "userId": user_id,
            }
        )
        return _json_response({"success": True, "taskId": task_id}, status=200)
    except Exception as exc:
        logger.exception("keywordAnalysisWorker failed: %s", exc)
        return _json_response({"success": False, "error": str(exc)}, status=500)


def handle_get_keyword_analysis_result_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        uid = _extract_auth_uid(req)
    except Exception:
        raise https_fn.HttpsError("unauthenticated", "인증이 필요합니다.")

    data = _get_callable_data(req)
    task_id = str(data.get("taskId") or "").strip()
    if not task_id:
        raise https_fn.HttpsError("invalid-argument", "taskId가 필요합니다.")

    try:
        task_doc = firestore.client().collection("keyword_tasks").document(task_id).get()
        if not task_doc.exists:
            raise https_fn.HttpsError("not-found", "작업을 찾을 수 없습니다.")

        task_data = _safe_dict(task_doc.to_dict())
        if str(task_data.get("userId") or "") != uid:
            raise https_fn.HttpsError("permission-denied", "권한이 없습니다.")

        return {
            "success": True,
            "taskId": task_id,
            "status": task_data.get("status"),
            "progress": int(task_data.get("progress") or 0),
            "keywords": _safe_list(task_data.get("keywords")),
            "fromCache": bool(task_data.get("fromCache")),
            "createdAt": _to_iso(task_data.get("createdAt")),
            "completedAt": task_data.get("completedAt"),
        }
    except Exception as exc:
        logger.error("getKeywordAnalysisResult failed: %s", exc)
        raise https_fn.HttpsError("internal", f"결과 조회 실패: {exc}") from exc


def handle_get_keyword_analysis_history_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        uid = _extract_auth_uid(req)
    except Exception:
        raise https_fn.HttpsError("unauthenticated", "인증이 필요합니다.")

    try:
        data = _get_callable_data(req)
        raw_limit = data.get("limit", 10)
        try:
            limit = int(raw_limit)
        except Exception:
            limit = 10
        limit = min(limit, 50)

        snapshot = (
            firestore.client()
            .collection("keyword_tasks")
            .where("userId", "==", uid)
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .get()
        )

        history: List[Dict[str, Any]] = []
        for doc in snapshot:
            row = _safe_dict(doc.to_dict())
            keywords = _safe_list(row.get("keywords"))
            history.append(
                {
                    "taskId": doc.id,
                    "district": row.get("district"),
                    "topic": row.get("topic"),
                    "status": row.get("status"),
                    "progress": int(row.get("progress") or 0),
                    "keywordCount": len(keywords),
                    "fromCache": bool(row.get("fromCache")),
                    "createdAt": _to_iso(row.get("createdAt")),
                    "completedAt": row.get("completedAt"),
                }
            )

        return {"success": True, "history": history, "total": len(history)}
    except Exception as exc:
        logger.error("getKeywordAnalysisHistory failed: %s", exc)
        raise https_fn.HttpsError("internal", f"히스토리 조회 실패: {exc}") from exc
