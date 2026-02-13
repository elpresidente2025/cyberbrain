import logging
from datetime import datetime, timezone
from typing import Any, Optional
from firebase_admin import firestore
from google.api_core import exceptions as gcloud_exceptions

logger = logging.getLogger(__name__)

def get_current_month_key() -> str:
    """YYYY-MM 형식의 현재 월 키 반환"""
    now = datetime.now()
    return now.strftime("%Y-%m")

def get_today_key() -> str:
    """YYYY-MM-DD 형식의 오늘 날짜 키 반환"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d")


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


def _get_monthly_used(user_data: dict, current_month: str) -> int:
    monthly_usage = user_data.get("monthlyUsage", {})
    if not isinstance(monthly_usage, dict):
        return 0

    current_value = monthly_usage.get(current_month, 0)
    if isinstance(current_value, dict):
        return _safe_int(current_value.get("generations", 0), 0)
    return _safe_int(current_value, 0)


def _normalize_subscription_status(user_data: dict) -> str:
    raw = user_data.get("subscriptionStatus")
    if raw is None:
        return "trial"
    status = str(raw).strip().lower()
    return status or "trial"


def _parse_trial_expires_at(value: Any) -> Optional[datetime]:
    if not value:
        return None

    # Firestore Timestamp / DatetimeWithNanoseconds
    if hasattr(value, "to_datetime"):
        try:
            dt = value.to_datetime()
            if dt.tzinfo:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            pass

    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
        except Exception:
            return None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            normalized = text.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            return None

    if hasattr(value, "timestamp"):
        try:
            ts = float(value.timestamp())
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        except Exception:
            return None

    return None

async def check_generation_permission(user_id: str, db_client: firestore.Client) -> dict:
    """
    콘텐츠 생성 권한 확인 (Node.js checkGenerationPermission 로직 포팅)
    
    Returns:
        {
            "allowed": bool,
            "reason": str,
            "message": str (optional),
            "remaining": int (optional)
        }
    """
    user_id = str(user_id or "").strip()
    if not user_id:
        return {"allowed": False, "reason": "unauthenticated", "message": "로그인이 필요합니다."}

    try:
        user_ref = db_client.collection("users").document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return {"allowed": False, "reason": "user_not_found", "message": "사용자 정보를 찾을 수 없습니다."}

        user_data = user_doc.to_dict() or {}
        if not isinstance(user_data, dict):
            user_data = {}

        # 0. 관리자 (무제한)
        role = str(user_data.get("role") or "").strip().lower()
        if role == "admin" or user_data.get("isAdmin") is True:
            logger.info(f"✅ 관리자 권한 - 사용량 무제한: {user_id}")
            return {"allowed": True, "reason": "admin", "remaining": 999}

        # 0-1. 테스터 (무료 체험 제한 스킵, 90회/월)
        if role == "tester" or user_data.get("isTester") is True:
            current_month = get_current_month_key()
            used = _get_monthly_used(user_data, current_month)
            limit = 90
            if used >= limit:
                return {
                    "allowed": False,
                    "reason": "monthly_limit_exceeded",
                    "message": f"이번 달 생성 한도({limit}회)를 모두 사용했습니다."
                }
            logger.info(f"✅ 테스터 권한: {user_id}, used={used}, limit={limit}")
            return {"allowed": True, "reason": "tester", "remaining": limit - used}

        # 1. 무료 체험 사용자
        subscription_status = _normalize_subscription_status(user_data)
        if subscription_status == "trial":
            # generationsRemaining 우선, 없으면 trialPostsRemaining, 그외 기본 8
            remaining_raw = user_data.get("generationsRemaining")
            if remaining_raw is None:
                remaining_raw = user_data.get("trialPostsRemaining", 8)
            remaining = _safe_int(remaining_raw, 8)

            if remaining <= 0:
                return {
                    "allowed": False,
                    "reason": "trial_exhausted",
                    "message": "무료 체험 횟수를 모두 사용했습니다. 유료 플랜을 구독해주세요."
                }
            
            # 말일 체크 (trialExpiresAt)
            trial_expires_at = _parse_trial_expires_at(user_data.get("trialExpiresAt"))
            if trial_expires_at and trial_expires_at < datetime.utcnow():
                return {
                        "allowed": False,
                        "reason": "trial_expired",
                        "message": "무료 체험 기간이 종료되었습니다."
                    }

            return {"allowed": True, "reason": "trial", "remaining": remaining}

        # 2. 구독 상태 확인 (Cancelled / Expired)
        if subscription_status in ["cancelled", "expired"]:
            return {
                "allowed": False,
                "reason": "subscription_inactive",
                "message": "구독이 만료되었습니다. 구독을 갱신해주세요."
            }

        # 3. 유료 사용자 - 우선권 확인 (district-priority.js 대응)
        # Node.js: if (userData.isPrimaryInDistrict === false) -> 차단
        is_primary = user_data.get("isPrimaryInDistrict")
        if is_primary is False:
            return {
                "allowed": False,
                "reason": "not_primary",
                "message": "현재 이 선거구는 다른 사용자가 우선권을 보유 중입니다.",
                "suggestion": "다른 선거구로 변경하시면 즉시 이용하실 수 있습니다."
            }

        # 4. 유료 사용자 - 월 사용량 확인
        current_month = get_current_month_key()
        used = _get_monthly_used(user_data, current_month)
        limit = _safe_int(user_data.get("monthlyLimit", 90), 90)
        if limit <= 0:
            limit = 90

        if used >= limit:
            return {
                "allowed": False,
                "reason": "monthly_limit_exceeded",
                "message": f"이번 달 생성 한도({limit}회)를 모두 사용했습니다."
            }

        return {
            "allowed": True,
            "reason": "primary" if is_primary is True else "legacy",
            "remaining": limit - used
        }

    except gcloud_exceptions.InvalidArgument as e:
        logger.warning("Invalid user id for permission check (%s): %s", user_id, e)
        return {
            "allowed": False,
            "reason": "invalid_user_id",
            "message": "유효하지 않은 사용자 정보입니다."
        }
    except Exception as e:
        logger.exception("Permission check failed: %s", e)
        raise

async def check_daily_limit_only_logging(user_id: str, db_client: firestore.Client):
    """하루 3회 초과 시 로그만 남김 (Node.js checkDailyLimit 대응)"""
    try:
        user_ref = db_client.collection("users").document(user_id)
        user_doc = user_ref.get()
        if not user_doc.exists: return
        
        user_data = user_doc.to_dict() or {}
        daily_usage = user_data.get("dailyUsage", {})
        if not isinstance(daily_usage, dict):
            daily_usage = {}
        today_key = get_today_key()

        today_generated = _safe_int(daily_usage.get(today_key, 0), 0)
        if today_generated >= 3:
            logger.warning(f"⚠️ 하루 3회 초과 생성 - {user_id} ({today_generated}회)")

    except Exception:
        pass
