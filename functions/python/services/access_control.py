
import logging
from datetime import datetime
from firebase_admin import firestore

logger = logging.getLogger(__name__)

def get_current_month_key() -> str:
    """YYYY-MM 형식의 현재 월 키 반환"""
    now = datetime.now()
    return now.strftime("%Y-%m")

def get_today_key() -> str:
    """YYYY-MM-DD 형식의 오늘 날짜 키 반환"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d")

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
    if not user_id:
        return {"allowed": False, "reason": "unauthenticated", "message": "로그인이 필요합니다."}

    try:
        user_ref = db_client.collection("users").document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return {"allowed": False, "reason": "user_not_found", "message": "사용자 정보를 찾을 수 없습니다."}
            
        user_data = user_doc.to_dict() or {}
        
        # 0. 관리자 (무제한)
        if user_data.get("role") == "admin" or user_data.get("isAdmin") is True:
            logger.info(f"✅ 관리자 권한 - 사용량 무제한: {user_id}")
            return {"allowed": True, "reason": "admin", "remaining": 999}

        # 0-1. 테스터 (무료 체험 제한 스킵, 90회/월)
        if user_data.get("role") == "tester" or user_data.get("isTester") is True:
            current_month = get_current_month_key()
            monthly_usage = user_data.get("monthlyUsage", {})
            # Firestore Map 구조에 따라 접근 방식이 다를 수 있음 (dict vs object)
            used = monthly_usage.get(current_month, {}).get("generations", 0) if isinstance(monthly_usage.get(current_month), dict) else 0
            # Node.js: used = monthlyUsage[currentMonth] || 0; (But sometimes structure differs)
            if isinstance(monthly_usage.get(current_month), int):
                 used = monthly_usage.get(current_month)

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
        subscription_status = user_data.get("subscriptionStatus", "trial")
        if subscription_status == "trial" or not subscription_status:
            # generationsRemaining 우선, 없으면 trialPostsRemaining, 그외 기본 8
            remaining = user_data.get("generationsRemaining")
            if remaining is None:
                remaining = user_data.get("trialPostsRemaining", 8)
                
            if remaining <= 0:
                return {
                    "allowed": False,
                    "reason": "trial_exhausted",
                    "message": "무료 체험 횟수를 모두 사용했습니다. 유료 플랜을 구독해주세요."
                }
            
            # 말일 체크 (trialExpiresAt)
            trial_expires_at = user_data.get("trialExpiresAt")
            if trial_expires_at:
                # Firestore Timestamp to datetime
                if hasattr(trial_expires_at, 'timestamp'):
                    expire_ts = trial_expires_at.timestamp()
                elif hasattr(trial_expires_at, 'timestamp_pb'): # protobuf
                     expire_ts = trial_expires_at.timestamp()
                else: 
                     expire_ts = trial_expires_at.timestamp() if hasattr(trial_expires_at, 'timestamp') else 0

                if expire_ts < datetime.now().timestamp():
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
        monthly_usage = user_data.get("monthlyUsage", {})
        used = 0
        if isinstance(monthly_usage.get(current_month), dict):
            used = monthly_usage.get(current_month, {}).get("generations", 0)
        elif isinstance(monthly_usage.get(current_month), int):
            used = monthly_usage.get(current_month)
            
        limit = user_data.get("monthlyLimit", 90)
        
        if used >= limit:
             return {
                "allowed": False, 
                "reason": "monthly_limit_exceeded", 
                "message": f"이번 달 생성 한도({limit}회)를 모두 사용했습니다."
            }

        return {
            "allowed": True,
            "reason": "active",
            "remaining": limit - used
        }

    except Exception as e:
        logger.error(f"Permission check failed: {e}")
        # Fail safe: DB 오류 시 일단 차단보다는 에러 리턴
        raise e

async def check_daily_limit_only_logging(user_id: str, db_client: firestore.Client):
    """하루 3회 초과 시 로그만 남김 (Node.js checkDailyLimit 대응)"""
    try:
        user_ref = db_client.collection("users").document(user_id)
        user_doc = user_ref.get()
        if not user_doc.exists: return
        
        user_data = user_doc.to_dict()
        daily_usage = user_data.get("dailyUsage", {})
        today_key = get_today_key()
        
        today_generated = daily_usage.get(today_key, 0)
        if today_generated >= 3:
            logger.warning(f"⚠️ 하루 3회 초과 생성 - {user_id} ({today_generated}회)")
            
    except Exception:
        pass
