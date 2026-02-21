"""
Publishing bonus callable handlers migrated from Node.js.

This module currently provides:
- checkBonusEligibility
- useBonusGeneration
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from firebase_admin import firestore
from firebase_functions import https_fn

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip()
        if not text:
            return default
        return int(float(text))
    except Exception:
        return default


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


def _extract_uid(req: https_fn.CallableRequest) -> str:
    auth_ctx = req.auth
    uid = auth_ctx.uid if auth_ctx else None
    if not uid:
        raise ApiError("unauthenticated", "로그인이 필요합니다.")
    return str(uid)


def _check_bonus_eligibility_core(req: https_fn.CallableRequest) -> Dict[str, Any]:
    uid = _extract_uid(req)
    db = firestore.client()
    user_doc = db.collection("users").document(uid).get()

    if not user_doc.exists:
        raise ApiError("not-found", "사용자를 찾을 수 없습니다.")

    user_data = _safe_dict(user_doc.to_dict())
    is_admin = str(user_data.get("role") or "").strip().lower() == "admin" or user_data.get("isAdmin") is True

    if is_admin:
        return {
            "success": True,
            "data": {
                "hasBonus": True,
                "availableBonus": 999999,
                "totalBonusGenerated": 999999,
                "bonusUsed": 0,
                "accessMethod": "admin",
            },
        }

    usage = _safe_dict(user_data.get("usage"))
    bonus_generated = _safe_int(usage.get("bonusGenerated"), 0)
    bonus_used = _safe_int(usage.get("bonusUsed"), 0)
    available_bonus = max(0, bonus_generated - bonus_used)

    return {
        "success": True,
        "data": {
            "hasBonus": available_bonus > 0,
            "availableBonus": available_bonus,
            "totalBonusGenerated": bonus_generated,
            "bonusUsed": bonus_used,
        },
    }


def _use_bonus_generation_core(req: https_fn.CallableRequest) -> Dict[str, Any]:
    uid = _extract_uid(req)
    db = firestore.client()
    user_ref = db.collection("users").document(uid)
    transaction = db.transaction()

    @firestore.transactional
    def _txn_apply(tx: firestore.Transaction) -> Dict[str, Any]:
        user_doc = user_ref.get(transaction=tx)
        if not user_doc.exists:
            raise ApiError("not-found", "사용자를 찾을 수 없습니다.")

        user_data = _safe_dict(user_doc.to_dict())
        is_admin = str(user_data.get("role") or "").strip().lower() == "admin" or user_data.get("isAdmin") is True
        if is_admin:
            return {"is_admin": True}

        usage = _safe_dict(user_data.get("usage"))
        bonus_generated = _safe_int(usage.get("bonusGenerated"), 0)
        bonus_used = _safe_int(usage.get("bonusUsed"), 0)
        available_bonus = max(0, bonus_generated - bonus_used)
        if available_bonus <= 0:
            raise ApiError("failed-precondition", "사용 가능한 보너스가 없습니다.")

        tx.update(user_ref, {"usage.bonusUsed": bonus_used + 1})
        return {"is_admin": False}

    result = _txn_apply(transaction)

    if result.get("is_admin"):
        return {
            "success": True,
            "message": "관리자 권한으로 보너스를 사용했습니다.",
        }

    return {
        "success": True,
        "message": "보너스 생성을 사용했습니다.",
    }


def handle_check_bonus_eligibility_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        return _check_bonus_eligibility_core(req)
    except ApiError as exc:
        raise _to_https_error(exc) from exc
    except https_fn.HttpsError:
        raise
    except Exception as exc:
        logger.exception("checkBonusEligibility failed: %s", exc)
        raise https_fn.HttpsError("internal", "보너스 조회 중 오류가 발생했습니다.") from exc


def handle_use_bonus_generation_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        return _use_bonus_generation_core(req)
    except ApiError as exc:
        raise _to_https_error(exc) from exc
    except https_fn.HttpsError:
        raise
    except Exception as exc:
        logger.exception("useBonusGeneration failed: %s", exc)
        raise https_fn.HttpsError("internal", "보너스 사용 중 오류가 발생했습니다.") from exc
