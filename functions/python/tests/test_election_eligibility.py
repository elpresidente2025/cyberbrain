from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from firebase_functions import https_fn


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.common import election_rules
from handlers import pipeline_start
from handlers.generate_posts_pkg import pipeline as generate_pipeline


class _DummyHttpRequest:
    def __init__(self, payload: dict, headers: dict | None = None):
        self._payload = payload
        self.headers = headers or {}

    def get_json(self, silent: bool = True) -> dict:
        _ = silent
        return self._payload


class _DummyAuth:
    def __init__(self, uid: str):
        self.uid = uid


class _DummyCallableRequest:
    def __init__(self, payload: dict, uid: str = "user-1"):
        self.data = payload
        self.auth = _DummyAuth(uid)


class _DummyProgressTracker:
    def __init__(self, *_args, **_kwargs):
        pass

    def step_preparing(self) -> None:
        pass

    def step_collecting(self) -> None:
        pass

    def step_generating(self) -> None:
        pass

    def error(self, _message: str) -> None:
        pass


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(election_rules, "_today_kst", lambda: election_rules._date(2026, 3, 29))


def test_check_election_eligibility_allows_incumbent() -> None:
    result = election_rules.check_election_eligibility({"status": "현역"})
    assert result["allowed"] is True
    assert result["reason"] == "현역"
    assert result["days_until_election"] is None


def test_check_election_eligibility_allows_preliminary_local_election_within_90_days() -> None:
    result = election_rules.check_election_eligibility(
        {"status": "예비", "targetElection": {"position": "부산시장"}}
    )
    assert result["allowed"] is True
    assert result["reason"] == "허용"
    assert result["days_until_election"] == 66


def test_check_election_eligibility_blocks_non_candidate_status() -> None:
    result = election_rules.check_election_eligibility({"status": "준비"})
    assert result["allowed"] is False
    assert result["reason"] == "예비_후보_아님"


def test_check_election_eligibility_blocks_national_election_outside_window() -> None:
    result = election_rules.check_election_eligibility(
        {"status": "예비", "targetElection": {"position": "국회의원"}}
    )
    assert result["allowed"] is False
    assert result["reason"] == "선거일_초과"
    assert result["days_until_election"] > 90


def test_check_election_eligibility_reads_current_status_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(election_rules, "_today_kst", lambda: election_rules._date(2026, 3, 5))
    result = election_rules.check_election_eligibility(
        {
            "currentStatus": {"status": "예비"},
            "targetElection": {"position": "부산시장"},
        }
    )
    assert result["allowed"] is True
    assert result["days_until_election"] == 90


def test_check_election_eligibility_boundary_d91_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(election_rules, "_today_kst", lambda: election_rules._date(2026, 3, 4))
    result = election_rules.check_election_eligibility(
        {"status": "후보", "targetElection": {"position": "부산시장"}}
    )
    assert result["allowed"] is False
    assert result["reason"] == "선거일_초과"
    assert result["days_until_election"] == 91


def test_pipeline_start_denies_ineligible_user(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.access_control as access_control
    import services.posts.profile_loader as profile_loader

    monkeypatch.setattr(
        profile_loader,
        "load_user_profile",
        lambda uid, category="", topic="": {
            "userProfile": {
                "uid": uid,
                "status": "준비",
                "position": "부산시장",
            },
            "isAdmin": False,
            "isTester": False,
        },
    )
    async def _unexpected_permission(*_args, **_kwargs):
        raise AssertionError("권한 검사 전에 선거 자격 가드가 먼저 실행되어야 합니다.")

    monkeypatch.setattr(access_control, "check_generation_permission", _unexpected_permission)

    req = _DummyHttpRequest(
        {
            "topic": "테스트 주제",
            "uid": "user-1",
            "userProfile": {"status": "현역"},
        }
    )
    response = pipeline_start.handle_start(req)
    body = json.loads(response.get_data(as_text=True))

    assert response.status_code == 403
    assert body["code"] == "ELECTION_ELIGIBILITY_DENIED"
    assert body["reason"] == "예비_후보_아님"


def test_generate_posts_call_denies_ineligible_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generate_pipeline, "ProgressTracker", _DummyProgressTracker)
    monkeypatch.setattr(
        generate_pipeline,
        "load_user_profile",
        lambda uid, category="", topic="", options=None: {
            "userProfile": {
                "uid": uid,
                "status": "준비",
                "position": "부산시장",
            },
            "isAdmin": False,
            "isTester": False,
        },
    )

    req = _DummyCallableRequest({"topic": "테스트 주제", "category": "daily-communication"})
    with pytest.raises(https_fn.HttpsError) as exc_info:
        generate_pipeline.handle_generate_posts_call(req)

    exc = exc_info.value
    assert exc.code == "permission-denied"
    assert "예비후보 또는 후보 등록 후 이용 가능합니다." in getattr(exc, "message", "")
