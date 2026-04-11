from __future__ import annotations

from typing import Any, Mapping


def normalize_role(role: Any) -> str:
    return str(role or "").strip().lower()


def is_admin_role(role: Any) -> bool:
    return normalize_role(role) == "admin"


def is_tester_role(role: Any) -> bool:
    return normalize_role(role) == "tester"


def has_legacy_tester_flag(user_data: Mapping[str, Any] | None) -> bool:
    return bool(isinstance(user_data, Mapping) and user_data.get("isTester") is True)


def get_admin_access_source(user_data: Mapping[str, Any] | None) -> str | None:
    if is_admin_role(user_data.get("role") if isinstance(user_data, Mapping) else None):
        return "role"
    return None


def get_tester_access_source(user_data: Mapping[str, Any] | None) -> str | None:
    if is_tester_role(user_data.get("role") if isinstance(user_data, Mapping) else None):
        return "role"
    if has_legacy_tester_flag(user_data):
        return "legacy-isTester"
    return None


def is_admin_user(user_data: Mapping[str, Any] | None) -> bool:
    return bool(get_admin_access_source(user_data))


def is_tester_user(user_data: Mapping[str, Any] | None) -> bool:
    return bool(get_tester_access_source(user_data))


def normalize_user_flags(user_data: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(user_data, Mapping):
        return {}

    normalized_user = dict(user_data)
    normalized_role = normalize_role(normalized_user.get("role"))
    legacy_tester = has_legacy_tester_flag(normalized_user)

    if normalized_role:
        normalized_user["role"] = normalized_role
    elif legacy_tester:
        normalized_user["role"] = "tester"

    normalized_user["isAdmin"] = is_admin_role(normalized_role)
    normalized_user["isTester"] = is_tester_role(normalized_role) or legacy_tester
    return normalized_user
