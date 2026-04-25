"""관리자 전용 — leadership.py 데이터 조회·수정·초기화 핸들러."""

from __future__ import annotations

import logging

from firebase_admin import firestore
from firebase_functions import https_fn
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

from services.authz import is_admin_user
from agents.common.leadership import (
    _VALID_SECTIONS,
    _invalidate_cache,
    get_effective_sections,
    get_override_status,
)

logger = logging.getLogger(__name__)

_SECTIONS_COL_PATH = ("system", "leadership_overrides", "sections")


def _require_admin(req: https_fn.CallableRequest) -> str:
    """관리자 권한 확인. uid 반환."""
    auth = req.auth
    if not auth or not auth.uid:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="로그인이 필요합니다.",
        )
    uid = auth.uid
    db = firestore.client()
    snap = db.collection("users").document(uid).get()
    if not snap.exists or not is_admin_user(snap.to_dict()):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="관리자 권한이 필요합니다.",
        )
    return uid


def _section_ref(db, section: str):
    return (
        db.collection(_SECTIONS_COL_PATH[0])
        .document(_SECTIONS_COL_PATH[1])
        .collection(_SECTIONS_COL_PATH[2])
        .document(section)
    )


def handle_get_leadership_data(req: https_fn.CallableRequest) -> dict:
    """6개 섹션 전체 조회 + 오버라이드 상태 반환."""
    _require_admin(req)
    return {
        "sections": get_effective_sections(),
        "overrideStatus": get_override_status(),
    }


def handle_update_leadership_section(req: https_fn.CallableRequest) -> dict:
    """섹션 데이터 저장 (Firestore 오버라이드 기록)."""
    uid = _require_admin(req)
    data = req.data or {}
    section = data.get("section")
    payload = data.get("data")

    if section not in _VALID_SECTIONS:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message=f"유효하지 않은 섹션: {section}",
        )
    if not isinstance(payload, dict):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="data 필드는 dict여야 합니다.",
        )

    db = firestore.client()
    _section_ref(db, section).set({
        "data": payload,
        "updatedAt": SERVER_TIMESTAMP,
        "updatedBy": uid,
    })
    _invalidate_cache()
    logger.info("[LeadershipAdmin] section=%s updated by uid=%s", section, uid)
    return {"success": True, "section": section}


def handle_reset_leadership_section(req: https_fn.CallableRequest) -> dict:
    """섹션 오버라이드 삭제 (Python 기본값으로 복원)."""
    _require_admin(req)
    data = req.data or {}
    section = data.get("section")

    if section not in _VALID_SECTIONS:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message=f"유효하지 않은 섹션: {section}",
        )

    db = firestore.client()
    _section_ref(db, section).delete()
    _invalidate_cache()
    logger.info("[LeadershipAdmin] section=%s reset to default", section)
    return {"success": True, "section": section}
