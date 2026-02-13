"""
Posts profile/session loader.

This module started as a minimal `end_session` port, and now also provides
read-side profile loading/session helpers used by Python pipeline handlers.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from firebase_admin import firestore

from .personalization import generate_all_personalization_hints

logger = logging.getLogger(__name__)


def _safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _is_admin(user_profile: Dict[str, Any]) -> bool:
    role = str(user_profile.get("role", "")).strip().lower()
    return bool(user_profile.get("isAdmin") is True or role == "admin")


def _is_tester(user_profile: Dict[str, Any]) -> bool:
    role = str(user_profile.get("role", "")).strip().lower()
    return bool(user_profile.get("isTester") is True or role == "tester")


def load_user_profile(
    uid: str,
    category: str = "",
    topic: str = "",
    options: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Load user profile + personalization hints from Firestore.

    This is intentionally read-focused (usage/session counting stays in Node
    path for now) so Python pipeline can work without relying on Node-only
    profile assembly.
    """
    _ = options

    base_result = {
        "userProfile": {},
        "bioMetadata": None,
        "personalizedHints": "",
        "dailyLimitWarning": False,
        "userMetadata": None,
        "ragContext": "",
        "memoryContext": "",
        "bioContent": "",
        "bioEntries": [],
        "styleGuide": "",
        "styleFingerprint": None,
        "isAdmin": False,
        "isTester": False,
        "slogan": "",
        "sloganEnabled": False,
        "donationInfo": "",
        "donationEnabled": False,
    }

    uid = str(uid or "").strip()
    if not uid:
        return base_result

    db = firestore.client()
    user_profile: Dict[str, Any] = {}
    bio_metadata = None
    style_fingerprint = None
    bio_content = ""
    bio_entries: list[Any] = []

    try:
        user_doc = db.collection("users").document(uid).get()
        if user_doc.exists:
            user_profile = _safe_dict(user_doc.to_dict())
    except Exception as exc:
        logger.warning("[ProfileLoader] users/%s lookup failed: %s", uid, exc)

    try:
        bio_doc = db.collection("bios").document(uid).get()
        if bio_doc.exists:
            bio_data = _safe_dict(bio_doc.to_dict())
            bio_content = str(bio_data.get("content") or "").strip()
            bio_entries = _safe_list(bio_data.get("entries"))
            extracted = bio_data.get("extractedMetadata")
            bio_metadata = _safe_dict(extracted) if isinstance(extracted, dict) else None
            style_raw = bio_data.get("styleFingerprint")
            style_fingerprint = _safe_dict(style_raw) if isinstance(style_raw, dict) else None
    except Exception as exc:
        logger.warning("[ProfileLoader] bios/%s lookup failed: %s", uid, exc)

    # Merge bio fields into profile for downstream agents.
    if bio_content and not user_profile.get("bio"):
        user_profile["bio"] = bio_content
    if bio_entries and not user_profile.get("bioEntries"):
        user_profile["bioEntries"] = bio_entries

    hints_bundle = generate_all_personalization_hints(
        {
            "bioMetadata": bio_metadata,
            "styleFingerprint": style_fingerprint,
            "userProfile": user_profile,
            "category": category,
            "topic": topic,
        }
    )
    personalized_hints = str(hints_bundle.get("personalizedHints") or "").strip()
    style_guide = str(hints_bundle.get("styleGuide") or "").strip()

    if not style_guide:
        style_guide = str(user_profile.get("styleGuide") or "").strip()

    is_admin = _is_admin(user_profile)
    is_tester = _is_tester(user_profile)

    return {
        "userProfile": user_profile,
        "bioMetadata": bio_metadata,
        "personalizedHints": personalized_hints,
        "dailyLimitWarning": False,
        "userMetadata": None,
        "ragContext": "",
        "memoryContext": "",
        "bioContent": bio_content,
        "bioEntries": bio_entries,
        "styleGuide": style_guide,
        "styleFingerprint": style_fingerprint,
        "isAdmin": is_admin,
        "isTester": is_tester,
        "slogan": str(user_profile.get("slogan") or ""),
        "sloganEnabled": bool(user_profile.get("sloganEnabled") is True),
        "donationInfo": str(user_profile.get("donationInfo") or ""),
        "donationEnabled": bool(user_profile.get("donationEnabled") is True),
    }


def get_or_create_session(
    uid: str,
    is_admin: bool = False,
    is_tester: bool = False,
    category: str = "",
    topic: str = "",
) -> Dict[str, Any]:
    """
    Python-side session helper (non-destructive, basic parity with Node).
    """
    if not uid:
        return {"sessionId": None, "attempts": 0, "maxAttempts": 3, "isNewSession": False}

    if is_admin:
        return {"sessionId": "admin", "attempts": 0, "maxAttempts": 3, "isNewSession": False}

    db = firestore.client()
    user_ref = db.collection("users").document(uid)

    try:
        user_doc = user_ref.get()
        user_data = _safe_dict(user_doc.to_dict()) if user_doc.exists else {}
        active_session = _safe_dict(user_data.get("activeGenerationSession"))

        if active_session:
            attempts = int(active_session.get("attempts") or 0)
            return {
                "sessionId": str(active_session.get("id") or f"session_{uid}"),
                "attempts": attempts,
                "maxAttempts": 3,
                "isNewSession": False,
            }

        session_id = f"session_{int(time.time() * 1000)}"
        user_ref.set(
            {
                "activeGenerationSession": {
                    "id": session_id,
                    "startedAt": firestore.SERVER_TIMESTAMP,
                    "attempts": 0,
                    "category": category,
                    "topic": topic,
                    "isTester": bool(is_tester),
                }
            },
            merge=True,
        )
        return {"sessionId": session_id, "attempts": 0, "maxAttempts": 3, "isNewSession": True}
    except Exception as exc:
        logger.warning("[ProfileLoader] session lookup/create failed: %s", exc)
        return {"sessionId": None, "attempts": 0, "maxAttempts": 3, "isNewSession": False}


def increment_session_attempts(
    uid: str,
    session: Dict[str, Any] | None,
    is_admin: bool = False,
    is_tester: bool = False,
) -> Dict[str, Any]:
    """
    Increment active session attempts if possible.
    """
    session = _safe_dict(session)
    attempts_before = int(session.get("attempts") or 0)
    attempts_after = attempts_before + 1

    if not uid:
        return {**session, "attempts": attempts_after}
    if is_admin:
        return {**session, "attempts": attempts_after}

    db = firestore.client()
    user_ref = db.collection("users").document(uid)
    update_payload: Dict[str, Any] = {
        "activeGenerationSession.attempts": firestore.Increment(1)
    }

    # Keep lightweight monthly attempts tracking for tester/active users.
    try:
        user_doc = user_ref.get()
        user_data = _safe_dict(user_doc.to_dict()) if user_doc.exists else {}
        status = str(user_data.get("subscriptionStatus") or "trial").strip().lower()
        if is_tester or status == "active":
            month_key = time.strftime("%Y-%m")
            update_payload[f"monthlyUsage.{month_key}.attempts"] = firestore.Increment(1)
    except Exception:
        pass

    try:
        user_ref.update(update_payload)
    except Exception as exc:
        logger.warning("[ProfileLoader] attempts increment failed: %s", exc)

    return {**session, "attempts": attempts_after}


def end_session(uid: str) -> None:
    """Clear activeGenerationSession after save."""
    if not uid:
        return

    db = firestore.client()
    try:
        db.collection("users").document(uid).update(
            {"activeGenerationSession": firestore.DELETE_FIELD}
        )
        logger.info("session ended: uid=%s", uid)
    except Exception as exc:
        logger.warning("session end failed (ignored): %s", exc)


# JS compatibility aliases
loadUserProfile = load_user_profile
getOrCreateSession = get_or_create_session
incrementSessionAttempts = increment_session_attempts
endSession = end_session
