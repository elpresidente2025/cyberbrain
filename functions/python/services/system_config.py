from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from firebase_admin import firestore

logger = logging.getLogger(__name__)

DEFAULT_FREE_MONTHLY_LIMIT = 8


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


def get_test_mode_config(db_client: Optional[firestore.Client] = None) -> Dict[str, Any]:
    client = db_client or firestore.client()
    fallback = {
        "enabled": False,
        "freeMonthlyLimit": DEFAULT_FREE_MONTHLY_LIMIT,
    }

    try:
        config_doc = client.collection("system").document("config").get()
    except Exception as exc:
        logger.warning("system/config lookup failed: %s", exc)
        return fallback

    if not config_doc.exists:
        return fallback

    raw_config = _safe_dict(config_doc.to_dict())
    test_mode_settings = _safe_dict(raw_config.get("testModeSettings"))
    free_monthly_limit = _safe_int(
        test_mode_settings.get("freeMonthlyLimit"),
        DEFAULT_FREE_MONTHLY_LIMIT,
    )
    if free_monthly_limit <= 0:
        free_monthly_limit = DEFAULT_FREE_MONTHLY_LIMIT

    return {
        "enabled": bool(raw_config.get("testMode") is True),
        "freeMonthlyLimit": free_monthly_limit,
    }
