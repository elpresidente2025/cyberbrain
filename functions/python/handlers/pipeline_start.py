# handlers/pipeline_start.py
"""
Pipeline Start Handler - POST /pipeline_start

Creates a pipeline job and triggers the first step.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from firebase_functions import https_fn

logger = logging.getLogger(__name__)


def _json_response(payload: Dict[str, Any], status: int) -> https_fn.Response:
    return https_fn.Response(
        json.dumps(payload, ensure_ascii=False, default=str),
        status=status,
        mimetype="application/json",
    )


def _extract_payload(req: https_fn.Request) -> Dict[str, Any]:
    raw = req.get_json(silent=True)
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        raw = raw["data"]
    if isinstance(raw, dict):
        return raw
    return {}


def _extract_uid(req: https_fn.Request, data: Dict[str, Any], user_profile: Dict[str, Any]) -> str:
    uid = str(data.get("uid") or data.get("userId") or user_profile.get("uid") or "").strip()
    if uid:
        return uid

    header_uid = str(req.headers.get("x-user-id") or req.headers.get("X-User-Id") or "").strip()
    if header_uid:
        return header_uid

    auth_header = req.headers.get("Authorization") or req.headers.get("authorization") or ""
    if auth_header.startswith("Bearer "):
        token = auth_header.split("Bearer ", 1)[1].strip()
        if token:
            try:
                from firebase_admin import auth

                decoded = auth.verify_id_token(token)
                token_uid = str(decoded.get("uid") or "").strip()
                if token_uid:
                    return token_uid
            except Exception as exc:
                logger.warning("Bearer token uid extraction failed: %s", exc)

    return ""


def _run_async(coro):
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _merge_profiles(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base or {})
    for key, value in (override or {}).items():
        if value is None:
            continue
        merged[key] = value
    return merged


def _normalize_text(value: Any, *, sep: str = "\n\n") -> str:
    """list/tuple 중첩 입력까지 안전하게 문자열로 정규화."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple, set)):
        parts: list[str] = []
        for item in value:
            normalized = _normalize_text(item, sep=sep)
            if normalized:
                parts.append(normalized)
        return sep.join(parts)
    return str(value).strip()


def _normalize_reference_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, (list, tuple, set)):
        text = str(value).strip()
        return [text] if text else []

    result: list[str] = []
    for item in value:
        if isinstance(item, (list, tuple, set)):
            result.extend(_normalize_reference_list(item))
            continue
        text = _normalize_text(item, sep=" ")
        if text:
            result.append(text)
    return result


def handle_start(req: https_fn.Request) -> https_fn.Response:
    """
    Start pipeline and return job_id.

    Request Body:
        {
            "topic": "...",
            "category": "activity-report",
            "keywords": ["..."],
            "uid": "...",
            "userProfile": { ... },
            "instructions": "..."
        }
    """
    # Keep locals initialized so we never hit unbound local failures.
    data: Dict[str, Any] = {}
    user_profile: Dict[str, Any] = {}

    try:
        import asyncio
        from firebase_admin import firestore

        from services.access_control import check_generation_permission
        from services.job_manager import JobManager
        from services.news_fetcher import (
            compress_news_with_ai,
            fetch_naver_news,
            should_fetch_news,
        )
        from services.posts.keyword_extractor import extract_keywords_from_instructions
        from services.posts.profile_loader import load_user_profile
        from services.task_trigger import create_step_task

        data = _extract_payload(req)

        topic = str(data.get("topic") or "").strip()
        if not topic:
            return _json_response({"error": "topic is required", "code": "INVALID_INPUT"}, 400)

        category = str(data.get("category") or "activity-report").strip() or "activity-report"
        request_keywords = data.get("keywords") if isinstance(data.get("keywords"), list) else []
        request_user_keywords = data.get("userKeywords") if isinstance(data.get("userKeywords"), list) else request_keywords

        normalized_request_keywords = [str(item).strip() for item in request_keywords if str(item).strip()]
        normalized_user_keywords = [str(item).strip() for item in request_user_keywords if str(item).strip()]
        extracted_keywords = extract_keywords_from_instructions(_normalize_text(data.get("instructions"), sep=" "))

        merged_keywords: list[str] = []
        seen_keywords: set[str] = set()
        for item in [*normalized_request_keywords, *extracted_keywords]:
            keyword = str(item or "").strip()
            if not keyword:
                continue
            lowered = keyword.lower()
            if lowered in seen_keywords:
                continue
            seen_keywords.add(lowered)
            merged_keywords.append(keyword)

        auto_keywords = [kw for kw in merged_keywords if kw not in set(normalized_user_keywords)]
        logger.info(
            "Keyword merge completed: user=%s extracted=%s merged=%s auto=%s",
            len(normalized_user_keywords),
            len(extracted_keywords),
            len(merged_keywords),
            len(auto_keywords),
        )

        input_user_profile = {}
        if isinstance(data.get("userProfile"), dict):
            input_user_profile = data.get("userProfile")
        elif isinstance(data.get("user"), dict):
            input_user_profile = data.get("user")

        uid = _extract_uid(req, data, input_user_profile)
        if not uid:
            return _json_response({"error": "User ID is required", "code": "UNAUTHENTICATED"}, 401)

        # Load profile from Firestore and merge with request payload profile.
        profile_bundle = load_user_profile(uid, category=category, topic=topic)
        loaded_user_profile = profile_bundle.get("userProfile") if isinstance(profile_bundle, dict) else {}
        if not isinstance(loaded_user_profile, dict):
            loaded_user_profile = {}

        user_profile = _merge_profiles(loaded_user_profile, input_user_profile)
        user_profile["uid"] = uid

        db = firestore.client()
        try:
            perm_result = _run_async(check_generation_permission(uid, db))
        except Exception as exc:
            logger.error("Permission check error: %s", exc)
            return _json_response(
                {"error": "권한 확인 중 오류가 발생했습니다.", "code": "INTERNAL_ERROR"},
                500,
            )

        if not perm_result.get("allowed"):
            return _json_response(
                {
                    "error": perm_result.get("message", "권한이 없습니다."),
                    "code": "PERMISSION_DENIED",
                    "reason": perm_result.get("reason"),
                    "suggestion": perm_result.get("suggestion"),
                },
                403,
            )

        logger.info(
            "Permission granted for %s: %s (remaining: %s)",
            uid,
            perm_result.get("reason"),
            perm_result.get("remaining", "N/A"),
        )

        rag_bucket_name = "ai-secretary-6e9c8.firebasestorage.app"

        async def prepare_additional_context() -> Dict[str, Any]:
            results: Dict[str, Any] = {
                "newsContext": _normalize_text(data.get("newsContext")),
                "ragContext": _normalize_text(data.get("ragContext")),
                "styleHints": {},
                "classifiedCategory": None,
            }

            tasks: dict[str, Any] = {}

            if not results["newsContext"] and should_fetch_news(category) and topic:

                async def fetch_news_task() -> str:
                    try:
                        news_items = await fetch_naver_news(topic)
                        if news_items:
                            compressed = await compress_news_with_ai(news_items)
                            if isinstance(compressed, dict):
                                return str(compressed.get("summary") or "")
                            if isinstance(compressed, str):
                                return compressed
                    except Exception as exc:
                        logger.warning("News fetch error: %s", exc)
                    return ""

                tasks["news"] = asyncio.create_task(fetch_news_task())

            bio = _normalize_text(user_profile.get("bio"))
            if bio and len(bio) > 50:

                async def style_task() -> Dict[str, Any]:
                    try:
                        from services.style_analyzer import analyze_style_from_bio

                        analyzed = await analyze_style_from_bio(bio)
                        return analyzed if isinstance(analyzed, dict) else {}
                    except Exception as exc:
                        logger.warning("Style analysis error: %s", exc)
                        return {}

                tasks["style"] = asyncio.create_task(style_task())

            if category in ["auto", "general", "activity-report"] and topic:

                async def classify_task() -> str | None:
                    try:
                        from services.topic_classifier import classify_topic

                        result = await classify_topic(topic)
                        return str(result.get("writingMethod") or "") or None
                    except Exception as exc:
                        logger.warning("Topic classification error: %s", exc)
                        return None

                tasks["classify"] = asyncio.create_task(classify_task())

            if not results["ragContext"] and topic:

                async def rag_task() -> str:
                    try:
                        from lightrag import QueryParam
                        from rag_manager import LightRAGManager

                        rag = LightRAGManager(bucket_name=rag_bucket_name)
                        await rag.initialize(mode="read")
                        rag_result = await rag.rag.query(topic, param=QueryParam(mode="hybrid"))
                        return str(rag_result or "")
                    except Exception as exc:
                        logger.warning("RAG retrieval failed (non-fatal): %s", exc)
                        return ""

                tasks["rag"] = asyncio.create_task(rag_task())

            if not tasks:
                return results

            done = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for key, value in zip(tasks.keys(), done):
                if isinstance(value, Exception):
                    logger.warning("additional context task failed (%s): %s", key, value)
                    continue
                if key == "news" and value:
                    results["newsContext"] = str(value)
                elif key == "style" and isinstance(value, dict):
                    results["styleHints"] = value
                elif key == "classify" and value:
                    results["classifiedCategory"] = str(value)
                elif key == "rag" and value:
                    results["ragContext"] = str(value)

            return results

        try:
            additional_context = _run_async(prepare_additional_context())
        except Exception as exc:
            logger.warning("Context preparation failed: %s", exc)
            additional_context = {}

        if additional_context.get("classifiedCategory"):
            category = str(additional_context["classifiedCategory"])
            logger.info("Category auto-classified to: %s", category)

        memory_context = _normalize_text(data.get("memoryContext") or profile_bundle.get("memoryContext") or "")
        personalized_hints = _normalize_text(data.get("personalizedHints") or profile_bundle.get("personalizedHints") or "")
        style_guide = _normalize_text(data.get("styleGuide") or profile_bundle.get("styleGuide") or "")

        style_fingerprint = data.get("styleFingerprint")
        if not isinstance(style_fingerprint, dict):
            style_fingerprint = profile_bundle.get("styleFingerprint")
        if not isinstance(style_fingerprint, dict):
            style_fingerprint = {}

        slogan = str(data.get("slogan") or user_profile.get("slogan") or "").strip()
        slogan_enabled = _as_bool(
            data.get("sloganEnabled"),
            bool(user_profile.get("sloganEnabled") is True),
        )
        donation_info = str(data.get("donationInfo") or user_profile.get("donationInfo") or "").strip()
        donation_enabled = _as_bool(
            data.get("donationEnabled"),
            bool(user_profile.get("donationEnabled") is True),
        )

        input_data = {
            "uid": uid,
            "topic": topic,
            "category": category,
            "subCategory": str(data.get("subCategory") or ""),
            "keywords": merged_keywords,
            "userKeywords": normalized_user_keywords,
            "autoKeywords": auto_keywords,
            "userProfile": user_profile,
            "instructions": _normalize_text(data.get("instructions")),
            "stanceText": _normalize_text(data.get("stanceText")),
            "newsDataText": _normalize_text(data.get("newsDataText")),
            "newsContext": _normalize_text(additional_context.get("newsContext", data.get("newsContext", ""))),
            "styleHints": additional_context.get("styleHints", {}),
            "styleGuide": style_guide,
            "styleFingerprint": style_fingerprint,
            "personalizedHints": personalized_hints,
            "memoryContext": memory_context,
            "ragContext": _normalize_text(additional_context.get("ragContext", data.get("ragContext", ""))),
            "background": _normalize_text(data.get("background", ""), sep="\n"),
            "references": _normalize_reference_list(data.get("references", [])),
            "factAllowlist": data.get("factAllowlist", []),
            "targetWordCount": data.get("targetWordCount", 2000),
            "slogan": slogan,
            "sloganEnabled": slogan_enabled,
            "donationInfo": donation_info,
            "donationEnabled": donation_enabled,
        }

        pipeline = str(data.get("pipeline") or "modular")

        logger.info("Starting pipeline '%s' for topic: %s...", pipeline, topic[:50])

        job_manager = JobManager()
        job_id = job_manager.create_job(input_data, pipeline)

        task_name = create_step_task(job_id, step_index=0)
        logger.info("Triggered first step for job %s: %s", job_id, task_name)

        return _json_response(
            {
                "success": True,
                "jobId": job_id,
                "status": "running",
                "message": "파이프라인이 시작되었습니다.",
            },
            202,
        )

    except Exception as exc:
        import traceback

        logger.error("Pipeline start failed: %s", exc)
        traceback.print_exc()
        return _json_response({"error": str(exc), "code": "INTERNAL_ERROR"}, 500)
