from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.authz import (
    get_admin_access_source,
    get_tester_access_source,
    is_admin_user,
    is_tester_user,
    normalize_user_flags,
)


def test_normalize_user_flags_uses_role_as_primary_source() -> None:
    normalized = normalize_user_flags({"role": " ADMIN "})

    assert normalized["role"] == "admin"
    assert normalized["isAdmin"] is True
    assert normalized["isTester"] is False
    assert get_admin_access_source(normalized) == "role"


def test_normalize_user_flags_does_not_promote_legacy_admin_when_role_missing() -> None:
    normalized = normalize_user_flags({"isAdmin": True})

    assert normalized.get("role") is None
    assert normalized["isAdmin"] is False
    assert is_admin_user(normalized) is False


def test_normalize_user_flags_promotes_legacy_tester_when_role_missing() -> None:
    normalized = normalize_user_flags({"isTester": True})

    assert normalized["role"] == "tester"
    assert normalized["isTester"] is True
    assert is_tester_user(normalized) is True


def test_access_source_helpers_distinguish_role_and_legacy_flags() -> None:
    assert get_admin_access_source({"role": "admin"}) == "role"
    assert get_admin_access_source({"isAdmin": True}) is None
    assert get_tester_access_source({"role": "tester"}) == "role"
    assert get_tester_access_source({"isTester": True}) == "legacy-isTester"
