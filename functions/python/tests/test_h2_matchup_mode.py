"""SubheadingAgent 매치업 모드 + h2_templates 단위 테스트 (PR 5).

CLAUDE.md 범용성 원칙: 인물/지역은 placeholder(홍길동·김철수·샘플구)만 사용.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.common.h2_templates import (
    MATCHUP_KIND_IDS,
    MATCHUP_KIND_TEMPLATES,
    build_matchup_heading,
    build_matchup_pair_sentence,
    score_matchup_kind_candidates,
    select_matchup_kind_sequence,
)
from agents.core.subheading_agent import SubheadingAgent


# ---------------------------------------------------------------------------
# h2_templates primitives
# ---------------------------------------------------------------------------


class TestBuildMatchupHeading:
    def test_primary_matchup_without_percent(self) -> None:
        heading = build_matchup_heading(
            "primary_matchup",
            speaker="홍길동",
            opponent="김철수",
        )
        assert "홍길동" in heading
        assert "김철수" in heading
        assert "배경" in heading

    def test_primary_matchup_with_percent(self) -> None:
        heading = build_matchup_heading(
            "primary_matchup",
            speaker="홍길동",
            opponent="김철수",
            speaker_percent="42%",
            opponent_percent="38%",
        )
        assert "42%" in heading
        assert "38%" in heading
        assert "홍길동" in heading

    def test_override_wins(self) -> None:
        heading = build_matchup_heading(
            "primary_matchup",
            speaker="홍길동",
            opponent="김철수",
            template_override="{speaker}가 답한다, {opponent}와의 정면 승부",
        )
        assert heading == "홍길동가 답한다, 김철수와의 정면 승부"

    def test_missing_speaker_returns_empty(self) -> None:
        assert build_matchup_heading("primary_matchup", speaker="", opponent="김철수") == ""

    def test_unknown_kind_returns_empty(self) -> None:
        assert build_matchup_heading("unknown_kind", speaker="홍길동") == ""

    def test_all_default_templates_render(self) -> None:
        for kind in MATCHUP_KIND_IDS:
            heading = build_matchup_heading(
                kind,
                speaker="홍길동",
                opponent="김철수",
            )
            assert heading, f"{kind} template should not be empty"
            assert "홍길동" in heading, f"{kind} template must include speaker"


class TestBuildMatchupPairSentence:
    def test_full_inputs(self) -> None:
        sentence = build_matchup_pair_sentence(
            speaker="홍길동",
            opponent="김철수",
            speaker_percent="42%",
            opponent_percent="38%",
        )
        assert "홍길동·김철수 가상대결" in sentence
        assert "42% 대 38%" in sentence

    def test_missing_percent_returns_empty(self) -> None:
        assert (
            build_matchup_pair_sentence(speaker="홍길동", opponent="김철수")
            == ""
        )


# ---------------------------------------------------------------------------
# select_matchup_kind_sequence
# ---------------------------------------------------------------------------


class TestSelectMatchupKindSequence:
    def test_empty_sections(self) -> None:
        assert select_matchup_kind_sequence([]) == []

    def test_last_section_is_closing(self) -> None:
        sections = [
            "홍길동과 김철수의 가상대결에서 약진이 두드러졌습니다. 42% 대 38%로 접전입니다.",
            "홍길동이 제시한 경제 정책은 산업과 일자리 혁신에 초점을 맞춥니다.",
            "홍길동은 인지도 확대를 위해 접점을 늘리고 있습니다.",
            "이제 홍길동과 함께 미래를 약속하며 마무리합니다.",
        ]
        seq = select_matchup_kind_sequence(
            sections,
            primary_opponent="김철수",
            speaker_percent="42%",
            opponent_percent="38%",
        )
        assert len(seq) == 4
        assert seq[-1] == "closing"
        assert "primary_matchup" in seq
        assert "policy" in seq
        assert len(set(seq)) == len(seq)  # used-once 제약

    def test_no_duplicate_kinds(self) -> None:
        sections = ["중립 문장 하나", "또 다른 중립 문장", "세 번째 중립 문장"]
        seq = select_matchup_kind_sequence(
            sections,
            primary_opponent="김철수",
        )
        assert len(seq) == 3
        assert len(set(filter(None, seq))) == len([k for k in seq if k])


# ---------------------------------------------------------------------------
# score_matchup_kind_candidates
# ---------------------------------------------------------------------------


class TestScoreMatchupKindCandidates:
    def test_primary_matchup_with_both_percents(self) -> None:
        text = "홍길동과 김철수의 가상대결에서 42% 대 38%로 나타났습니다."
        scores = score_matchup_kind_candidates(
            text,
            section_index=0,
            section_count=4,
            primary_opponent="김철수",
            speaker_percent="42%",
            opponent_percent="38%",
        )
        assert scores.get("primary_matchup") == 130

    def test_primary_matchup_contest_only(self) -> None:
        text = "홍길동과 김철수의 가상대결이 박빙입니다."
        scores = score_matchup_kind_candidates(
            text,
            section_index=0,
            section_count=4,
            primary_opponent="김철수",
        )
        assert scores.get("primary_matchup") == 110

    def test_last_section_closing_bonus(self) -> None:
        text = "함께 미래를 약속하며 마무리합니다."
        scores = score_matchup_kind_candidates(
            text,
            section_index=3,
            section_count=4,
        )
        assert scores.get("closing", 0) >= 120


# ---------------------------------------------------------------------------
# SubheadingAgent._process_matchup end-to-end
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if not asyncio.get_event_loop().is_running() else None


def _arun(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


SAMPLE_CONTENT = (
    "<h2>대결의 시작</h2>"
    "<p>홍길동과 김철수의 가상대결이 42% 대 38%로 접전입니다.</p>"
    "<h2>정책 얘기</h2>"
    "<p>홍길동은 경제와 일자리, 산업 혁신 정책을 내놓았습니다.</p>"
    "<h2>인지도 확대</h2>"
    "<p>홍길동은 접점을 늘려 인지도를 넓히고 있습니다.</p>"
    "<h2>마무리 인사</h2>"
    "<p>끝으로 홍길동은 미래를 함께 약속합니다.</p>"
)


class TestSubheadingAgentMatchupMode:
    def test_matchup_branch_produces_templates(self) -> None:
        agent = SubheadingAgent()
        context = {
            "content": SAMPLE_CONTENT,
            "category": "poll-matchup",
            "fullName": "홍길동",
            "pollFocusBundle": {
                "scope": "matchup",
                "primaryPair": {
                    "speaker": "홍길동",
                    "opponent": "김철수",
                    "speakerPercent": "42%",
                    "opponentPercent": "38%",
                },
                "secondaryPairs": [],
                "allowedH2Kinds": [
                    {"id": kind, "template": MATCHUP_KIND_TEMPLATES[kind].get("template", "")}
                    for kind in MATCHUP_KIND_IDS
                ],
            },
        }
        result = _arun(agent.process(context))
        assert result["optimized"] is True
        stats = result["subheadingStats"]
        assert stats["mode"] == "matchup"
        assert stats["llm_calls"] == 0
        assert stats["matches"] == 4
        trace = result["h2Trace"]
        assert len(trace) == 4
        # 최소 1개 이상이 template 로 치환되었어야 함
        template_count = sum(1 for t in trace if t["action"] == "matchup_template")
        assert template_count >= 2
        # 화자 이름이 치환된 heading 에 포함되어야 함
        for t in trace:
            if t["action"] == "matchup_template":
                assert "홍길동" in t["final"]

    def test_matchup_branch_skips_without_speaker(self) -> None:
        agent = SubheadingAgent()
        context = {
            "content": SAMPLE_CONTENT,
            "category": "poll-matchup",
            "pollFocusBundle": {
                "scope": "matchup",
                "primaryPair": {},
            },
        }
        result = _arun(agent.process(context))
        assert result["optimized"] is False
        assert result["subheadingStats"].get("skipped") == "missing_speaker_or_opponent"
        # 원본 유지
        assert result["content"] == SAMPLE_CONTENT

    def test_non_matchup_scope_uses_generic_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        agent = SubheadingAgent()
        called = {"generic": False}

        async def _fake_optimize(**_kwargs):
            called["generic"] = True
            return ("optimized", [], {"mode": "generic"})

        monkeypatch.setattr(agent, "optimize_headings_in_content", _fake_optimize)

        context = {
            "content": SAMPLE_CONTENT,
            "category": "policy-proposal",
            "fullName": "홍길동",
            "pollFocusBundle": {"scope": "policy"},  # not matchup
        }
        result = _arun(agent.process(context))
        assert called["generic"] is True
        assert result["content"] == "optimized"
