from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import access_control


class _DummySnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self):
        return self._data


class _DummyDocumentRef:
    def __init__(self, store: dict, collection_name: str, doc_id: str):
        self._store = store
        self._collection_name = collection_name
        self._doc_id = doc_id

    def get(self) -> _DummySnapshot:
        collection = self._store.get(self._collection_name, {})
        return _DummySnapshot(collection.get(self._doc_id))


class _DummyCollectionRef:
    def __init__(self, store: dict, collection_name: str):
        self._store = store
        self._collection_name = collection_name

    def document(self, doc_id: str) -> _DummyDocumentRef:
        return _DummyDocumentRef(self._store, self._collection_name, doc_id)


class _DummyDb:
    def __init__(self, store: dict):
        self._store = store

    def collection(self, collection_name: str) -> _DummyCollectionRef:
        return _DummyCollectionRef(self._store, collection_name)


def test_demo_mode_keeps_trial_user_active_after_trial_expiry() -> None:
    db = _DummyDb(
        {
            "users": {
                "user-1": {
                    "subscriptionStatus": "trial",
                    "trialExpiresAt": "2000-01-01T00:00:00Z",
                    "generationsRemaining": 8,
                    "monthlyUsage": {},
                }
            },
            "system": {
                "config": {
                    "testMode": True,
                    "testModeSettings": {"freeMonthlyLimit": 8},
                }
            },
        }
    )

    result = asyncio.run(access_control.check_generation_permission("user-1", db))

    assert result["allowed"] is True
    assert result["reason"] == "demo"
    assert result["remaining"] == 8


def test_demo_mode_allows_non_active_user_without_payment() -> None:
    current_month = access_control.get_current_month_key()
    db = _DummyDb(
        {
            "users": {
                "user-2": {
                    "subscriptionStatus": "expired",
                    "monthlyUsage": {
                        current_month: {"generations": 7},
                    },
                }
            },
            "system": {
                "config": {
                    "testMode": True,
                    "testModeSettings": {"freeMonthlyLimit": 8},
                }
            },
        }
    )

    result = asyncio.run(access_control.check_generation_permission("user-2", db))

    assert result["allowed"] is True
    assert result["reason"] == "demo"
    assert result["remaining"] == 1


def test_demo_mode_still_enforces_monthly_free_limit() -> None:
    current_month = access_control.get_current_month_key()
    db = _DummyDb(
        {
            "users": {
                "user-3": {
                    "subscriptionStatus": "trial",
                    "monthlyUsage": {
                        current_month: {"generations": 3},
                    },
                }
            },
            "system": {
                "config": {
                    "testMode": True,
                    "testModeSettings": {"freeMonthlyLimit": 3},
                }
            },
        }
    )

    result = asyncio.run(access_control.check_generation_permission("user-3", db))

    assert result["allowed"] is False
    assert result["reason"] == "monthly_limit_exceeded"
    assert "데모 모드" in result["message"]


def test_production_mode_keeps_trial_expiry_check() -> None:
    db = _DummyDb(
        {
            "users": {
                "user-4": {
                    "subscriptionStatus": "trial",
                    "trialExpiresAt": "2000-01-01T00:00:00Z",
                    "generationsRemaining": 8,
                }
            },
            "system": {
                "config": {
                    "testMode": False,
                }
            },
        }
    )

    result = asyncio.run(access_control.check_generation_permission("user-4", db))

    assert result["allowed"] is False
    assert result["reason"] == "trial_expired"
