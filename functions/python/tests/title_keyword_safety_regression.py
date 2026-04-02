import asyncio
import pathlib
import sys
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from agents.common.title_generation import (
    _build_previous_attempt_pattern_feedback,
    _detect_title_structural_defect,
    _detect_possessive_modifier_pattern,
    build_title_prompt,
    calculate_title_quality_score,
    generate_and_validate_title,
    resolve_title_purpose,
)
from agents.common.title_common import build_structured_title_candidates, detect_content_type
from agents.common.h2_guide import has_incomplete_h2_ending, sanitize_h2_text
from agents.common.role_keyword_policy import build_role_keyword_policy
from agents.core.keyword_injector_agent import KeywordInjectorAgent
from agents.core.prompt_builder import build_structure_prompt
from agents.core.structure_agent import StructureAgent
from agents.core.title_agent import TitleAgent
from handlers.generate_posts_pkg.pipeline import (
    _apply_final_sentence_polish_once,
    _drop_low_signal_analysis_sentences_once,
    _drop_observer_frame_sentences_once,
    _ensure_closing_section_min_sentences_once,
    _recover_short_content_once,
    _repair_contextless_section_openers_once,
    _repair_identity_signature_exact_form_once,
    _repair_speaker_consistency_once,
    _repair_self_reference_placeholders_once,
    _scrub_broken_poll_fragments_once,
)
from services.posts.validation.keyword_injection import _find_similar_sentence_in_content
from services.posts.validation.keyword_reduction import _rewrite_sentence_to_reduce_keyword


def _build_matchup_bundle() -> dict:
    return {
        "scope": "matchup",
        "speaker": "이재성",
        "focusNames": ["이재성", "전재수"],
        "titleNamePriority": ["이재성", "전재수"],
        "titleNameRepeatLimit": 1,
        "primaryPair": {
            "speaker": "이재성",
            "opponent": "전재수",
            "speakerPercent": "31.7%",
            "opponentPercent": "29.4%",
        },
        "secondaryPairs": [],
        "primaryFactTemplate": {
            "sentence": "이재성·전재수 가상대결에서는 31.7% 대 29.4%로 나타났습니다.",
            "heading": "전재수와의 가상대결서 확인된 이재성 경쟁력",
        },
        "allowedTitleLanes": [
            {
                "id": "fact_direct",
                "label": "fact_direct",
                "template": "이재성·전재수 가상대결 31.7% 대 29.4%",
            }
        ],
        "allowedH2Kinds": [],
        "forbiddenMetrics": ["정당 지지율"],
        "focusedSourceText": "[주대결] 이재성·전재수 가상대결에서는 31.7% 대 29.4%로 나타났습니다.",
    }


def test_keyword_injector_insert_after_anchor_rejects_mid_sentence_boundary() -> None:
    agent = object.__new__(KeywordInjectorAgent)
    content = "<p>서로의 비전과 정책을 통해 시민과 만나겠습니다.</p>"

    updated, changed = agent._insert_after_anchor(content, "서로의", "이재성 전재수")

    assert changed is False
    assert updated == content


def test_keyword_injector_apply_instructions_rolls_back_unsafe_replace() -> None:
    agent = object.__new__(KeywordInjectorAgent)
    content = "<p>서로의 비전과 정책을 통해 시민과 만나겠습니다.</p>"
    sections = [{"startIndex": 0, "endIndex": len(content), "type": "body1"}]
    instructions = [
        {
            "section": 0,
            "action": "replace",
            "target": "서로의",
            "replacement": "서로의 이재성 전재수",
        }
    ]

    updated = agent.apply_instructions(
        content,
        sections,
        instructions,
        user_keywords=["이재성", "전재수"],
    )

    assert updated == content


def test_find_similar_sentence_in_content_detects_near_duplicate_keyword_padding() -> None:
    candidate = "핵심 부산 교통 과제를 단계별로 정리하고 성과가 보이도록 꾸준히 점검하겠습니다."
    existing = (
        "<p>핵심 과제를 단계별로 정리하고 성과가 보이도록 꾸준히 점검하겠습니다.</p>"
        "<p>핵심 부산 교통 과제를 단계별로 정리하고 성과가 보이도록 꾸준히 점검하겠습니다.</p>"
    )

    matched = _find_similar_sentence_in_content(
        candidate,
        existing,
        exclude_sentences=["핵심 과제를 단계별로 정리하고 성과가 보이도록 꾸준히 점검하겠습니다."],
    )

    assert "핵심 부산 교통 과제를 단계별로 정리" in matched


def test_build_structure_prompt_includes_first_person_news_rewrite_rule() -> None:
    prompt = build_structure_prompt(
        {
            "topic": "이재성 전재수 경선",
            "instructions": "이번 경선의 의미를 주민의 일상과 연결해 설명합니다.",
            "newsContext": "이재성은 미래형 리더라는 이미지를 구축하며 당심 잡기에 나섰습니다.",
            "author": {"name": "이재성"},
            "userProfile": {"name": "이재성"},
        }
    )

    assert "문장 자체를 원고에 옮기지 않음" in prompt
    assert "3인칭 보도 서술" in prompt
    assert "본인의 이미지·전략·포지셔닝을 외부 시선으로 서술하지 않음" in prompt
    assert "이미지를 구축하며" in prompt
    assert "당심 잡기에 나서고 있습니다" in prompt


def test_build_structure_prompt_includes_observer_voice_review_and_section_continuity_rules() -> None:
    prompt = build_structure_prompt(
        {
            "topic": "이재성 전재수 경선",
            "category": "current-affairs",
            "writingMethod": "logical_writing",
            "authorName": "이재성",
            "authorBio": "이재성 소개",
            "instructions": "부산 경제 해법과 경선 의미를 설명합니다.",
            "newsContext": "민주당 공관위는 경선 후보를 선정했습니다.",
            "ragContext": "",
            "targetWordCount": 2000,
            "partyStanceGuide": "",
            "contextAnalysis": {},
            "userProfile": {"name": "이재성"},
            "personalizationContext": "",
            "memoryContext": "",
            "styleGuide": "",
            "styleFingerprint": {},
            "profileSupportContext": "",
            "profileSubstituteContext": "",
            "newsSourceMode": "news",
            "userKeywords": ["이재성", "전재수"],
            "pollFocusBundle": {},
            "lengthSpec": {
                "body_sections": 3,
                "total_sections": 5,
                "min_chars": 1800,
                "max_chars": 2400,
                "per_section_min": 260,
                "per_section_max": 420,
                "per_section_recommended": 340,
            },
            "outputMode": "json",
        }
    )

    assert "기자가 쓴 것처럼 들리는 문장" in prompt
    assert "\"이는\", \"이러한\", \"이것은\"으로 시작하려면" in prompt


def test_sanitize_h2_text_repairs_duplicate_particles_and_tokens() -> None:
    cleaned = sanitize_h2_text("부산 경제 도약을을 전략")
    deduped = sanitize_h2_text("민주당 민주당 혁신 전략 구상")

    assert cleaned == "부산 경제 도약을 전략"
    assert deduped == "민주당 혁신 전략 구상"


def test_sanitize_h2_text_truncates_at_word_boundary() -> None:
    result = sanitize_h2_text("이재성 vs 전재수, 부산 미래를 건 진짜 승부")

    assert result == "이재성 vs 전재수, 부산 미래를 건 진짜"
    assert not result.endswith("진짜 승")
    assert len(result) <= 25
    assert len(result) >= 10


def test_sanitize_h2_text_truncates_exact_max_length_incomplete_ending() -> None:
    text = "부산경제 대혁신, 시민 여러분과 함께 이뤄내겠"

    assert len(text) == 25

    result = sanitize_h2_text(text, max_length=25)

    assert not result.endswith("겠")
    assert result == "부산경제 대혁신, 시민 여러분과 함께"
    assert len(result) <= 25


def test_has_incomplete_h2_ending_detects_particle_and_unfinished_endings() -> None:
    bad = ["부산의 미래를", "미래 확신을", "시민과 함께 이뤄내겠", "부산의 새로운 시"]
    good = ["부산의 미래는?", "경제 혁신의 시작", "4월 3일 KNN 토론"]

    for text in bad:
        assert has_incomplete_h2_ending(text) is True, text

    for text in good:
        assert has_incomplete_h2_ending(text) is False, text


def test_structure_agent_json_prompt_includes_heading_self_check_and_concrete_fill_rules() -> None:
    agent = StructureAgent(options={})
    prompt = agent._build_structure_json_prompt(
        prompt="BASE",
        length_spec={
            "body_sections": 3,
            "total_sections": 5,
            "paragraphs_per_section": 2,
            "per_section_min": 260,
            "per_section_max": 420,
            "min_chars": 1800,
            "max_chars": 2400,
        },
    )

    assert "조사나 단어가 중복되거나 의미가 덜 끝난 부분" in prompt
    assert "소제목에 '[인물명]의 [형용사형 어구]' 구조를 쓰지 말 것" in prompt
    assert "서술어 없는 명사 나열로 끝나면 질문형" in prompt
    assert "조사나 술어가 어색하게 잘린 경우('확신을 길', '진짜 승' 등)" in prompt
    assert "그래서 구체적으로 어떻게 할 건데?" in prompt
    assert "직전 섹션 마지막 2문장" in prompt


def test_drop_observer_frame_sentences_once_removes_news_voice_residue() -> None:
    content = (
        "<p>민주당 공관위는 27일 후보 공모 참여자를 경선 후보로 선정했습니다.</p>"
        "<p>저는 현장에서 확인한 부산 경제 문제를 정책으로 풀겠습니다.</p>"
        "<p>저는 IT 기업인 출신의 전문성을 살려 미래형 리더라는 이미지를 구축하며 당심 잡기에 나서고 있습니다.</p>"
    )

    result = _drop_observer_frame_sentences_once(content)

    assert result["edited"] is True
    assert "경선 후보로 선정했습니다" not in result["content"]
    assert "이미지를 구축하며" not in result["content"]
    assert "당심 잡기에 나서고 있습니다" not in result["content"]
    assert "부산 경제 문제를 정책으로 풀겠습니다" in result["content"]


def test_drop_observer_frame_sentences_once_removes_observer_variant_phrase() -> None:
    content = (
        "<p>저는 IT 기업인 출신의 전문성을 살려 미래형 리더라는 이미지를 확고히 구축하며 "
        "당심과 민심을 동시에 사로잡기 위해 나섰습니다.</p>"
        "<p>스마트 항만과 자율운항 산업을 부산의 성장축으로 만들겠습니다.</p>"
    )

    result = _drop_observer_frame_sentences_once(content)

    assert result["edited"] is True
    assert "이미지를 확고히 구축하며" not in result["content"]
    assert "사로잡기 위해 나섰습니다" not in result["content"]
    assert "스마트 항만과 자율운항 산업을 부산의 성장축으로 만들겠습니다." in result["content"]


def test_drop_observer_frame_sentences_once_removes_convention_effect_sentence() -> None:
    content = (
        "<p>민주당 공관위는 경선 과정을 통해 선거 분위기를 고조시키는 컨벤션 효과를 "
        "극대화하기 위해 최종적으로 경선 실시를 결정했습니다.</p>"
        "<p>저는 부산 경제의 해법을 정책 경쟁으로 분명하게 보여드리겠습니다.</p>"
    )

    result = _drop_observer_frame_sentences_once(content)

    assert result["edited"] is True
    assert "컨벤션 효과" not in result["content"]
    assert "경선 실시를 결정했습니다" not in result["content"]
    assert "부산 경제의 해법을 정책 경쟁으로 분명하게 보여드리겠습니다." in result["content"]


def test_drop_observer_frame_sentences_once_removes_role_emphasis_sentence() -> None:
    content = (
        "<p>전재수 의원은 풍부한 의정 경험과 지역 기반을 바탕으로 준비된 시장임을 강조합니다.</p>"
        "<p>저는 부산 경제를 바꿀 실행 계획을 시민 여러분께 직접 말씀드리겠습니다.</p>"
    )

    result = _drop_observer_frame_sentences_once(content)

    assert result["edited"] is True
    assert "준비된 시장임을 강조합니다" not in result["content"]
    assert "저는 부산 경제를 바꿀 실행 계획을 시민 여러분께 직접 말씀드리겠습니다." in result["content"]


def test_repair_contextless_section_openers_once_rewrites_ireohan_lead() -> None:
    content = (
        "<p>소년의집에서 아이들과 함께 지내며 공동체의 어려움을 가까이에서 봤습니다.</p>"
        "<h2>정치적 무게감과 혁신성, 부산의 선택은</h2>"
        "<p>이러한 선택은 부산 시민들에게 과거와 현재, 미래를 아우르는 다양한 선택지를 제공합니다.</p>"
    )

    result = _repair_contextless_section_openers_once(content)

    assert result["edited"] is True
    assert "이러한 선택은" not in result["content"]
    assert "부산 시민들에게" in result["content"]


def test_repair_contextless_section_openers_once_rewrites_choice_opportunity_lead() -> None:
    content = (
        "<p>소년의집에서 아이들과 함께 지내며 공동체의 어려움을 가까이에서 봤습니다.</p>"
        "<h2>혁신 기업인 이재성의 부산 경제 대전환 비전</h2>"
        "<p>이는 부산의 미래를 위한 중요한 선택의 기회를 시민들에게 제공하는 것입니다.</p>"
    )

    result = _repair_contextless_section_openers_once(content)

    assert result["edited"] is True
    assert "이는 부산의 미래를 위한 중요한 선택의 기회를" not in result["content"]
    assert "비전은 부산의 미래를 위한 중요한 선택의 기회를" in result["content"]


def test_repair_contextless_section_openers_once_rewrites_choice_start_lead() -> None:
    content = (
        "<p>소년의집에서 아이들과 함께 지내며 공동체의 어려움을 가까이에서 봤습니다.</p>"
        "<h2>민주당 예비후보 확정, 새로운 부산의 시작입니다</h2>"
        "<p>이는 부산의 미래를 위한 중요한 선택의 시작을 알리는 것입니다. 다음 문장입니다.</p>"
    )

    result = _repair_contextless_section_openers_once(content)

    assert result["edited"] is True
    assert "이는 부산의 미래를 위한 중요한 선택의 시작을 알리는 것입니다." not in result["content"]
    assert "선택의 시작을 알리는 것입니다." in result["content"]


def test_ensure_closing_section_min_sentences_once_appends_support_sentence() -> None:
    content = (
        "<p>부산의 변화는 더 미룰 수 없습니다.</p>"
        "<h2>시민 여러분과 함께 이뤄내겠습니다</h2>"
        "<p>부산 경제를 다시 세우겠습니다.</p>"
    )

    result = _ensure_closing_section_min_sentences_once(content, full_name="이재성")

    assert result["edited"] is True
    assert "부산 경제를 다시 세우겠습니다." in result["content"]
    assert "시민 여러분과 함께 약속한 변화를 생활의 결과로 보여드리겠습니다." in result["content"]


def test_ensure_closing_section_min_sentences_once_restores_empty_closing_before_tail_text() -> None:
    content = (
        "<p>부산의 변화는 더 미룰 수 없습니다.</p>"
        "<h2>부산 경제 대혁신, 반드시 이뤄내겠습니다</h2>"
        "후원계좌 안내"
    )

    result = _ensure_closing_section_min_sentences_once(content, full_name="이재성")

    assert result["edited"] is True
    assert "<p>" in result["content"]
    assert "후원계좌 안내" in result["content"]
    assert "부산 경제 대혁신" in result["content"]


def test_recover_short_content_once_targets_short_sections_with_concrete_fill_prompt() -> None:
    captured: dict[str, str] = {}

    async def _fake_generate_content_async(prompt: str, **_kwargs):
        captured["prompt"] = prompt
        return "<content><p>짧은 본문</p><h2>부산 경제 해법</h2><p>스마트 항만으로 물류 경쟁력을 높이겠습니다. 실행 계획도 공개하겠습니다.</p></content>"

    with patch("agents.common.gemini_client.generate_content_async", new=_fake_generate_content_async):
        _recover_short_content_once(
            content="<p>도입입니다.</p><h2>부산 경제 해법</h2><p>스마트 항만을 만들겠습니다.</p>",
            title="부산 경제 해법",
            topic="이재성 전재수 경선",
            min_required_chars=1600,
            target_word_count=2000,
            user_keywords=["이재성", "전재수"],
            auto_keywords=[],
            body_min_overrides={},
            user_keyword_expected_overrides={},
            user_keyword_max_overrides={},
            skip_user_keywords=None,
            role_keyword_policy={},
    )

    assert "그래서 구체적으로 어떻게 할 건데?" in captured["prompt"]
    assert "<short_sections>" in captured["prompt"]
    assert "부산 경제 해법" in captured["prompt"]


def test_recover_short_content_once_retries_when_first_pass_still_short() -> None:
    prompts: list[str] = []
    responses = iter(
        [
            (
                "<content><p>도입입니다.</p><h2>부산 경제 해법</h2>"
                "<p>산업 전환 계획을 설명하겠습니다. 실행 방향도 함께 말씀드리겠습니다.</p></content>"
            ),
            (
                "<content><p>도입입니다.</p><h2>부산 경제 해법</h2>"
                "<p>산업 전환 계획을 설명하겠습니다. 실행 순서와 대상 산업, 예산 확보 방식까지 이어서 말씀드리겠습니다.</p></content>"
            ),
        ]
    )

    async def _fake_generate_content_async(prompt: str, **_kwargs):
        prompts.append(prompt)
        return next(responses)

    with patch("agents.common.gemini_client.generate_content_async", new=_fake_generate_content_async):
        result = _recover_short_content_once(
            content="<p>도입입니다.</p><h2>부산 경제 해법</h2><p>산업 전환 계획을 설명하겠습니다.</p>",
            title="부산 경제 해법",
            topic="이재성 전재수 경선",
            min_required_chars=1600,
            target_word_count=2000,
            user_keywords=["이재성", "전재수"],
            auto_keywords=[],
            body_min_overrides={},
            user_keyword_expected_overrides={},
            user_keyword_max_overrides={},
            skip_user_keywords=None,
            role_keyword_policy={},
        )

    assert result["edited"] is True
    assert len(prompts) == 2
    assert "retry_hint" in prompts[1]
    assert "부족합니다" in prompts[1]


def test_scrub_broken_poll_fragments_once_removes_incomplete_news_clause() -> None:
    content = (
        "<p>민주당 공관위는 27일 부산시장 선거 후보 공모에 참여한 "
        "이번 결정은 현역 의원의 정치적 무게감과 혁신성이 맞붙는 구도로 읽힙니다.</p>"
        "<p>저는 부산 경제의 해법을 더 분명하게 제시하겠습니다.</p>"
    )

    result = _scrub_broken_poll_fragments_once(content, known_names=["이재성", "전재수"])

    assert result["edited"] is True
    assert "후보 공모에 참여한 이번 결정은" not in result["content"]
    assert "부산 경제의 해법을 더 분명하게 제시하겠습니다." in result["content"]


def test_rewrite_sentence_to_reduce_keyword_keeps_self_identification_sentence() -> None:
    policy = build_role_keyword_policy(
        ["이재성"],
        source_texts=["부산시장 예비후보 이재성이 정책을 발표했다."],
    )

    rewritten = _rewrite_sentence_to_reduce_keyword(
        "뼛속까지 부산사람, 이재성입니다.",
        "이재성",
        role_keyword_policy=policy,
    )

    assert rewritten == "뼛속까지 부산사람, 이재성입니다."


def test_repair_identity_signature_exact_form_once_restores_name_after_keyword_reduction() -> None:
    result = _repair_identity_signature_exact_form_once(
        "<p>뼛속까지 부산사람, 이 후보입니다.</p>",
        full_name="이재성",
    )

    assert result["edited"] is True
    assert "뼛속까지 부산사람, 이재성입니다." in result["content"]


def test_repair_self_reference_placeholders_once_restores_name_or_first_person_surface() -> None:
    content = (
        "<p>저 이 후보에게 매우 뜻깊은 순간입니다.</p>"
        "<h2>부산 경제 대혁신, 이 후보가 반드시 이뤄내겠습니다</h2>"
    )

    result = _repair_self_reference_placeholders_once(content, full_name="이재성")

    assert result["edited"] is True
    assert "저에게 매우 뜻깊은 순간입니다." in result["content"]
    assert "이재성 후보가 반드시 이뤄내겠습니다" in result["content"]


def test_repair_self_reference_placeholders_once_restores_name_in_h2_without_pledge_signal() -> None:
    content = "<h2>민주당 이 예비후보 확정, 새로운 부산의 시작입니다</h2>"

    result = _repair_self_reference_placeholders_once(content, full_name="이재성")

    assert result["edited"] is True
    assert "민주당 이재성 예비후보 확정, 새로운 부산의 시작입니다" in result["content"]


def test_repair_self_reference_placeholders_once_restores_compact_placeholder_surface() -> None:
    content = "<p>저 이후보에게 다시 한 번 기회를 부탁드립니다.</p>"

    result = _repair_self_reference_placeholders_once(content, full_name="이재성")

    assert result["edited"] is True
    assert "저에게 다시 한 번 기회를 부탁드립니다." in result["content"]


def test_repair_self_reference_placeholders_once_restores_named_surface_in_body_statement() -> None:
    content = "<p>민주당 이 후보의 확정은 새로운 부산의 출발점입니다.</p>"

    result = _repair_self_reference_placeholders_once(content, full_name="이재성")

    assert result["edited"] is True
    assert "민주당 이재성 후보의 확정은 새로운 부산의 출발점입니다." in result["content"]


def test_repair_speaker_consistency_once_removes_name_plus_first_person_pronoun() -> None:
    result = _repair_speaker_consistency_once(
        "<p>이재성 저는 33세에 CJ인터넷 이사로 일했습니다.</p>",
        "이재성",
    )

    assert result["edited"] is True
    assert "이재성 저는" not in result["content"]
    assert "저는 33세에 CJ인터넷 이사로 일했습니다." in result["content"]


def test_drop_low_signal_analysis_sentences_once_removes_self_certification_claim() -> None:
    content = (
        "<p>저는 실질적인 성과를 만들어낼 수 있는 유일한 후보라고 자부합니다.</p>"
        "<p>스마트 항만과 자율운항 산업을 부산의 성장축으로 만들겠습니다.</p>"
        "<p>이는 저의 비전과 실질적인 경제 전문성을 인정한 결과라고 생각합니다.</p>"
    )

    result = _drop_low_signal_analysis_sentences_once(content)

    assert result["edited"] is True
    assert "유일한 후보라고 자부합니다" not in result["content"]
    assert "인정한 결과라고 생각합니다" not in result["content"]
    assert "스마트 항만과 자율운항 산업을 부산의 성장축으로 만들겠습니다." in result["content"]


def test_drop_low_signal_analysis_sentences_once_removes_generic_padding_variants() -> None:
    content = (
        "<p>행정 절차와 예산 흐름까지 살펴 실현 가능한 해법으로 다듬겠습니다.</p>"
        "<p>현장 목소리를 꾸준히 듣고 미흡한 지점은 빠르게 손보겠습니다.</p>"
        "<p>지역 현안에 대한 전문가 자문과 주민 토론을 병행하겠습니다.</p>"
        "<p>스마트 항만과 자율운항 산업을 부산의 성장축으로 만들겠습니다.</p>"
    )

    result = _drop_low_signal_analysis_sentences_once(content)

    assert result["edited"] is True
    assert "행정 절차와 예산 흐름까지 살펴" not in result["content"]
    assert "현장 목소리를 꾸준히 듣고" not in result["content"]
    assert "전문가 자문과 주민 토론을 병행하겠습니다" not in result["content"]
    assert "스마트 항만과 자율운항 산업을 부산의 성장축으로 만들겠습니다." in result["content"]


def test_final_sentence_polish_removes_passive_self_certification_and_repairs_section_opener() -> None:
    content = (
        "<h2>사람 곁에서 쌓은 현장 경험</h2>"
        "<p>소년의집에서 10년 동안 아이들과 생활하며 공동체의 어려움을 가까이서 보았습니다.</p>"
        "<h2>정치적 무게감과 혁신성, 부산의 선택은?</h2>"
        "<p>이는 부산 시민들에게 과거와 현재, 그리고 미래를 아우르는 다양한 선택지를 제공하며 "
        "더 분명한 판단 기준을 만들고 있습니다.</p>"
        "<p>이는 저의 비전과 실질적인 경제 전문성을 인정받은 결과입니다.</p>"
        "<p>부산의 새로운 미래를 이끌 준비가 완벽하게 되어 있습니다.</p>"
        "<p>스마트 항만과 자율운항 산업을 부산의 성장축으로 만들겠습니다.</p>"
    )

    result = _apply_final_sentence_polish_once(content, full_name="이재성")
    updated = str(result.get("content") or "")

    assert "이는 부산 시민들에게" not in updated
    assert "선택은" in updated
    assert "선택지를 제공하며" in updated
    assert "인정받은 결과입니다" not in updated
    assert "완벽하게 되어 있습니다" not in updated
    assert "스마트 항만과 자율운항 산업을 부산의 성장축으로 만들겠습니다." in updated


def test_ensure_closing_section_min_sentences_once_strengthens_single_sentence_closing() -> None:
    content = (
        "<p>부산의 변화는 더 미룰 수 없습니다.</p>"
        "<h2>부산 경제 대혁신, 이재성이 반드시 이뤄내겠습니다!</h2>"
        "<p>저의 실질적인 경영 노하우는 부산의 경제를 한 단계 더 도약시키는 강력한 원동력이 될 것입니다.</p>"
    )

    result = _ensure_closing_section_min_sentences_once(content, full_name="이재성")
    updated = str(result.get("content") or "")
    tail = updated.split("</h2>", 1)[-1]

    assert result["edited"] is True
    assert tail.count(".") + tail.count("!") + tail.count("?") >= 2
    assert "말보다 실행으로 결과를 증명하겠습니다." in updated or "시민의 삶에서 먼저 달라지는 변화로 끝까지 증명하겠습니다." in updated


def test_build_title_prompt_includes_name_priority_rule_for_matchup() -> None:
    prompt = build_title_prompt(
        {
            "topic": "이재성 전재수 경선",
            "contentPreview": "이재성·전재수 가상대결 31.7% 대 29.4% 결과가 나왔습니다.",
            "userKeywords": ["이재성", "전재수"],
            "keywords": [],
            "fullName": "이재성",
            "category": "current-affairs",
            "status": "active",
            "titleScope": {},
            "backgroundText": "",
            "stanceText": "",
            "contextAnalysis": {},
            "pollFocusBundle": _build_matchup_bundle(),
            "roleKeywordPolicy": {},
            "titleConstraintText": "동일 인물 이름은 제목 전체에서 1회만 사용할 것.",
            "titlePromptLite": True,
        }
    )

    assert "<title_name_priority>" in prompt
    assert "동일 인물명은 제목에서 최대 1회만 사용합니다." in prompt
    assert "동일 인물 이름은 제목 전체에서 1회만 사용할 것." in prompt


def test_build_title_prompt_blocks_content_phrase_fragment_attachment() -> None:
    prompt = build_title_prompt(
        {
            "topic": "경선 확정 입장",
            "contentPreview": "이번 경선은 네거티브 없는 정책 경선이 되어야 합니다.",
            "userKeywords": ["이재성", "전재수"],
            "keywords": [],
            "fullName": "이재성",
            "category": "current-affairs",
            "status": "active",
            "titleScope": {},
            "backgroundText": "",
            "stanceText": "",
            "contextAnalysis": {},
            "roleKeywordPolicy": {},
            "titlePromptLite": True,
        }
    )

    assert 'no_content_phrase_fragment' in prompt
    assert '"[인물명] 없는 정책"' in prompt


def test_calculate_title_quality_score_rejects_duplicate_focus_name_title() -> None:
    result = calculate_title_quality_score(
        "이재성 전재수, 이재성 위한 정책",
        {
            "topic": "이재성 전재수 경선",
            "contentPreview": "이재성·전재수 가상대결 31.7% 대 29.4% 결과가 나왔습니다.",
            "userKeywords": ["이재성", "전재수"],
            "fullName": "이재성",
            "category": "current-affairs",
            "pollFocusBundle": _build_matchup_bundle(),
        },
    )

    assert result["passed"] is False
    assert "focusNameRepeat" in result["breakdown"]
    assert result.get("repairedTitle") == "이재성·전재수 가상대결 31.7% 대 29.4%"


def test_calculate_title_quality_score_rejects_consecutive_duplicate_token_title() -> None:
    result = calculate_title_quality_score(
        "민주당 민주당, 혁신과 정치적 무게감의 대결 구도",
        {
            "topic": "민주당 경선 구도 분석",
            "contentPreview": "민주당 경선에서 혁신성과 정치 경험이 대비됐습니다.",
            "userKeywords": [],
            "fullName": "이재성",
            "category": "current-affairs",
        },
    )

    assert result["passed"] is False
    assert "malformedSurface" in result["breakdown"]
    assert result.get("repairedTitle") == "민주당, 혁신과 정치적 무게감의 대결 구도"


def test_calculate_title_quality_score_repairs_missing_object_particle_title() -> None:
    result = calculate_title_quality_score(
        "이재성 위한 정책",
        {
            "topic": "이재성 정책 방향",
            "contentPreview": "이재성이 부산 경제 정책 방향을 설명했습니다.",
            "userKeywords": ["이재성"],
            "fullName": "이재성",
            "category": "current-affairs",
        },
    )

    assert result["passed"] is False
    assert "malformedSurface" in result["breakdown"]
    assert result.get("repairedTitle") == "이재성을 위한 정책"


def test_calculate_title_quality_score_repairs_empty_modifier_title_from_topic() -> None:
    result = calculate_title_quality_score(
        "전재수, 이재성의 없는 정책",
        {
            "topic": "네거티브 없는 정책 경선",
            "contentPreview": "두 후보가 네거티브 없는 정책 경쟁을 강조했습니다.",
            "userKeywords": ["전재수"],
            "fullName": "이재성",
            "category": "current-affairs",
        },
    )

    assert result["passed"] is False
    assert "malformedSurface" in result["breakdown"]
    assert result.get("repairedTitle") == "전재수, 네거티브 없는 정책"


def test_generate_and_validate_title_raises_when_auto_repair_disabled() -> None:
    async def _fake_generate_fn(_prompt: str) -> str:
        return "이재성 위한 정책"

    async def _run() -> None:
        try:
            await generate_and_validate_title(
                _fake_generate_fn,
                {
                    "topic": "이재성 정책 방향",
                    "contentPreview": "이재성이 부산 경제 정책 방향을 설명했습니다.",
                    "userKeywords": ["이재성"],
                    "fullName": "이재성",
                    "category": "current-affairs",
                },
                {
                    "minScore": 1,
                    "maxAttempts": 1,
                    "candidateCount": 1,
                    "allowAutoRepair": False,
                },
            )
        except RuntimeError as error:
            assert "제목 생성 실패" in str(error)
            return
        raise AssertionError("자동 보정이 꺼진 상태에서는 예외가 그대로 올라와야 합니다.")

    asyncio.run(_run())


def test_build_structured_title_candidates_for_matchup_policy_topic() -> None:
    candidates = build_structured_title_candidates(
        {
            "topic": "전재수 의원과의 경선 확정 이후 부산 경제 정책 경쟁",
            "contentPreview": "이재성과 전재수의 경선 확정 이후 부산 경제 해법과 정책 경쟁 구도에 관심이 모이고 있습니다.",
            "backgroundText": "부산 경제와 정책 대결의 쟁점",
            "stanceText": "정책 경쟁으로 부산 경제를 바꾸겠다는 입장입니다.",
            "userKeywords": ["이재성", "전재수"],
            "fullName": "이재성",
        }
    )

    assert candidates
    assert any("이재성·전재수" in title for title in candidates)
    assert any("정책 대결" in title or "경제 해법" in title for title in candidates)
    assert all("…" not in title and "..." not in title for title in candidates)


def test_generate_and_validate_title_retries_ellipsis_surface_twice_before_success() -> None:
    prompts: list[str] = []
    responses = iter(
        [
            "이재성, 전재수 경선 확정…부산 정치 지형 바뀔까?",
            "이재성, 전재수 경선 확정…부산 경제, 누가 이끌까?",
            "이재성·전재수 경선 확정, 부산 정치 지형은 어디로",
        ]
    )

    async def _fake_generate_fn(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    result = asyncio.run(
        generate_and_validate_title(
            _fake_generate_fn,
            {
                "topic": "전재수 의원과의 경선 확정 이후 부산시장 선거 구도 평가",
                "contentPreview": (
                    "이재성과 전재수의 경선 확정 이후 부산시장 선거 구도와 정책 경쟁의 방향이 "
                    "부산 정치 지형에 어떤 변화를 만들지 관심이 모이고 있습니다."
                ),
                "userKeywords": ["이재성", "전재수"],
                "fullName": "이재성",
                "category": "current-affairs",
            },
            {
                "minScore": 1,
                "maxAttempts": 1,
                "candidateCount": 1,
                "allowAutoRepair": False,
            },
        )
    )

    assert result["title"] == "이재성·전재수 경선 확정, 부산 정치 지형은 어디로"
    assert len(prompts) == 3
    assert "<surface_retry" in prompts[1]
    assert "<surface_retry" in prompts[2]
    assert "말줄임표" in prompts[1]


def test_detect_possessive_modifier_pattern_flags_broken_title_shape() -> None:
    assert _detect_possessive_modifier_pattern("이재성의 존중하는 정책") is True
    assert _detect_possessive_modifier_pattern("문세종의 되는 정책 방향") is True
    assert _detect_possessive_modifier_pattern("이재성·전재수 경선 확정, 부산 경제 해법 경쟁") is False


def test_detect_title_structural_defect_flags_duplicate_name_negation_pattern() -> None:
    defect = _detect_title_structural_defect("이재성, 이재성 없는 정책")

    assert "이름 없는 정책" in defect


def test_detect_title_structural_defect_flags_missing_delimiter_after_vs_event_phrase() -> None:
    defect = _detect_title_structural_defect("이재성 vs 전재수 4월 3일 KNN 방송토론 안내")

    assert "구분자 누락" in defect
    assert "A vs B, C" in defect


def test_detect_title_structural_defect_flags_duplicate_name_possessive_pattern() -> None:
    defect = _detect_title_structural_defect("문세종, 문세종의 되는 정책")

    assert "이름 반복" in defect


def test_detect_content_type_prefers_policy_profile_over_question_answer() -> None:
    content = (
        "존경하는 인천 계양구민 여러분, 인천 계양구에서 당원과 시민을 위해 헌신해 온 문세종입니다. "
        "시민이 체감하는 입법 활동과 예산 확보를 통해 지역의 변화를 이끌어내고, "
        "여러분의 삶에 실질적인 도움이 되는 정책을 제안하고 실현해 나가겠습니다. "
        "이익공유형 기본소득 조례 제정을 추진합니다."
    )

    assert detect_content_type(content, "논평/이슈대응") == "EXPERT_KNOWLEDGE"


def test_build_title_prompt_includes_common_title_anti_patterns_block() -> None:
    prompt = build_title_prompt(
        {
            "topic": "문세종 정책 방향",
            "contentPreview": (
                "시민이 체감하는 입법 활동과 예산 확보를 통해 지역의 변화를 이끌어내고, "
                "삶에 실질적인 도움이 되는 정책을 제안하고 실현해 나가겠습니다."
            ),
            "stanceText": "계양구민에게 실질적인 도움이 되는 정책을 제시하겠습니다.",
            "fullName": "문세종",
            "userKeywords": ["문세종"],
            "category": "current-affairs",
        }
    )

    assert "<common_title_anti_patterns" in prompt
    assert "후보의 되는 정책" in prompt
    assert "후보, 후보의 되는 정책" in prompt


def test_calculate_title_quality_score_rejects_focus_name_possessive_modifier_title() -> None:
    result = calculate_title_quality_score(
        "문세종의 되는 정책 방향",
        {
            "topic": "계양구 민생 정책 방향",
            "contentPreview": "계양구민의 삶에 실질적인 도움이 되는 정책을 제안하고 실현해 나가겠습니다.",
            "userKeywords": ["문세종"],
            "fullName": "문세종",
            "category": "current-affairs",
        },
    )

    assert result["passed"] is False
    assert "malformedSurface" in result["breakdown"]
    assert result["breakdown"]["malformedSurface"]["issue"] == "focus_name_possessive_modifier"


def test_build_previous_attempt_pattern_feedback_mentions_possessive_modifier_pattern() -> None:
    feedback = _build_previous_attempt_pattern_feedback("이재성의 새로운 일자리")

    assert "직전 제목 구조 결함" in feedback
    assert "이름의 되는/하는/있는" in feedback
    assert "팩트+서사 구조" in feedback
    assert "지방선거 경선 확정, 원칙이 가른 판세" in feedback


def test_build_previous_attempt_pattern_feedback_mentions_structural_defect() -> None:
    feedback = _build_previous_attempt_pattern_feedback("이재성, 이재성 없는 정책")

    assert "직전 제목 구조 결함" in feedback
    assert "이름을 반복하거나 이름에 부정어를 직접 붙이지 말고" in feedback


def test_resolve_title_purpose_detects_event_from_stance_text() -> None:
    purpose = resolve_title_purpose(
        "",
        {
            "topic": "",
            "stanceText": "4월 3일 KNN에서 경선 확정 행사 안내를 드립니다. 함께해 주십시오.",
            "contentPreview": "부산시장 예비후보 일정 안내와 행사 참석 요청을 담은 글입니다.",
            "backgroundText": "",
        },
    )

    assert purpose == "event_announcement"


def test_resolve_title_purpose_does_not_treat_attendance_history_as_event() -> None:
    purpose = resolve_title_purpose(
        "",
        {
            "topic": "",
            "stanceText": (
                "불법 비상계엄과 탄핵 정국에서도 국회 결집과 거리 집회에 참석하며 "
                "민주주의와 당을 지키는 데 앞장섰습니다."
            ),
            "contentPreview": (
                "인천 계양구에서 당원과 시민을 위해 뛰어온 문세종입니다. "
                "지역 현안을 해결하기 위해 현장에서 발로 뛰었습니다."
            ),
            "backgroundText": "",
        },
    )

    assert purpose == ""


def test_build_structured_title_candidates_for_event_announcement() -> None:
    candidates = build_structured_title_candidates(
        {
            "topic": "4월 3일 KNN 방송토론 안내",
            "contentPreview": "전재수 의원과의 경선 확정 이후 4월 3일 KNN 방송토론 안내",
            "stanceText": "전재수 의원과의 경선 확정 이후 4월 3일 KNN 방송토론 승부가 시작됩니다.",
            "userKeywords": ["이재성", "전재수"],
            "fullName": "이재성",
            "contextAnalysis": {
                "mustPreserve": {
                    "eventDate": "2026-04-03",
                    "eventLocation": "KNN",
                }
            },
        },
        title_purpose="event_announcement",
    )

    assert candidates
    assert any("이재성" in title and "전재수" in title for title in candidates)
    assert any("4월 3일" in title for title in candidates)
    assert any("KNN" in title for title in candidates)
    assert any("토론" in title or "안내" in title for title in candidates)


def test_build_structured_title_candidates_skips_generic_event_label_fallback() -> None:
    candidates = build_structured_title_candidates(
        {
            "topic": "",
            "contentPreview": (
                "인천 계양구에서 당원과 시민을 위해 뛰어온 문세종입니다. "
                "거리 집회에 참석하며 민주주의를 지키는 데 앞장섰습니다."
            ),
            "stanceText": (
                "지역 현안을 챙기고 시민과 소통해 왔습니다. "
                "행사 안내가 아니라 정치 활동 소개문입니다."
            ),
            "userKeywords": ["문세종"],
            "fullName": "문세종",
        },
        title_purpose="event_announcement",
    )

    assert candidates == []


def test_calculate_title_quality_score_allows_event_title_with_extra_anchor() -> None:
    result = calculate_title_quality_score(
        "이재성·전재수 경선, 4월 3일 KNN 방송토론 안내",
        {
            "topic": "4월 3일 KNN 방송토론 안내",
            "contentPreview": "전재수 의원과의 경선 확정 이후 4월 3일 KNN 방송토론 안내",
            "stanceText": "전재수 의원과의 경선 확정 이후 4월 3일 KNN 방송토론 승부가 시작됩니다.",
            "userKeywords": ["이재성", "전재수"],
            "fullName": "이재성",
            "category": "current-affairs",
            "contextAnalysis": {
                "mustPreserve": {
                    "eventDate": "2026-04-03",
                    "eventLocation": "KNN",
                }
            },
        },
        {"autoFitLength": False},
    )

    assert result["passed"] is True
    assert int(result["score"]) >= 70
    assert "topicCopy" not in result.get("breakdown", {})


def test_calculate_title_quality_score_repairs_adjacent_focus_keywords_surface() -> None:
    result = calculate_title_quality_score(
        "이재성 전재수 4월 3일 KNN 방송토론 안내",
        {
            "topic": "4월 3일 KNN 방송토론 안내",
            "contentPreview": "전재수 의원과의 경선 확정 이후 4월 3일 KNN 방송토론 안내",
            "stanceText": "전재수 의원과의 경선 확정 이후 4월 3일 KNN 방송토론 승부가 시작됩니다.",
            "userKeywords": ["이재성", "전재수"],
            "fullName": "이재성",
            "category": "current-affairs",
            "contextAnalysis": {
                "mustPreserve": {
                    "eventDate": "2026-04-03",
                    "eventLocation": "KNN",
                }
            },
        },
        {"autoFitLength": False},
    )

    assert result["passed"] is False
    assert "malformedSurface" in result["breakdown"]
    assert result.get("repairedTitle") == "이재성·전재수 4월 3일 KNN 방송토론 안내"


def test_generate_and_validate_title_uses_structured_rescue_for_event_title() -> None:
    async def _fake_generate_fn(_prompt: str) -> str:
        return "4월 3일 KNN 방송토론 안내"

    def _fake_score(title: str, _params: dict, _options: dict | None = None) -> dict:
        if title == "이재성·전재수 경선, 4월 3일 KNN 방송토론 안내":
            return {
                "score": 74,
                "passed": True,
                "suggestions": [],
                "breakdown": {
                    "keywordPosition": {"score": 20, "max": 20, "status": "최적", "keyword": "이재성"}
                },
            }
        return {
            "score": 0,
            "passed": False,
            "suggestions": ["주제(topic) 텍스트를 그대로 제목으로 사용하지 마세요."],
            "breakdown": {
                "topicCopy": {"score": 0, "max": 100, "status": "실패", "reason": "주제 직복"}
            },
        }

    with patch(
        "agents.common.title_generation.build_structured_title_candidates",
        return_value=["이재성·전재수 경선, 4월 3일 KNN 방송토론 안내"],
    ), patch(
        "agents.common.title_generation.calculate_title_quality_score",
        side_effect=_fake_score,
    ):
        result = asyncio.run(
            generate_and_validate_title(
                _fake_generate_fn,
                {
                    "topic": "4월 3일 KNN 방송토론 안내",
                    "contentPreview": "전재수 의원과의 경선 확정 이후 4월 3일 KNN 방송토론 안내",
                    "stanceText": "전재수 의원과의 경선 확정 이후 4월 3일 KNN 방송토론 승부가 시작됩니다.",
                    "userKeywords": ["이재성", "전재수"],
                    "fullName": "이재성",
                    "category": "current-affairs",
                    "contextAnalysis": {
                        "mustPreserve": {
                            "eventDate": "2026-04-03",
                            "eventLocation": "KNN",
                        }
                    },
                },
                {
                    "minScore": 70,
                    "maxAttempts": 1,
                    "candidateCount": 1,
                    "allowAutoRepair": False,
                },
            )
        )

    assert result["passed"] is True
    assert result.get("source") == "structured_rescue"
    assert result["title"] == "이재성·전재수 경선, 4월 3일 KNN 방송토론 안내"


def test_generate_and_validate_title_ignores_recent_title_similarity_for_event_announcement() -> None:
    async def _fake_generate_fn(_prompt: str) -> str:
        return "이재성·전재수 경선, 4월 3일 KNN 방송토론 안내"

    result = asyncio.run(
        generate_and_validate_title(
            _fake_generate_fn,
            {
                "topic": "4월 3일 KNN 방송토론 안내",
                "contentPreview": "전재수 의원과의 경선 확정 이후 4월 3일 KNN 방송토론 안내",
                "stanceText": "전재수 의원과의 경선 확정 이후 4월 3일 KNN 방송토론 승부가 시작됩니다.",
                "userKeywords": ["이재성", "전재수"],
                "fullName": "이재성",
                "category": "current-affairs",
                "contextAnalysis": {
                    "mustPreserve": {
                        "eventDate": "2026-04-03",
                        "eventLocation": "KNN",
                    }
                },
                "recentTitles": ["이재성·전재수 경선, 4월 3일 KNN 방송토론 안내"],
            },
            {
                "minScore": 70,
                "maxAttempts": 1,
                "candidateCount": 1,
                "allowAutoRepair": False,
                "recentTitles": ["이재성·전재수 경선, 4월 3일 KNN 방송토론 안내"],
            },
        )
    )

    assert result["passed"] is True
    assert int(result.get("similarityPenalty", 0) or 0) == 0


def test_generate_and_validate_title_applies_final_repair_before_raising() -> None:
    prompts: list[str] = []

    async def _fake_generate_fn(prompt: str) -> str:
        prompts.append(prompt)
        if "<final_title_repair" in prompt:
            return "이재성, 4월 3일 KNN 경선 확정 행사 안내"
        return "이재성 4월 3일 KNN 경선 확정 행사 안내"

    def _fake_score(title: str, _params, _options=None):
        if title == "이재성, 4월 3일 KNN 경선 확정 행사 안내":
            return {
                "score": 74,
                "passed": True,
                "suggestions": [],
                "breakdown": {"topicMatch": {"score": 20, "max": 25, "status": "충분"}},
            }
        return {
            "score": 68,
            "passed": False,
            "suggestions": [
                '키워드 "이재성" 뒤에 쉼표나 조사를 넣어 다음 단어와 분리하세요. (예: "부산 지방선거, ~")',
                "제목이 주제와 많이 다릅니다. 주제 핵심어를 반영하세요.",
            ],
            "breakdown": {"topicMatch": {"score": 15, "max": 25, "status": "보통"}},
        }

    with patch("agents.common.title_generation.calculate_title_quality_score", side_effect=_fake_score):
        result = asyncio.run(
            generate_and_validate_title(
                _fake_generate_fn,
                {
                    "topic": "",
                    "contentPreview": "4월 3일 KNN 경선 확정 행사 안내와 참석 요청을 담은 글입니다.",
                    "stanceText": "4월 3일 KNN 경선 확정 행사 안내를 드립니다.",
                    "userKeywords": ["이재성"],
                    "fullName": "이재성",
                },
                {
                    "minScore": 70,
                    "maxAttempts": 1,
                    "candidateCount": 1,
                    "allowAutoRepair": False,
                    "maxSimilarityPenalty": 0,
                },
            )
        )

    assert result["title"] == "이재성, 4월 3일 KNN 경선 확정 행사 안내"
    assert result["history"][-1]["source"] == "final_repair"
    assert any("<final_title_repair" in prompt for prompt in prompts)


def test_generate_and_validate_title_retries_final_repair_loop() -> None:
    prompts: list[str] = []
    responses = iter(
        [
            "이재성 4월 3일 KNN 경선 방송토론 행사 안내",
            "이재성, 4월 3일 KNN 경선 방송토론 행사 안내",
            "이재성, 전재수 4월 3일 KNN 경선 토론 안내",
        ]
    )

    async def _fake_generate_fn(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    def _fake_score(title: str, _params, _options=None):
        if title == "이재성, 전재수 4월 3일 KNN 경선 토론 안내":
            return {
                "score": 74,
                "passed": True,
                "suggestions": [],
                "breakdown": {"topicMatch": {"score": 20, "max": 25, "status": "충분"}},
            }
        if title == "이재성, 4월 3일 KNN 경선 방송토론 행사 안내":
            return {
                "score": 68,
                "passed": False,
                "suggestions": [
                    "제목이 31자입니다. 30자 이하가 클릭률 최고.",
                    "제목에 두 검색어를 모두 포함하세요: 이재성, 전재수",
                ],
                "breakdown": {"keywordCoverage": {"score": 0, "max": 100, "status": "실패"}},
            }
        return {
            "score": 62,
            "passed": False,
            "suggestions": [
                '키워드 "이재성" 뒤에 쉼표나 조사를 넣어 다음 단어와 분리하세요. (예: "부산 지방선거, ~")',
                "제목에 두 검색어를 모두 포함하세요: 이재성, 전재수",
            ],
            "breakdown": {"keywordCoverage": {"score": 0, "max": 100, "status": "실패"}},
        }

    with patch("agents.common.title_generation.calculate_title_quality_score", side_effect=_fake_score):
        result = asyncio.run(
            generate_and_validate_title(
                _fake_generate_fn,
                {
                    "topic": "",
                    "contentPreview": "4월 3일 KNN 경선 방송토론 행사 안내와 참석 요청을 담은 글입니다.",
                    "stanceText": "4월 3일 KNN 경선 방송토론 행사 안내를 드립니다.",
                    "userKeywords": ["이재성", "전재수"],
                    "fullName": "이재성",
                },
                {
                    "minScore": 70,
                    "maxAttempts": 1,
                    "candidateCount": 1,
                    "allowAutoRepair": False,
                    "maxSimilarityPenalty": 0,
                },
            )
        )

    assert result["title"] == "이재성, 전재수 4월 3일 KNN 경선 토론 안내"
    assert sum(1 for prompt in prompts if "<final_title_repair" in prompt) == 2


def test_calculate_title_quality_score_requires_two_independent_user_keywords() -> None:
    result = calculate_title_quality_score(
        "이재성, 4월 3일 KNN 경선 방송토론 행사 안내",
        {
            "topic": "",
            "contentPreview": "4월 3일 KNN 경선 방송토론 행사 안내와 참석 요청을 담은 글입니다.",
            "userKeywords": ["이재성", "전재수"],
            "fullName": "이재성",
        },
        {"autoFitLength": False},
    )

    assert result["passed"] is False
    assert "전재수" in str(result.get("repairedTitle") or "")


def test_calculate_title_quality_score_accepts_middle_dot_between_two_keywords() -> None:
    result = calculate_title_quality_score(
        "이재성·전재수 경선, 4월 3일 KNN 방송토론 안내",
        {
            "topic": "전재수 의원과의 경선 이후 4월 3일 KNN 방송토론 안내",
            "contentPreview": "4월 3일 KNN 방송토론 일정과 경선 관련 안내를 담은 글입니다.",
            "userKeywords": ["이재성", "전재수"],
            "fullName": "이재성",
        },
        {"autoFitLength": False},
    )

    assert '키워드 "이재성" 뒤에 쉼표나 조사를 넣어' not in list(result.get("suggestions") or [])


def test_calculate_title_quality_score_rejects_bare_day_fragment_title() -> None:
    result = calculate_title_quality_score(
        "이재성, 전재수 경선 확정 27일? 부산 경제의 미래는",
        {
            "topic": "전재수 의원과의 경선 확정 이후 부산 경제 정책 경쟁",
            "contentPreview": "민주당 공관위는 27일 경선 실시를 결정했고 부산 경제 정책 경쟁이 본격화됐습니다.",
            "userKeywords": ["이재성", "전재수"],
            "fullName": "이재성",
        },
        {"autoFitLength": False},
    )

    assert result["passed"] is False
    assert result["breakdown"]["malformedSurface"]["reason"].startswith("제목의 날짜 조각")
    assert "27일?" not in str(result.get("repairedTitle") or "")


def test_calculate_title_quality_score_rejects_matchup_possessive_title() -> None:
    result = calculate_title_quality_score(
        "전재수, 이재성의 새로운 일자리",
        {
            "topic": "전재수 의원과의 경선 확정 이후 부산 일자리 해법 경쟁",
            "contentPreview": "전재수와의 경선에서 부산 일자리와 경제 해법 경쟁이 본격화됐다.",
            "userKeywords": ["이재성", "전재수"],
            "fullName": "이재성",
            "category": "current-affairs",
            "pollFocusBundle": _build_matchup_bundle(),
        },
    )

    assert result["passed"] is False
    assert "malformedSurface" in result["breakdown"]
    assert result.get("repairedTitle") == "전재수·이재성, 새로운 일자리"


def test_title_agent_prefers_structured_title_before_llm() -> None:
    async def _fake_generate_and_validate_title(*_args, **_kwargs):
        raise AssertionError("structured title path should return before LLM generation")

    async def _run() -> None:
        with patch(
            "agents.core.title_agent.build_structured_title_candidates",
            return_value=["이재성·전재수 경선 확정, 부산 경제 해법 경쟁"],
        ), patch(
            "agents.core.title_agent.calculate_title_quality_score",
            return_value={"score": 78, "passed": True, "suggestions": [], "breakdown": {}},
        ), patch(
            "agents.core.title_agent.generate_and_validate_title",
            new=_fake_generate_and_validate_title,
        ):
            agent = TitleAgent(options={})
            result = await agent.process(
                {
                    "topic": "전재수 의원과의 경선 확정 이후 부산 경제 정책 경쟁",
                    "content": "<p>이재성과 전재수의 경선 확정 이후 부산 경제 해법과 정책 경쟁 구도에 관심이 모이고 있습니다.</p>",
                    "stanceText": "정책 경쟁으로 부산 경제를 바꾸겠다는 입장입니다.",
                    "background": "부산 경제와 정책 대결의 쟁점",
                    "userKeywords": ["이재성", "전재수"],
                    "author": {"name": "이재성"},
                    "category": "current-affairs",
                    "pollFocusBundle": {
                        **_build_matchup_bundle(),
                        "allowedTitleLanes": [
                            {
                                "id": "structured_anchor",
                                "label": "structured_anchor",
                                "template": "이재성·전재수 경선 확정, 부산 경제 해법 경쟁",
                            }
                        ],
                    },
                }
            )

        assert result["titleType"] == "STRUCTURED_PLAN"
        assert result["titleHistory"][0]["source"] == "structured_plan"
        assert "이재성" in result["title"] and "전재수" in result["title"]

    asyncio.run(_run())


def test_title_agent_uses_full_context_compliance_retry_before_minimal_prompt() -> None:
    calls: list[dict[str, object]] = []

    async def _fake_generate_and_validate_title(_generate_fn, params, options):
        calls.append({"params": dict(params), "options": dict(options)})
        call_index = len(calls)
        if call_index <= 2:
            raise RuntimeError(
                '[TitleGen] 제목 생성 실패: 최소 점수 1점 미달 '
                '(최고 0점, 제목: "이재성, 전재수 경선 확정…부산 경제, 누가 이끌까?"). '
                '개선 힌트: 말줄임표("...", "…") 사용 금지. 내용을 자르지 말고 완결된 제목을 작성하세요.'
            )
        return {
            "title": "이재성·전재수 경선 확정, 부산 경제는 누가 이끄나",
            "score": 78,
            "history": [],
        }

    async def _run() -> None:
        with patch(
            "agents.core.title_agent.build_structured_title_candidates",
            return_value=[],
        ), patch(
            "agents.core.title_agent.generate_and_validate_title",
            new=_fake_generate_and_validate_title,
        ):
            agent = TitleAgent(options={})
            result = await agent.process(
                {
                    "topic": "전재수 의원과의 경선 확정 이후 부산시장 선거 구도 평가",
                    "content": "<p>경선 확정 이후 부산 경제와 선거 구도 변화에 관심이 모이고 있습니다.</p>",
                    "stanceText": "경선 확정을 뜻깊게 생각하며 정책 경쟁으로 부산 경제를 바꾸겠습니다.",
                    "background": "부산시장 선거 구도와 경제 현안",
                    "userKeywords": ["이재성", "전재수"],
                    "author": {"name": "이재성"},
                    "category": "current-affairs",
                    "pollFocusBundle": _build_matchup_bundle(),
                }
            )

        assert result["title"] == "이재성·전재수 경선 확정, 부산 경제는 누가 이끄나"
        assert len(calls) == 3
        third_params = calls[2]["params"]
        assert third_params.get("contentPreview")
        assert third_params.get("stanceText")
        assert third_params.get("titlePromptLite") is False

    asyncio.run(_run())


def test_title_agent_raises_when_generated_title_repeats_same_name() -> None:
    async def _fake_generate_and_validate_title(*_args, **_kwargs):
        return {
            "title": "전재수 이재성, 이재성 부산의 현안",
            "score": 82,
            "history": [],
        }

    async def _run() -> None:
        with patch(
            "agents.core.title_agent.build_structured_title_candidates",
            return_value=[],
        ), patch(
            "agents.core.title_agent.generate_and_validate_title",
            new=_fake_generate_and_validate_title,
        ):
            agent = TitleAgent(options={})
            try:
                await agent.process(
                    {
                        "topic": "이재성 전재수 경선",
                        "content": "<p>이재성·전재수 가상대결 31.7% 대 29.4%가 확인됐습니다.</p>",
                        "userKeywords": ["이재성", "전재수"],
                        "author": {"name": "이재성"},
                        "category": "current-affairs",
                        "pollFocusBundle": _build_matchup_bundle(),
                    }
                )
            except Exception as error:
                assert "인물명" in str(error) or "반복" in str(error)
                return

        raise AssertionError("중복 이름 제목은 fallback 없이 예외가 나와야 합니다.")

    asyncio.run(_run())


def test_title_agent_propagates_generation_error_without_safe_fallback() -> None:
    async def _fake_generate_and_validate_title(*_args, **_kwargs):
        raise RuntimeError("제목 생성 실패")

    async def _run() -> None:
        with patch(
            "agents.core.title_agent.build_structured_title_candidates",
            return_value=[],
        ), patch(
            "agents.core.title_agent.generate_and_validate_title",
            new=_fake_generate_and_validate_title,
        ):
            agent = TitleAgent(options={})
            try:
                await agent.process(
                    {
                        "topic": "이재성 전재수 경선 확정",
                        "content": "<p>이재성·전재수 경선 확정 이후 부산의 정책 경쟁이 본격화됐습니다.</p>",
                        "userKeywords": ["이재성", "전재수"],
                        "author": {"name": "이재성"},
                        "category": "current-affairs",
                        "pollFocusBundle": _build_matchup_bundle(),
                    }
                )
            except RuntimeError as error:
                assert "제목 생성 실패" in str(error)
                return

        raise AssertionError("생성 실패는 safe fallback 없이 그대로 전파되어야 합니다.")

    asyncio.run(_run())


def test_title_agent_uses_sentence_topic_fallback_on_compliance_failure() -> None:
    async def _fake_generate_and_validate_title(*_args, **_kwargs):
        raise RuntimeError(
            '[TitleGen] 제목 생성 실패: 최소 점수 70점 미달 '
            '(최고 0점, 제목: "문세종 의원, 계양구민을 위한 충직한 역할 안내 행사"). '
            '개선 힌트: 제목의 수식 관계가 어색합니다. "무엇을 위한" 구조를 완결해 다시 작성하세요.'
        )

    async def _run() -> None:
        with patch(
            "agents.core.title_agent.build_structured_title_candidates",
            return_value=[],
        ), patch(
            "agents.core.title_agent.generate_and_validate_title",
            new=_fake_generate_and_validate_title,
        ):
            agent = TitleAgent(options={})
            result = await agent.process(
                {
                    "topic": "대통령님의 지역구를 지켜온 책임감으로, 계양구민에게 가장 충직한 인천광역시의원으로 역할을 해내겠습니다.",
                    "content": (
                        "<p>인천 계양구에서 당원과 시민을 위해 뛰어온 인천광역시의원 문세종입니다.</p>"
                        "<p>계양구을 지역위원회와 시의회 활동을 통해 지역구를 지켜왔고, 계양테크노밸리와 생활 조례 개정에도 힘써 왔습니다.</p>"
                    ),
                    "stanceText": (
                        "인천 계양구에서 당원과 시민을 위해 뛰어온 인천광역시의원 문세종입니다. "
                        "계양구민에게 가장 충직한 시의원으로 남겠습니다."
                    ),
                    "background": "계양구 의정활동과 입법 성과",
                    "userKeywords": ["문세종"],
                    "author": {"name": "문세종"},
                    "category": "current-affairs",
                }
            )

        assert result["titleType"] in {"COMPLIANCE_FALLBACK", "COMPLIANCE_FALLBACK_SOFT"}
        assert "문세종" in result["title"]
        assert result["titleHistory"][0]["fallbackUsed"] is True
        assert result["titleHistory"][0]["source"] == "topic_sentence_fallback"
        assert int(result["titleScore"] or 0) >= 60

    asyncio.run(_run())


def test_title_agent_rejects_malformed_soft_fallback_candidate() -> None:
    async def _fake_generate_and_validate_title(*_args, **_kwargs):
        raise RuntimeError(
            '[TitleGen] 제목 생성 실패: 최소 점수 70점 미달 '
            '(최고 0점, 제목: "문세종, 문세종의 되는 정책").'
        )

    async def _run() -> None:
        with patch(
            "agents.core.title_agent.build_structured_title_candidates",
            return_value=[],
        ), patch(
            "agents.core.title_agent.generate_and_validate_title",
            new=_fake_generate_and_validate_title,
        ), patch(
            "agents.core.title_agent._build_topic_sentence_fallback_candidates",
            return_value=["문세종, 문세종의 되는 정책"],
        ), patch(
            "agents.core.title_agent.calculate_title_quality_score",
            return_value={
                "score": 69,
                "passed": False,
                "suggestions": ["제목이 주제와 많이 다릅니다. 주제 핵심어를 반영하세요."],
                "breakdown": {"topicMatch": {"score": 5, "max": 25, "status": "낮음"}},
            },
        ):
            agent = TitleAgent(options={})
            try:
                await agent.process(
                    {
                        "topic": "계양구 민생 정책 방향",
                        "content": "<p>계양구민의 삶에 실질적인 도움이 되는 정책을 제안하고 실현해 나가겠습니다.</p>",
                        "stanceText": "문세종은 계양구민에게 필요한 정책을 제안합니다.",
                        "userKeywords": ["문세종"],
                        "author": {"name": "문세종"},
                        "category": "current-affairs",
                    }
                )
            except RuntimeError as error:
                assert "제목 생성 실패" in str(error)
                return

        raise AssertionError("구조 결함 제목은 soft fallback으로 수용되면 안 됩니다.")

    asyncio.run(_run())


def main() -> None:
    tests = [
        (
            "keyword_injector_insert_after_anchor_rejects_mid_sentence_boundary",
            test_keyword_injector_insert_after_anchor_rejects_mid_sentence_boundary,
        ),
        (
            "keyword_injector_apply_instructions_rolls_back_unsafe_replace",
            test_keyword_injector_apply_instructions_rolls_back_unsafe_replace,
        ),
        (
            "find_similar_sentence_in_content_detects_near_duplicate_keyword_padding",
            test_find_similar_sentence_in_content_detects_near_duplicate_keyword_padding,
        ),
        (
            "build_structure_prompt_includes_first_person_news_rewrite_rule",
            test_build_structure_prompt_includes_first_person_news_rewrite_rule,
        ),
        (
            "build_structure_prompt_includes_observer_voice_review_and_section_continuity_rules",
            test_build_structure_prompt_includes_observer_voice_review_and_section_continuity_rules,
        ),
        (
            "sanitize_h2_text_repairs_duplicate_particles_and_tokens",
            test_sanitize_h2_text_repairs_duplicate_particles_and_tokens,
        ),
        (
            "sanitize_h2_text_truncates_at_word_boundary",
            test_sanitize_h2_text_truncates_at_word_boundary,
        ),
        (
            "sanitize_h2_text_truncates_exact_max_length_incomplete_ending",
            test_sanitize_h2_text_truncates_exact_max_length_incomplete_ending,
        ),
        (
            "has_incomplete_h2_ending_detects_particle_and_unfinished_endings",
            test_has_incomplete_h2_ending_detects_particle_and_unfinished_endings,
        ),
        (
            "structure_agent_json_prompt_includes_heading_self_check_and_concrete_fill_rules",
            test_structure_agent_json_prompt_includes_heading_self_check_and_concrete_fill_rules,
        ),
        (
            "drop_observer_frame_sentences_once_removes_news_voice_residue",
            test_drop_observer_frame_sentences_once_removes_news_voice_residue,
        ),
        (
            "drop_observer_frame_sentences_once_removes_observer_variant_phrase",
            test_drop_observer_frame_sentences_once_removes_observer_variant_phrase,
        ),
        (
            "drop_observer_frame_sentences_once_removes_convention_effect_sentence",
            test_drop_observer_frame_sentences_once_removes_convention_effect_sentence,
        ),
        (
            "drop_observer_frame_sentences_once_removes_role_emphasis_sentence",
            test_drop_observer_frame_sentences_once_removes_role_emphasis_sentence,
        ),
        (
            "repair_contextless_section_openers_once_rewrites_ireohan_lead",
            test_repair_contextless_section_openers_once_rewrites_ireohan_lead,
        ),
        (
            "repair_contextless_section_openers_once_rewrites_choice_opportunity_lead",
            test_repair_contextless_section_openers_once_rewrites_choice_opportunity_lead,
        ),
        (
            "repair_contextless_section_openers_once_rewrites_choice_start_lead",
            test_repair_contextless_section_openers_once_rewrites_choice_start_lead,
        ),
        (
            "ensure_closing_section_min_sentences_once_appends_support_sentence",
            test_ensure_closing_section_min_sentences_once_appends_support_sentence,
        ),
        (
            "ensure_closing_section_min_sentences_once_restores_empty_closing_before_tail_text",
            test_ensure_closing_section_min_sentences_once_restores_empty_closing_before_tail_text,
        ),
        (
            "recover_short_content_once_targets_short_sections_with_concrete_fill_prompt",
            test_recover_short_content_once_targets_short_sections_with_concrete_fill_prompt,
        ),
        (
            "recover_short_content_once_retries_when_first_pass_still_short",
            test_recover_short_content_once_retries_when_first_pass_still_short,
        ),
        (
            "scrub_broken_poll_fragments_once_removes_incomplete_news_clause",
            test_scrub_broken_poll_fragments_once_removes_incomplete_news_clause,
        ),
        (
            "rewrite_sentence_to_reduce_keyword_keeps_self_identification_sentence",
            test_rewrite_sentence_to_reduce_keyword_keeps_self_identification_sentence,
        ),
        (
            "repair_identity_signature_exact_form_once_restores_name_after_keyword_reduction",
            test_repair_identity_signature_exact_form_once_restores_name_after_keyword_reduction,
        ),
        (
            "repair_self_reference_placeholders_once_restores_name_or_first_person_surface",
            test_repair_self_reference_placeholders_once_restores_name_or_first_person_surface,
        ),
        (
            "repair_self_reference_placeholders_once_restores_name_in_h2_without_pledge_signal",
            test_repair_self_reference_placeholders_once_restores_name_in_h2_without_pledge_signal,
        ),
        (
            "repair_self_reference_placeholders_once_restores_compact_placeholder_surface",
            test_repair_self_reference_placeholders_once_restores_compact_placeholder_surface,
        ),
        (
            "repair_self_reference_placeholders_once_restores_named_surface_in_body_statement",
            test_repair_self_reference_placeholders_once_restores_named_surface_in_body_statement,
        ),
        (
            "repair_speaker_consistency_once_removes_name_plus_first_person_pronoun",
            test_repair_speaker_consistency_once_removes_name_plus_first_person_pronoun,
        ),
        (
            "drop_low_signal_analysis_sentences_once_removes_self_certification_claim",
            test_drop_low_signal_analysis_sentences_once_removes_self_certification_claim,
        ),
        (
            "drop_low_signal_analysis_sentences_once_removes_generic_padding_variants",
            test_drop_low_signal_analysis_sentences_once_removes_generic_padding_variants,
        ),
        (
            "final_sentence_polish_removes_passive_self_certification_and_repairs_section_opener",
            test_final_sentence_polish_removes_passive_self_certification_and_repairs_section_opener,
        ),
        (
            "ensure_closing_section_min_sentences_once_strengthens_single_sentence_closing",
            test_ensure_closing_section_min_sentences_once_strengthens_single_sentence_closing,
        ),
        (
            "build_title_prompt_includes_name_priority_rule_for_matchup",
            test_build_title_prompt_includes_name_priority_rule_for_matchup,
        ),
        (
            "build_title_prompt_blocks_content_phrase_fragment_attachment",
            test_build_title_prompt_blocks_content_phrase_fragment_attachment,
        ),
        (
            "calculate_title_quality_score_rejects_duplicate_focus_name_title",
            test_calculate_title_quality_score_rejects_duplicate_focus_name_title,
        ),
        (
            "calculate_title_quality_score_rejects_consecutive_duplicate_token_title",
            test_calculate_title_quality_score_rejects_consecutive_duplicate_token_title,
        ),
        (
            "calculate_title_quality_score_repairs_missing_object_particle_title",
            test_calculate_title_quality_score_repairs_missing_object_particle_title,
        ),
        (
            "calculate_title_quality_score_repairs_empty_modifier_title_from_topic",
            test_calculate_title_quality_score_repairs_empty_modifier_title_from_topic,
        ),
        (
            "build_structured_title_candidates_for_matchup_policy_topic",
            test_build_structured_title_candidates_for_matchup_policy_topic,
        ),
        (
            "generate_and_validate_title_raises_when_auto_repair_disabled",
            test_generate_and_validate_title_raises_when_auto_repair_disabled,
        ),
        (
            "generate_and_validate_title_retries_ellipsis_surface_twice_before_success",
            test_generate_and_validate_title_retries_ellipsis_surface_twice_before_success,
        ),
        (
            "detect_possessive_modifier_pattern_flags_broken_title_shape",
            test_detect_possessive_modifier_pattern_flags_broken_title_shape,
        ),
        (
            "detect_title_structural_defect_flags_duplicate_name_negation_pattern",
            test_detect_title_structural_defect_flags_duplicate_name_negation_pattern,
        ),
        (
            "detect_title_structural_defect_flags_missing_delimiter_after_vs_event_phrase",
            test_detect_title_structural_defect_flags_missing_delimiter_after_vs_event_phrase,
        ),
        (
            "detect_title_structural_defect_flags_duplicate_name_possessive_pattern",
            test_detect_title_structural_defect_flags_duplicate_name_possessive_pattern,
        ),
        (
            "detect_content_type_prefers_policy_profile_over_question_answer",
            test_detect_content_type_prefers_policy_profile_over_question_answer,
        ),
        (
            "build_title_prompt_includes_common_title_anti_patterns_block",
            test_build_title_prompt_includes_common_title_anti_patterns_block,
        ),
        (
            "calculate_title_quality_score_rejects_focus_name_possessive_modifier_title",
            test_calculate_title_quality_score_rejects_focus_name_possessive_modifier_title,
        ),
        (
            "build_previous_attempt_pattern_feedback_mentions_possessive_modifier_pattern",
            test_build_previous_attempt_pattern_feedback_mentions_possessive_modifier_pattern,
        ),
        (
            "build_previous_attempt_pattern_feedback_mentions_structural_defect",
            test_build_previous_attempt_pattern_feedback_mentions_structural_defect,
        ),
        (
            "resolve_title_purpose_detects_event_from_stance_text",
            test_resolve_title_purpose_detects_event_from_stance_text,
        ),
        (
            "resolve_title_purpose_does_not_treat_attendance_history_as_event",
            test_resolve_title_purpose_does_not_treat_attendance_history_as_event,
        ),
        (
            "build_structured_title_candidates_for_event_announcement",
            test_build_structured_title_candidates_for_event_announcement,
        ),
        (
            "build_structured_title_candidates_skips_generic_event_label_fallback",
            test_build_structured_title_candidates_skips_generic_event_label_fallback,
        ),
        (
            "calculate_title_quality_score_allows_event_title_with_extra_anchor",
            test_calculate_title_quality_score_allows_event_title_with_extra_anchor,
        ),
        (
            "calculate_title_quality_score_repairs_adjacent_focus_keywords_surface",
            test_calculate_title_quality_score_repairs_adjacent_focus_keywords_surface,
        ),
        (
            "generate_and_validate_title_uses_structured_rescue_for_event_title",
            test_generate_and_validate_title_uses_structured_rescue_for_event_title,
        ),
        (
            "generate_and_validate_title_ignores_recent_title_similarity_for_event_announcement",
            test_generate_and_validate_title_ignores_recent_title_similarity_for_event_announcement,
        ),
        (
            "generate_and_validate_title_applies_final_repair_before_raising",
            test_generate_and_validate_title_applies_final_repair_before_raising,
        ),
        (
            "generate_and_validate_title_retries_final_repair_loop",
            test_generate_and_validate_title_retries_final_repair_loop,
        ),
        (
            "calculate_title_quality_score_requires_two_independent_user_keywords",
            test_calculate_title_quality_score_requires_two_independent_user_keywords,
        ),
        (
            "calculate_title_quality_score_accepts_middle_dot_between_two_keywords",
            test_calculate_title_quality_score_accepts_middle_dot_between_two_keywords,
        ),
        (
            "calculate_title_quality_score_rejects_bare_day_fragment_title",
            test_calculate_title_quality_score_rejects_bare_day_fragment_title,
        ),
        (
            "calculate_title_quality_score_rejects_matchup_possessive_title",
            test_calculate_title_quality_score_rejects_matchup_possessive_title,
        ),
        (
            "title_agent_prefers_structured_title_before_llm",
            test_title_agent_prefers_structured_title_before_llm,
        ),
        (
            "title_agent_uses_full_context_compliance_retry_before_minimal_prompt",
            test_title_agent_uses_full_context_compliance_retry_before_minimal_prompt,
        ),
        (
            "title_agent_raises_when_generated_title_repeats_same_name",
            test_title_agent_raises_when_generated_title_repeats_same_name,
        ),
        (
            "title_agent_propagates_generation_error_without_safe_fallback",
            test_title_agent_propagates_generation_error_without_safe_fallback,
        ),
        (
            "title_agent_uses_sentence_topic_fallback_on_compliance_failure",
            test_title_agent_uses_sentence_topic_fallback_on_compliance_failure,
        ),
        (
            "title_agent_rejects_malformed_soft_fallback_candidate",
            test_title_agent_rejects_malformed_soft_fallback_candidate,
        ),
    ]
    passed = 0
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
        passed += 1
    print(f"OK {passed}")


if __name__ == "__main__":
    main()
