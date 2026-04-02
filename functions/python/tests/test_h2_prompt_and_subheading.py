from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agents.core.subheading_agent as subheading_module
from agents.common.h2_guide import H2_MAX_LENGTH, sanitize_h2_text
from agents.common.title_prompt_parts import (
    _build_few_shot_slot_values,
    build_user_provided_few_shot_instruction,
)
from agents.core.prompt_builder import build_structure_prompt
from agents.core.subheading_agent import SubheadingAgent


def _run_async(coro):
    return asyncio.run(coro)


def test_build_structure_prompt_uses_h2_ssot_block_only() -> None:
    prompt = build_structure_prompt(
        {
            "topic": "지역 경제를 다시 세울 해법",
            "category": "policy-proposal",
            "writingMethod": "logical_writing",
            "authorName": "김민우",
            "authorBio": "김민우 소개",
            "instructions": "청년 일자리와 교통 해법을 제시합니다.",
            "newsContext": "지역 교통 혼잡과 일자리 감소가 동시에 나타나고 있습니다.",
            "ragContext": "",
            "targetWordCount": 1800,
            "partyStanceGuide": "",
            "contextAnalysis": {},
            "userProfile": {"name": "김민우", "status": "ready"},
            "personalizationContext": "",
            "memoryContext": "",
            "styleGuide": "직접적이고 간결한 설명형으로 쓴다.",
            "styleFingerprint": {},
            "profileSupportContext": "",
            "profileSubstituteContext": "",
            "newsSourceMode": "news",
            "userKeywords": ["지역 경제"],
            "pollFocusBundle": {},
            "lengthSpec": {
                "body_sections": 3,
                "total_sections": 5,
                "min_chars": 1600,
                "max_chars": 2200,
                "per_section_min": 240,
                "per_section_max": 400,
                "per_section_recommended": 320,
            },
            "outputMode": "json",
        }
    )

    assert '<h2_strategy name="소제목 작성 전략 (AEO+SEO)">' not in prompt
    assert '<h2_rules name="소제목 작성 규칙 (AEO+SEO)" severity="critical">' in prompt
    assert '<h2_examples name="소제목 교정 예시 (bad → good)">' in prompt


def test_title_few_shot_slot_defaults_are_concrete() -> None:
    slot_values = _build_few_shot_slot_values({})
    assert slot_values["지역명"] == "한빛시"
    assert slot_values["정책명"] == "청년주거지원"
    assert slot_values["수치"] == "10"
    assert slot_values["지표명"] == "처리 기간"

    prompt = build_user_provided_few_shot_instruction("QUESTION_ANSWER", {})
    assert 'value="지역명"' not in prompt
    assert 'value="정책명"' not in prompt
    assert 'value="수치"' not in prompt
    assert '<example>한빛시 청년주거지원, 주거비 얼마까지?</example>' in prompt


@pytest.mark.parametrize(
    ("category", "expected_rule", "returned_heading"),
    [
        (
            "policy-proposal",
            '<h2_rules name="소제목 작성 규칙 (AEO+SEO)" severity="critical">',
            "청년 주거 지원 신청 절차와 준비 서류 안내!!!",
        ),
        (
            "current-affairs",
            '<h2_rules name="논평용 소제목 작성 규칙" severity="critical">',
            "특검은 정치 보복이 아니다",
        ),
    ],
)
def test_subheading_agent_uses_ssot_rules_and_normalizes_length(
    monkeypatch: pytest.MonkeyPatch,
    category: str,
    expected_rule: str,
    returned_heading: str,
) -> None:
    captured: dict[str, str] = {}

    async def _fake_generate_json_async(prompt: str, **_kwargs):
        captured["prompt"] = prompt
        return {"headings": [returned_heading]}

    monkeypatch.setattr(subheading_module, "generate_json_async", _fake_generate_json_async)

    agent = SubheadingAgent(options={})
    result = _run_async(
        agent.generate_aeo_subheadings(
            sections=["청년 주거 지원 절차와 준비 서류를 정리하고, 실제 신청 흐름을 설명합니다."],
            style_config=agent.get_style_config(category),
            full_name="김민우",
            full_region="한빛시 중앙구",
            stance_text="핵심 입장을 분명히 설명합니다." if category == "current-affairs" else "",
        )
    )

    assert expected_rule in captured["prompt"]
    assert "SSOT" in captured["prompt"]
    assert len(result) == 1
    assert result[0] == sanitize_h2_text(returned_heading)
    assert len(result[0]) <= H2_MAX_LENGTH
    assert "..." not in result[0]

    if category == "current-affairs":
        assert "논평용 소제목 교정 예시" in captured["prompt"]
    else:
        assert "소제목 교정 예시 (bad → good)" in captured["prompt"]
