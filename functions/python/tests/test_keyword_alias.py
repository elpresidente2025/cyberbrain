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
