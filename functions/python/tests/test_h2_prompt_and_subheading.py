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
    resolve_category_archetypes,
    sanitize_h2_text,
)
from agents.common.h2_planning import (
    extract_key_claim,
    extract_section_plan,
    extract_stance_claims,
    pick_must_include_keyword,
    pick_suggested_type,
)
from agents.common import korean_morph
from agents.common.h2_scoring import H2_MIN_PASSING_SCORE, score_h2
from agents.common.title_prompt_parts import (
    _build_few_shot_slot_values,
    build_user_provided_few_shot_instruction,
)
from agents.core.prompt_builder import build_structure_prompt
from agents.core.subheading_agent import SubheadingAgent, _is_field_copy


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
    pool = resolve_category_archetypes("current-affairs")
    assert "주장형" in pool["primary"]
    assert any("아니다" in ex or "이유" in ex or "없다" in ex for ex in tone["examples"])


def test_get_category_tone_falls_back_to_default_on_unknown() -> None:
    tone = get_category_tone("unknown-category")
    assert tone["style"] == "aeo"
    assert tone["examples"] == []


def test_build_category_tone_block_emits_examples_for_current_affairs() -> None:
    block = build_category_tone_block("current-affairs")
    assert '<h2_category_tone category="current-affairs" style="assertive">' in block
    assert "<primary_archetypes>" in block
    assert "주장형" in block
    assert "특검은 정치 보복이 아니다" in block


def test_build_category_tone_block_emits_archetypes_for_default() -> None:
    # default 카테고리는 예시가 없지만 아키타입 풀은 명시된다
    block = build_category_tone_block("default")
    assert '<h2_category_tone category="default" style="aeo">' in block
    assert "<primary_archetypes>" in block


def test_build_category_tone_block_honors_commemorative_override() -> None:
    block = build_category_tone_block("current-affairs", commemorative=True)
    # 기념/성찰 오버라이드 시 주장·이유 아키타입만 노출
    assert "주장형, 이유형" in block
    assert "auxiliary_archetypes" not in block


def test_build_category_tone_block_honors_matchup_override() -> None:
    block = build_category_tone_block("current-affairs", matchup=True)
    # 매치업 오버라이드: 질문·대조 주, 사례 보조
    assert "질문형, 대조형" in block
    assert "사례형" in block


# ---------------------------------------------------------------------------
# h2_planning — 결정론적 Plan 추출
# ---------------------------------------------------------------------------


def _policy_style_config() -> dict:
    # preferred_types 를 비워서 카테고리 아키타입 풀(resolve_category_archetypes)이 사용되도록 한다.
    return {
        "style": "aeo",
        "description": "정책 제안 카테고리는 질문·목표·주장·이유 아키타입을 사용합니다.",
    }


def _assertive_style_config() -> dict:
    return {
        "style": "assertive",
        "description": "논평/시사 카테고리는 주장·이유·질문 아키타입을 사용합니다.",
    }


def test_extract_section_plan_picks_goal_type_from_procedural_markers() -> None:
    plan = extract_section_plan(
        section_text="청년 기본소득 신청은 정해진 절차로 진행되며 준비 서류를 미리 확인해야 합니다.",
        index=0,
        category="policy-proposal",
        style_config=_policy_style_config(),
        user_keywords=["청년 기본소득"],
        full_name="김민우",
        full_region="한빛시 중앙구",
    )
    # 절차 마커는 새 시스템에서 목표형으로 흡수된다 (약속/이행 promise).
    assert plan["suggested_type"] == "목표형"
    assert plan["must_include_keyword"] == "청년 기본소득"
    assert plan["key_claim"].startswith("청년 기본소득")


def test_extract_section_plan_picks_evidence_type_from_numerics() -> None:
    plan = extract_section_plan(
        section_text="상반기에 국비 120억을 확보하고 청년 일자리 274명을 창출했습니다.",
        index=0,
        category="activity-report",
        style_config={"style": "aeo"},
        user_keywords=[],
        full_name="",
        full_region="",
    )
    # 숫자·실적 마커는 사례형으로 매핑된다 (activity-report 의 auxiliary pool).
    assert plan["suggested_type"] == "사례형"
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


def test_pick_must_include_keyword_skips_peripheral_mention() -> None:
    """본문 끝에 1회만 언급된 keyword는 주제가 아니므로 건너뛴다."""
    text = (
        "보행 도로 설치는 오랜 시간 투자심사를 통과하지 못한 현안입니다. "
        "경제성을 높일 방안을 다각도로 강구하겠습니다. "
        "탄약고 이전과 연계하여 시너지를 창출할 수 있습니다."
    )
    keyword = pick_must_include_keyword(
        text,
        user_keywords=["탄약고"],
        entity_hints=[],
    )
    # "탄약고"는 첫 2문장에 없고 전체에서 1회만 → 건너뜀 → 빈도 기반 fallback
    assert keyword != "탄약고"


def test_pick_must_include_keyword_keeps_prominent_keyword() -> None:
    """첫 문장에 등장하는 keyword는 정상 채택."""
    text = (
        "탄약고 이전은 주민 안전의 핵심 과제입니다. "
        "대체 부지 마련과 국방부 협의를 통해 해결하겠습니다. "
        "탄약고 주변 개발 잠재력을 극대화하겠습니다."
    )
    keyword = pick_must_include_keyword(
        text,
        user_keywords=["탄약고"],
        entity_hints=[],
    )
    assert keyword == "탄약고"


def test_pick_must_include_keyword_accepts_two_occurrences() -> None:
    """첫 2문장에 없어도 전체에서 2회 이상이면 채택."""
    text = (
        "경제성 분석이 시급한 상황입니다. "
        "주민 의견을 반영한 노선안을 도출하겠습니다. "
        "탄약고 이전 문제와 탄약고 주변 개발을 함께 추진합니다."
    )
    keyword = pick_must_include_keyword(
        text,
        user_keywords=["탄약고"],
        entity_hints=[],
    )
    assert keyword == "탄약고"


def test_pick_suggested_type_assertive_declarative() -> None:
    text = "특검은 정치 보복이 아니며 진실 규명의 수단이 되어야 한다."
    suggested = pick_suggested_type(
        text,
        preferred_types=["주장형", "이유형"],
        style="assertive",
    )
    # 단정 tail("한다") 이 주장형에 매핑된다.
    assert suggested == "주장형"


def test_extract_key_claim_respects_length_band() -> None:
    claim = extract_key_claim(
        "청년 주거 지원은 지역 경제 순환을 보장하는 핵심 정책이다. 추가 조건도 고려해야 한다.",
        style="aeo",
    )
    assert 15 <= len(claim) <= 80


def test_extract_key_claim_skips_greeting_first_sentence() -> None:
    """인사말 첫 문장보다 뒤쪽 주장 문장을 우선 선택해야 한다.

    본문은 H2 아래 섹션의 "정답" — 인사말이 key_claim 으로 박히면 H2 가
    본문 결론을 못 반영한다.
    """
    section = (
        "존경하는 샘플구 주민 여러분, 반갑습니다. "
        "저는 지난 4년간 지역 활성화를 위해 쉼 없이 달려왔습니다. "
        "앞으로도 광역교통망 확충과 앵커기업 유치를 위해 전념하겠습니다."
    )
    claim = extract_key_claim(section, style="aeo")
    assert "존경하는" not in claim, (
        f"인사말이 key_claim 으로 선택됨: {claim!r}"
    )
    # 주장·행동 키워드(전념) 포함된 결론 문장이 선호되어야 함
    assert "전념" in claim or "앵커기업" in claim or "광역교통망" in claim


def test_extract_key_claim_skips_self_intro_sentence() -> None:
    """'저는 ~ 의원입니다' 형태 자기소개는 key_claim 후보에서 밀려야 한다."""
    section = (
        "저는 샘플구에서 당원과 시민을 위해 뛰어온 샘플광역시의원 홍길동입니다. "
        "지역 경제 재도약을 위해 취득세 감면 조례 개정안을 발의해 통과시켰습니다."
    )
    claim = extract_key_claim(section, style="aeo")
    assert "홍길동입니다" not in claim
    assert "조례" in claim or "통과" in claim or "발의" in claim


def test_extract_key_claim_prefers_declarative_conclusion() -> None:
    """뒤쪽에 위치한 단정·주장 어미 문장이 도입부 문장보다 선호되어야 한다."""
    section = (
        "2018년 3기 신도시로 지정된 이후 발전 속도가 더뎠습니다. "
        "경기 인근 지구와 비교해 뒤처진 산단이라는 평가를 받고 있습니다. "
        "앵커기업 유치를 위한 세제 혜택을 반드시 확대해야 합니다."
    )
    claim = extract_key_claim(section, style="aeo")
    # 결론부("확대해야 합니다")가 도입부("지정된 이후...")보다 우선되어야 함
    assert "확대" in claim or "앵커" in claim, (
        f"도입 문장이 선택됨: {claim!r}"
    )


def test_extract_key_claim_falls_back_to_longest_when_no_band_hit() -> None:
    """모든 문장이 길이 밴드(15~80) 탈락이면 가장 긴 문장을 절단해 반환."""
    short_only = "짧음. 매우 짧음. 또 짧음."
    claim = extract_key_claim(short_only, style="aeo")
    # 최소 1 개 문장에서 뽑혀야 하고, 빈 문자열은 아니어야 함
    assert claim
    assert len(claim) <= 80


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
        preferred_types=["질문형", "주장형", "사례형"],
    )
    assert result["passed"] is True
    assert result["score"] >= H2_MIN_PASSING_SCORE
    assert "KEYWORD_MISSING" not in result["issues"]


def test_score_h2_fails_when_keyword_missing() -> None:
    plan = _plan_for("청년 기본소득", "주장형")
    result = score_h2(
        "지역 경제의 다양한 도전 과제",
        plan,
        style="aeo",
        preferred_types=["주장형", "사례형"],
    )
    assert "KEYWORD_MISSING" in result["issues"]
    # 하드 게이트 — KEYWORD_MISSING 은 점수 총합과 무관하게 passed=False
    assert result["passed"] is False


def test_score_h2_fails_on_incomplete_ending() -> None:
    plan = _plan_for("청년 기본소득", "주장형")
    result = score_h2(
        "청년 기본소득을 확대하는",
        plan,
        style="aeo",
        preferred_types=["주장형"],
    )
    assert "INCOMPLETE_ENDING" in result["issues"]
    assert result["passed"] is False


def test_score_h2_fails_on_verbal_modifier_ending() -> None:
    """관형형 어미 `-(으)ㄹ` 단독 종결 감지 (PR 4.5).

    용언 관형형(다할/이어갈/해낼/펼칠)은 수식할 명사가 붙지 않으면 미완결.
    """
    plan = _plan_for("청년 책임", "주장형")
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
            preferred_types=["주장형"],
        )
        assert "INCOMPLETE_ENDING" in result["issues"], heading
        assert result["passed"] is False, heading


def test_score_h2_accepts_verbal_modifier_with_noun() -> None:
    """관형형 뒤에 수식 명사가 있으면 완결 — false positive 방지."""
    plan = _plan_for("청년 약속", "주장형")
    result = score_h2(
        "청년이 지킬 약속 3가지",
        plan,
        style="aeo",
        preferred_types=["주장형"],
    )
    assert "INCOMPLETE_ENDING" not in result["issues"]


def test_score_h2_fails_on_dangling_subject_particle_without_predicate() -> None:
    plan = _plan_for("청년의 목소리", "주장형")
    result = score_h2(
        "청년의 목소리가 실질적 변화",
        plan,
        style="assertive",
        preferred_types=["주장형", "이유형"],
    )
    assert "INCOMPLETE_ENDING" in result["issues"]
    assert result["passed"] is False


def test_score_h2_accepts_subject_particle_with_predicate() -> None:
    plan = _plan_for("청년의 목소리", "주장형")
    result = score_h2(
        "청년의 목소리가 변화를 만든다",
        plan,
        style="assertive",
        preferred_types=["주장형", "이유형"],
    )
    assert "INCOMPLETE_ENDING" not in result["issues"]


def test_score_h2_fails_on_time_continuation_adverb_without_predicate() -> None:
    # Why: "앞으로도 기업" 처럼 시간 지속 부사 + bare 명사 조합은 서술어가
    #      없어 의미 미완결. hard-fail 처리되어야 한다.
    plan = _plan_for("기업 지원", "주장형")
    result = score_h2(
        "앞으로도 기업",
        plan,
        style="assertive",
        preferred_types=["주장형"],
    )
    assert "INCOMPLETE_ENDING" in result["issues"]
    assert result["passed"] is False


def test_score_h2_accepts_time_continuation_adverb_with_predicate() -> None:
    plan = _plan_for("기업 지원", "주장형")
    result = score_h2(
        "앞으로도 기업을 돕겠습니다",
        plan,
        style="assertive",
        preferred_types=["주장형"],
    )
    assert "INCOMPLETE_ENDING" not in result["issues"]


def test_score_h2_skips_profession_ga_suffix_false_positive() -> None:
    plan = _plan_for("홍길동 독립운동가", "주장형")
    result = score_h2(
        "홍길동 독립운동가 후손의 책임",
        plan,
        style="assertive",
        preferred_types=["주장형"],
    )
    assert "INCOMPLETE_ENDING" not in result["issues"]


def test_score_h2_blocks_question_form_in_assertive() -> None:
    plan = _plan_for("특검", "주장형")
    result = score_h2(
        "특검은 정치 보복인가요?",
        plan,
        style="assertive",
        preferred_types=["주장형", "이유형"],
    )
    assert "QUESTION_FORM_IN_ASSERTIVE" in result["issues"]
    assert result["passed"] is False


def test_score_h2_accepts_assertive_declarative() -> None:
    plan = _plan_for("특검", "주장형")
    result = score_h2(
        "특검은 정치 보복이 아니다",
        plan,
        style="assertive",
        preferred_types=["주장형", "이유형"],
    )
    assert result["passed"] is True


def test_score_h2_length_band_penalty_out_of_best_range() -> None:
    plan = _plan_for("청년", "주장형")
    short_result = score_h2("청년 정책 요약", plan, style="aeo", preferred_types=["주장형"])
    best_result = score_h2("청년 기본소득 5대 핵심 정책 정리", plan, style="aeo", preferred_types=["주장형"])
    assert short_result["breakdown"]["length"]["raw"] < best_result["breakdown"]["length"]["raw"]


def test_score_h2_banned_pattern_penalty() -> None:
    plan = _plan_for("청년 기본소득", "주장형")
    result = score_h2(
        "청년 기본소득 저는 제가 해냅니다",
        plan,
        style="aeo",
        preferred_types=["주장형"],
    )
    assert any("BANNED_PATTERN" in issue for issue in result["issues"])


def test_score_h2_fails_on_adnominal_etm_ending() -> None:
    """관형형 전성어미 `-(으)ㄴ/-는` 단독 종결은 미완결 (Bug 3).

    "더딘", "가는", "느린" 같이 수식할 명사 없이 ETM 으로 끝나면
    kiwi 형태소 분석이 미완결로 판정해야 한다.
    이 테스트는 kiwi 가 동작하는 환경(Linux / ASCII 경로 Windows) 에서만 유효.
    """
    from agents.common.korean_morph import get_kiwi

    if get_kiwi() is None:
        pytest.skip("kiwipiepy unavailable (Windows non-ASCII path)")

    plan = _plan_for("대장지구", "이유형")
    for heading in (
        "대장지구 개발, 진척이 더딘",
        "대장지구 재정비 속도가 느린",
    ):
        result = score_h2(
            heading,
            plan,
            style="aeo",
            preferred_types=["이유형"],
        )
        assert "INCOMPLETE_ENDING" in result["issues"], heading
        assert result["passed"] is False, heading


def test_score_h2_hard_fails_when_question_archetype_not_met() -> None:
    """plan 이 `질문형` archetype 을 배정했는데 output 이 의문형이 아니면 hard-fail (Bug 2)."""
    plan = _plan_for("청년 기본소득", "질문형")
    result = score_h2(
        "청년 기본소득, 지역 예산 확보 절차",
        plan,
        style="aeo",
        preferred_types=["질문형", "사례형"],
    )
    assert "H2_QUESTION_FORM_REQUIRED" in result["issues"]
    assert result["passed"] is False


def test_score_h2_accepts_question_archetype_with_question_form() -> None:
    """질문형 배정에 의문 종결 어미가 있으면 통과."""
    plan = _plan_for("청년 기본소득", "질문형")
    result = score_h2(
        "청년 기본소득, 신청 방법은 무엇일까요?",
        plan,
        style="aeo",
        preferred_types=["질문형"],
    )
    assert "H2_QUESTION_FORM_REQUIRED" not in result["issues"]


# ---------------------------------------------------------------------------
# AEO 아키타입 판정 회귀 — Gap A/B/C (검출기 확장) + Gap D (hard-fail 격상)
# ---------------------------------------------------------------------------


def test_detect_h2_archetype_question_eul_kka_family() -> None:
    """Gap A: -을까 / ㄹ-받침 어간 + 까 종결을 질문형으로 잡는다.

    기존 regex 는 '할까' 1형만 enum. '벗을까/찾을까/만들까/갈까' 등 빈출
    변형이 전부 누락돼 질문형이 ''로 떨어졌다.
    """
    from agents.common.h2_guide import detect_h2_archetype

    cases = [
        "책임의 옷은 누가 벗을까",
        "청년 기본소득, 어디서 찾을까?",
        "지역 일자리, 무엇을 만들까",
        "예산 심사, 이대로 갈까",
    ]
    for text in cases:
        assert detect_h2_archetype(text) == "질문형", text


def test_detect_h2_archetype_claim_n_da_family() -> None:
    """Gap B: ~는다 / ~ㄴ다 (빈출 음절) / ~했다/~됐다 주장형 매치."""
    from agents.common.h2_guide import detect_h2_archetype

    claim_cases = [
        "청년이 새 길을 만든다",
        "지역이 변화를 이끈다",
        "시민이 나선다",
        "예산이 투명해졌다",
        "정책은 비로소 완성됐다",
    ]
    for text in claim_cases:
        assert detect_h2_archetype(text) == "주장형", text


def test_detect_h2_archetype_evidence_requires_unit_with_digit() -> None:
    """Gap C: 숫자 단독은 사례형 아님. 수량 단위 또는 증거 키워드 수반 필요.

    전: "RE100 추진" / "지난 4년간 조성" 도 \\d 만으로 사례형 매치 → 주장형/
    목표형을 삼켰다. 후: 숫자는 단위와 결합해야 사례형.
    """
    from agents.common.h2_guide import detect_h2_archetype

    # 숫자만 있지만 단위/키워드 없음 → 사례형 아님
    assert detect_h2_archetype("RE100 투자로 지역을 바꾼다") != "사례형"
    assert detect_h2_archetype("지난 4년간 조성한 인프라") != "사례형"

    # 숫자 + 단위 → 사례형 OK
    assert detect_h2_archetype("지난 3년간 17곳 현장을 점검") == "사례형"
    assert detect_h2_archetype("청년 일자리 2만 개 창출") == "사례형"

    # 증거 키워드 단독도 사례형 OK
    assert detect_h2_archetype("청년 정책 집행 실적 공개") == "사례형"


def test_detect_h2_archetype_returns_empty_for_topic_description() -> None:
    """Gap D 준비: 6 아키타입 어디에도 안 맞는 '단순 토픽 기술' 은 빈 문자열."""
    from agents.common.h2_guide import detect_h2_archetype

    # "정책 방향 제시", "지난 4년간 조성" 류 — 약속 없음, 단순 설명
    assert detect_h2_archetype("지역 발전 정책 방향 제시") == ""
    assert detect_h2_archetype("지난 4년간 조성") == ""


def test_score_h2_hard_fails_on_archetype_mismatch() -> None:
    """Gap D: detect_h2_archetype 이 ''를 반환하면 ARCHETYPE_MISMATCH hard-fail."""
    from agents.common.h2_scoring import H2_HARD_FAIL_ISSUES

    plan = _plan_for("청년 기본소득", "주장형")
    # "정책 방향 제시" — 어떤 아키타입도 매치 안 되는 단순 토픽 나열
    result = score_h2(
        "청년 기본소득 정책 방향 제시",
        plan,
        style="aeo",
        preferred_types=["주장형", "이유형"],
    )
    assert "ARCHETYPE_MISMATCH" in result["issues"]
    assert "ARCHETYPE_MISMATCH" in H2_HARD_FAIL_ISSUES
    assert result["passed"] is False
    # breakdown 에 detected archetype 정보 기록
    assert result["breakdown"].get("archetype", {}).get("detected") == ""


def test_score_h2_does_not_flag_archetype_mismatch_when_archetype_present() -> None:
    """주장형/질문형 등 하나라도 매치되면 ARCHETYPE_MISMATCH 가 붙지 않아야 한다."""
    plan = _plan_for("청년 기본소득", "주장형")
    result = score_h2(
        "청년 기본소득, 지역이 새 길을 만든다",
        plan,
        style="aeo",
        preferred_types=["주장형"],
    )
    assert "ARCHETYPE_MISMATCH" not in result["issues"]
    assert result["breakdown"].get("archetype", {}).get("detected") in {
        "주장형", "목표형", "이유형", "질문형", "대조형", "사례형",
    }


def test_should_replace_prefers_passed_over_higher_score() -> None:
    """passed=True 는 score 가 낮아도 passed=False 를 이긴다."""
    from agents.core.subheading_agent import _should_replace

    hard_fail_high = {"passed": False, "score": 0.85, "issues": ["ARCHETYPE_MISMATCH"]}
    passing_low = {"passed": True, "score": 0.75, "issues": []}

    assert _should_replace(passing_low, hard_fail_high) is True
    assert _should_replace(hard_fail_high, passing_low) is False


def test_should_replace_uses_score_when_passed_equal() -> None:
    """둘 다 passed=True 거나 둘 다 passed=False 면 score 비교로 되돌아간다."""
    from agents.core.subheading_agent import _should_replace

    both_pass_higher = {"passed": True, "score": 0.82}
    both_pass_lower = {"passed": True, "score": 0.78}
    assert _should_replace(both_pass_higher, both_pass_lower) is True
    assert _should_replace(both_pass_lower, both_pass_higher) is False

    both_fail_higher = {"passed": False, "score": 0.70}
    both_fail_lower = {"passed": False, "score": 0.60}
    assert _should_replace(both_fail_higher, both_fail_lower) is True


def test_repair_entity_consistency_never_replaces_speaker_name() -> None:
    """Bug 1: preferred_names 가 오염돼도 speaker(본인 full_name)는 H2 에서 치환되지 않는다."""
    from agents.common.h2_repair import repair_entity_consistency

    content = (
        "<h2>샘플구 개발, 홍길동이 이끈다</h2>\n"
        "<p>아무개 시장이 샘플구 개발 전권을 쥐고 있다. 아무개 시장은 매주 현장을 방문한다.</p>\n"
    )
    # preferred_names 에 홍길동(본인) 과 아무개(타인)이 섞여 있는 dilution 상황을 모사.
    result = repair_entity_consistency(
        content,
        known_names=["홍길동", "아무개"],
        preferred_names=["홍길동", "아무개"],
        role_facts={},
    )
    assert "홍길동" in result["content"]
    # speaker_name == 홍길동 이므로 heading 의 홍길동이 아무개로 치환돼선 안 된다.
    assert "아무개이 이끈다" not in result["content"]
    assert "아무개가 이끈다" not in result["content"]


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
                "청년 기본소득 3단계 신청 절차 현황",
                "국비 120억 일자리 274명 창출 실적",
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
            user_keywords=["청년 기본소득", "일자리 창출"],
            topic="청년 정책",
        )
    )
    rebuilt, trace, stats = result
    assert calls["n"] == 1  # short-circuit: primary만 호출
    assert stats["llm_calls"] == 1
    assert "청년 기본소득 3단계 신청 절차 현황" in rebuilt
    assert "국비 120억 일자리 274명 창출 실적" in rebuilt
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
        # 2차 수리: 깨끗한 헤딩 (prefix 겹침 없도록 첫 어절 다르게)
        return {
            "repairs": [
                {"index": 0, "heading": "청년 기본소득 3단계 신청 절차 현황"},
                {"index": 1, "heading": "국비 120억 일자리 274명 창출 실적"},
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
            user_keywords=["청년 기본소득", "일자리 창출"],
            topic="청년 정책",
        )
    )

    assert len(call_log) == 2  # primary + repair
    assert stats["llm_calls"] == 2
    # 1차 primary 의 "제가 해냅니다" 는 확실히 rebuilt 에 없어야 한다 (garbage 추방).
    assert "제가 해냅니다" not in rebuilt
    assert "좋은 성과입니다" not in rebuilt
    # user keyword 가 H2에 살아남아야 한다.
    assert "청년 기본소득" in rebuilt
    # 어떤 형태로든 repair 경로 (llm_repaired 또는 h2_repair_chain) 를 거쳤어야 한다.
    assert any(
        item["action"] == "llm_repaired" or item.get("h2_repair_chain")
        for item in trace
    )
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
    # repair 실패 시 Gen 최선 결과 사용 (original fallback 없음)
    actions = {item["action"] for item in trace}
    assert "best_effort" in actions


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

    # primary 가 ARCHETYPE_MISMATCH (hard-fail) 인 heading 을 내보내 repair 체인이
    # 반드시 돌도록 유도한다. "신청 3단계 절차" 는 약속 성격 없음 → hard-fail.
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
            "<h2>청년 기본소득 274명 지원 실적</h2>",
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

    # primary heading 은 ARCHETYPE_MISMATCH hard-fail → h2_repair_chain 실행 →
    # branding mock 이 "신청 핵심 정리" 로 교체 → "핵심" 이 claim regex 에 걸려
    # 재스코어링 통과 → 최종 rebuilt 에 반영.
    async def _fake_primary(_prompt: str, **_kwargs):
        return {
            "headings": [
                "청년 기본소득 신청 3단계 절차",
                "국비 120억 일자리 274명 창출 실적",
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
            user_keywords=["청년 기본소득", "일자리 창출"],
            topic="청년 정책",
            known_person_names=["김민우"],
            role_facts={},
            preferred_keyword="청년 기본소득",
        )
    )

    assert "청년 기본소득 274명 지원 실적" in rebuilt
    assert trace[0].get("h2_repair_chain") == "청년 기본소득 274명 지원 실적"
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

    # primary 가 ARCHETYPE_MISMATCH hard-fail 유도 → repair 체인 실행되어야
    # 본 테스트 (체인 스텝 선택 로직) 가 유효해진다.
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


# ---------------------------------------------------------------------------
# kiwi/regex 기반 고유명사·명사 후보 정화 (h2_planning 잔재 정리)
# ---------------------------------------------------------------------------


def test_extract_section_plan_rejects_verb_stem_si_false_proper_noun() -> None:
    """'약화시키는' → '약화시' 같은 동사 사동접미 '-시-' 오매칭을 걸러낸다."""
    plan = extract_section_plan(
        section_text="경쟁력을 약화시키는 제도의 공백을 바로잡겠습니다.",
        index=0,
        category="policy-proposal",
        style_config=_policy_style_config(),
        user_keywords=["제도 개선"],
        full_name="",
        full_region="",
    )
    assert "약화시" not in plan.get("entity_hints", [])
    assert "약화시" not in plan.get("candidate_keywords", [])


def test_extract_section_plan_rejects_adverb_do_false_proper_noun() -> None:
    """'외에도' (부사+보조사) 가 행정구 접미 '도' 로 오매칭되어 entity_hints 로 들어가면 안 된다."""
    plan = extract_section_plan(
        section_text="기본 감면 외에도 취득세를 최대 25% 추가 감면합니다.",
        index=0,
        category="policy-proposal",
        style_config=_policy_style_config(),
        user_keywords=["취득세 감면"],
        full_name="",
        full_region="",
    )
    assert "외에도" not in plan.get("entity_hints", [])


def test_extract_section_plan_keeps_legitimate_administrative_proper_nouns() -> None:
    """정상 지역명(경기도/수원시)은 여전히 entity_hints 로 살아남아야 한다."""
    plan = extract_section_plan(
        section_text="경기도 수원시에 위치한 공장이 이전 대상 목록에 포함됐습니다.",
        index=0,
        category="policy-proposal",
        style_config=_policy_style_config(),
        user_keywords=[],
        full_name="",
        full_region="",
    )
    hints = set(plan.get("entity_hints", []))
    assert "경기도" in hints
    assert "수원시" in hints


def test_extract_section_plan_exposes_user_keywords_for_template_guard() -> None:
    """deterministic fallback 템플릿 가드용으로 plan 에 user_keywords 가 실려야 한다."""
    plan = extract_section_plan(
        section_text="청년 기본소득으로 지역 경제를 살립니다.",
        index=0,
        category="policy-proposal",
        style_config=_policy_style_config(),
        user_keywords=["청년 기본소득", "지역 경제"],
        full_name="",
        full_region="",
    )
    assert plan.get("user_keywords") == ["청년 기본소득", "지역 경제"]


    # deterministic fallback 템플릿 테스트 제거됨 — 파이프라인에서 비활성화


# ---------------------------------------------------------------------------
# Entity surface variant canonicalization — "인천"/"인천시"/"인천광역시" 등은
# 동일 entity 로 묶여 cap 규제 대상이 된다.
# ---------------------------------------------------------------------------


def test_canonicalize_entity_surface_groups_administrative_variants() -> None:
    from agents.common.h2_planning import canonicalize_entity_surface

    assert canonicalize_entity_surface("샘플") == "샘플"
    assert canonicalize_entity_surface("샘플시") == "샘플"
    assert canonicalize_entity_surface("샘플광역시") == "샘플"
    assert canonicalize_entity_surface("샘플특별시") == "샘플"
    assert canonicalize_entity_surface("샘플구") == "샘플"
    assert canonicalize_entity_surface("샘플군") == "샘플"
    assert canonicalize_entity_surface("샘플도") == "샘플"


def test_canonicalize_entity_surface_preserves_short_tokens() -> None:
    from agents.common.h2_planning import canonicalize_entity_surface

    # stem 이 1 글자 이하로 줄면 원본 유지 (단독 접미사 방어)
    assert canonicalize_entity_surface("시") == "시"
    assert canonicalize_entity_surface("도") == "도"
    assert canonicalize_entity_surface("") == ""


def test_distribute_keyword_assignments_treats_variants_as_same_entity() -> None:
    """6 개 섹션 plan 의 must_include_keyword 가 '샘플'/'샘플시'/'샘플광역시' 로
    표면형만 다르게 분산된 경우, canonical '샘플' 로 묶여 cap=3 을 초과한
    4 번째부터 대안으로 교체된다.
    """
    from agents.common.h2_planning import distribute_keyword_assignments

    plans = [
        {"must_include_keyword": "샘플", "candidate_keywords": ["샘플", "경제"]},
        {"must_include_keyword": "샘플시", "candidate_keywords": ["샘플시", "청년"]},
        {"must_include_keyword": "샘플광역시", "candidate_keywords": ["샘플광역시", "교육"]},
        {"must_include_keyword": "샘플", "candidate_keywords": ["샘플", "복지"]},
        {"must_include_keyword": "샘플시", "candidate_keywords": ["샘플시", "산업"]},
        {"must_include_keyword": "샘플광역시", "candidate_keywords": ["샘플광역시", "문화"]},
    ]
    result = distribute_keyword_assignments(plans)

    # cap = ceil(6 * 0.5) = 3. 앞 3개는 변이형 그대로 유지, 뒤 3개는 대안으로 교체.
    assert result[0]["must_include_keyword"] == "샘플"
    assert result[1]["must_include_keyword"] == "샘플시"
    assert result[2]["must_include_keyword"] == "샘플광역시"
    # 뒤 3개는 canonical '샘플' 계열이 아닌 대안으로 교체돼야 한다
    for idx in (3, 4, 5):
        replaced = result[idx]["must_include_keyword"]
        assert replaced not in {"샘플", "샘플시", "샘플광역시"}, (
            f"plan[{idx}] 가 여전히 '샘플' canonical 에 속함: {replaced!r}"
        )


def test_enforce_keyword_diversity_accepts_entity_hints() -> None:
    """entity_hints 로 전달된 지역명도 변이형 포함해 cap 규제 대상이 된다.

    cap = ceil(4 * 0.5) = 2. 앞 2개 유지, 뒤 2개는 매칭된 표면형을 strip.
    strip 결과가 >= 8 글자여야 유효하므로 본문을 넉넉히 사용한다.
    """
    from agents.common.h2_repair import enforce_keyword_diversity

    headings = [
        "샘플시, 청년 정책 대전환의 출발",  # keep (surface "샘플시")
        "샘플광역시, 교육 혁신 종합 로드맵",  # keep (surface "샘플광역시")
        "샘플, 지역 경제 재도약의 설계도",  # strip → "지역 경제 재도약의 설계도"
        "샘플시, 복지 확대 정책 종합 패키지",  # strip → "복지 확대 정책 종합 패키지"
    ]
    result = enforce_keyword_diversity(
        headings,
        user_keywords=[],
        entity_hints=["샘플", "샘플시", "샘플광역시"],
    )

    assert result["edited"], "변이형 4회 반복은 strip 되어야 함"
    edited_headings = result["headings"]
    # 앞 2개는 원본 유지 (cap 이내)
    assert edited_headings[0] == "샘플시, 청년 정책 대전환의 출발"
    assert edited_headings[1] == "샘플광역시, 교육 혁신 종합 로드맵"
    # 뒤 2개는 canonical "샘플" 계열 표면형이 제거됐다
    assert "샘플" not in edited_headings[2]
    assert "샘플" not in edited_headings[3]
    # action 메타데이터: index 2/3, canonical "샘플"
    action_indices = {a["index"] for a in result["actions"]}
    assert action_indices == {2, 3}
    for action in result["actions"]:
        assert action.get("canonical") == "샘플"


# ---------------------------------------------------------------------------
# Body alignment — H2 가 자기 아래 본문을 정답으로 삼는지 검증
# ---------------------------------------------------------------------------


def test_score_h2_flags_body_alignment_low_when_heading_talks_about_different_topic() -> None:
    """H2 에 박힌 명사 대부분이 본문에 없으면 BODY_ALIGNMENT_LOW hard-fail."""
    plan = {
        "section_text": (
            "과거 우리 지역은 전국 광역시 중 유일하게 산업단지 입주 기업에 대한 "
            "취득세 감면 조례가 없었습니다. 2014년 이후 10여 년간 움직임이 없어 "
            "기업 유치 경쟁에서 불리한 위치에 있었습니다. 조성 중인 신규 산단 "
            "여러 곳의 경쟁력이 약화되었다는 평가를 받아왔습니다."
        ),
        "suggested_type": "주장형",
        "must_include_keyword": "샘플 테크노밸리",
        "candidate_keywords": ["샘플 테크노밸리"],
        "numerics": ["10"],
        "entity_hints": [],
        "user_keywords": ["샘플 테크노밸리"],
        "key_claim": "",
    }
    # H2 는 "샘플 테크노밸리" 를 얘기하지만 본문은 "취득세 감면 조례 공백"이 주제
    heading = "샘플 테크노밸리, 10년 공백 바로잡기"
    result = score_h2(heading, plan)

    assert "BODY_ALIGNMENT_LOW" in result["issues"], (
        f"본문과 동떨어진 H2 가 통과됨: coverage={result['breakdown'].get('body_alignment', {}).get('coverage')}"
    )
    assert not result["passed"], "BODY_ALIGNMENT_LOW 은 hard-fail 이어야 함"


def test_score_h2_passes_body_alignment_when_heading_tokens_in_body() -> None:
    """H2 의 내용 토큰이 본문에 등장하면 body_alignment 만점·이슈 없음."""
    plan = {
        "section_text": (
            "취득세 감면 조례 개정안이 본회의를 통과해 9월부터 시행되고 있습니다. "
            "기본 감면 외에도 추가 감면을 받을 수 있도록 했습니다. "
            "기업 유치 경쟁력 확보의 중요한 신호탄이 될 것입니다."
        ),
        "suggested_type": "주장형",
        "must_include_keyword": "취득세 감면",
        "candidate_keywords": ["취득세 감면", "조례", "기업 유치"],
        "numerics": [],
        "entity_hints": [],
        "user_keywords": ["취득세 감면"],
        "key_claim": "",
    }
    heading = "취득세 감면 조례, 기업 유치 경쟁력 회복"
    result = score_h2(heading, plan)

    assert "BODY_ALIGNMENT_LOW" not in result["issues"]
    assert "BODY_ALIGNMENT_PARTIAL" not in result["issues"]
    alignment = result["breakdown"].get("body_alignment", {})
    assert alignment.get("coverage", 0.0) >= 0.67


def test_score_h2_skips_body_alignment_when_section_text_empty() -> None:
    """plan 에 section_text 가 없으면 coverage 체크 생략 (raw=1.0)."""
    plan = {
        "section_text": "",
        "suggested_type": "주장형",
        "must_include_keyword": "청년 기본소득",
        "candidate_keywords": ["청년 기본소득"],
        "numerics": [],
        "entity_hints": [],
        "user_keywords": ["청년 기본소득"],
        "key_claim": "",
    }
    heading = "청년 기본소득, 지역 경제 활성화의 첫걸음"
    result = score_h2(heading, plan)

    # section_text 없을 때는 coverage 체크 생략 → alignment 이슈 없음
    assert "BODY_ALIGNMENT_LOW" not in result["issues"]
    alignment = result["breakdown"].get("body_alignment", {})
    assert alignment.get("raw") == 1.0


def test_score_h2_partial_alignment_is_soft_warning_not_hard_fail() -> None:
    """coverage 0.34~0.67 구간은 감점만 있고 hard-fail 은 아니다."""
    plan = {
        "section_text": (
            "본 정책은 지역 일자리 창출을 위한 종합 대책입니다. "
            "신규 산업단지 조성과 함께 진행됩니다."
        ),
        "suggested_type": "주장형",
        "must_include_keyword": "일자리",
        "candidate_keywords": ["일자리", "산업단지"],
        "numerics": [],
        "entity_hints": [],
        "user_keywords": ["일자리"],
        "key_claim": "",
    }
    # "일자리" + "산업단지" 는 본문 있음 / "대전환" + "설계도" 는 본문 없음
    heading = "일자리 산업단지, 대전환 설계도"
    result = score_h2(heading, plan)

    # partial warning 은 허용 (hard-fail 아님)
    assert "BODY_ALIGNMENT_LOW" not in result["issues"]


def test_enforce_keyword_diversity_user_keywords_still_regulated() -> None:
    """기존 user_keywords 경로도 유지 — 변이형 없이 동일 표면 반복 시 strip."""
    from agents.common.h2_repair import enforce_keyword_diversity

    headings = [
        "청년 기본소득, 지역 살리는 첫걸음의 시작",
        "청년 기본소득, 교육 혁신의 본격 출발",
        "청년 기본소득, 산업 재도약 설계도 공개",
        "청년 기본소득, 복지 확대 로드맵 제시",
    ]
    result = enforce_keyword_diversity(
        headings,
        user_keywords=["청년 기본소득"],
    )
    assert result["edited"]
    # cap = 2 → 뒤 2개는 strip 대상
    action_indices = {a["index"] for a in result["actions"]}
    assert action_indices.issubset({2, 3})


# ---------------------------------------------------------------------------
# candidate_keywords body-presence filter — 본문에 없는 user_keyword/entity_hint 는
# candidate_keywords 풀에서 제거돼 distribute_keyword_assignments 의 대안으로 쓰이지 않는다.
# ---------------------------------------------------------------------------


def test_extract_section_plan_drops_user_keyword_absent_from_body() -> None:
    """user_keyword 가 이 섹션 본문에 없으면 candidate_keywords 에서 제외된다."""
    plan = extract_section_plan(
        section_text=(
            "지역 산단 기업에 대한 취득세 감면 조례가 9월 본회의를 통과했습니다. "
            "신규 기업 유치 경쟁력의 중요한 토대가 될 것입니다."
        ),
        index=0,
        category="policy-proposal",
        style_config=_policy_style_config(),
        # '샘플 테크노밸리' 는 본문에 없다 — candidate_keywords 에서 빠져야 함
        user_keywords=["샘플 테크노밸리", "취득세 감면"],
        full_name="",
        full_region="",
    )
    candidates = plan.get("candidate_keywords") or []
    assert "샘플 테크노밸리" not in candidates, (
        f"본문에 없는 user_keyword 가 candidate_keywords 에 남아 있음: {candidates}"
    )
    assert "취득세 감면" in candidates, (
        f"본문에 있는 user_keyword 가 candidate_keywords 에서 사라짐: {candidates}"
    )


def test_extract_section_plan_drops_entity_hint_absent_from_body() -> None:
    """full_name/full_region 이 이 섹션 본문에 없으면 candidate_keywords 에서 제외된다."""
    plan = extract_section_plan(
        section_text=(
            "청년 일자리 확대를 위해 신규 산업단지 조성 사업을 본격화합니다. "
            "지역 경제 재도약의 출발점이 될 것입니다."
        ),
        index=0,
        category="policy-proposal",
        style_config=_policy_style_config(),
        user_keywords=[],
        # 본인 이름과 지역이 이 섹션 본문에 등장하지 않음
        full_name="홍길동",
        full_region="샘플시",
    )
    candidates = plan.get("candidate_keywords") or []
    assert "홍길동" not in candidates
    assert "샘플시" not in candidates


def test_extract_section_plan_keeps_entity_hint_present_in_body() -> None:
    """본문에 등장하는 full_name/full_region 은 candidate_keywords 에 남는다."""
    plan = extract_section_plan(
        section_text=(
            "홍길동 의원은 샘플시 청년 일자리 확대 공약을 발표했습니다. "
            "샘플시 산업단지 조성과 함께 추진됩니다."
        ),
        index=0,
        category="policy-proposal",
        style_config=_policy_style_config(),
        user_keywords=[],
        full_name="홍길동",
        full_region="샘플시",
    )
    candidates = plan.get("candidate_keywords") or []
    assert "홍길동" in candidates
    assert "샘플시" in candidates


def test_distribute_keyword_assignments_does_not_reassign_to_absent_keyword() -> None:
    """extract_section_plan → distribute_keyword_assignments 통합 경로에서,
    본문에 없는 user_keyword 는 재배치 대안으로 선택되지 않는다.
    """
    from agents.common.h2_planning import distribute_keyword_assignments

    # 4 개 섹션 — 앞 3 개는 '샘플' canonical, 마지막 1 개는 다른 주제.
    # '유령 키워드' 는 어떤 섹션 본문에도 없으므로 candidate_keywords 에서 제외돼야 함.
    section_texts = [
        "샘플시 청년 일자리 공약이 발표됐습니다. 지역 경제 재도약의 출발점입니다.",
        "샘플시 교육 혁신 로드맵이 공개됐습니다. 학교 현장의 변화가 기대됩니다.",
        "샘플광역시 복지 확대 패키지가 추진됩니다. 취약 계층 지원이 강화됩니다.",
        "취득세 감면 조례 개정안이 본회의를 통과했습니다. 기업 유치 경쟁력이 회복됩니다.",
    ]
    plans = [
        extract_section_plan(
            section_text=section_texts[i],
            index=i,
            category="policy-proposal",
            style_config=_policy_style_config(),
            # '유령 키워드' 는 어떤 본문에도 없음
            user_keywords=["유령 키워드"],
            full_name="",
            full_region="",
        )
        for i in range(4)
    ]
    result = distribute_keyword_assignments(plans)
    for plan in result:
        assert plan.get("must_include_keyword") != "유령 키워드", (
            "본문에 없는 user_keyword 가 재배치 대안으로 선택됨"
        )
        candidates = plan.get("candidate_keywords") or []
        assert "유령 키워드" not in candidates


def test_detect_sibling_prefix_overlap_catches_duplicate_lead() -> None:
    """첫 어절이 같은 H2 가 2개 이상이면 overlap 반환."""
    from agents.common.h2_scoring import detect_sibling_prefix_overlap

    headings = [
        "인천, 17개 시도 중 유일한 미감면",
        "인천, 뒤처진 산단 오명 벗을 수 있을까",
        "계양구, 서울 접근성으로 도약할 수 있을까",
    ]
    overlaps = detect_sibling_prefix_overlap(headings)
    tokens = [tok for tok, _ in overlaps]
    assert "인천" in tokens


def test_detect_sibling_prefix_overlap_no_false_positive() -> None:
    """첫 어절이 모두 다르면 빈 리스트."""
    from agents.common.h2_scoring import detect_sibling_prefix_overlap

    headings = [
        "계양 테크노밸리, 지난 4년 무엇을 했나",
        "인천시, 무엇이 달라지나요",
        "산업 단지 취득세, 최대 75% 감면",
    ]
    assert detect_sibling_prefix_overlap(headings) == []


def test_score_h2_aeo_flags_prefix_overlap_in_siblings() -> None:
    """형제 H2 와 첫 어절이 겹치면 H2_SIBLING_PREFIX_OVERLAP 이슈 발생."""
    from agents.common.h2_scoring import score_h2_aeo

    result = score_h2_aeo(
        "인천, 뒤처진 산단 오명 벗을 수 있을까",
        siblings=["인천, 17개 시도 중 유일한 미감면"],
        full_name="홍길동",
    )
    assert "H2_SIBLING_PREFIX_OVERLAP" in result["issues"]
    assert result["breakdown"]["uniqueness"] <= 0.5


def test_sanitize_h2_text_preserves_internal_quotes() -> None:
    """내부 인용구 따옴표는 보존하고, 전체를 감싼 대칭 따옴표만 제거한다."""
    assert sanitize_h2_text("인천, 17개 시도 중 유일한 '미감면'") == "인천, 17개 시도 중 유일한 '미감면'"
    assert sanitize_h2_text("'전체를 감싼 따옴표'") == "전체를 감싼 따옴표"
    assert sanitize_h2_text('"쌍따옴표 감쌈"') == "쌍따옴표 감쌈"


def test_detect_register_mismatch_catches_polite_plain_mix() -> None:
    """경어체(-인가요)와 평서체(-되나)가 혼재하면 True."""
    from agents.common.h2_scoring import detect_register_mismatch

    headings = [
        "광역교통망, 해법은 무엇인가요",
        "취득세 감면 얼마나 되나",
        "문세종, 취득세 감면으로 무엇을 노리나",
    ]
    assert detect_register_mismatch(headings) is True


def test_detect_register_mismatch_passes_uniform_plain() -> None:
    """전부 평서체면 False."""
    from agents.common.h2_scoring import detect_register_mismatch

    headings = [
        "취득세 감면 얼마나 되나",
        "문세종, 무엇을 노리나",
        "계양구, 도약할 수 있을까",
    ]
    assert detect_register_mismatch(headings) is False


def test_score_h2_aeo_flags_register_mismatch() -> None:
    """형제와 register 가 다르면 H2_REGISTER_MISMATCH 이슈 발생."""
    from agents.common.h2_scoring import score_h2_aeo

    result = score_h2_aeo(
        "취득세 감면 얼마나 되나",
        siblings=["광역교통망, 해법은 무엇인가요"],
        full_name="홍길동",
    )
    assert "H2_REGISTER_MISMATCH" in result["issues"]


# ── 서술형 아키타입 ──


def test_detect_archetype_narrative_basic() -> None:
    """사전형 종결(열다, 묻다, 잇다)은 서술형으로 감지되어야 한다."""
    from agents.common.h2_guide import detect_h2_archetype

    assert detect_h2_archetype("지역 경제의 새 판을 열다") == "서술형"
    assert detect_h2_archetype("주민 목소리에 귀를 기울이다") == "서술형"
    assert detect_h2_archetype("도시 재생이 삶을 바꾸다") == "서술형"


def test_detect_archetype_narrative_not_claim() -> None:
    """주장형 단정 패턴(이다/한다/없다)은 여전히 주장형이어야 한다."""
    from agents.common.h2_guide import detect_h2_archetype

    assert detect_h2_archetype("청년 기본소득은 필수다") == "주장형"
    assert detect_h2_archetype("지역 격차는 바로잡아야 한다") == "주장형"
    assert detect_h2_archetype("대안은 없다") == "주장형"


def test_narrative_not_archetype_mismatch() -> None:
    """서술형이 인식되면 ARCHETYPE_MISMATCH hard-fail이 발생하지 않아야 한다."""
    plan: dict = {
        "suggested_type": "서술형",
        "primary_archetypes": ["질문형", "주장형"],
        "auxiliary_archetypes": ["서술형"],
    }
    result = score_h2("지역 경제의 새 판을 열다", plan)
    assert "ARCHETYPE_MISMATCH" not in result["issues"]


def test_score_h2_aeo_flags_narrative_overuse() -> None:
    """서술형이 세트에서 2회 이상이면 H2_NARRATIVE_OVERUSE 이슈."""
    from agents.common.h2_scoring import score_h2_aeo

    result = score_h2_aeo(
        "지역 경제의 새 판을 열다",
        siblings=["주민 목소리에 귀를 기울이다", "청년 정책은 어떻게 바뀌나"],
        full_name="홍길동",
    )
    assert "H2_NARRATIVE_OVERUSE" in result["issues"]


def test_score_h2_aeo_no_narrative_overuse_single() -> None:
    """서술형이 세트에서 1회면 H2_NARRATIVE_OVERUSE 미발생."""
    from agents.common.h2_scoring import score_h2_aeo

    result = score_h2_aeo(
        "지역 경제의 새 판을 열다",
        siblings=["청년 정책은 어떻게 바뀌나", "지역 격차는 바로잡아야 한다"],
        full_name="홍길동",
    )
    assert "H2_NARRATIVE_OVERUSE" not in result["issues"]


# ── 사례형 regex 엄격화 ──


def test_evidence_regex_no_bare_result() -> None:
    """'결과' 단독(숫자 없음)은 사례형이 아니어야 한다."""
    from agents.common.h2_guide import detect_h2_archetype

    assert detect_h2_archetype("주민 설문 결과를 정책에 반영") != "사례형"


def test_evidence_regex_with_number() -> None:
    """숫자 동반 '분석'/'결과'는 여전히 사례형."""
    from agents.common.h2_guide import detect_h2_archetype

    # "사례", "현장" 같은 강한 키워드는 무조건 사례형
    assert detect_h2_archetype("민원 처리 14일 단축 사례") == "사례형"
    assert detect_h2_archetype("청년 일자리 274명 창출 현장") == "사례형"


def test_evidence_regex_bare_analysis_not_case() -> None:
    """'분석' 단독(숫자 없음)은 사례형이 아니어야 한다."""
    from agents.common.h2_guide import detect_h2_archetype

    assert detect_h2_archetype("정책 분석의 새로운 방향") != "사례형"


# ── 쉼표형 counting ──


def test_comma_form_excess_detected() -> None:
    """쉼표 분리형 3개 이상이면 H2_COMMA_FORM_EXCESS."""
    from agents.common.h2_scoring import score_h2_aeo

    result = score_h2_aeo(
        "계양 테크노밸리, 제가 해내겠습니다",
        siblings=[
            "계양 광역철도, 주민 설문 결과를 반영",
            "B/C 분석 추진, 구체적인 계획은?",
        ],
        full_name="홍길동",
    )
    assert "H2_COMMA_FORM_EXCESS" in result["issues"]


def test_comma_form_ok_within_limit() -> None:
    """쉼표 분리형 2개 이하면 H2_COMMA_FORM_EXCESS 미발생."""
    from agents.common.h2_scoring import score_h2_aeo

    result = score_h2_aeo(
        "계양 테크노밸리, 제가 해내겠습니다",
        siblings=["광역철도 도입의 핵심 과제는 무엇인가"],
        full_name="홍길동",
    )
    assert "H2_COMMA_FORM_EXCESS" not in result["issues"]


# ── Prefix overlap hard-fail ──


def test_prefix_overlap_is_hard_fail() -> None:
    """PREFIX_OVERLAP이 H2_HARD_FAIL_ISSUES에 포함되어 있어야 한다."""
    from agents.common.h2_scoring import H2_HARD_FAIL_ISSUES

    assert "H2_SIBLING_PREFIX_OVERLAP" in H2_HARD_FAIL_ISSUES


# ── H2-title echo ──


def test_title_echo_detected() -> None:
    """H2가 제목과 Jaccard 0.7 이상이면 H2_TITLE_ECHO."""
    from agents.common.h2_scoring import score_h2_aeo

    # H2가 제목의 거의 그대로 복사 — 높은 Jaccard
    result = score_h2_aeo(
        "테크노밸리 광역철도 상반기 분석 추진",
        article_title="테크노밸리 광역철도, 2026년 상반기 분석 추진",
        full_name="홍길동",
    )
    assert "H2_TITLE_ECHO" in result["issues"]


def test_title_echo_not_triggered_different() -> None:
    """H2가 제목과 충분히 다르면 H2_TITLE_ECHO 미발생."""
    from agents.common.h2_scoring import score_h2_aeo

    result = score_h2_aeo(
        "광역철도 도입, 주민 설문 결과를 정책에 반영",
        article_title="계양 테크노밸리 광역철도, 2026년 상반기 B/C 분석 추진",
        full_name="홍길동",
    )
    assert "H2_TITLE_ECHO" not in result["issues"]


# ── 구체성 체크 (H2_GENERIC_CONTENT) ──


def test_generic_content_is_hard_fail() -> None:
    """H2_GENERIC_CONTENT가 hard-fail 목록에 포함되어 있어야 한다."""
    from agents.common.h2_scoring import H2_HARD_FAIL_ISSUES

    assert "H2_GENERIC_CONTENT" in H2_HARD_FAIL_ISSUES


@pytest.mark.skipif(
    korean_morph.get_kiwi() is None,
    reason="kiwi unavailable — NNP 기반 구체성 판정 불가",
)
def test_generic_content_detected_for_cliche_h2() -> None:
    """인물명·지역명 제외 시 고유명사/숫자 없는 상투적 H2 → H2_GENERIC_CONTENT."""
    from agents.common.h2_scoring import score_h2_aeo

    result = score_h2_aeo(
        "샘플시 샘플구, 혁신과 포용으로 나아가는 길",
        full_name="홍길동",
        full_region="샘플시 샘플구",
    )
    assert "H2_GENERIC_CONTENT" in result["issues"]


@pytest.mark.skipif(
    korean_morph.get_kiwi() is None,
    reason="kiwi unavailable — NNP 기반 구체성 판정 불가",
)
def test_generic_content_not_triggered_for_concrete_h2() -> None:
    """구체적 고유명사·숫자가 포함된 H2 → H2_GENERIC_CONTENT 미발생."""
    from agents.common.h2_scoring import score_h2_aeo

    result = score_h2_aeo(
        "귤현동 탄약고 이전, 군사시설 문제 해결 방안",
        full_name="홍길동",
        full_region="샘플시 샘플구",
    )
    assert "H2_GENERIC_CONTENT" not in result["issues"]


# ---------------------------------------------------------------------------
# 상투어 밀도 체크 (NNP 1개 + 상투어 다수 → 실패)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    korean_morph.get_kiwi() is None,
    reason="kiwi unavailable — NNG 밀도 판정 불가",
)
def test_cliche_density_blocks_single_nnp_with_cliches() -> None:
    """NNP 1개 + 상투어 다수 → H2_GENERIC_CONTENT."""
    from agents.common.h2_scoring import _has_concrete_content

    # "광역철도"(NNP 1개) + "미래"/"도약"(상투어 2/2)
    assert _has_concrete_content("광역철도, 미래를 향한 새로운 도약", "", "") is False


@pytest.mark.skipif(
    korean_morph.get_kiwi() is None,
    reason="kiwi unavailable — NNG 밀도 판정 불가",
)
def test_cliche_density_passes_with_enough_concrete() -> None:
    """구체 토큰 충분 → 상투어가 있어도 통과."""
    from agents.common.h2_scoring import _has_concrete_content

    # "귤현동"(NNP) + "탄약고"(NNP) + "이전"(NNG, 상투어 아님)
    assert _has_concrete_content("귤현동 탄약고 이전, 왜 지금인가", "", "") is True


@pytest.mark.skipif(
    korean_morph.get_kiwi() is None,
    reason="kiwi unavailable — NNG 밀도 판정 불가",
)
def test_cliche_density_passes_low_density() -> None:
    """상투어 밀도 낮으면 NNP 1개라도 통과."""
    from agents.common.h2_scoring import _has_concrete_content

    # NNG 중 상투어 비율이 0.6 미만
    assert _has_concrete_content("광역철도 사업 추진 일정 공개", "", "") is True


# ---------------------------------------------------------------------------
# 영문 약어 잘림 감지 (has_incomplete_h2_ending)
# ---------------------------------------------------------------------------

def test_incomplete_ending_ascii_abbreviation() -> None:
    """슬래시 포함 영문 약어(B/C)로 끝나면 잘림으로 감지."""
    from agents.common.h2_guide import has_incomplete_h2_ending

    assert has_incomplete_h2_ending("광역철도, 2026년 상반기 B/C") is True


def test_incomplete_ending_ascii_abbreviation_with_korean_suffix() -> None:
    """영문 약어 뒤에 한국어가 붙으면 정상."""
    from agents.common.h2_guide import has_incomplete_h2_ending

    assert has_incomplete_h2_ending("광역철도, 2026년 B/C 분석 완료") is False


def test_incomplete_ending_trailing_slash() -> None:
    """슬래시로 끝나면 잘림."""
    from agents.common.h2_guide import has_incomplete_h2_ending

    assert has_incomplete_h2_ending("계양 테크노밸리 S-BRT/") is True


# ── 개체 명사 종결 / "왜" 미완결 질문 ────────────────────────────────

def _kiwi_can_run() -> bool:
    import os
    for key in ("USERPROFILE", "HOME", "TEMP", "TMP"):
        value = os.environ.get(key, "")
        if not value:
            continue
        try:
            value.encode("ascii")
        except UnicodeEncodeError:
            return False
    try:
        from agents.common import korean_morph
        return korean_morph.get_kiwi() is not None
    except Exception:
        return False


_KIWI_OK = _kiwi_can_run()
_kiwi_required = pytest.mark.skipif(
    not _KIWI_OK,
    reason="kiwipiepy 초기화 불가 환경",
)


@_kiwi_required
def test_entity_noun_ending_blocked() -> None:
    """동작 명사가 아닌 개체 명사(주민, 청년)로 끝나면 미완결."""
    from agents.common.h2_guide import has_incomplete_h2_ending

    assert has_incomplete_h2_ending("계양 테크노밸리 주민") is True
    assert has_incomplete_h2_ending("주변 개발, 인천광역시 청년") is True


@_kiwi_required
def test_action_noun_ending_passes() -> None:
    """동작 명사(이전, 분석)로 끝나면 완결."""
    from agents.common.h2_guide import has_incomplete_h2_ending

    assert has_incomplete_h2_ending("귤현동 탄약고 이전") is False
    assert has_incomplete_h2_ending("광역철도, 2026년 경제성 분석") is False


@_kiwi_required
def test_incomplete_wae_question() -> None:
    """'왜' 의문사 + 서술어 없음 → 미완결."""
    from agents.common.h2_guide import has_incomplete_h2_ending

    assert has_incomplete_h2_ending("왜 재정사업") is True


@_kiwi_required
def test_complete_wae_question_passes() -> None:
    """'왜' + 종결어미 있으면 완결."""
    from agents.common.h2_guide import has_incomplete_h2_ending

    assert has_incomplete_h2_ending("귤현동 탄약고 이전, 왜 지금인가") is False
    assert has_incomplete_h2_ending("왜 지금인가?") is False


@_kiwi_required
def test_truncated_comma_tail_single_nnp() -> None:
    """쉼표 뒤 NNP 1개 → 잘림."""
    from agents.common.h2_guide import has_incomplete_h2_ending

    assert has_incomplete_h2_ending("코로나 이후 인천e음, 인천") is True


@_kiwi_required
def test_truncated_comma_tail_year() -> None:
    """쉼표 뒤 연도만 → 잘림."""
    from agents.common.h2_guide import has_incomplete_h2_ending

    assert has_incomplete_h2_ending("광역철도 경제성 분석, 2026년") is True


@_kiwi_required
def test_comma_tail_with_predicate_passes() -> None:
    """쉼표 뒤에 용언 종결 있으면 통과."""
    from agents.common.h2_guide import has_incomplete_h2_ending

    assert has_incomplete_h2_ending("귤현동 탄약고 이전, 왜 지금인가") is False


def test_comma_tail_long_passes() -> None:
    """쉼표 뒤 토큰 3개 이상이면 통과."""
    from agents.common.h2_guide import has_incomplete_h2_ending

    assert has_incomplete_h2_ending("귤현역 탄약고 문제, 인천 청년 정치인의 해법") is False


# ---------------------------------------------------------------------------
# _is_field_copy — repair LLM 필드값 복사 거부
# ---------------------------------------------------------------------------
def test_is_field_copy_detects_entity_surface() -> None:
    """repair 결과가 assigned_entity_surface 그대로이면 True."""
    plan = {"assigned_entity_surface": "인천광역시 청년 정치인", "must_include_keyword": "탄약고", "key_claim": ""}
    assert _is_field_copy("인천광역시 청년 정치인", plan) is True


def test_is_field_copy_passes_normal_heading() -> None:
    """정상 H2는 False."""
    plan = {"assigned_entity_surface": "인천광역시 청년 정치인", "must_include_keyword": "탄약고", "key_claim": ""}
    assert _is_field_copy("귤현동 탄약고 이전, 2027년까지 완료", plan) is False


def test_is_field_copy_detects_keyword_copy() -> None:
    """repair 결과가 must_include_keyword 그대로이면 True."""
    plan = {"assigned_entity_surface": "", "must_include_keyword": "계양 테크노밸리", "key_claim": ""}
    assert _is_field_copy("계양 테크노밸리", plan) is True


# ── _deterministic_prerepair: question-form "?" 보충 + comma tail cascade 방지 ──


def test_prerepair_question_form_appends_question_mark() -> None:
    """question-form plan + topic particle 종결 → "?" 보충, while loop 미진입."""
    agent = SubheadingAgent.__new__(SubheadingAgent)
    plan = {"answer_type": "question-form"}
    result = agent._deterministic_prerepair(
        "아라뱃길 공연장, 재추진 방안은", plan, style="aeo",
    )
    assert result.endswith("?"), f"expected trailing '?', got {result!r}"
    assert "방안은?" in result


def test_prerepair_no_question_mark_for_assertive() -> None:
    """assertive style 에서는 topic particle 이 있어도 "?" 보충 안 함."""
    agent = SubheadingAgent.__new__(SubheadingAgent)
    plan = {"answer_type": "question-form"}
    result = agent._deterministic_prerepair(
        "아라뱃길 공연장 재추진 방안은", plan, style="assertive",
    )
    assert "?" not in result


@pytest.mark.parametrize("ending,expected_tail", [
    ("선호하는 노선은 무엇인가요", "무엇인가요?"),
    ("철도 시대가 열릴까요", "열릴까요?"),
    ("어떻게 약속했나요", "약속했나요?"),
    ("경제성 분석 완료될까", "완료될까?"),
    ("왜 지금 추진하나", "추진하나?"),
])
def test_prerepair_question_ef_appends_question_mark(ending: str, expected_tail: str) -> None:
    """의문형 EF(나요/까요/까/나) 종결 → "?" 보충."""
    agent = SubheadingAgent.__new__(SubheadingAgent)
    plan = {"answer_type": "question-form"}
    result = agent._deterministic_prerepair(ending, plan, style="aeo")
    assert result.endswith("?"), f"expected trailing '?', got {result!r}"
    assert expected_tail in result


def test_prerepair_comma_tail_no_cascade() -> None:
    """while loop 에서 쉼표 꼬리 연쇄 절단이 발생하지 않아야 한다."""
    agent = SubheadingAgent.__new__(SubheadingAgent)
    plan = {"answer_type": "declarative-list"}
    result = agent._deterministic_prerepair(
        "샘플구 공연장, 민선9기 재추진", plan, style="aeo",
    )
    # "재추진" 이 살아 있어야 한다 (cascade 가 없으면 제거 안 됨)
    assert "재추진" in result, f"cascade truncation occurred: {result!r}"


def test_prerepair_incomplete_interrogative_completion() -> None:
    """미완결 관형절 '것인' → '것인가?' 완성."""
    agent = SubheadingAgent.__new__(SubheadingAgent)
    plan = {"answer_type": "question-form"}
    result = agent._deterministic_prerepair(
        "시민 약속을 어떻게 지킬 것인", plan, style="aeo",
    )
    assert result.endswith("것인가?"), f"expected '것인가?' ending: {result!r}"


def test_prerepair_incomplete_interrogative_것일() -> None:
    """미완결 관형절 '것일' → '것일까?' 완성."""
    agent = SubheadingAgent.__new__(SubheadingAgent)
    plan = {"answer_type": "question-form"}
    result = agent._deterministic_prerepair(
        "정책 방향은 어떤 것일", plan, style="aeo",
    )
    assert result.endswith("것일까?"), f"expected '것일까?' ending: {result!r}"


def test_prerepair_completion_respects_max_length() -> None:
    """완성 후 H2_MAX_LENGTH 초과 시 보충하지 않는다."""
    agent = SubheadingAgent.__new__(SubheadingAgent)
    plan = {"answer_type": "question-form"}
    # 24자 + "가?" = 26자 > H2_MAX_LENGTH(25) → 보충 안 됨
    long_h2 = "가나다라마바사아자차카타파하하하하하하하하하 것인"  # 24 chars
    result = agent._deterministic_prerepair(long_h2, plan, style="aeo")
    assert not result.endswith("것인가?"), f"should not complete over max: {result!r}"
