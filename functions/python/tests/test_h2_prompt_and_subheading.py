from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agents.core.subheading_agent as subheading_module
from agents.common.h2_guide import (
    H2_MAX_LENGTH,
    build_category_tone_block,
    get_category_tone,
    sanitize_h2_text,
)
from agents.common.h2_planning import (
    extract_key_claim,
    extract_section_plan,
    extract_stance_claims,
    pick_must_include_keyword,
    pick_suggested_type,
)
from agents.common.h2_scoring import H2_MIN_PASSING_SCORE, score_h2
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


# ---------------------------------------------------------------------------
# h2_guide — Category Tone Anchor
# ---------------------------------------------------------------------------


def test_get_category_tone_resolves_current_affairs_to_assertive() -> None:
    tone = get_category_tone("current-affairs")
    assert tone["style"] == "assertive"
    assert "주장형" in tone["preferred_types"]
    assert any("아니다" in ex or "질서" in ex or "없다" in ex for ex in tone["examples"])


def test_get_category_tone_falls_back_to_default_on_unknown() -> None:
    tone = get_category_tone("unknown-category")
    assert tone["style"] == "aeo"
    assert tone["examples"] == []


def test_build_category_tone_block_emits_examples_for_current_affairs() -> None:
    block = build_category_tone_block("current-affairs")
    assert '<h2_category_tone category="current-affairs" style="assertive">' in block
    assert "<preferred_types>" in block
    assert "특검은 정치 보복이 아니다" in block


def test_build_category_tone_block_empty_for_default() -> None:
    # default 카테고리는 예시가 비어 있으므로 빈 문자열 반환 (프롬프트 노이즈 방지)
    assert build_category_tone_block("default") == ""


# ---------------------------------------------------------------------------
# h2_planning — 결정론적 Plan 추출
# ---------------------------------------------------------------------------


def _policy_style_config() -> dict:
    return {
        "style": "aeo",
        "description": "정책 제안 카테고리는 구체적인 정보형 소제목을 사용합니다.",
        "preferred_types": ["데이터형", "명사형", "절차형"],
    }


def _assertive_style_config() -> dict:
    return {
        "style": "assertive",
        "description": "논평/시사 카테고리는 주장형 소제목을 사용합니다.",
        "preferred_types": ["주장형", "명사형", "단정형", "비판형"],
    }


def test_extract_section_plan_picks_procedural_type_from_markers() -> None:
    plan = extract_section_plan(
        section_text="청년 기본소득 신청은 정해진 절차로 진행되며 준비 서류를 미리 확인해야 합니다.",
        index=0,
        category="policy-proposal",
        style_config=_policy_style_config(),
        user_keywords=["청년 기본소득"],
        full_name="김민우",
        full_region="한빛시 중앙구",
    )
    assert plan["suggested_type"] == "절차형"
    assert plan["must_include_keyword"] == "청년 기본소득"
    assert plan["key_claim"].startswith("청년 기본소득")


def test_extract_section_plan_picks_data_type_from_numerics() -> None:
    plan = extract_section_plan(
        section_text="상반기에 국비 120억을 확보하고 청년 일자리 274명을 창출했습니다.",
        index=0,
        category="activity-report",
        style_config={
            "style": "aeo",
            "preferred_types": ["데이터형", "명사형"],
        },
        user_keywords=[],
        full_name="",
        full_region="",
    )
    assert plan["suggested_type"] == "데이터형"
    assert any("120억" in n or "274명" in n for n in plan["numerics"])


def test_pick_must_include_keyword_prefers_user_keyword_when_present() -> None:
    text = "청년 기본소득은 지역 경제를 살리는 핵심 정책입니다."
    keyword = pick_must_include_keyword(
        text,
        user_keywords=["청년 기본소득", "지역 경제"],
        entity_hints=["김민우"],
    )
    assert keyword == "청년 기본소득"


def test_pick_must_include_keyword_falls_back_to_entity_hint() -> None:
    text = "한빛시는 올해 예산을 대폭 확대했습니다."
    keyword = pick_must_include_keyword(
        text,
        user_keywords=["청년 기본소득"],
        entity_hints=["한빛시"],
    )
    assert keyword == "한빛시"


def test_pick_suggested_type_assertive_declarative() -> None:
    text = "특검은 정치 보복이 아니며 진실 규명의 수단이 되어야 한다."
    suggested = pick_suggested_type(
        text,
        preferred_types=["단정형", "비판형", "명사형"],
        style="assertive",
    )
    assert suggested in ("단정형", "비판형")


def test_extract_key_claim_respects_length_band() -> None:
    claim = extract_key_claim(
        "청년 주거 지원은 지역 경제 순환을 보장하는 핵심 정책이다. 추가 조건도 고려해야 한다.",
        style="aeo",
    )
    assert 15 <= len(claim) <= 80


def test_extract_stance_claims_dedupes_top_claims() -> None:
    brief = extract_stance_claims(
        "특검은 정치 보복이 아니다. 특검은 정치 보복이 아니다. 당당하면 피할 이유가 없다."
    )
    assert len(brief["top_claims"]) <= 3
    assert "특검은 정치 보복이 아니다" in brief["top_claims"]
    # 중복 제거 확인
    assert len(brief["top_claims"]) == len(set(brief["top_claims"]))


# ---------------------------------------------------------------------------
# h2_scoring — 가중 rubric
# ---------------------------------------------------------------------------


def _plan_for(keyword: str, suggested_type: str) -> dict:
    return {
        "index": 0,
        "section_text": "",
        "suggested_type": suggested_type,
        "must_include_keyword": keyword,
        "candidate_keywords": [],
        "numerics": [],
        "entity_hints": [],
        "key_claim": "",
    }


def test_score_h2_passes_for_clean_aeo_question_form() -> None:
    plan = _plan_for("청년 기본소득", "질문형")
    result = score_h2(
        "청년 기본소득, 신청 방법은?",
        plan,
        style="aeo",
        preferred_types=["질문형", "명사형", "데이터형"],
    )
    assert result["passed"] is True
    assert result["score"] >= H2_MIN_PASSING_SCORE
    assert "KEYWORD_MISSING" not in result["issues"]


def test_score_h2_fails_when_keyword_missing() -> None:
    plan = _plan_for("청년 기본소득", "명사형")
    result = score_h2(
        "지역 경제의 다양한 도전 과제",
        plan,
        style="aeo",
        preferred_types=["명사형", "데이터형"],
    )
    assert "KEYWORD_MISSING" in result["issues"]
    # 하드 게이트 — KEYWORD_MISSING 은 점수 총합과 무관하게 passed=False
    assert result["passed"] is False


def test_score_h2_fails_on_incomplete_ending() -> None:
    plan = _plan_for("청년 기본소득", "명사형")
    result = score_h2(
        "청년 기본소득을 확대하는",
        plan,
        style="aeo",
        preferred_types=["명사형"],
    )
    assert "INCOMPLETE_ENDING" in result["issues"]
    assert result["passed"] is False


def test_score_h2_fails_on_verbal_modifier_ending() -> None:
    """관형형 어미 `-(으)ㄹ` 단독 종결 감지 (PR 4.5).

    용언 관형형(다할/이어갈/해낼/펼칠)은 수식할 명사가 붙지 않으면 미완결.
    """
    plan = _plan_for("청년 책임", "명사형")
    for heading in (
        "청년 정치인, 공동체 책임 다할",
        "청년 정치인, 독립정신을 이어갈",
        "청년의 약속을 해낼",
        "미래로 꿈을 펼칠",
    ):
        result = score_h2(
            heading,
            plan,
            style="aeo",
            preferred_types=["명사형"],
        )
        assert "INCOMPLETE_ENDING" in result["issues"], heading
        assert result["passed"] is False, heading


def test_score_h2_accepts_verbal_modifier_with_noun() -> None:
    """관형형 뒤에 수식 명사가 있으면 완결 — false positive 방지."""
    plan = _plan_for("청년 약속", "명사형")
    result = score_h2(
        "청년이 지킬 약속 3가지",
        plan,
        style="aeo",
        preferred_types=["명사형"],
    )
    assert "INCOMPLETE_ENDING" not in result["issues"]


def test_score_h2_fails_on_dangling_subject_particle_without_predicate() -> None:
    plan = _plan_for("청년의 목소리", "명사형")
    result = score_h2(
        "청년의 목소리가 실질적 변화",
        plan,
        style="assertive",
        preferred_types=["명사형", "단정형"],
    )
    assert "INCOMPLETE_ENDING" in result["issues"]
    assert result["passed"] is False


def test_score_h2_accepts_subject_particle_with_predicate() -> None:
    plan = _plan_for("청년의 목소리", "단정형")
    result = score_h2(
        "청년의 목소리가 변화를 만든다",
        plan,
        style="assertive",
        preferred_types=["단정형", "명사형"],
    )
    assert "INCOMPLETE_ENDING" not in result["issues"]


def test_score_h2_fails_on_time_continuation_adverb_without_predicate() -> None:
    # Why: "앞으로도 기업" 처럼 시간 지속 부사 + bare 명사 조합은 서술어가
    #      없어 의미 미완결. hard-fail 처리되어야 한다.
    plan = _plan_for("기업 지원", "명사형")
    result = score_h2(
        "앞으로도 기업",
        plan,
        style="assertive",
        preferred_types=["명사형"],
    )
    assert "INCOMPLETE_ENDING" in result["issues"]
    assert result["passed"] is False


def test_score_h2_accepts_time_continuation_adverb_with_predicate() -> None:
    plan = _plan_for("기업 지원", "단정형")
    result = score_h2(
        "앞으로도 기업을 돕겠습니다",
        plan,
        style="assertive",
        preferred_types=["단정형"],
    )
    assert "INCOMPLETE_ENDING" not in result["issues"]


def test_score_h2_skips_profession_ga_suffix_false_positive() -> None:
    plan = _plan_for("박지상 독립운동가", "명사형")
    result = score_h2(
        "박지상 독립운동가 후손의 책임",
        plan,
        style="assertive",
        preferred_types=["명사형"],
    )
    assert "INCOMPLETE_ENDING" not in result["issues"]


def test_score_h2_blocks_question_form_in_assertive() -> None:
    plan = _plan_for("특검", "단정형")
    result = score_h2(
        "특검은 정치 보복인가요?",
        plan,
        style="assertive",
        preferred_types=["단정형", "비판형"],
    )
    assert "QUESTION_FORM_IN_ASSERTIVE" in result["issues"]
    assert result["passed"] is False


def test_score_h2_accepts_assertive_declarative() -> None:
    plan = _plan_for("특검", "단정형")
    result = score_h2(
        "특검은 정치 보복이 아니다",
        plan,
        style="assertive",
        preferred_types=["단정형", "명사형"],
    )
    assert result["passed"] is True


def test_score_h2_length_band_penalty_out_of_best_range() -> None:
    plan = _plan_for("청년", "명사형")
    short_result = score_h2("청년 정책 요약", plan, style="aeo", preferred_types=["명사형"])
    best_result = score_h2("청년 기본소득 5대 핵심 정책 정리", plan, style="aeo", preferred_types=["명사형"])
    assert short_result["breakdown"]["length"]["raw"] < best_result["breakdown"]["length"]["raw"]


def test_score_h2_banned_pattern_penalty() -> None:
    plan = _plan_for("청년 기본소득", "명사형")
    result = score_h2(
        "청년 기본소득 저는 제가 해냅니다",
        plan,
        style="aeo",
        preferred_types=["명사형"],
    )
    assert any("BANNED_PATTERN" in issue for issue in result["issues"])


# ---------------------------------------------------------------------------
# SubheadingAgent — Plan → Gen → Score → Repair 통합
# ---------------------------------------------------------------------------


def _make_agent() -> SubheadingAgent:
    return SubheadingAgent(options={})


def _sample_content() -> str:
    return (
        "<h2>원본 제목 1</h2>\n"
        "<p>청년 기본소득은 지역 경제 순환을 보장합니다. 신청 절차는 3단계로 진행됩니다.</p>\n"
        "<h2>원본 제목 2</h2>\n"
        "<p>국비 120억을 확보해 청년 일자리 274명을 창출했습니다.</p>\n"
    )


def test_optimize_headings_short_circuits_when_first_pass_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    async def _fake(_prompt: str, **_kwargs):
        calls["n"] += 1
        return {
            "headings": [
                "청년 기본소득 신청 3단계 절차",
                "청년 일자리 274명 창출 현황",
            ]
        }

    monkeypatch.setattr(subheading_module, "generate_json_async", _fake)

    agent = _make_agent()
    result = _run_async(
        agent.optimize_headings_in_content(
            content=_sample_content(),
            category="policy-proposal",
            full_name="김민우",
            full_region="한빛시 중앙구",
            stance_text="",
            user_keywords=["청년 기본소득", "청년 일자리"],
            topic="청년 정책",
        )
    )
    rebuilt, trace, stats = result
    assert calls["n"] == 1  # short-circuit: primary만 호출
    assert stats["llm_calls"] == 1
    assert "청년 기본소득 신청 3단계 절차" in rebuilt
    assert "청년 일자리 274명 창출 현황" in rebuilt
    assert all(item["action"] in {"kept", "pre_repaired"} for item in trace)


def test_optimize_headings_triggers_repair_loop_on_bad_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_log: list[dict] = []

    async def _fake(prompt: str, **_kwargs):
        call_log.append({"prompt": prompt})
        if len(call_log) == 1:
            # 1차: banned 1인칭 + 너무 짧음 + 키워드 누락 → 실패
            return {
                "headings": [
                    "제가 해냅니다",
                    "좋은 성과입니다",
                ]
            }
        # 2차 수리: 깨끗한 헤딩
        return {
            "repairs": [
                {"index": 0, "heading": "청년 기본소득 신청 3단계 절차"},
                {"index": 1, "heading": "청년 일자리 274명 창출 현황"},
            ]
        }

    monkeypatch.setattr(subheading_module, "generate_json_async", _fake)

    agent = _make_agent()
    rebuilt, trace, stats = _run_async(
        agent.optimize_headings_in_content(
            content=_sample_content(),
            category="policy-proposal",
            full_name="김민우",
            full_region="한빛시 중앙구",
            stance_text="",
            user_keywords=["청년 기본소득", "청년 일자리"],
            topic="청년 정책",
        )
    )

    assert len(call_log) == 2  # primary + repair
    assert stats["llm_calls"] == 2
    assert "청년 기본소득 신청 3단계 절차" in rebuilt
    assert "청년 일자리 274명 창출 현황" in rebuilt
    assert any(item["action"] == "llm_repaired" for item in trace)
    # count parity
    assert len(trace) == 2


def test_optimize_headings_deterministic_fallback_when_repair_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_log: list[int] = []

    async def _fake(_prompt: str, **_kwargs):
        call_log.append(1)
        if len(call_log) == 1:
            return {"headings": ["제가 해냅니다", "좋은 성과입니다"]}
        raise subheading_module.StructuredOutputError("forced repair failure")

    monkeypatch.setattr(subheading_module, "generate_json_async", _fake)

    agent = _make_agent()
    rebuilt, trace, stats = _run_async(
        agent.optimize_headings_in_content(
            content=_sample_content(),
            category="policy-proposal",
            full_name="김민우",
            full_region="한빛시 중앙구",
            stance_text="",
            user_keywords=["청년 기본소득", "청년 일자리"],
            topic="청년 정책",
        )
    )
    # H2 개수 parity — 원본 매치 수 유지
    assert rebuilt.count("<h2>") == 2
    assert stats["matches"] == 2
    # 최소한 한 항목은 deterministic_fallback 또는 fallback_original
    actions = {item["action"] for item in trace}
    assert actions & {"deterministic_fallback", "fallback_original"}


def test_optimize_headings_preserves_original_on_total_primary_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake(_prompt: str, **_kwargs):
        raise subheading_module.StructuredOutputError("total failure")

    monkeypatch.setattr(subheading_module, "generate_json_async", _fake)

    agent = _make_agent()
    rebuilt, trace, _stats = _run_async(
        agent.optimize_headings_in_content(
            content=_sample_content(),
            category="policy-proposal",
            full_name="김민우",
            full_region="한빛시 중앙구",
            stance_text="",
            user_keywords=["청년 기본소득"],
            topic="청년 정책",
        )
    )
    # 원본 H2 2개 유지 (count parity)
    assert rebuilt.count("<h2>") == 2
    assert len(trace) == 2


def test_primary_prompt_injects_category_tone_block_for_current_affairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def _fake(prompt: str, **_kwargs):
        captured["prompt"] = prompt
        return {"headings": ["특검은 정치 보복이 아니다", "민주주의 질서를 지키는 기준"]}

    monkeypatch.setattr(subheading_module, "generate_json_async", _fake)

    agent = _make_agent()
    _run_async(
        agent.optimize_headings_in_content(
            content="<h2>A</h2><p>특검 수사는 정치적 보복이 아니라 진실 규명의 절차입니다.</p><h2>B</h2><p>민주주의의 기본 질서를 지키는 것이 중요합니다.</p>",
            category="current-affairs",
            full_name="김민우",
            full_region="한빛시 중앙구",
            stance_text="특검은 정치 보복이 아니다.",
            user_keywords=["특검"],
            topic="특검법",
        )
    )
    assert '<h2_category_tone category="current-affairs" style="assertive">' in captured["prompt"]
    assert "특검은 정치 보복이 아니다" in captured["prompt"]


# ---------------------------------------------------------------------------
# SubheadingAgent — h2_repair content-level chain (PR 2)
# ---------------------------------------------------------------------------


def test_subheading_agent_invokes_h2_repair_chain_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 4b h2_repair 체인이 entity → awkward → branding → user_keyword 순으로 호출되는지 확인."""

    call_order: list[str] = []

    def _fake_entity(content, known_names, *, preferred_names=(), role_facts=None):
        call_order.append("entity_consistency")
        return {"content": content, "edited": False, "replacements": []}

    def _fake_awkward(content):
        call_order.append("awkward_phrases")
        return {"content": content, "edited": False, "actions": []}

    def _fake_branding(content):
        call_order.append("branding_phrases")
        return {"content": content, "edited": False, "actions": []}

    def _fake_user_keyword(content, user_keywords, *, preferred_keyword=""):
        call_order.append("ensure_user_keyword_first_slot")
        return {"content": content, "edited": False}

    monkeypatch.setattr(subheading_module, "repair_entity_consistency", _fake_entity)
    monkeypatch.setattr(subheading_module, "repair_awkward_phrases", _fake_awkward)
    monkeypatch.setattr(subheading_module, "repair_branding_phrases", _fake_branding)
    monkeypatch.setattr(
        subheading_module, "ensure_user_keyword_first_slot", _fake_user_keyword
    )

    async def _fake_primary(_prompt: str, **_kwargs):
        return {
            "headings": [
                "청년 기본소득 신청 3단계 절차",
                "청년 일자리 274명 창출 현황",
            ]
        }

    monkeypatch.setattr(subheading_module, "generate_json_async", _fake_primary)

    agent = _make_agent()
    _run_async(
        agent.optimize_headings_in_content(
            content=_sample_content(),
            category="policy-proposal",
            full_name="김민우",
            full_region="한빛시 중앙구",
            stance_text="",
            user_keywords=["청년 기본소득", "청년 일자리"],
            topic="청년 정책",
            known_person_names=["김민우"],
            role_facts={},
            preferred_keyword="청년 기본소득",
        )
    )

    assert call_order == [
        "entity_consistency",
        "awkward_phrases",
        "branding_phrases",
        "ensure_user_keyword_first_slot",
    ]


def test_subheading_agent_h2_repair_chain_applies_branding_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """체인에서 변경된 헤딩이 추출되어 working·trace·content에 반영되는지 확인."""

    def _fake_entity(content, *args, **kwargs):
        return {"content": content, "edited": False, "replacements": []}

    def _fake_awkward(content):
        return {"content": content, "edited": False, "actions": []}

    def _fake_branding(content):
        replaced = content.replace(
            "<h2>청년 기본소득 신청 3단계 절차</h2>",
            "<h2>청년 기본소득 신청 핵심 정리</h2>",
        )
        return {
            "content": replaced,
            "edited": replaced != content,
            "actions": ["branding_neutralized"],
        }

    def _fake_user_keyword(content, *args, **kwargs):
        return {"content": content, "edited": False}

    monkeypatch.setattr(subheading_module, "repair_entity_consistency", _fake_entity)
    monkeypatch.setattr(subheading_module, "repair_awkward_phrases", _fake_awkward)
    monkeypatch.setattr(subheading_module, "repair_branding_phrases", _fake_branding)
    monkeypatch.setattr(
        subheading_module, "ensure_user_keyword_first_slot", _fake_user_keyword
    )

    async def _fake_primary(_prompt: str, **_kwargs):
        return {
            "headings": [
                "청년 기본소득 신청 3단계 절차",
                "청년 일자리 274명 창출 현황",
            ]
        }

    monkeypatch.setattr(subheading_module, "generate_json_async", _fake_primary)

    agent = _make_agent()
    rebuilt, trace, stats = _run_async(
        agent.optimize_headings_in_content(
            content=_sample_content(),
            category="policy-proposal",
            full_name="김민우",
            full_region="한빛시 중앙구",
            stance_text="",
            user_keywords=["청년 기본소득", "청년 일자리"],
            topic="청년 정책",
            known_person_names=["김민우"],
            role_facts={},
            preferred_keyword="청년 기본소득",
        )
    )

    assert "청년 기본소득 신청 핵심 정리" in rebuilt
    assert trace[0].get("h2_repair_chain") == "청년 기본소득 신청 핵심 정리"
    chain_steps = [item["step"] for item in stats["h2_repair_chain"]]
    assert "branding_phrases" in chain_steps


def test_subheading_agent_h2_repair_chain_skips_when_no_known_names_and_no_keywords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """known_person_names·user_keywords 모두 없으면 entity·user_keyword 단계는 생략된다."""

    called: list[str] = []

    def _fake_entity(content, *args, **kwargs):
        called.append("entity_consistency")
        return {"content": content, "edited": False, "replacements": []}

    def _fake_awkward(content):
        called.append("awkward_phrases")
        return {"content": content, "edited": False, "actions": []}

    def _fake_branding(content):
        called.append("branding_phrases")
        return {"content": content, "edited": False, "actions": []}

    def _fake_user_keyword(content, *args, **kwargs):
        called.append("ensure_user_keyword_first_slot")
        return {"content": content, "edited": False}

    monkeypatch.setattr(subheading_module, "repair_entity_consistency", _fake_entity)
    monkeypatch.setattr(subheading_module, "repair_awkward_phrases", _fake_awkward)
    monkeypatch.setattr(subheading_module, "repair_branding_phrases", _fake_branding)
    monkeypatch.setattr(
        subheading_module, "ensure_user_keyword_first_slot", _fake_user_keyword
    )

    async def _fake_primary(_prompt: str, **_kwargs):
        return {
            "headings": [
                "청년 기본소득 신청 3단계 절차",
                "청년 일자리 274명 창출 현황",
            ]
        }

    monkeypatch.setattr(subheading_module, "generate_json_async", _fake_primary)

    agent = _make_agent()
    _run_async(
        agent.optimize_headings_in_content(
            content=_sample_content(),
            category="policy-proposal",
            full_name="",
            full_region="",
            stance_text="",
            user_keywords=[],
            topic="",
            known_person_names=[],
            role_facts={},
            preferred_keyword="",
        )
    )

    assert "entity_consistency" not in called
    assert "ensure_user_keyword_first_slot" not in called
    assert "awkward_phrases" in called
    assert "branding_phrases" in called
