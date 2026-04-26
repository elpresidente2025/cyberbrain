"""support_appeal — RAG 필터, validator, prompt_builder 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from handlers.pipeline_start import _should_discard_support_appeal_rag
from agents.common.support_appeal_validator import validate_support_appeal_writing
from agents.common.support_appeal_bio_sanitizer import sanitize_support_appeal_author_bio
from agents.core.prompt_builder import build_structure_prompt
from agents.templates.support_appeal import build_support_appeal_prompt


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

    def test_detects_question_h2_tail_na(self):
        """'~나' 종결도 질문형으로 감지 (예: '어떤 목소리를 듣나')."""
        content = self._make_content(
            ["박지상은 어떤 목소리를 듣나"],
            "선택해 주십시오.",
        )
        result = validate_support_appeal_writing(content)
        assert any("QUESTION_H2" in issue for issue in result["issues"])

    def test_detects_question_h2_tail_inga(self):
        """'~인가' 종결도 질문형으로 감지."""
        content = self._make_content(
            ["우리는 무엇을 해야 하는 사람인가"],
            "선택해 주십시오.",
        )
        result = validate_support_appeal_writing(content)
        assert any("QUESTION_H2" in issue for issue in result["issues"])

    def test_detects_question_h2_lead_word(self):
        """문장 첫머리 의문 부사도 질문형으로 감지."""
        content = self._make_content(
            ["어떻게 다시 시작할 수 있을까"],
            "선택해 주십시오.",
        )
        result = validate_support_appeal_writing(content)
        assert any("QUESTION_H2" in issue for issue in result["issues"])

    def test_policy_h2_detects_newly_synced_keywords(self):
        """BODY와 동기화한 정책어(바우처·수당·프로그램·제도)도 H2 정책 감지."""
        content = self._make_content(
            ["청년 바우처 도입 약속"],
            "선택해 주십시오.",
        )
        result = validate_support_appeal_writing(content)
        assert any("POLICY_H2" in issue for issue in result["issues"])

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

    def test_cta_detected_sojounghan_hanpyo(self):
        """'소중한 한 표를 주십시오' 형태 CTA 감지."""
        content = self._make_content(
            ["말할 자격"],
            "샘플구의원 예비후보 홍길동에게 소중한 한 표를 주십시오.",
        )
        result = validate_support_appeal_writing(content)
        assert "SUPPORT_APPEAL_CTA_MISSING" not in result["issues"]

    def test_cta_detected_matgyeo_ju(self):
        """'맡겨 주십시오' 형태 CTA 감지."""
        content = self._make_content(
            ["말할 자격"],
            "이 지역의 변화를 저 홍길동에게 맡겨 주십시오.",
        )
        result = validate_support_appeal_writing(content)
        assert "SUPPORT_APPEAL_CTA_MISSING" not in result["issues"]


# ---------------------------------------------------------------------------
# prompt_builder: support_appeal 전용 블록 주입 차단
# ---------------------------------------------------------------------------

class TestSupportAppealPromptBuilder:

    _BASE_PARAMS = {
        "writingMethod": "support_appeal_writing",
        "category": "daily-communication",
        "topic": "샘플구의원 예비후보 홍길동, 주민 삶에 실질적 변화 약속드립니다",
        "authorBio": "홍길동, 샘플구의원 예비후보",
        "instructions": ["계산동과 작전동은 오랜 시간 활력을 잃어가고 있습니다."],
        "ragContext": "지역화폐 지급 방안 조례 제정 및 예산 편성을 추진합니다.",
        "contextAnalysis": {
            "answer_type": "implementation_plan",
            "central_claim": "주민 삶 개선",
            "execution_items": ["조례 제정", "예산 확보"],
            "source_contract": {},
            "contentStrategy": {},
        },
        "stanceList": [
            {"topic": "지역화폐 도입", "expansion_why": "소비 활성화", "expansion_effect": "골목상권 살리기"}
        ],
        "lengthSpec": {"targetChars": 1200, "minChars": 900, "maxChars": 1600},
        "outputMode": "xml",
        "newsSourceMode": "news",
        "userProfile": {},
    }

    def test_rag_context_excluded_from_prompt(self):
        """support_appeal_writing 에서는 ragContext가 source_blocks에 포함되지 않음."""
        prompt = build_structure_prompt(self._BASE_PARAMS)
        assert "사용자 프로필 기반 맥락" not in prompt

    def test_body_expansion_excluded_from_prompt(self):
        """support_appeal_writing 에서는 body_expansion 블록이 주입되지 않음."""
        prompt = build_structure_prompt(self._BASE_PARAMS)
        assert "<body_expansion" not in prompt

    def test_execution_plan_excluded_from_prompt(self):
        """support_appeal_writing 에서는 execution_plan 블록이 주입되지 않음."""
        prompt = build_structure_prompt(self._BASE_PARAMS)
        assert "<execution_plan" not in prompt

    def test_instructions_text_sanitized_for_support_appeal(self):
        """support_appeal_writing에서 instructions의 정책-only 문장은 reference_materials에 들어가지 않음."""
        params = {
            **self._BASE_PARAMS,
            "instructions": [
                "계산동은 오랜 시간 활력을 잃어가고 있습니다.",
                "지역 청년 바우처 도입과 조례 제정을 추진합니다.",
            ],
        }
        prompt = build_structure_prompt(params)
        assert "계산동은 오랜 시간 활력을 잃어가고 있습니다" in prompt
        assert "지역 청년 바우처 도입과 조례 제정을 추진합니다" not in prompt

    def test_profile_support_context_sanitized_for_support_appeal(self):
        """support_appeal_writing에서 profileSupportContext의 정책-only 문장은 보조 자료에 들어가지 않음."""
        params = {
            **self._BASE_PARAMS,
            "newsContext": "지역 뉴스",  # profileSupportContext가 보강 경로로 들어가도록
            "profileSupportContext": (
                "더불어민주당 청년위원장으로 활동했습니다. "
                "건강바우처 도입과 조례 제정을 추진합니다."
            ),
        }
        prompt = build_structure_prompt(params)
        assert "청년위원장" in prompt
        assert "건강바우처 도입과 조례 제정을 추진합니다" not in prompt


# ---------------------------------------------------------------------------
# support_appeal template: <h2_examples> good/bad block
# ---------------------------------------------------------------------------

class TestSupportAppealH2Examples:

    _BASE_OPTIONS = {
        "topic": "샘플구의원 예비후보 홍길동",
        "authorName": "홍길동",
        "authorBio": "더불어민주당 청년위원장",
        "instructions": ["계산동은 오랜 시간 활력을 잃었습니다."],
        "userProfile": {"status": "예비"},
    }

    def test_h2_examples_block_present(self):
        prompt = build_support_appeal_prompt(self._BASE_OPTIONS)
        assert "<h2_examples" in prompt
        assert "<bad" in prompt
        assert "<good" in prompt
        # 정책 카드 H2 예시가 bad로 명시
        assert "골목경제 활력 불어넣는 이유" in prompt
        # 서사형 H2 예시가 good으로 명시
        assert "골목에서 배운 책임" in prompt

    def test_local_council_ratio_block_present(self):
        """기초의원·구의원 분량 비중 블록이 포함됨."""
        prompt = build_support_appeal_prompt(self._BASE_OPTIONS)
        assert "<local_council_ratio" in prompt
        assert "50~60" in prompt  # 서사 비중
        assert "15~25" in prompt  # 정책 비중


# ---------------------------------------------------------------------------
# Validator POLICY_BODY_OVERLOAD gate (telemetry only)
# ---------------------------------------------------------------------------

class TestSupportAppealValidatorBodyOverload:

    def _make_content(self, h2s, tail):
        h2_html = "".join(f"<h2>{h}</h2><p>본문입니다.</p>" for h in h2s)
        return h2_html + f"<p>{tail}</p>"

    def test_body_policy_overload_detected(self):
        """본문 정책 구조어 6개 초과면 POLICY_BODY_OVERLOAD 발급."""
        body = self._make_content(
            ["말할 자격"],
            "조례와 예산, 시범사업과 바우처, 수당과 지원금, 시스템 도입을 추진합니다. 기회를 주십시오.",
        )
        result = validate_support_appeal_writing(body)
        assert any("POLICY_BODY_OVERLOAD" in issue for issue in result["issues"])
        assert result["body_policy_hits"] > 6

    def test_low_policy_count_passes(self):
        """본문 정책 구조어 ≤ 6이면 POLICY_BODY_OVERLOAD 없음."""
        body = self._make_content(
            ["말할 자격"],
            "조례 한 번, 예산 한 번. 기회를 주십시오.",
        )
        result = validate_support_appeal_writing(body)
        assert "POLICY_BODY_OVERLOAD" not in str(result["issues"])
        assert result["body_policy_hits"] <= 6


# ---------------------------------------------------------------------------
# Bio sanitizer: sanitize_support_appeal_author_bio
# ---------------------------------------------------------------------------

class TestSupportAppealBioSanitizer:

    def test_keeps_pure_identity_sentence(self):
        """직책·활동 이력만 있는 문장은 보존."""
        bio = "더불어민주당 청년위원장으로 활동했습니다."
        result = sanitize_support_appeal_author_bio(bio)
        assert "청년위원장" in result
        assert "활동" in result

    def test_drops_pure_policy_sentence(self):
        """정체성 마커 없이 정책 구조어만 있는 문장은 제거."""
        bio = "지역 청년 건강바우처를 도입하고 조례 제정을 추진합니다."
        result = sanitize_support_appeal_author_bio(bio)
        assert result == ""

    def test_keeps_mixed_sentence_with_identity(self):
        """직책 + 정책 혼합 문장은 정체성을 위해 보존."""
        bio = "청년위원장으로 활동하며 지역 청년 바우처 도입에 참여했습니다."
        result = sanitize_support_appeal_author_bio(bio)
        assert "청년위원장" in result

    def test_drops_only_policy_keeps_identity_in_multiline(self):
        """여러 문장 중 정책-only 문장만 제거하고 정체성 문장은 보존."""
        bio = (
            "더불어민주당 청년위원장으로 활동했습니다. "
            "지역화폐 지급과 청년 바우처 도입을 추진합니다. "
            "주민참여예산 시민위원장을 역임했습니다."
        )
        result = sanitize_support_appeal_author_bio(bio)
        assert "청년위원장" in result
        assert "주민참여예산" in result
        assert "지역화폐 지급" not in result
        assert "바우처 도입" not in result

    def test_empty_input_returns_empty(self):
        assert sanitize_support_appeal_author_bio("") == ""
        assert sanitize_support_appeal_author_bio("   ") == ""

    def test_does_not_hardcode_brand_policy_names(self):
        """특정 정책 브랜드명(지역화폐·천원의 아침밥)을 정체성 문장에서 제거하지 않음."""
        bio = "인천에서 태어나 지역화폐 운동에 참여한 청년위원장입니다."
        result = sanitize_support_appeal_author_bio(bio)
        assert "지역화폐" in result
        assert "청년위원장" in result


# ---------------------------------------------------------------------------
# Validator donation footer strip
# ---------------------------------------------------------------------------

class TestSupportAppealValidatorFooterStrip:

    def _make_content(self, h2s, tail):
        h2_html = "".join(f"<h2>{h}</h2><p>본문입니다.</p>" for h in h2s)
        return h2_html + f"<p>{tail}</p>"

    def test_donation_footer_does_not_trigger_numeric_overload(self):
        """후원 안내 블록(연간 10만원/100만원/25%)은 NUMERIC 카운트에서 제외."""
        body = self._make_content(["말할 자격"], "기회를 주십시오.")
        donation = (
            "\n새마을금고 9002-2087-6629-2 후원회"
            "\n* 본인의 실명으로만 후원 가능하며, 외국인은 불가합니다."
            "\n* 연간 10만원까지 전액 세액공제가 가능합니다."
            "\n* 1인당 연간 100만원까지 후원할 수 있습니다."
        )
        result = validate_support_appeal_writing(body + donation)
        assert "SUPPORT_APPEAL_NUMERIC_OVERLOAD" not in str(result["issues"])
        assert result["numeric_count"] == 0

    def test_body_numerics_still_counted_after_strip(self):
        """본문에 정책 수치가 3개 있으면 후원 안내와 무관하게 NUMERIC_OVERLOAD."""
        body = self._make_content(
            ["말할 자격"],
            "100억 규모, 50명 목표, 30개 사업, 기회를 주십시오.",
        )
        donation = "\n새마을금고 9002-2087-6629-2 후원회\n* 본인의 실명으로만 후원."
        result = validate_support_appeal_writing(body + donation)
        assert any("NUMERIC_OVERLOAD" in issue for issue in result["issues"])


# ---------------------------------------------------------------------------
# support_appeal template: material_usage_lock + sanitized author_bio
# ---------------------------------------------------------------------------

class TestSupportAppealTemplate:

    _BASE_OPTIONS = {
        "topic": "샘플구의원 예비후보 홍길동, 주민과 함께",
        "authorName": "홍길동",
        "instructions": ["계산동은 오랜 시간 활력을 잃었습니다."],
        "userProfile": {"status": "예비"},
    }

    def test_material_usage_lock_block_present(self):
        prompt = build_support_appeal_prompt({
            **self._BASE_OPTIONS,
            "authorBio": "더불어민주당 청년위원장",
        })
        assert "<material_usage_lock" in prompt
        assert "identity_only" in prompt
        assert "policy_not_section" in prompt

    def test_author_bio_sanitized_in_prompt(self):
        """authorBio의 정책-only 문장은 프롬프트의 <author>에 들어가지 않음."""
        prompt = build_support_appeal_prompt({
            **self._BASE_OPTIONS,
            "authorBio": (
                "더불어민주당 청년위원장으로 활동했습니다. "
                "조례 제정과 청년 바우처 도입을 추진합니다."
            ),
        })
        assert "청년위원장" in prompt
        assert "조례 제정과 청년 바우처 도입을 추진합니다" not in prompt
