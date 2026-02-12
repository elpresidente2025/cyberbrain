"""
선택된 원고 저장 핸들러.

Node.js `handlers/posts/save-handler.js`의 Python 포팅 버전이다.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Dict, List

from firebase_admin import auth as firebase_auth
from firebase_admin import firestore
from firebase_functions import https_fn

from services.evaluation import evaluate_content, meets_quality_threshold
from services.memory import update_memory_on_selection
from services.posts.profile_loader import end_session

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _json_response(payload: Dict[str, Any], status: int = 200) -> https_fn.Response:
    return https_fn.Response(
        json.dumps(payload, ensure_ascii=False),
        status=status,
        mimetype="application/json",
    )


def _error_response(status: int, code: str, message: str) -> https_fn.Response:
    return _json_response({"error": {"code": code, "message": message}}, status=status)


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


def _get_request_data(req: https_fn.Request) -> Dict[str, Any]:
    data = req.get_json(silent=True) or {}
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return data if isinstance(data, dict) else {}


def _get_callable_data(req: https_fn.CallableRequest) -> Dict[str, Any]:
    data = req.data
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return data if isinstance(data, dict) else {}


def _extract_uid_from_request(req: https_fn.Request, data: Dict[str, Any]) -> str:
    naver_auth = data.get("__naverAuth") if isinstance(data, dict) else None
    if isinstance(naver_auth, dict):
        uid = naver_auth.get("uid")
        provider = naver_auth.get("provider")
        if uid and provider == "naver":
            data.pop("__naverAuth", None)
            return str(uid)

    auth_header = req.headers.get("Authorization") or req.headers.get("authorization") or ""
    if auth_header.startswith("Bearer "):
        id_token = auth_header.split("Bearer ", 1)[1].strip()
        if not id_token:
            raise ApiError(401, "unauthenticated", "유효하지 않은 인증 토큰입니다.")
        try:
            verified = firebase_auth.verify_id_token(id_token)
            uid = verified.get("uid")
            if uid:
                return str(uid)
        except Exception as exc:
            logger.warning("ID 토큰 검증 실패: %s", exc)
            raise ApiError(401, "unauthenticated", "유효하지 않은 인증 토큰입니다.") from exc

    raise ApiError(401, "unauthenticated", "인증이 필요합니다.")


def _extract_uid_from_callable(req: https_fn.CallableRequest) -> str:
    auth = req.auth
    uid = auth.uid if auth else None
    if not uid:
        raise ApiError(401, "unauthenticated", "로그인이 필요합니다.")
    return uid


def _count_without_html_tags(content: str) -> int:
    text = re.sub(r"<[^>]*>", "", content or "")
    return len(text)


def _normalize_keywords(raw_keywords: Any) -> List[str]:
    if isinstance(raw_keywords, list):
        return [str(item).strip() for item in raw_keywords if str(item).strip()]
    if isinstance(raw_keywords, str):
        return [item.strip() for item in raw_keywords.split(",") if item.strip()]
    return []


def _evaluate_and_update_post(
    doc_ref,
    *,
    content: str,
    category: str,
    topic: str,
    author: str,
) -> Dict[str, Any] | None:
    try:
        evaluation = evaluate_content(
            {
                "content": content,
                "category": category,
                "topic": topic,
                "author": author,
            }
        )
        if evaluation:
            doc_ref.update(
                {
                    "evaluation": {
                        "overallScore": evaluation.get("overallScore"),
                        "scores": evaluation.get("scores", {}),
                        "summary": evaluation.get("summary", ""),
                        "evaluatedAt": firestore.SERVER_TIMESTAMP,
                    }
                }
            )
            logger.info(
                "[Evaluation] 평가 완료: score=%s meetsThreshold=%s",
                evaluation.get("overallScore"),
                meets_quality_threshold(evaluation),
            )
        return evaluation
    except Exception as exc:
        logger.warning("[Evaluation] 평가 실패(무시): %s", exc)
        return None


def _save_selected_post_core(uid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    title = str(data.get("title") or "").strip()
    content = str(data.get("content") or "").strip()
    if not title or not content:
        raise ApiError(400, "invalid-argument", "제목과 내용이 필요합니다.")

    db = firestore.client()
    session_id = data.get("sessionId")
    logger.info("saveSelectedPost 시작: uid=%s sessionId=%s", uid, session_id)

    try:
        word_count = _count_without_html_tags(content)
        post_data = {
            "userId": uid,
            "title": title,
            "topic": str(data.get("topic") or ""),
            "content": content,
            "category": str(data.get("category") or "일반"),
            "subCategory": str(data.get("subCategory") or ""),
            "keywords": data.get("keywords") or "",
            "wordCount": word_count,
            "status": "scheduled",
            "createdAt": firestore.SERVER_TIMESTAMP,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        }

        doc_ref = db.collection("posts").document()
        doc_ref.set(post_data)
        post_id = doc_ref.id

        evaluation = None
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            _evaluate_and_update_post,
            doc_ref,
            content=content,
            category=str(data.get("category") or ""),
            topic=str(data.get("topic") or title),
            author=str(data.get("authorName") or "작성자"),
        )
        try:
            evaluation = future.result(timeout=5.0)
        except FutureTimeoutError:
            logger.warning("[Evaluation] 평가 타임아웃(5초) - 메모리 업데이트는 계속")
            future.cancel()
        except Exception as exc:
            logger.warning("[Evaluation] 평가 실행 실패(무시): %s", exc)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        try:
            keywords = _normalize_keywords(data.get("keywords"))
            update_memory_on_selection(
                uid,
                {
                    "category": data.get("category"),
                    "content": content,
                    "title": title,
                    "topic": data.get("topic") or "",
                    "keywords": keywords,
                    "qualityScore": (evaluation or {}).get("overallScore"),
                },
            )
            logger.info("메모리 업데이트 완료")
        except Exception as exc:
            logger.warning("메모리 업데이트 실패(무시): %s", exc)

        applied_strategy = data.get("appliedStrategy")
        if isinstance(applied_strategy, dict) and applied_strategy.get("id"):
            try:
                strategy_id = str(applied_strategy.get("id"))
                db.collection("users").document(uid).update(
                    {
                        f"rhetoricalPreferences.{strategy_id}": firestore.Increment(1),
                    }
                )
                logger.info("수사학 전략 선호도 업데이트 완료: %s", strategy_id)
            except Exception as exc:
                logger.warning("수사학 전략 선호도 업데이트 실패(무시): %s", exc)

        end_session(uid)
        logger.info("saveSelectedPost 완료: postId=%s wordCount=%s", post_id, word_count)
        return {
            "success": True,
            "message": "원고가 성공적으로 저장되었습니다.",
            "postId": post_id,
        }
    except ApiError:
        raise
    except Exception as exc:
        logger.exception("saveSelectedPost 오류: %s", exc)
        raise ApiError(500, "internal", "원고 저장에 실패했습니다.") from exc


def handle_save_selected_post(req: https_fn.Request) -> https_fn.Response:
    if req.method == "OPTIONS":
        return https_fn.Response("", status=204)
    if req.method != "POST":
        return _error_response(405, "method-not-allowed", "POST 요청만 지원합니다.")

    try:
        data = _get_request_data(req)
        uid = _extract_uid_from_request(req, data)
        result = _save_selected_post_core(uid, data)
        return _json_response(result, status=200)
    except ApiError as exc:
        return _error_response(exc.status, exc.code, exc.message)
    except Exception as exc:  # pragma: no cover
        logger.exception("saveSelectedPost(on_request) 실패: %s", exc)
        return _error_response(500, "internal", "원고 저장 중 오류가 발생했습니다.")


def handle_save_selected_post_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        data = _get_callable_data(req)
        uid = _extract_uid_from_callable(req)
        return _save_selected_post_core(uid, data)
    except ApiError as exc:
        raise _to_https_error(exc) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("saveSelectedPost(on_call) 실패: %s", exc)
        raise https_fn.HttpsError("internal", "원고 저장 중 오류가 발생했습니다.") from exc
