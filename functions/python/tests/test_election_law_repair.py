import pathlib
import sys
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from handlers.generate_posts_pkg.pipeline import _recover_legal_issues_once
from services.posts.validation.election_law import detect_election_law_violation
from services.posts.validation.heuristics import run_heuristic_validation_sync


def test_detect_election_law_violation_returns_structured_indirect_defamation_item() -> None:
    content = "<p>그는 지역 정치의 실세라고 알려져 있습니다.</p>"

    result = detect_election_law_violation(content, "현역")

    assert result["passed"] is False
    item = next(item for item in result["items"] if item["type"] == "indirect_defamation")
    assert item["matchedText"] == "라고 알려져"
    assert item["sentence"] == "그는 지역 정치의 실세라고 알려져 있습니다."
    assert "수정 가이드" in result["violations"][0]


def test_run_heuristic_validation_sync_includes_sentence_and_hint_for_election_law() -> None:
    content = "<p>그는 지역 정치의 실세라고 알려져 있습니다.</p>"

    result = run_heuristic_validation_sync(content, "현역")

    issue = next(item for item in result["issues"] if "선거법 위반 표현" in item)
    assert "문제 문장:" in issue
    assert "수정 가이드:" in issue
    assert "실세라고 알려져 있습니다" in issue


def test_recover_legal_issues_once_returns_rewritten_content_from_model() -> None:
    content = "<p>그는 지역 정치의 실세라고 알려져 있습니다.</p>"
    legal_items = detect_election_law_violation(content, "현역")["items"]

    with patch("agents.common.gemini_client.generate_content_async", return_value="<content><p>그는 지역 정치의 핵심 인물입니다.</p></content>"):
        repaired = _recover_legal_issues_once(
            content=content,
            title="",
            legal_items=legal_items,
            status="현역",
            target_word_count=1200,
            user_keywords=[],
        )

    assert repaired["edited"] is True
    assert "핵심 인물입니다" in repaired["content"]
    assert repaired["summary"]
