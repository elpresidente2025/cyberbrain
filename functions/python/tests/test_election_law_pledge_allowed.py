# tests/test_election_law_pledge_allowed.py
# 공직선거법 제59조 3항: 온라인(SNS/블로그) 게시글은 선거운동 시기 제한 면제
# 공약성 표현은 더 이상 차단하지 않고, 형사 위험(기부행위·허위사실·비방)만 검증

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.posts.validation.election_law import detect_election_law_violation


class TestPledgeExpressionsAllowed:
    """공약성 표현이 온라인 매체에서 합법이므로 violation으로 잡히지 않아야 한다."""

    def test_basic_pledge_not_blocked(self):
        content = "<p>교통 문제를 해결하겠습니다. 주민 여러분을 지원하겠습니다.</p>"
        result = detect_election_law_violation(content, "현역")
        assert result["passed"] is True

    def test_promise_expression_not_blocked(self):
        content = "<p>약속드립니다. 반드시 실현하겠습니다.</p>"
        result = detect_election_law_violation(content, "현역")
        assert result["passed"] is True

    def test_support_appeal_not_blocked(self):
        content = "<p>지지해 주십시오. 투표해 주십시오.</p>"
        result = detect_election_law_violation(content, "준비")
        assert result["passed"] is True

    def test_election_reference_not_blocked(self):
        content = "<p>다음 선거에서 승리하겠습니다. 재선을 위해 노력하겠습니다.</p>"
        result = detect_election_law_violation(content, "현역")
        assert result["passed"] is True

    def test_multiple_pledge_patterns_not_blocked(self):
        content = "<p>추진하겠습니다. 만들겠습니다. 바꾸겠습니다. 이루겠습니다.</p>"
        result = detect_election_law_violation(content, "현역")
        assert result["passed"] is True


class TestCriminalViolationsStillBlocked:
    """형사처벌 대상 표현은 여전히 차단되어야 한다."""

    def test_bribery_blocked(self):
        content = "<p>참석자 전원에게 상품권을 제공하겠습니다.</p>"
        result = detect_election_law_violation(content, "현역")
        assert result["passed"] is False
        assert any(item["type"] == "BRIBERY" for item in result["items"])

    def test_indirect_defamation_blocked(self):
        content = "<p>그가 비리를 저질렀다라는 소문이 있습니다.</p>"
        result = detect_election_law_violation(content, "현역")
        assert result["passed"] is False
        assert any(item["type"] == "indirect_defamation" for item in result["items"])

    def test_opponent_fact_claim_blocked(self):
        content = "<p>상대 후보가 공금을 횡령했습니다.</p>"
        result = detect_election_law_violation(content, "현역")
        assert result["passed"] is False

    def test_unsourced_number_flagged(self):
        content = "<p>실업률이 15%에 달합니다.</p>"
        result = detect_election_law_violation(content, "현역")
        assert result["passed"] is False
        assert any(item["type"] == "false_info_risk" for item in result["items"])


class TestAllStagesCheckCriminal:
    """모든 스테이지에서 형사 위험 검증이 수행되어야 한다."""

    def test_stage1_checks_bribery(self):
        content = "<p>참석자 전원에게 상품권을 제공하겠습니다.</p>"
        result = detect_election_law_violation(content, "현역")
        assert result["passed"] is False

    def test_stage2_checks_bribery(self):
        content = "<p>참석자 전원에게 상품권을 제공하겠습니다.</p>"
        result = detect_election_law_violation(content, "예비")
        assert result["passed"] is False

    def test_stage3_checks_bribery(self):
        content = "<p>참석자 전원에게 상품권을 제공하겠습니다.</p>"
        result = detect_election_law_violation(content, "후보")
        assert result["passed"] is False

    def test_clean_content_passes_all_stages(self):
        content = "<p>지역 경제를 살리겠습니다. 교육 환경을 개선하겠습니다.</p>"
        for status in ["준비", "현역", "예비", "후보"]:
            result = detect_election_law_violation(content, status)
            assert result["passed"] is True, f"status={status}에서 실패"
