"""support_appeal — RAG 필터 및 validator 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from handlers.pipeline_start import _should_discard_support_appeal_rag
from agents.common.support_appeal_validator import validate_support_appeal_writing


# ---------------------------------------------------------------------------
# RAG filter: _should_discard_support_appeal_rag
# ---------------------------------------------------------------------------

class TestSupportAppealRagFilter:

    def test_discard_specific_policy_names(self):
        """지역화폐/천원의 아침밥 등 구체적 정책명 2개 = 4점 → 폐기."""
        rag_text = (
            "단계별 참여 수당을 지역화폐로 지급합니다. "
            "천원의 아침밥 사업을 지역 식당과 연계합니다."
        )
        assert _should_discard_support_appeal_rag(rag_text) is True

    def test_discard_mixed_specific_and_general(self):
        """구체적 1개(2점) + 일반 2개(2점) = 4점 → 폐기."""
        rag_text = "지역화폐 지급 방안 조례 제정 및 예산 편성을 추진합니다."
        assert _should_discard_support_appeal_rag(rag_text) is True

    def test_keep_biographical_text(self):
        """경력·연고 위주 bio 텍스트는 차단되지 않음."""
        rag_text = (
            "청년위원장으로 지역 주민들의 목소리를 직접 듣고 소통해왔습니다. "
            "이 지역에서 오래 살며 주민 네트워크를 함께 만들어왔습니다."
        )
        assert _should_discard_support_appeal_rag(rag_text) is False

    def test_keep_single_general_term(self):
        """일반 정책어 1개(1점)는 임계값 미달 → 통과."""
        rag_text = "지역 재개발 공약에 대한 주민 의견 수렴이 필요합니다."
        assert _should_discard_support_appeal_rag(rag_text) is False

    def test_discard_all_four_general_terms(self):
        """일반 정책어 4개(4점) → 폐기."""
        rag_text = "조례 제정, 예산 확보, 국비 지원 확대, 공약 이행을 추진합니다."
        assert _should_discard_support_appeal_rag(rag_text) is True

    def test_empty_string_returns_false(self):
        assert _should_discard_support_appeal_rag("") is False

    def test_failing_article_rag_context(self):
        """2026-04-26 실패 케이스: 지역화폐·참여 소득·청년 스테이션 포함."""
        rag_text = (
            "참여 소득형 자립 지원을 통해 심리 상담과 진로 컨설팅을 통합 지원하고, "
            "단계별 참여 수당을 지역화폐로 지급합니다. "
            "동네방네 청년 스테이션을 조성합니다. "
            "천원의 아침밥 사업을 지역 식당과 연계하여 확대합니다."
        )
        assert _should_discard_support_appeal_rag(rag_text) is True


# ---------------------------------------------------------------------------
# Validator: validate_support_appeal_writing
# ---------------------------------------------------------------------------

class TestSupportAppealValidator:

    def _make_content(self, h2s: list[str], tail: str) -> str:
        h2_html = "".join(f"<h2>{h}</h2><p>본문입니다.</p>" for h in h2s)
        return h2_html + f"<p>{tail}</p>"

    def test_passes_clean_article(self):
        content = self._make_content(
            ["말할 자격", "공동체 서사"],
            "저에게 기회를 주십시오.",
        )
        result = validate_support_appeal_writing(content)
        assert result["passed"] is True
        assert result["issues"] == []

    def test_detects_policy_h2(self):
        """'지원합니다' 포함 H2는 정책 H2로 감지."""
        content = self._make_content(
            ["말할 자격", "청년 참여, 지역화폐로 지원합니다"],
            "함께해 주십시오.",
        )
        result = validate_support_appeal_writing(content)
        assert result["passed"] is False
        assert any("POLICY_H2" in issue for issue in result["issues"])

    def test_detects_question_h2(self):
        content = self._make_content(
            ["왜 이 지역이 변해야 하는가?"],
            "선택해 주십시오.",
        )
        result = validate_support_appeal_writing(content)
        assert result["passed"] is False
        assert any("QUESTION_H2" in issue for issue in result["issues"])

    def test_detects_missing_cta(self):
        content = self._make_content(
            ["말할 자격"],
            "앞으로 열심히 하겠습니다.",
        )
        result = validate_support_appeal_writing(content)
        assert result["passed"] is False
        assert "SUPPORT_APPEAL_CTA_MISSING" in result["issues"]

    def test_detects_numeric_overload(self):
        content = self._make_content(
            ["말할 자격"],
            "100억 규모, 50명 목표, 30개 사업, 기회를 주십시오.",
        )
        result = validate_support_appeal_writing(content)
        assert result["passed"] is False
        assert any("NUMERIC_OVERLOAD" in issue for issue in result["issues"])

    def test_failing_article_policy_h2(self):
        """2026-04-26 실패 케이스: 지역화폐 섹션 H2가 정책 H2로 감지돼야 함."""
        content = self._make_content(
            ["말할 자격", "젊은 계양을 위한 청년 참여, 지역화폐로 지원합니다"],
            "저 홍길동에게 기회를 주십시오.",
        )
        result = validate_support_appeal_writing(content)
        assert result["policy_h2_count"] >= 1
        assert result["passed"] is False
