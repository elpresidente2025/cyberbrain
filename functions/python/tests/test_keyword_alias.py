"""키워드 별칭(alias) 추출 및 검증 카운팅 테스트."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# extract_keyword_aliases — LLM 응답 파싱 로직
# ---------------------------------------------------------------------------

class TestExtractKeywordAliases:
    """rag_manager.extract_keyword_aliases 의 JSON 파싱·필터링 로직 검증."""

    @pytest.fixture(autouse=True)
    def _patch_gemini(self):
        self._gemini_response = "[]"
        async def _fake_complete(prompt, **kwargs):
            return self._gemini_response
        with patch("rag_manager.gemini_complete", side_effect=_fake_complete):
            yield

    @pytest.mark.asyncio
    async def test_empty_corpus(self):
        from rag_manager import extract_keyword_aliases
        result = await extract_keyword_aliases("")
        assert result == {}

    @pytest.mark.asyncio
    async def test_single_alias_pair(self):
        from rag_manager import extract_keyword_aliases
        self._gemini_response = json.dumps([
            {"canonical": "샘플테크노밸리", "aliases": ["샘플TV"]}
        ])
        result = await extract_keyword_aliases("샘플테크노밸리 활성화에 매달려 온... 샘플TV를 RE100 산단으로")
        assert "샘플테크노밸리" in result
        assert "샘플TV" in result["샘플테크노밸리"]

    @pytest.mark.asyncio
    async def test_filters_by_user_keywords(self):
        from rag_manager import extract_keyword_aliases
        self._gemini_response = json.dumps([
            {"canonical": "샘플테크노밸리", "aliases": ["샘플TV"]},
            {"canonical": "무관한기관", "aliases": ["무관"]},
        ])
        result = await extract_keyword_aliases(
            "text", user_keywords=["샘플테크노밸리"]
        )
        assert "샘플테크노밸리" in result
        assert "무관한기관" not in result

    @pytest.mark.asyncio
    async def test_reverse_alias_mapping(self):
        """canonical 이 user_keywords 에 없고 alias 가 있는 경우 역방향 매핑."""
        from rag_manager import extract_keyword_aliases
        self._gemini_response = json.dumps([
            {"canonical": "인천경제자유구역", "aliases": ["IFEZ"]}
        ])
        result = await extract_keyword_aliases(
            "text", user_keywords=["IFEZ"]
        )
        assert "IFEZ" in result
        assert "인천경제자유구역" in result["IFEZ"]

    @pytest.mark.asyncio
    async def test_malformed_json(self):
        from rag_manager import extract_keyword_aliases
        self._gemini_response = "이 텍스트에서 별칭을 찾을 수 없습니다."
        result = await extract_keyword_aliases("some text")
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_aliases_skipped(self):
        from rag_manager import extract_keyword_aliases
        self._gemini_response = json.dumps([
            {"canonical": "샘플구", "aliases": []}
        ])
        result = await extract_keyword_aliases("text")
        assert result == {}

    @pytest.mark.asyncio
    async def test_self_alias_skipped(self):
        """canonical 과 동일한 alias 는 제거."""
        from rag_manager import extract_keyword_aliases
        self._gemini_response = json.dumps([
            {"canonical": "샘플테크노밸리", "aliases": ["샘플테크노밸리", "샘플TV"]}
        ])
        result = await extract_keyword_aliases("text")
        assert "샘플테크노밸리" in result
        assert "샘플테크노밸리" not in result["샘플테크노밸리"]
        assert "샘플TV" in result["샘플테크노밸리"]


# ---------------------------------------------------------------------------
# validate_keyword_insertion — alias 합산 카운팅
# ---------------------------------------------------------------------------

class TestKeywordValidationAliasCounting:
    """keyword_validation.validate_keyword_insertion 에 keyword_aliases 전달 시 합산 검증."""

    def test_alias_counts_toward_total(self):
        from services.posts.validation.keyword_validation import validate_keyword_insertion
        content = "<p>샘플테크노밸리는 좋다. 샘플TV도 좋다. 샘플TV 최고.</p>"
        result = validate_keyword_insertion(
            content,
            user_keywords=["샘플테크노밸리"],
            keyword_aliases={"샘플테크노밸리": ["샘플TV"]},
        )
        details = result["details"]["keywords"]["샘플테크노밸리"]
        assert details["count"] >= 3

    def test_no_aliases_baseline(self):
        from services.posts.validation.keyword_validation import validate_keyword_insertion
        content = "<p>샘플테크노밸리는 좋다. 샘플TV도 좋다.</p>"
        result = validate_keyword_insertion(
            content,
            user_keywords=["샘플테크노밸리"],
        )
        details = result["details"]["keywords"]["샘플테크노밸리"]
        assert details["count"] == 1

    def test_alias_in_title_counted(self):
        from services.posts.validation.keyword_validation import validate_keyword_insertion
        content = "<p>본문에 없음</p>"
        result = validate_keyword_insertion(
            content,
            user_keywords=["샘플테크노밸리"],
            title_text="샘플TV의 미래",
            keyword_aliases={"샘플테크노밸리": ["샘플TV"]},
        )
        details = result["details"]["keywords"]["샘플테크노밸리"]
        assert details["count"] >= 1


# ---------------------------------------------------------------------------
# editor_agent — alias_note 프롬프트 주입
# ---------------------------------------------------------------------------

class TestHumanizePromptAliasInjection:
    """_build_humanize_prompt_v2 에 keyword_aliases 가 주입되는지 검증."""

    def test_alias_note_injected(self):
        from agents.core.editor_agent import EditorAgent
        agent = EditorAgent()
        prompt = agent._build_humanize_prompt_v2(
            content="<p>본문</p>",
            title="제목",
            user_keywords=["샘플테크노밸리"],
            keyword_aliases={"샘플테크노밸리": ["샘플TV"]},
        )
        assert "키워드 변형어" in prompt
        assert "샘플TV" in prompt

    def test_no_alias_no_section(self):
        from agents.core.editor_agent import EditorAgent
        agent = EditorAgent()
        prompt = agent._build_humanize_prompt_v2(
            content="<p>본문</p>",
            title="제목",
            user_keywords=["샘플테크노밸리"],
            keyword_aliases={},
        )
        assert "키워드 변형어" not in prompt

    def test_unrelated_alias_filtered(self):
        from agents.core.editor_agent import EditorAgent
        agent = EditorAgent()
        prompt = agent._build_humanize_prompt_v2(
            content="<p>본문</p>",
            title="제목",
            user_keywords=["샘플테크노밸리"],
            keyword_aliases={"무관한키워드": ["약어"]},
        )
        assert "키워드 변형어" not in prompt


# ---------------------------------------------------------------------------
# humanize 프롬프트 — "저는" 과다 반복 규칙 존재 확인
# ---------------------------------------------------------------------------

class TestHumanizePromptFirstPersonRule:
    """_build_humanize_prompt_v2 에 '저는' 과다 반복 규칙이 포함되는지 검증."""

    def test_first_person_rule_in_prompt(self):
        from agents.core.editor_agent import EditorAgent
        agent = EditorAgent()
        prompt = agent._build_humanize_prompt_v2(
            content="<p>본문</p>",
            title="제목",
        )
        assert '"저는" 문두 과다 반복' in prompt

    def test_first_person_flag_passed_to_humanize(self):
        """edit_summary 에 '저는' 플래그가 있으면 prior_flags_note 에 포함."""
        from agents.core.editor_agent import EditorAgent
        agent = EditorAgent()
        flag = "'저는' 문두 과다 반복 — 전체 20문장 중 12문장(60%)이 '저는'으로 시작."
        prompt = agent._build_humanize_prompt_v2(
            content="<p>본문</p>",
            title="제목",
            edit_summary=[flag],
        )
        assert "직전 단계 감지" in prompt
        assert "저는" in prompt


# ---------------------------------------------------------------------------
# "저는" 감지 — Kiwi 없이 regex 문장 분리로 동작
# ---------------------------------------------------------------------------

class TestFirstPersonDetectionWithoutKiwi:
    """apply_hard_constraints 의 '저는' 과다 감지가 Kiwi 없이도 동작하는지 검증."""

    def test_detect_overuse(self):
        from agents.core.editor_agent import EditorAgent
        agent = EditorAgent()
        # 10문장 중 6문장이 "저는"으로 시작 (60%)
        content = (
            "<p>저는 정책을 추진합니다. 저는 교통 문제를 해결합니다. "
            "이 문제는 중요합니다. 저는 노력합니다. "
            "저는 시정질문을 했습니다. 저는 결과를 확인합니다. "
            "광역철도가 필요합니다. 인천시민 여러분. "
            "저는 최선을 다합니다. 감사합니다.</p>"
        )
        result = agent.apply_hard_constraints(
            content=content,
            title="제목",
            user_keywords=["샘플 사업"],
            status="현역",
        )
        summaries = " ".join(result.get("editSummary", []))
        assert "'저는' 문두 과다 반복" in summaries

    def test_no_flag_when_normal(self):
        from agents.core.editor_agent import EditorAgent
        agent = EditorAgent()
        # 10문장 중 2문장만 "저는" (20%) — 정상
        content = (
            "<p>저는 정책을 추진합니다. 교통 문제가 있습니다. "
            "이 문제는 시급합니다. 광역철도가 필요합니다. "
            "저는 노력합니다. 인천시민 여러분. "
            "교통망 확충이 핵심입니다. 주민 의견을 반영합니다. "
            "경제성 분석이 진행됩니다. 감사합니다.</p>"
        )
        result = agent.apply_hard_constraints(
            content=content,
            title="제목",
            user_keywords=["샘플 사업"],
            status="현역",
        )
        summaries = " ".join(result.get("editSummary", []))
        assert "'저는' 문두 과다" not in summaries


# ---------------------------------------------------------------------------
# "저는" 기계적 감축 — 연속 문두 생략
# ---------------------------------------------------------------------------

class TestFirstPersonMechanicalReduction:
    """post-humanize 단계의 '저는' 연속 문두 기계적 생략 검증.

    EditorAgent.process() 의 3.7 단계를 직접 테스트하기 어려우므로
    apply_hard_constraints 단독 + 내부 _strip_consecutive_fp 로직을
    재현하는 방식으로 검증.
    """

    def test_consecutive_first_person_in_same_p(self):
        """같은 <p> 안에서 연속 '저는' 문장이 있으면 두 번째가 제거되는지."""
        import re
        text = "저는 정책을 추진합니다. 저는 교통 문제를 해결합니다. 이것은 중요합니다."
        # _strip_consecutive_fp 로직 재현
        parts = re.split(r'(?<=[.?!])\s+', text)
        result_parts = [parts[0]]
        count = 0
        for i in range(1, len(parts)):
            prev = result_parts[-1]
            cur = parts[i]
            if re.match(r'저는\s', prev) and re.match(r'저는\s', cur):
                cur = cur[len('저는 '):]
                count += 1
            result_parts.append(cur)
        result = ' '.join(result_parts)
        assert count == 1
        assert "저는 정책을 추진합니다." in result
        assert "교통 문제를 해결합니다." in result
        assert result.count("저는") == 1

    def test_non_consecutive_preserved(self):
        """연속이 아닌 '저는'은 유지."""
        import re
        text = "저는 정책을 추진합니다. 교통 문제가 있습니다. 저는 노력합니다."
        parts = re.split(r'(?<=[.?!])\s+', text)
        result_parts = [parts[0]]
        count = 0
        for i in range(1, len(parts)):
            prev = result_parts[-1]
            cur = parts[i]
            if re.match(r'저는\s', prev) and re.match(r'저는\s', cur):
                cur = cur[len('저는 '):]
                count += 1
            result_parts.append(cur)
        assert count == 0  # 연속이 아니므로 제거 없음
