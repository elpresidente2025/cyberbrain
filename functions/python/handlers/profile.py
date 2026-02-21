"""
Profile callable handlers migrated from Node.js.

This module currently provides:
- getUserProfile
- updateProfile
- checkDistrictAvailability
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from firebase_admin import firestore
from firebase_functions import https_fn

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


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


def _to_https_error(error: ApiError) -> https_fn.HttpsError:
    valid_codes = {
        "cancelled",
        "unknown",
        "invalid-argument",
        "deadline-exceeded",
        "not-found",
        "already-exists",
        "permission-denied",
        "resource-exhausted",
        "failed-precondition",
        "aborted",
        "out-of-range",
        "unimplemented",
        "internal",
        "unavailable",
        "data-loss",
        "unauthenticated",
    }
    code = error.code if error.code in valid_codes else "internal"
    return https_fn.HttpsError(code, error.message)


def _extract_uid(req: https_fn.CallableRequest) -> str:
    auth_ctx = req.auth
    uid = auth_ctx.uid if auth_ctx else None
    if not uid:
        raise ApiError("unauthenticated", "로그인이 필요합니다.")
    return str(uid)


def _get_callable_data(req: https_fn.CallableRequest) -> Dict[str, Any]:
    data = req.data
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return data if isinstance(data, dict) else {}


def _normalize_gender(value: Any) -> Any:
    if value is None:
        return value
    raw = str(value).strip()
    if not raw:
        return raw

    upper = raw.upper()
    if upper in {"M", "MALE"} or raw in {"남", "남자", "남성"}:
        return "남성"
    if upper in {"F", "FEMALE"} or raw in {"여", "여자", "여성"}:
        return "여성"
    return raw


def _derive_age_fields(profile: Dict[str, Any]) -> None:
    age = profile.get("age")
    age_decade = profile.get("ageDecade")

    if not age_decade and age is not None:
        m_age = re.match(r"^\s*(\d{2})\s*-\s*\d{2}\s*$", str(age))
        if m_age:
            profile["ageDecade"] = f"{m_age.group(1)}대"

    if not age and age_decade is not None:
        m_decade = re.match(r"^\s*(\d{2})\s*대\s*$", str(age_decade))
        if m_decade:
            start = int(m_decade.group(1))
            profile["age"] = f"{start}-{start + 9}"


def _normalize_district_token(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", "", text)
    return "".join(ch for ch in text if ch.isalnum())


def _canonical_position(position: Any) -> str:
    text = str(position or "")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"(예비|현역|후보|candidate|incumbent)", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()

    if re.search(r"국회|국회의원", text):
        return "국회의원"
    if re.search(r"광역|시의원|도의원", text):
        return "광역의원"
    if re.search(r"기초|구의원|군의원", text):
        return "기초의원"
    if "광역자치단체장" in text:
        return "광역자치단체장"
    if "기초자치단체장" in text:
        return "기초자치단체장"

    return text or "기초의원"


def _district_key_from_parts(parts: Dict[str, Any]) -> str:
    position = _canonical_position(parts.get("position"))
    region_metro = parts.get("regionMetro")
    region_local = parts.get("regionLocal")
    electoral_district = parts.get("electoralDistrict")

    if position == "광역자치단체장":
        pieces = [_normalize_district_token(position), _normalize_district_token(region_metro)]
        if any(not p for p in pieces):
            raise ApiError("invalid-argument", "광역자치단체장은 position, regionMetro가 필요합니다.")
        return "__".join(pieces)

    if position == "기초자치단체장":
        pieces = [
            _normalize_district_token(position),
            _normalize_district_token(region_metro),
            _normalize_district_token(region_local),
        ]
        if any(not p for p in pieces):
            raise ApiError("invalid-argument", "기초자치단체장은 position, regionMetro, regionLocal이 필요합니다.")
        return "__".join(pieces)

    pieces = [
        _normalize_district_token(position),
        _normalize_district_token(region_metro),
        _normalize_district_token(region_local),
        _normalize_district_token(electoral_district),
    ]
    if any(not p for p in pieces):
        raise ApiError(
            "invalid-argument",
            "선거구 키 생성에는 position, regionMetro, regionLocal, electoralDistrict가 필요합니다.",
        )
    return "__".join(pieces)


def _member_is_paid_active(member: Dict[str, Any]) -> bool:
    if member.get("paidAt") is None:
        return False
    status = str(member.get("subscriptionStatus") or "").strip().lower()
    return status == "active"


def _member_priority_sort_key(member: Dict[str, Any]) -> tuple[float, str]:
    priority = member.get("priority")
    priority_value = float(_safe_int(priority, 10**9)) if priority is not None else float(10**9)
    user_id = str(member.get("userId") or "")
    return (priority_value, user_id)


def _count_paid_members(members: List[Dict[str, Any]]) -> int:
    return sum(1 for m in members if _member_is_paid_active(m))


def _count_waitlist_members(members: List[Dict[str, Any]]) -> int:
    return max(0, len(members) - _count_paid_members(members))


def _remove_user_from_district_claim(db: firestore.Client, uid: str, district_key: str) -> None:
    doc_ref = db.collection("district_claims").document(district_key)
    doc = doc_ref.get()
    if not doc.exists:
        return

    data = _safe_dict(doc.to_dict())
    members = [_safe_dict(m) for m in _safe_list(data.get("members"))]

    removed_member: Optional[Dict[str, Any]] = None
    kept_members: List[Dict[str, Any]] = []
    for member in members:
        member_uid = str(member.get("userId") or "")
        if member_uid == uid and removed_member is None:
            removed_member = member
            continue
        kept_members.append(member)

    if removed_member is None:
        return

    if not kept_members:
        doc_ref.delete()
        return

    previous_primary = str(data.get("primaryUserId") or "")
    was_primary = previous_primary == uid or bool(removed_member.get("isPrimary"))
    new_primary: Optional[str] = previous_primary if previous_primary and previous_primary != uid else None

    if was_primary:
        for member in kept_members:
            member["isPrimary"] = False

        candidates = [m for m in kept_members if _member_is_paid_active(m)]
        if candidates:
            candidates.sort(key=_member_priority_sort_key)
            new_primary = str(candidates[0].get("userId") or "")
            for member in kept_members:
                if str(member.get("userId") or "") == new_primary:
                    member["isPrimary"] = True
                    break
        else:
            new_primary = None

    update_payload = {
        "members": kept_members,
        "primaryUserId": new_primary,
        "totalMembers": len(kept_members),
        "paidMembers": _count_paid_members(kept_members),
        "waitlistCount": _count_waitlist_members(kept_members),
        "lastUpdated": firestore.SERVER_TIMESTAMP,
    }
    doc_ref.set(update_payload, merge=True)


def _add_user_to_district_claim(
    db: firestore.Client,
    uid: str,
    district_key: str,
    user_data: Dict[str, Any],
) -> None:
    doc_ref = db.collection("district_claims").document(district_key)
    doc = doc_ref.get()
    now = datetime.now(timezone.utc)

    subscription_status = str(user_data.get("subscriptionStatus") or "trial").strip().lower()
    paid_at = user_data.get("paidAt")
    is_paid_active = subscription_status == "active" and paid_at is not None

    new_member: Dict[str, Any] = {
        "userId": uid,
        "registeredAt": now,
        "paidAt": paid_at if is_paid_active else None,
        "subscriptionStatus": "active" if is_paid_active else "trial",
        "priority": None,
        "isPrimary": False,
    }

    if not doc.exists:
        if is_paid_active:
            new_member["priority"] = 1
            new_member["isPrimary"] = True

        members = [new_member]
        doc_ref.set(
            {
                "members": members,
                "primaryUserId": uid if new_member["isPrimary"] else None,
                "totalMembers": 1,
                "paidMembers": _count_paid_members(members),
                "waitlistCount": _count_waitlist_members(members),
                "createdAt": firestore.SERVER_TIMESTAMP,
                "lastUpdated": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        return

    data = _safe_dict(doc.to_dict())
    members = [_safe_dict(m) for m in _safe_list(data.get("members"))]

    if any(str(m.get("userId") or "") == uid for m in members):
        return

    primary_user_id = str(data.get("primaryUserId") or "")
    if is_paid_active:
        active_paid = [m for m in members if _member_is_paid_active(m)]
        new_member["priority"] = len(active_paid) + 1
        if not primary_user_id and len(active_paid) == 0:
            new_member["isPrimary"] = True
            primary_user_id = uid

    members.append(new_member)
    doc_ref.set(
        {
            "members": members,
            "primaryUserId": primary_user_id or None,
            "totalMembers": len(members),
            "paidMembers": _count_paid_members(members),
            "waitlistCount": _count_waitlist_members(members),
            "lastUpdated": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def _sync_user_district_claims(
    db: firestore.Client,
    uid: str,
    old_district_key: Optional[str],
    new_district_key: Optional[str],
    user_data: Dict[str, Any],
) -> None:
    old_key = str(old_district_key or "").strip()
    new_key = str(new_district_key or "").strip()
    if not new_key or new_key == old_key:
        return

    if old_key:
        _remove_user_from_district_claim(db, uid, old_key)
    _add_user_to_district_claim(db, uid, new_key, user_data)


def _to_iso(value: datetime) -> str:
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _serialize_for_callable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if hasattr(value, "to_datetime"):
        try:
            return _to_iso(value.to_datetime())
        except Exception:
            return str(value)

    if isinstance(value, datetime):
        return _to_iso(value)

    if isinstance(value, dict):
        return {str(k): _serialize_for_callable(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_serialize_for_callable(v) for v in value]

    return str(value)


def _get_user_profile_core(req: https_fn.CallableRequest) -> Dict[str, Any]:
    uid = _extract_uid(req)
    auth_token = _safe_dict(getattr(req.auth, "token", {}) if req.auth else {})

    profile: Dict[str, Any] = {
        "name": str(auth_token.get("name") or ""),
        "position": "",
        "regionMetro": "",
        "regionLocal": "",
        "electoralDistrict": "",
        "status": "현역",
        "bio": "",
        "targetElection": None,
    }

    db = firestore.client()
    user_doc = db.collection("users").document(uid).get()
    if user_doc.exists:
        user_data = _safe_dict(user_doc.to_dict())
        profile = {**profile, **user_data}

    _derive_age_fields(profile)
    profile["gender"] = _normalize_gender(profile.get("gender"))

    bio_doc = db.collection("bios").document(uid).get()
    if bio_doc.exists:
        bio_data = _safe_dict(bio_doc.to_dict())
        bio_content = bio_data.get("content")
        if isinstance(bio_content, str):
            profile["bio"] = bio_content

        bio_entries = bio_data.get("entries")
        if isinstance(bio_entries, list):
            profile["bioEntries"] = bio_entries

    logger.info("getUserProfile success uid=%s", uid)
    return {
        "success": True,
        "profile": _serialize_for_callable(profile),
    }


def _update_profile_core(req: https_fn.CallableRequest) -> Dict[str, Any]:
    uid = _extract_uid(req)
    profile_data = _get_callable_data(req)
    if not isinstance(profile_data, dict):
        raise ApiError("invalid-argument", "올바른 프로필 데이터를 입력해 주세요.")

    allowed_fields = [
        "name",
        "position",
        "regionMetro",
        "regionLocal",
        "electoralDistrict",
        "status",
        "bio",
        "customTitle",
        "bioEntries",
        "targetElection",
        "ageDecade",
        "ageDetail",
        "familyStatus",
        "backgroundCareer",
        "localConnection",
        "politicalExperience",
        "committees",
        "customCommittees",
        "constituencyType",
        "gender",
        "slogan",
        "sloganEnabled",
        "donationInfo",
        "donationEnabled",
    ]

    sanitized: Dict[str, Any] = {}
    for field in allowed_fields:
        if field in profile_data:
            sanitized[field] = profile_data[field]

    _derive_age_fields(sanitized)
    if "gender" in sanitized:
        sanitized["gender"] = _normalize_gender(sanitized.get("gender"))

    db = firestore.client()
    user_ref = db.collection("users").document(uid)
    user_doc = user_ref.get()
    current_user = _safe_dict(user_doc.to_dict()) if user_doc.exists else {}

    next_fields = {
        "position": sanitized.get("position", current_user.get("position")),
        "regionMetro": sanitized.get("regionMetro", current_user.get("regionMetro")),
        "regionLocal": sanitized.get("regionLocal", current_user.get("regionLocal")),
        "electoralDistrict": sanitized.get("electoralDistrict", current_user.get("electoralDistrict")),
    }

    old_district_key = current_user.get("districtKey")
    new_district_key: Optional[str] = None
    if all(next_fields.get(k) for k in ("position", "regionMetro", "regionLocal", "electoralDistrict")):
        new_district_key = _district_key_from_parts(next_fields)

    if new_district_key and new_district_key != old_district_key:
        merged_user_for_claim = {**current_user, **sanitized}
        _sync_user_district_claims(
            db,
            uid,
            str(old_district_key or ""),
            new_district_key,
            merged_user_for_claim,
        )

    bio = str(sanitized.get("bio") or "").strip() if "bio" in sanitized else ""
    raw_bio_entries = sanitized.get("bioEntries")
    bio_entries = raw_bio_entries if isinstance(raw_bio_entries, list) else None
    is_active = False

    if bio or bio_entries is not None:
        bio_ref = db.collection("bios").document(uid)
        bio_doc = bio_ref.get()
        current_bio = _safe_dict(bio_doc.to_dict()) if bio_doc.exists else {}
        current_version = _safe_int(current_bio.get("version"), 0)

        bio_payload: Dict[str, Any] = {
            "userId": uid,
            "version": current_version + 1,
            "updatedAt": firestore.SERVER_TIMESTAMP,
            "createdAt": current_bio.get("createdAt") or firestore.SERVER_TIMESTAMP,
            "metadataStatus": "pending",
            "usage": current_bio.get("usage")
            or {
                "generatedPostsCount": 0,
                "avgQualityScore": 0,
                "lastUsedAt": None,
            },
        }

        if bio:
            bio_payload["content"] = bio
        if bio_entries is not None:
            bio_payload["entries"] = bio_entries

        bio_ref.set(bio_payload, merge=True)
        is_active = True
    else:
        existing_bio_doc = db.collection("bios").document(uid).get()
        existing_bio = _safe_dict(existing_bio_doc.to_dict()) if existing_bio_doc.exists else {}
        has_bio_content = bool(str(existing_bio.get("content") or "").strip())
        has_bio_entries = len(_safe_list(existing_bio.get("entries"))) > 0
        is_active = has_bio_content or has_bio_entries

    for restricted in ("isAdmin", "role", "bio", "bioEntries"):
        sanitized.pop(restricted, None)

    update_payload: Dict[str, Any] = {
        **sanitized,
        "isActive": is_active,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }

    if new_district_key:
        update_payload["districtKey"] = new_district_key
    elif old_district_key:
        update_payload["districtKey"] = old_district_key

    user_ref.set(update_payload, merge=True)

    return {
        "success": True,
        "message": "프로필이 성공적으로 업데이트되었습니다.",
        "isActive": is_active,
    }


def _check_district_availability_core(req: https_fn.CallableRequest) -> Dict[str, Any]:
    data = _get_callable_data(req)
    position = str(data.get("position") or "").strip()
    region_metro = str(data.get("regionMetro") or "").strip()
    region_local = str(data.get("regionLocal") or "").strip()
    electoral_district = str(data.get("electoralDistrict") or "").strip()

    if not position or not region_metro or not region_local or not electoral_district:
        raise ApiError("invalid-argument", "지역, 선거구, 직책을 모두 입력해 주세요.")

    district_key = _district_key_from_parts(
        {
            "position": position,
            "regionMetro": region_metro,
            "regionLocal": region_local,
            "electoralDistrict": electoral_district,
        }
    )

    db = firestore.client()
    district_doc = db.collection("district_claims").document(district_key).get()

    if not district_doc.exists:
        has_primary = False
        message = "사용 가능한 선거구입니다."
    else:
        district_data = _safe_dict(district_doc.to_dict())
        has_primary = bool(district_data.get("primaryUserId"))
        if not has_primary:
            members = [_safe_dict(m) for m in _safe_list(district_data.get("members"))]
            has_primary = any(bool(m.get("isPrimary")) for m in members)

        message = (
            "해당 선거구에 이미 다른 사용자가 있습니다. 가입 후 결제 시 대기 순번이 부여됩니다."
            if has_primary
            else "가입 후 먼저 결제하면 우선권을 획득할 수 있습니다."
        )

    return {
        "success": True,
        "available": True,
        "hasPrimary": has_primary,
        "message": message,
    }


def _district_status_summary(db: firestore.Client, district_key: str) -> tuple[bool, str]:
    district_doc = db.collection("district_claims").document(district_key).get()
    if not district_doc.exists:
        return False, "사용 가능한 선거구입니다."

    district_data = _safe_dict(district_doc.to_dict())
    has_primary = bool(district_data.get("primaryUserId"))
    if not has_primary:
        members = [_safe_dict(m) for m in _safe_list(district_data.get("members"))]
        has_primary = any(bool(m.get("isPrimary")) for m in members)

    message = (
        "해당 선거구에 이미 다른 사용자가 있습니다. 가입 후 결제 시 대기 순번이 부여됩니다."
        if has_primary
        else "가입 후 먼저 결제하면 우선권을 획득할 수 있습니다."
    )
    return has_primary, message


def _end_of_month_utc(now_utc: datetime) -> datetime:
    year = now_utc.year
    month = now_utc.month
    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return next_month - timedelta(seconds=1)


def _register_with_district_check_core(req: https_fn.CallableRequest) -> Dict[str, Any]:
    uid = _extract_uid(req)
    data = _get_callable_data(req)
    profile_data = _safe_dict(data.get("profileData"))
    if not profile_data:
        raise ApiError("invalid-argument", "프로필 데이터가 필요합니다.")

    position = str(profile_data.get("position") or "").strip()
    region_metro = str(profile_data.get("regionMetro") or "").strip()
    region_local = str(profile_data.get("regionLocal") or "").strip()
    electoral_district = str(profile_data.get("electoralDistrict") or "").strip()
    if not position or not region_metro or not region_local or not electoral_district:
        raise ApiError("invalid-argument", "직책과 지역 정보를 모두 입력해 주세요.")

    district_key = _district_key_from_parts(
        {
            "position": position,
            "regionMetro": region_metro,
            "regionLocal": region_local,
            "electoralDistrict": electoral_district,
        }
    )

    db = firestore.client()
    _has_primary, district_message = _district_status_summary(db, district_key)

    user_ref = db.collection("users").document(uid)
    user_doc = user_ref.get()
    current_user = _safe_dict(user_doc.to_dict()) if user_doc.exists else {}

    _add_user_to_district_claim(
        db,
        uid,
        district_key,
        {
            **current_user,
            **profile_data,
            "subscriptionStatus": "trial",
            "paidAt": None,
        },
    )

    bio = str(profile_data.get("bio") or "").strip()
    raw_bio_entries = profile_data.get("bioEntries")
    bio_entries = raw_bio_entries if isinstance(raw_bio_entries, list) else None
    is_active = bool(bio)

    if bio or bio_entries is not None:
        bio_ref = db.collection("bios").document(uid)
        bio_doc = bio_ref.get()
        current_bio = _safe_dict(bio_doc.to_dict()) if bio_doc.exists else {}
        current_version = _safe_int(current_bio.get("version"), 0)

        bio_payload: Dict[str, Any] = {
            "userId": uid,
            "version": current_version + 1,
            "updatedAt": firestore.SERVER_TIMESTAMP,
            "createdAt": current_bio.get("createdAt") or firestore.SERVER_TIMESTAMP,
            "metadataStatus": "pending",
            "usage": current_bio.get("usage")
            or {
                "generatedPostsCount": 0,
                "avgQualityScore": 0,
                "lastUsedAt": None,
            },
        }
        if bio:
            bio_payload["content"] = bio
        if bio_entries is not None:
            bio_payload["entries"] = bio_entries

        bio_ref.set(bio_payload, merge=True)

    sanitized = dict(profile_data)
    for restricted in ("isAdmin", "role", "bio", "bioEntries"):
        sanitized.pop(restricted, None)

    _derive_age_fields(sanitized)
    if "gender" in sanitized:
        sanitized["gender"] = _normalize_gender(sanitized.get("gender"))

    trial_expires_at = _end_of_month_utc(datetime.now(timezone.utc))
    user_ref.set(
        {
            **sanitized,
            "isActive": is_active,
            "districtKey": district_key,
            "districtPriority": None,
            "isPrimaryInDistrict": False,
            "districtStatus": "trial",
            "subscriptionStatus": "trial",
            "paidAt": None,
            "trialPostsRemaining": 8,
            "generationsRemaining": 8,
            "trialExpiresAt": trial_expires_at,
            "monthlyLimit": 8,
            "monthlyUsage": {},
            "activeGenerationSession": None,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )

    return {
        "success": True,
        "message": "회원가입이 완료되었습니다.",
        "isActive": is_active,
        "districtWarning": district_message,
    }


def handle_get_user_profile_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        return _get_user_profile_core(req)
    except ApiError as exc:
        raise _to_https_error(exc) from exc
    except https_fn.HttpsError:
        raise
    except Exception as exc:
        logger.exception("getUserProfile failed: %s", exc)
        raise https_fn.HttpsError("internal", "프로필 조회 중 오류가 발생했습니다.") from exc


def handle_update_profile_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        return _update_profile_core(req)
    except ApiError as exc:
        raise _to_https_error(exc) from exc
    except https_fn.HttpsError:
        raise
    except Exception as exc:
        logger.exception("updateProfile failed: %s", exc)
        raise https_fn.HttpsError("internal", "프로필 업데이트 중 오류가 발생했습니다.") from exc


def handle_check_district_availability_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        return _check_district_availability_core(req)
    except ApiError as exc:
        raise _to_https_error(exc) from exc
    except https_fn.HttpsError:
        raise
    except Exception as exc:
        logger.exception("checkDistrictAvailability failed: %s", exc)
        raise https_fn.HttpsError("internal", "선거구 상태 확인 중 오류가 발생했습니다.") from exc
def handle_register_with_district_check_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        return _register_with_district_check_core(req)
    except ApiError as exc:
        raise _to_https_error(exc) from exc
    except https_fn.HttpsError:
        raise
    except Exception as exc:
        logger.exception("registerWithDistrictCheck failed: %s", exc)
        raise https_fn.HttpsError("internal", "회원가입 처리 중 오류가 발생했습니다.") from exc
