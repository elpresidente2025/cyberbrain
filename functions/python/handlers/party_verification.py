"""
Party verification handlers migrated from `functions/handlers/party-verification.js`.

This module provides:
- verifyPartyCertificate
- verifyPaymentReceipt
- getVerificationHistory
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

from firebase_admin import firestore
from firebase_functions import https_fn

logger = logging.getLogger(__name__)

YEAR_SUFFIX = "\uB144"  # 년
QUARTER_SUFFIX = "\uBD84\uAE30"  # 분기


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if hasattr(value, "to_datetime"):
        value = value.to_datetime()
    if isinstance(value, datetime):
        return value
    return None


def _to_iso(value: Any) -> Optional[str]:
    dt = _to_datetime(value)
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def _get_callable_data(req: https_fn.CallableRequest) -> Dict[str, Any]:
    data = req.data
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    return _safe_dict(data)


def _get_current_quarter() -> str:
    now = datetime.now()
    year = now.year
    month = now.month
    if month <= 3:
        quarter = 1
    elif month <= 6:
        quarter = 2
    elif month <= 9:
        quarter = 3
    else:
        quarter = 4
    return f"{year}{YEAR_SUFFIX} {quarter}{QUARTER_SUFFIX}"


def _get_quarter_from_month(month_zero_based: int) -> int:
    if month_zero_based <= 2:
        return 1
    if month_zero_based <= 5:
        return 2
    if month_zero_based <= 8:
        return 3
    return 4


def _get_next_quarter(current_quarter: str) -> str:
    match = re.search(r"(\d{4})\D*([1-4])", str(current_quarter or ""))
    if not match:
        return ""

    year = int(match.group(1))
    quarter = int(match.group(2))
    quarter += 1
    if quarter > 4:
        quarter = 1
        year += 1
    return f"{year}{YEAR_SUFFIX} {quarter}{QUARTER_SUFFIX}"


def _get_next_quarter_start_month(current_month: int) -> int:
    if current_month < 3:
        return 4
    if current_month < 6:
        return 7
    if current_month < 9:
        return 10
    return 1


def _validate_payment_month(payment_year_month: str, current_quarter: str) -> bool:
    if not payment_year_month or not current_quarter:
        return False

    quarter_match = re.search(r"(\d{4})\D*([1-4])", str(current_quarter))
    if not quarter_match:
        return False
    year = int(quarter_match.group(1))
    quarter = int(quarter_match.group(2))

    payment_match = re.search(r"(\d{4})-(\d{2})", str(payment_year_month))
    if not payment_match:
        return False
    payment_year = int(payment_match.group(1))
    payment_month = int(payment_match.group(2))
    if payment_year != year:
        return False

    valid_months = []
    if quarter == 1:
        valid_months = [1, 2, 3]
    elif quarter == 2:
        valid_months = [4, 5, 6]
    elif quarter == 3:
        valid_months = [7, 8, 9]
    elif quarter == 4:
        valid_months = [10, 11, 12]
    return payment_month in valid_months


def _save_verification_result(user_id: str, verification_data: Dict[str, Any]) -> None:
    db = firestore.client()
    verification_ref = db.collection("users").document(user_id).collection("verifications").document()
    verification_ref.set(verification_data)

    db.collection("users").document(user_id).update(
        {
            "verificationStatus": verification_data.get("status"),
            "lastVerification": {
                "quarter": verification_data.get("quarter"),
                "status": verification_data.get("status"),
                "verifiedAt": verification_data.get("verifiedAt"),
            },
        }
    )


def _save_verification_request(user_id: str, request_data: Dict[str, Any]) -> None:
    db = firestore.client()
    request_ref = db.collection("verification_requests").document()
    request_ref.set({"userId": user_id, **request_data})

    db.collection("users").document(user_id).update(
        {
            "verificationStatus": "pending_manual_review",
            "lastVerification": {
                "quarter": request_data.get("quarter") or _get_current_quarter(),
                "status": "pending_manual_review",
                "requestedAt": firestore.SERVER_TIMESTAMP,
                "type": request_data.get("type"),
            },
        }
    )


def _check_quarterly_verification(user_id: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
    db = firestore.client()
    now = datetime.now()
    current_month = now.month - 1
    current_quarter = _get_current_quarter()

    quarter_start_months = [0, 3, 6, 9]
    is_quarter_start_month = current_month in quarter_start_months

    created_at = _to_datetime(_safe_dict(user_data).get("createdAt"))
    if created_at:
        join_year = created_at.year
        join_month = created_at.month - 1
        join_quarter = _get_quarter_from_month(join_month)
        joined_in_quarter_start_month = join_month in quarter_start_months
        if joined_in_quarter_start_month:
            join_quarter_str = f"{join_year}{YEAR_SUFFIX} {join_quarter}{QUARTER_SUFFIX}"
            if join_quarter_str == current_quarter:
                return {
                    "needsVerification": False,
                    "reason": f"{join_month + 1}월 분기 시작월 가입으로 {current_quarter} 인증이 면제됩니다.",
                    "nextQuarter": _get_next_quarter(current_quarter),
                }

    last_verification = _safe_dict(_safe_dict(user_data).get("lastVerification"))
    if (
        str(last_verification.get("quarter") or "") == current_quarter
        and str(last_verification.get("status") or "") == "verified"
    ):
        return {
            "needsVerification": False,
            "reason": f"{current_quarter} 인증이 이미 완료되었습니다.",
            "nextQuarter": _get_next_quarter(current_quarter),
        }

    if not is_quarter_start_month:
        has_any_verification = (
            db.collection("users")
            .document(user_id)
            .collection("verifications")
            .limit(1)
            .get()
        )
        if len(has_any_verification) > 0:
            next_quarter_month = _get_next_quarter_start_month(current_month)
            return {
                "needsVerification": False,
                "reason": f"분기별 인증은 {next_quarter_month}월에 진행합니다.",
                "nextQuarter": _get_next_quarter(current_quarter),
            }

    return {
        "needsVerification": True,
        "reason": "당적 인증이 필요합니다.",
        "currentQuarter": current_quarter,
    }


def handle_verify_party_certificate_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        data = _get_callable_data(req)
        user_id = str(data.get("userId") or "").strip()
        base64_data = str(data.get("base64Data") or "").strip()
        file_name = str(data.get("fileName") or "").strip()
        _image_format = str(data.get("imageFormat") or "jpg")

        if not user_id:
            raise https_fn.HttpsError("invalid-argument", "사용자 ID가 필요합니다.")
        if not base64_data or not file_name:
            raise https_fn.HttpsError("invalid-argument", "파일 데이터와 파일명이 필요합니다.")

        user_doc = firestore.client().collection("users").document(user_id).get()
        user_data = _safe_dict(user_doc.to_dict()) if user_doc.exists else {}
        storage_path = f"party-certificates/{user_id}/{file_name}"

        verification_check = _check_quarterly_verification(user_id, user_data)
        if not verification_check.get("needsVerification"):
            return {
                "success": True,
                "exempted": True,
                "message": verification_check.get("reason"),
                "nextVerificationQuarter": verification_check.get("nextQuarter"),
            }

        quarter = _get_current_quarter()
        _save_verification_result(
            user_id,
            {
                "type": "party_certificate",
                "quarter": quarter,
                "status": "verified",
                "method": "auto_approval",
                "storagePath": storage_path,
                "verifiedAt": firestore.SERVER_TIMESTAMP,
            },
        )
        return {
            "success": True,
            "message": "당적증명서 인증이 완료되었습니다.",
            "quarter": quarter,
        }
    except Exception as exc:
        logger.exception("verifyPartyCertificate failed: %s", exc)
        raise https_fn.HttpsError("internal", "인증 처리 중 오류가 발생했습니다.", str(exc)) from exc


def handle_verify_payment_receipt_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        data = _get_callable_data(req)
        user_id = str(data.get("userId") or "").strip()
        base64_data = str(data.get("base64Data") or "").strip()
        file_name = str(data.get("fileName") or "").strip()
        _image_format = str(data.get("imageFormat") or "jpg")

        if not user_id:
            raise https_fn.HttpsError("invalid-argument", "사용자 ID가 필요합니다.")
        if not base64_data or not file_name:
            raise https_fn.HttpsError("invalid-argument", "파일 데이터와 파일명이 필요합니다.")

        storage_path = f"payment-receipts/{user_id}/{file_name}"
        current_quarter = _get_current_quarter()
        _save_verification_result(
            user_id,
            {
                "type": "payment_receipt",
                "quarter": current_quarter,
                "status": "verified",
                "method": "auto_approval",
                "storagePath": storage_path,
                "verifiedAt": firestore.SERVER_TIMESTAMP,
            },
        )
        return {
            "success": True,
            "message": "당비 납부 영수증 인증이 완료되었습니다.",
            "quarter": current_quarter,
        }
    except Exception as exc:
        logger.exception("verifyPaymentReceipt failed: %s", exc)
        raise https_fn.HttpsError("internal", "인증 처리 중 오류가 발생했습니다.", str(exc)) from exc


def handle_get_verification_history_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        auth_ctx = req.auth
        if not auth_ctx:
            raise https_fn.HttpsError("unauthenticated", "로그인이 필요합니다.")
        user_id = str(auth_ctx.uid)

        snapshot = (
            firestore.client()
            .collection("users")
            .document(user_id)
            .collection("verifications")
            .order_by("verifiedAt", direction=firestore.Query.DESCENDING)
            .limit(20)
            .get()
        )

        history = []
        for doc in snapshot:
            row = _safe_dict(doc.to_dict())
            history.append(
                {
                    "id": doc.id,
                    "quarter": row.get("quarter"),
                    "status": row.get("status"),
                    "method": row.get("method"),
                    "type": row.get("type"),
                    "verifiedAt": _to_iso(row.get("verifiedAt")),
                    "partyInfo": row.get("partyInfo"),
                    "paymentInfo": row.get("paymentInfo"),
                }
            )
        return {"success": True, "history": history}
    except Exception as exc:
        logger.exception("getVerificationHistory failed: %s", exc)
        raise https_fn.HttpsError("internal", "인증 이력 조회 중 오류가 발생했습니다.", str(exc)) from exc


# Keep helper functions exported for parity with Node module internals if needed.
validate_payment_month = _validate_payment_month
save_verification_request = _save_verification_request
