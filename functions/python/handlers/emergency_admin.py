"""
Emergency admin restore callable handler migrated from Node.js.

This module currently provides:
- emergencyRestoreAdmin
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from firebase_admin import firestore
from firebase_functions import https_fn

logger = logging.getLogger(__name__)


def _emergency_restore_admin_core() -> Dict[str, Any]:
    new_uid = "wRk4hx6x8QdTQYoZQu8l"
    old_uid = "DIedFGGUOzmoVU1rUWeF"

    admin_only_data = {
        "role": "admin",
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }

    db = firestore.client()
    db.collection("users").document(new_uid).set(admin_only_data, merge=True)
    db.collection("users").document(old_uid).set(admin_only_data, merge=True)

    return {
        "success": True,
        "message": "관리자 권한 복구 완료",
        "uids": [new_uid, old_uid],
    }


def handle_emergency_restore_admin_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    _ = req
    try:
        return _emergency_restore_admin_core()
    except Exception as exc:
        logger.exception("emergencyRestoreAdmin failed: %s", exc)
        raise https_fn.HttpsError("internal", f"복구 실패: {exc}") from exc
