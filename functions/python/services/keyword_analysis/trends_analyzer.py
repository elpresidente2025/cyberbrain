"""
Trends analyzer service migrated from `functions/services/trends-analyzer.js`.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from firebase_admin import firestore

logger = logging.getLogger(__name__)

try:
    from pytrends.request import TrendReq
except Exception:  # pragma: no cover - optional dependency at runtime
    TrendReq = None  # type: ignore


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return default
        return float(text)
    except Exception:
        return default


def analyze_trend(values: List[Any]) -> Dict[str, Any]:
    numeric_values = [float(_safe_number(v, 0)) for v in values]
    if len(numeric_values) == 0:
        return {"trendScore": 5, "trend": "stable", "average": 0, "change": 0}

    average = sum(numeric_values) / len(numeric_values)
    recent_days = numeric_values[-3:]
    previous_days = numeric_values[:-3]

    recent_avg = sum(recent_days) / len(recent_days) if len(recent_days) > 0 else 0
    previous_avg = (sum(previous_days) / len(previous_days)) if len(previous_days) > 0 else recent_avg
    change = ((recent_avg - previous_avg) / previous_avg * 100) if previous_avg > 0 else 0

    trend = "stable"
    trend_score = 5
    if change > 20:
        trend = "rising_fast"
        trend_score = 10
    elif change > 10:
        trend = "rising"
        trend_score = 8
    elif change > 5:
        trend = "slightly_rising"
        trend_score = 7
    elif change < -20:
        trend = "falling_fast"
        trend_score = 2
    elif change < -10:
        trend = "falling"
        trend_score = 3
    elif change < -5:
        trend = "slightly_falling"
        trend_score = 4
    else:
        trend = "stable"
        trend_score = 6

    if average < 10:
        trend_score = max(1, trend_score - 2)

    return {
        "trendScore": int(trend_score),
        "trend": trend,
        "average": average,
        "change": round(change, 1),
    }


def _extract_timeline_values(keyword: str) -> List[float]:
    if TrendReq is None:
        raise RuntimeError("pytrends is not available")

    now = datetime.now()
    seven_days_ago = now - timedelta(days=7)
    timeframe = f"{seven_days_ago.strftime('%Y-%m-%d')} {now.strftime('%Y-%m-%d')}"

    client = TrendReq(hl="ko-KR", tz=540)
    client.build_payload([keyword], timeframe=timeframe, geo="KR")
    frame = client.interest_over_time()
    if frame is None or frame.empty or keyword not in frame.columns:
        return []
    return [float(_safe_number(v, 0)) for v in frame[keyword].tolist()]


def get_trend_score(keyword: str) -> Dict[str, Any]:
    try:
        values = _extract_timeline_values(keyword)
        if len(values) == 0:
            return {"trendScore": 5, "trend": "stable", "data": []}

        analysis = analyze_trend(values)
        return {
            "trendScore": analysis["trendScore"],
            "trend": analysis["trend"],
            "data": values,
            "average": analysis["average"],
            "change": analysis["change"],
        }
    except Exception as exc:
        logger.warning("Trend analysis failed for keyword=%s error=%s", keyword, exc)
        return {
            "trendScore": 5,
            "trend": "unknown",
            "data": [],
            "error": str(exc),
        }


def get_batch_trend_scores(keywords: List[str]) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    for index, keyword in enumerate(keywords):
        try:
            results[keyword] = get_trend_score(keyword)
        except Exception as exc:
            results[keyword] = {"trendScore": 5, "trend": "unknown", "error": str(exc)}
        if index < len(keywords) - 1:
            time.sleep(2)
    return results


def cache_trend_score(db: firestore.Client, keyword: str, trend_data: Dict[str, Any]) -> None:
    db.collection("trend_cache").document(keyword).set(
        {
            **trend_data,
            "timestamp": datetime.now(timezone.utc),
            "cachedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    )


def _to_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if hasattr(value, "to_datetime"):
        value = value.to_datetime()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return None


def get_cached_trend_score(db: firestore.Client, keyword: str, max_age_hours: int = 12) -> Optional[Dict[str, Any]]:
    try:
        doc = db.collection("trend_cache").document(keyword).get()
        if not doc.exists:
            return None

        data = doc.to_dict() or {}
        timestamp = _to_datetime(data.get("timestamp"))
        if timestamp is None:
            return None

        age = datetime.now(timezone.utc) - timestamp
        max_age = timedelta(hours=max_age_hours)
        if age > max_age:
            return None
        return data
    except Exception as exc:
        logger.warning("Trend cache lookup failed for keyword=%s error=%s", keyword, exc)
        return None
