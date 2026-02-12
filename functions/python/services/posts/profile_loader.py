"""
Posts Profile Loader - 세션 관련 유틸.

현재 save-handler 포팅 범위에서는 end_session만 사용한다.
"""

from __future__ import annotations

import logging

from firebase_admin import firestore

logger = logging.getLogger(__name__)


def end_session(uid: str) -> None:
    """원고 저장 시 activeGenerationSession을 삭제한다."""
    if not uid:
        return

    db = firestore.client()
    try:
        db.collection("users").document(uid).update(
            {"activeGenerationSession": firestore.DELETE_FIELD}
        )
        logger.info("생성 세션 종료 완료: uid=%s", uid)
    except Exception as exc:
        logger.warning("생성 세션 종료 실패(무시): %s", exc)

