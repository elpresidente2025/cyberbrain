"""
Per-call telemetry for Gemini calls and quality signals.

Phase A of the gemini pipeline observability plan:
- A-1 cost emit: one Firestore row per Gemini API call (tokens, latency, success).
- A-2 quality emit: one Firestore row per quality signal (score_h2, contract, repair).

Request-scoped attribution (jobId, uid, agent name) flows via contextvars set by
the pipeline step handler — no plumbing through every gemini call site.

All emits are best-effort: failures must not break the pipeline.
"""

from __future__ import annotations

import contextvars
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

GEMINI_CALLS_COLLECTION = "telemetry_gemini_calls"
QUALITY_SIGNALS_COLLECTION = "telemetry_quality_signals"

_current_job_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "telemetry_job_id", default=None
)
_current_uid: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "telemetry_uid", default=None
)
_current_agent: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "telemetry_agent", default=None
)


def set_request_context(
    *,
    job_id: Optional[str] = None,
    uid: Optional[str] = None,
    agent: Optional[str] = None,
) -> None:
    """Set per-request attribution. Pass only the fields you want to update."""
    if job_id is not None:
        _current_job_id.set(job_id)
    if uid is not None:
        _current_uid.set(uid)
    if agent is not None:
        _current_agent.set(agent)


def get_current_context() -> Dict[str, Optional[str]]:
    return {
        "jobId": _current_job_id.get(),
        "uid": _current_uid.get(),
        "agent": _current_agent.get(),
    }


def _firestore_client():
    try:
        from firebase_admin import firestore
        return firestore.client()
    except Exception as exc:
        logger.debug("[Telemetry] firestore client unavailable: %s", exc)
        return None


def emit_gemini_call(
    *,
    model: str,
    prompt_tokens: Optional[int],
    candidates_tokens: Optional[int],
    thoughts_tokens: Optional[int],
    total_tokens: Optional[int],
    duration_ms: int,
    timeout_sec: Optional[float],
    timed_out: bool,
    retries_used: int,
    success: bool,
    error_type: Optional[str] = None,
    cached: bool = False,
    cached_tokens: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Append one row to telemetry_gemini_calls. Best-effort."""
    try:
        db = _firestore_client()
        if db is None:
            return

        ctx = get_current_context()
        doc: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc),
            "jobId": ctx["jobId"],
            "uid": ctx["uid"],
            "agent": ctx["agent"],
            "model": model,
            "promptTokens": prompt_tokens,
            "candidatesTokens": candidates_tokens,
            "thoughtsTokens": thoughts_tokens,
            "totalTokens": total_tokens,
            "durationMs": int(duration_ms),
            "timeoutSec": timeout_sec,
            "timedOut": bool(timed_out),
            "retriesUsed": int(retries_used),
            "success": bool(success),
            "errorType": error_type,
            "cached": bool(cached),
            "cachedTokens": cached_tokens,
        }
        if extra:
            doc["extra"] = extra
        db.collection(GEMINI_CALLS_COLLECTION).add(doc)
    except Exception as exc:
        logger.warning("[Telemetry] gemini call emit failed: %s", exc)


def emit_quality_signal(
    *,
    signal_type: str,
    payload: Dict[str, Any],
) -> None:
    """Append one row to telemetry_quality_signals. Best-effort.

    signal_type examples: "h2_score", "contract", "repair_round", "section_length".
    payload is a free-form dict captured into Firestore.
    """
    try:
        db = _firestore_client()
        if db is None:
            return

        ctx = get_current_context()
        doc: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc),
            "jobId": ctx["jobId"],
            "uid": ctx["uid"],
            "agent": ctx["agent"],
            "signalType": signal_type,
            "payload": payload,
        }
        db.collection(QUALITY_SIGNALS_COLLECTION).add(doc)
    except Exception as exc:
        logger.warning("[Telemetry] quality emit failed: %s", exc)
